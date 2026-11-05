# -*- coding: utf-8 -*-
"""
Pengujian Menyeluruh untuk Task 4-05:
Commit Impor Anggota Massal Atomik, Token Konfirmasi Persisten, Validasi Keputusan,
Idempotensi Replay, Skala > 1.000 Baris, Rollback Atomik, dan Kepatuhan Privasi DEC-023.
"""
import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import app
from policy import (
    CONFIRMATION_TOKEN_TTL_SECONDS,
    MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
    MAX_MEMBER_IMPORT_ROWS,
)
from repositories import (
    member_repo,
    audit_repo,
)
from services import (
    create_member_import_confirmation_token,
    commit_member_import_with_token,
    commit_member_import,
    clear_member_confirmation_tokens,
    canonicalize_member_import_payload,
    compute_member_import_payload_hash,
    preview_member_import_matching,
    validate_member_import_decisions,
    generate_member_qr_token,
    verify_member_qr_token,
    ValidationError,
    ConfirmationTokenError,
    ConcurrencyConflictError,
    MemberNotFoundError,
)
from services.member_service import (
    _MEMBER_CONFIRMATION_TOKENS,
    _ACTIVE_PROCESSING_MEMBER_TOKENS,
    _MEMBER_TOKEN_LOCK,
    ensure_confirmation_tokens_table,
)


def _init_test_db(db_path: str) -> None:
    """Menginisialisasi basis data uji mandiri dengan skema v2 terisolasi."""
    migration_file = os.path.join(
        os.path.dirname(__file__), "..", "migrations", "0001_initial_v2_schema.sql"
    )
    with open(migration_file, "r", encoding="utf-8") as f:
        ddl_script = f.read()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(ddl_script)
    ensure_confirmation_tokens_table(conn)
    member_repo.seed_default_categories(conn)
    conn.commit()
    conn.close()


class MemberImportCommitServiceTests(unittest.TestCase):
    """Pengujian Service Layer untuk Komit Impor Anggota Atomik."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_member_import_service.db")
        _init_test_db(self.test_db_path)
        self.conn = sqlite3.connect(self.test_db_path)
        self.conn.row_factory = sqlite3.Row

        self.old_secret = os.environ.get("SECRET_KEY")
        os.environ["SECRET_KEY"] = "test_secret_key_perpustakaan_digital_2026_xyz"

        # Bersihkan token cache
        with _MEMBER_TOKEN_LOCK:
            _MEMBER_CONFIRMATION_TOKENS.clear()
            _ACTIVE_PROCESSING_MEMBER_TOKENS.clear()

        # Seed data awal anggota untuk pengujian pembaruan dan integritas non-mutasi
        self.conn.execute(
            """
            INSERT INTO members (id, nama, status, category_id, qr_version, created_at, updated_at)
            VALUES 
            ('M-222222', 'Budi Santoso', 'aktif', 'MC-MURID', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
            ('M-222223', 'Siti Aminah', 'aktif', 'MC-GURU-UMUM', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
            ('M-222224', 'Untouched Member', 'aktif', 'MC-STAF', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self.old_secret is not None:
            os.environ["SECRET_KEY"] = self.old_secret
        else:
            os.environ.pop("SECRET_KEY", None)

    # ==============================================================================
    # A. OPERASI DASAR (BUAT BARU, PERBARUI, LEWATI, RINGKASAN, ZERO-MUTASI)
    # ==============================================================================

    def test_01_create_new_members_basic(self):
        """Membuat anggota baru dengan aksi BUAT_BARU dan ID Crockford Base32 otomatis."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Dewi Sartika,murid,Teknik Otomotif,aktif,\n"
            "Bambang Hermanto,teknisi,Bengkel Mesin,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={
                2: {"action": "BUAT_BARU", "target_member_id": None},
                3: {"action": "BUAT_BARU", "target_member_id": None},
            },
            admin_username="admin_test",
        )
        summary, is_replay = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )

        self.assertFalse(is_replay)
        self.assertEqual(summary["total_processed"], 2)
        self.assertEqual(summary["created_count"], 2)
        self.assertEqual(summary["updated_count"], 0)
        self.assertEqual(summary["skipped_count"], 0)
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(len(summary["created_members"]), 2)

        # Verifikasi anggota tersimpan di database dengan ID valid
        for m in summary["created_members"]:
            self.assertTrue(m["id"].startswith("M-"))
            db_row = member_repo.get_member_by_id(self.conn, m["id"])
            self.assertIsNotNone(db_row)
            self.assertEqual(db_row["nama"], m["nama"])
            self.assertEqual(db_row["status"], "aktif")

    def test_02_update_existing_members_explicit(self):
        """Memperbarui data anggota yang dipilih secara eksplisit via PERBARUI."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Budi Santoso Pembaruan,guru_jurusan,Keahlian Listrik,nonaktif,M-222222\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={
                2: {"action": "PERBARUI", "target_member_id": "M-222222"},
            },
            admin_username="admin_test",
        )
        summary, is_replay = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )

        self.assertFalse(is_replay)
        self.assertEqual(summary["created_count"], 0)
        self.assertEqual(summary["updated_count"], 1)
        self.assertEqual(summary["skipped_count"], 0)

        # Verifikasi data terupdate di basis data
        updated_budi = member_repo.get_member_by_id(self.conn, "M-222222")
        self.assertEqual(updated_budi["nama"], "Budi Santoso Pembaruan")
        self.assertEqual(updated_budi["category_id"], "MC-GURU-JUR")
        self.assertEqual(updated_budi["status"], "nonaktif")

    def test_03_skip_rows_explicit(self):
        """Melewati baris impor yang dipilih LEWATI tanpa memutasi basis data."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siti Aminah,guru_umum,Guru Bahasa,aktif,M-222223\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={
                2: {"action": "LEWATI", "target_member_id": None},
            },
            admin_username="admin_test",
        )
        summary, is_replay = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )

        self.assertFalse(is_replay)
        self.assertEqual(summary["created_count"], 0)
        self.assertEqual(summary["updated_count"], 0)
        self.assertEqual(summary["skipped_count"], 1)

        # Siti Aminah tetap utuh dan tidak berubah
        siti = member_repo.get_member_by_id(self.conn, "M-222223")
        self.assertEqual(siti["nama"], "Siti Aminah")
        self.assertEqual(siti["category_id"], "MC-GURU-UMUM")
        self.assertEqual(siti["status"], "aktif")

    def test_04_mixed_batch_commit(self):
        """Memproses batch campuran: BUAT_BARU, PERBARUI, dan LEWATI."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Anggota Baru 1,murid,RPL,aktif,\n"
            "Siti Aminah Baru,guru_umum,Bahasa Indonesia,aktif,M-222223\n"
            "Lewati Saja,staf,Tata Usaha,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={
                2: {"action": "BUAT_BARU", "target_member_id": None},
                3: {"action": "PERBARUI", "target_member_id": "M-222223"},
                4: {"action": "LEWATI", "target_member_id": None},
            },
            admin_username="admin_test",
        )
        summary, is_replay = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )

        self.assertEqual(summary["total_processed"], 3)
        self.assertEqual(summary["created_count"], 1)
        self.assertEqual(summary["updated_count"], 1)
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["failed_count"], 0)

    def test_05_unrelated_members_strictly_untouched(self):
        """Kriteria Wajib: Anggota di luar berkas impor 100% tidak dimutasi."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Baru Mandiri,murid,TKJ,aktif,\n"
        )
        before_untouched = member_repo.get_member_by_id(self.conn, "M-222224")

        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )
        commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )

        after_untouched = member_repo.get_member_by_id(self.conn, "M-222224")
        self.assertEqual(before_untouched["nama"], after_untouched["nama"])
        self.assertEqual(before_untouched["category_id"], after_untouched["category_id"])
        self.assertEqual(before_untouched["status"], after_untouched["status"])
        self.assertEqual(before_untouched["updated_at"], after_untouched["updated_at"])

    def test_06_commit_member_import_direct_helper(self):
        """Helper commit_member_import mengeksekusi komit langsung secara atomik."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Helper,murid,Multimedia,aktif,\n"
        )
        result = commit_member_import(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["created_count"], 1)

    # ==============================================================================
    # B. KEAMANAN DAN VALIDASI KEPUTUSAN SERVER-SIDE
    # ==============================================================================

    def test_07_invalid_action_rejected(self):
        """Tindakan tidak sah ditolak dengan ValidationError."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Test,murid,TKJ,aktif,\n"
        )
        with self.assertRaises(ValidationError):
            create_member_import_confirmation_token(
                conn=self.conn,
                csv_content=csv_text,
                decisions={2: {"action": "HAPUS_MEMBER"}},
                admin_username="admin_test",
            )

    def test_08_invalid_target_member_rejected(self):
        """Pembaruan dengan target ID yang bukan kandidat sah ditolak."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Nama Acak Banget,murid,TKJ,aktif,\n"
        )
        # Baris ini berstatus BARU (0 kandidat), memilih PERBARUI ke ID acak harus ditolak
        with self.assertRaises(ValidationError):
            create_member_import_confirmation_token(
                conn=self.conn,
                csv_content=csv_text,
                decisions={2: {"action": "PERBARUI", "target_member_id": "M-999999"}},
                admin_username="admin_test",
            )

    def test_09_target_collision_rejected(self):
        """Dua baris yang sama-sama menargetkan member_id yang sama ditolak (anti-collision)."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Budi Santoso,murid,TKJ,aktif,M-222222\n"
            "Budi Santoso,murid,RPL,aktif,\n"
        )
        # Baris 2 cocok dengan M-222222, Baris 3 memilih target M-222222 juga
        with self.assertRaises(ValidationError) as ctx:
            create_member_import_confirmation_token(
                conn=self.conn,
                csv_content=csv_text,
                decisions={
                    2: {"action": "PERBARUI", "target_member_id": "M-222222"},
                    3: {"action": "PERBARUI", "target_member_id": "M-222222"},
                },
                admin_username="admin_test",
            )
        self.assertIn("Konflik target pembaruan ganda", str(ctx.exception))

    def test_10_error_row_cannot_be_buat_baru_or_perbarui(self):
        """Baris berstatus ERROR tidak dapat dipaksa menjadi BUAT_BARU atau PERBARUI."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            ",murid,TKJ,aktif,\n"  # Nama kosong -> ERROR
        )
        with self.assertRaises(ValidationError):
            create_member_import_confirmation_token(
                conn=self.conn,
                csv_content=csv_text,
                decisions={2: {"action": "BUAT_BARU"}},
                admin_username="admin_test",
            )

    def test_11_expired_token_rejected(self):
        """Token yang sudah kedaluwarsa ditolak saat commit."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Expired,murid,TKJ,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
            ttl_seconds=-10,  # Kedaluwarsa 10 detik lalu
        )
        with self.assertRaises(ConfirmationTokenError) as ctx:
            commit_member_import_with_token(
                conn=self.conn,
                token=token,
                admin_username="admin_test",
            )
        self.assertIn("kedaluwarsa", str(ctx.exception).lower())

    def test_12_wrong_admin_token_rejected(self):
        """Token yang dieksekusi oleh admin selain penerbit token ditolak."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Wrong Admin,murid,TKJ,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_original",
        )
        with self.assertRaises(ConfirmationTokenError) as ctx:
            commit_member_import_with_token(
                conn=self.conn,
                token=token,
                admin_username="admin_hacker",
            )
        self.assertIn("tidak sah untuk sesi admin", str(ctx.exception))

    def test_13_tampered_payload_rejected(self):
        """Payload CSV atau keputusan yang dimodifikasi setelah pratinjau ditolak."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Asli,murid,TKJ,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )
        with self.assertRaises(ConfirmationTokenError) as ctx:
            commit_member_import_with_token(
                conn=self.conn,
                token=token,
                admin_username="admin_test",
                submitted_csv_content="nama,jenis,keterangan,status,id_anggota\nSiswa Palsu,murid,TKJ,aktif,\n",
            )
        self.assertIn("dimodifikasi", str(ctx.exception))

    def test_14_replay_idempotency_returns_cached_summary(self):
        """Menjalankan commit dua kali dengan token yang sama mengembalikan hasil cache tanpa duplikasi."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Idempoten,murid,TKJ,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )
        summary1, is_replay1 = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )
        self.assertFalse(is_replay1)
        self.assertEqual(summary1["created_count"], 1)

        # Hitung jumlah anggota sebelum replay
        count_before = member_repo.count_members(self.conn)

        # Panggilan kedua (Replay)
        summary2, is_replay2 = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )
        self.assertTrue(is_replay2)
        self.assertEqual(summary2["created_count"], 1)

        # Jumlah anggota di database tidak bertambah sama sekali
        count_after = member_repo.count_members(self.conn)
        self.assertEqual(count_before, count_after)

    def test_15_concurrency_conflict_handling(self):
        """Permintaan ganda bersamaan (race condition) memicu ConcurrencyConflictError."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Concurrency,murid,TKJ,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )

        with _MEMBER_TOKEN_LOCK:
            _ACTIVE_PROCESSING_MEMBER_TOKENS.add(token)

        try:
            with self.assertRaises(ConcurrencyConflictError):
                commit_member_import_with_token(
                    conn=self.conn,
                    token=token,
                    admin_username="admin_test",
                )
        finally:
            with _MEMBER_TOKEN_LOCK:
                _ACTIVE_PROCESSING_MEMBER_TOKENS.discard(token)

    # ==============================================================================
    # C. ATOMISITAS (ROLLBACK 100% PADA KEGAGALAN)
    # ==============================================================================

    def test_16_atomic_rollback_on_failure(self):
        """Jika terjadi error di tengah proses, seluruh perubahan dibatalkan 100% tanpa sisa."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Anggota Sukses 1,murid,TKJ,aktif,\n"
            "Anggota Gagal 2,murid,RPL,aktif,\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={
                2: {"action": "BUAT_BARU"},
                3: {"action": "BUAT_BARU"},
            },
            admin_username="admin_test",
        )

        initial_count = member_repo.count_members(self.conn)
        real_create_member = member_repo.create_member

        # Simulasikan kegagalan saat baris kedua dibuat
        def mock_create_member_fail(conn, data, seen_ids=None):
            if data.get("nama") == "Anggota Gagal 2":
                raise RuntimeError("Simulated Database Disk Crash on Row 2!")
            return real_create_member(conn, data, seen_ids)

        with patch("repositories.member_repo.create_member", side_effect=mock_create_member_fail):
            with self.assertRaises(RuntimeError) as ctx:
                commit_member_import_with_token(
                    conn=self.conn,
                    token=token,
                    admin_username="admin_test",
                )
            self.assertIn("Simulated Database Disk Crash", str(ctx.exception))

        # Verifikasi rollback 100%: Anggota Sukses 1 TIDAK boleh tersimpan di DB
        final_count = member_repo.count_members(self.conn)
        self.assertEqual(initial_count, final_count)

        sukses1_check = self.conn.execute("SELECT 1 FROM members WHERE nama = 'Anggota Sukses 1';").fetchone()
        self.assertIsNone(sukses1_check)

        # Token harus ditandai FAILED di database
        token_row = self.conn.execute("SELECT status FROM confirmation_tokens WHERE token = ?;", (token,)).fetchone()
        self.assertEqual(token_row["status"], "FAILED")

        # Tidak ada audit log sukses
        audits = self.conn.execute("SELECT 1 FROM audit_log WHERE object_id = ?;", (token,)).fetchall()
        self.assertEqual(len(audits), 0)

    # ==============================================================================
    # D. SKALA (>1.000 BARIS SESUAI BATAS RESMI)
    # ==============================================================================

    def test_17_scale_over_1000_rows_successful(self):
        """Memproses batch lebih dari 1.000 baris (1.050 baris) secara atomik dan efisien."""
        rows = ["nama,jenis,keterangan,status,id_anggota"]
        decisions = {}
        target_count = 1050

        for i in range(1, target_count + 1):
            row_num = i + 1
            rows.append(f"Siswa Batch {i:04d},murid,Program Keahlian,aktif,")
            decisions[row_num] = {"action": "BUAT_BARU"}

        csv_text = "\n".join(rows) + "\n"

        start_time = time.time()
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions=decisions,
            admin_username="admin_test",
        )
        summary, is_replay = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )
        elapsed = time.time() - start_time

        self.assertFalse(is_replay)
        self.assertEqual(summary["total_processed"], target_count)
        self.assertEqual(summary["created_count"], target_count)
        self.assertEqual(summary["updated_count"], 0)
        self.assertEqual(summary["skipped_count"], 0)
        self.assertEqual(summary["failed_count"], 0)

        # Verifikasi performa memadai untuk database lokal (< 15 detik)
        self.assertLess(elapsed, 15.0)

        # Verifikasi total baris di database
        total_in_db = member_repo.count_members(self.conn)
        self.assertEqual(total_in_db, 3 + target_count)

    def test_18_exceeding_max_rows_limit_rejected(self):
        """Melebihi batas resmi MAX_MEMBER_IMPORT_ROWS (2.000 baris) ditolak sejak validasi awal."""
        rows = ["nama,jenis,keterangan,status,id_anggota"]
        decisions = {}
        for i in range(1, MAX_MEMBER_IMPORT_ROWS + 5):
            rows.append(f"Siswa Lebih {i},murid,TKJ,aktif,")
            decisions[i + 1] = {"action": "BUAT_BARU"}
        csv_text = "\n".join(rows)

        with self.assertRaises(ValidationError) as ctx:
            create_member_import_confirmation_token(
                conn=self.conn,
                csv_content=csv_text,
                decisions=decisions,
                admin_username="admin_test",
            )
        self.assertIn("melebihi batas maksimum", str(ctx.exception))

    # ==============================================================================
    # E. PRIVASI DEC-023 & INTEGRASI TASK TERKAIT
    # ==============================================================================

    def test_19_privacy_no_kelas_no_telepon_stored(self):
        """Memastikan data kelas dan telepon diabaikan dan tidak tersimpan di database maupun audit."""
        csv_text = (
            "nama,jenis,kelas,telepon,status\n"
            "Ananda Rahma,murid,XII RPL 1,081234567890,aktif\n"
        )
        token = create_member_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )
        summary, _ = commit_member_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
        )
        new_member_id = summary["created_members"][0]["id"]
        member_data = member_repo.get_member_by_id(self.conn, new_member_id)

        # Verifikasi schema members tidak memiliki kolom kelas atau telepon
        self.assertNotIn("kelas", member_data)
        self.assertNotIn("telepon", member_data)

        # Verifikasi audit log tidak memuat nomor telepon
        audit_row = self.conn.execute("SELECT detail_json FROM audit_log WHERE object_id = ?;", (token,)).fetchone()
        self.assertNotIn("081234567890", audit_row["detail_json"])

    def test_20_qr_token_compatibility_task_4_01(self):
        """Anggota baru hasil impor langsung kompatibel dengan token QR Task 4-01."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa QR Ready,murid,TKJ,aktif,\n"
        )
        result = commit_member_import(
            conn=self.conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin_test",
        )
        created_id = result["created_members"][0]["id"]

        # Terbitkan token QR HMAC-SHA256 untuk anggota baru ini
        qr_token = generate_member_qr_token(member_id=created_id, qr_version=1)
        member_data = verify_member_qr_token(self.conn, qr_token)

        self.assertIsNotNone(member_data)
        self.assertEqual(member_data["id"], created_id)
        self.assertEqual(member_data["qr_version"], 1)


class MemberImportCommitRouteTests(unittest.TestCase):
    """Pengujian Integrasi Route Flask untuk Konfirmasi & Commit Impor Anggota."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_member_import_routes.db")
        _init_test_db(self.test_db_path)

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

        def _get_test_conn(db_path=None):
            conn = sqlite3.connect(self.test_db_path)
            conn.row_factory = sqlite3.Row
            return conn

        # Patch get_db_connection
        self.db_patcher = patch("app.get_db_connection", side_effect=_get_test_conn)
        self.db_patcher.start()

        # Patch get_connection di db.py
        self.db_patcher2 = patch("db.get_connection", side_effect=_get_test_conn)
        self.db_patcher2.start()

        with _MEMBER_TOKEN_LOCK:
            _MEMBER_CONFIRMATION_TOKENS.clear()
            _ACTIVE_PROCESSING_MEMBER_TOKENS.clear()

    def tearDown(self):
        self.db_patcher.stop()
        self.db_patcher2.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login(self, client):
        """Helper login sesi admin dengan CSRF token valid."""
        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin_username"] = "admin"
            sess["user_role"] = "admin"
            sess["_csrf_token"] = "mock_csrf_token_1234567890abcdef"
            sess["last_active"] = time.time()

    def test_21_konfirmasi_route_get_redirects(self):
        """GET /admin/members/impor/konfirmasi mengarahkan kembali ke panduan impor."""
        self._login(self.client)
        res = self.client.get("/admin/members/impor/konfirmasi")
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers.get("Location", "").endswith("/panduan"))

    def test_22_konfirmasi_route_post_success_json(self):
        """POST /admin/members/impor/konfirmasi menerbitkan token konfirmasi."""
        self._login(self.client)
        csv_text = "nama,jenis,keterangan,status,id_anggota\nBudi Baru,murid,TKJ,aktif,\n"
        raw_b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")

        payload = {
            "csrf_token": "mock_csrf_token_1234567890abcdef",
            "raw_csv_b64": raw_b64,
            "filename": "test.csv",
            "decisions": {
                2: {"action": "BUAT_BARU"}
            }
        }
        res = self.client.post(
            "/admin/members/impor/konfirmasi",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-CSRFToken": "mock_csrf_token_1234567890abcdef"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("confirm_token", data)
        self.assertEqual(data["confirmation_stats"]["buat_baru_rencana"], 1)

    def test_23_commit_route_post_success_json(self):
        """POST /admin/members/impor/commit mengeksekusi komit atomik."""
        self._login(self.client)
        conn = sqlite3.connect(self.test_db_path)
        csv_text = "nama,jenis,keterangan,status,id_anggota\nSiswa Route Commit,murid,TKJ,aktif,\n"
        token = create_member_import_confirmation_token(
            conn=conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin",
        )
        conn.close()

        payload = {
            "csrf_token": "mock_csrf_token_1234567890abcdef",
            "confirm_token": token,
        }
        res = self.client.post(
            "/admin/members/impor/commit",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-CSRFToken": "mock_csrf_token_1234567890abcdef"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["is_replay"])
        self.assertEqual(data["summary"]["created_count"], 1)

    def test_24_commit_route_unauthenticated_rejected(self):
        """Permintaan tanpa autentikasi admin ditolak 401."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = False
            sess["_csrf_token"] = "mock_csrf_token_1234567890abcdef"

        payload = {
            "csrf_token": "mock_csrf_token_1234567890abcdef",
            "confirm_token": "any_token",
        }
        res = self.client.post(
            "/admin/members/impor/commit",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-CSRFToken": "mock_csrf_token_1234567890abcdef"},
        )
        self.assertEqual(res.status_code, 401)

    def test_25_alias_routes_work(self):
        """Route alias bahasa Indonesia /admin/anggota/impor/* berfungsi identik."""
        self._login(self.client)
        conn = sqlite3.connect(self.test_db_path)
        csv_text = "nama,jenis,keterangan,status,id_anggota\nSiswa Alias Route,murid,TKJ,aktif,\n"
        token = create_member_import_confirmation_token(
            conn=conn,
            csv_content=csv_text,
            decisions={2: {"action": "BUAT_BARU"}},
            admin_username="admin",
        )
        conn.close()

        payload = {
            "csrf_token": "mock_csrf_token_1234567890abcdef",
            "confirm_token": token,
        }
        res = self.client.post(
            "/admin/anggota/impor/commit",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-CSRFToken": "mock_csrf_token_1234567890abcdef"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
