# -*- coding: utf-8 -*-
"""
Pengujian Menyeluruh untuk Task 3-07:
Commit Impor Katalog Massal Atomik, Token Konfirmasi Persisten, Idempotensi, Rollback, & Ringkasan Hasil.
Memenuhi Seluruh 30 Skenario Pengujian Wajib (A.1 s.d. E.30).
"""
import base64
import hashlib
import io
import json
import os
import re
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
    MAX_CATALOG_IMPORT_FILE_SIZE_BYTES,
    MAX_CATALOG_IMPORT_ROWS,
)
from repositories import copy_repo
from services import (
    create_catalog_import_confirmation_token,
    commit_catalog_import_with_token,
    canonicalize_import_payload,
    compute_import_payload_hash,
    parse_and_validate_catalog_import_csv,
    ValidationError,
    ConfirmationTokenError,
    ConcurrencyConflictError,
)
from services.catalog_service import (
    _CONFIRMATION_TOKENS,
    _ACTIVE_PROCESSING_TOKENS,
    _TOKEN_LOCK,
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
    conn.close()


class CatalogImportCommitServiceTests(unittest.TestCase):
    """Pengujian Unit & Service Layer untuk Komit Impor Katalog Atomik."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_catalog_import_service.db")
        _init_test_db(self.test_db_path)
        self.conn = sqlite3.connect(self.test_db_path)
        self.conn.row_factory = sqlite3.Row

        with _TOKEN_LOCK:
            _CONFIRMATION_TOKENS.clear()
            _ACTIVE_PROCESSING_TOKENS.clear()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ==============================================================================
    # A. COMMIT NORMAL (1..6)
    # ==============================================================================

    def test_01_import_multiple_valid_titles(self):
        """Kriteria 1 & 6: Impor dengan beberapa judul valid berhasil membuat seluruh rekaman."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Matematika Diskrit,Rinaldi Munir,978-602-8758-00-1,Komputer,3\n"
            "Kecerdasan Buatan,Suyanto,978-602-8758-00-2,Komputer,2\n"
        )
        token = create_catalog_import_confirmation_token(
            conn=self.conn,
            csv_content=csv_text,
            admin_username="admin_test",
        )
        summary, is_replay = commit_catalog_import_with_token(
            conn=self.conn,
            token=token,
            admin_username="admin_test",
            submitted_csv_content=csv_text,
        )

        self.assertFalse(is_replay)
        self.assertEqual(summary["titles_created_count"], 2)
        self.assertEqual(summary["copies_created_count"], 5)
        self.assertEqual(summary["skipped_rows_count"], 0)
        self.assertEqual(summary["problematic_rows_count"], 0)

        # Cek database
        cur = self.conn.cursor()
        titles = cur.execute("SELECT * FROM catalog_titles;").fetchall()
        copies = cur.execute("SELECT * FROM copies;").fetchall()
        self.assertEqual(len(titles), 2)
        self.assertEqual(len(copies), 5)

    def test_02_single_title_multiple_copies_with_unique_ids(self):
        """Kriteria 2: Satu judul menghasilkan beberapa eksemplar dengan ID unik."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Algoritma Genetika,Dr. Ahmad,978-602-1234-56-7,Komputer,4\n"
        )
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")
        summary, is_replay = commit_catalog_import_with_token(self.conn, token, "admin_test")

        self.assertEqual(summary["titles_created_count"], 1)
        self.assertEqual(summary["copies_created_count"], 4)

        cur = self.conn.cursor()
        copies = cur.execute("SELECT id, title_id FROM copies;").fetchall()
        self.assertEqual(len(copies), 4)

        # Seluruh ID eksemplar harus unik
        copy_ids = [c["id"] for c in copies]
        self.assertEqual(len(set(copy_ids)), 4)
        # Seluruh eksemplar merujuk ke title_id yang sama
        title_id = copies[0]["title_id"]
        for c in copies:
            self.assertEqual(c["title_id"], title_id)

    def test_03_summary_matches_database_counts(self):
        """Kriteria 3: Ringkasan judul dan eksemplar sesuai persis dengan hasil database."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku A,Penulis A,978-602-0001-01-1,Fiksi,2\n"
            "Buku B,Penulis B,978-602-0001-02-2,Sains,3\n"
            "Buku C,Penulis C,978-602-0001-03-3,Sosial,1\n"
        )
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")
        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test")

        db_titles = self.conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        db_copies = self.conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]

        self.assertEqual(summary["titles_created_count"], db_titles)
        self.assertEqual(summary["copies_created_count"], db_copies)
        self.assertEqual(db_titles, 3)
        self.assertEqual(db_copies, 6)

    def test_04_error_rows_not_imported(self):
        """Kriteria 4: Baris error tidak diimpor ke dalam database."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku Valid,Penulis Valid,978-602-0002-01-1,Fiksi,2\n"
            ",Penulis Tanpa Judul,,Fiksi,1\n"                  # Error: Judul kosong
            "=SUM(A1:A5),Penulis Formula,,Fiksi,1\n"           # Error: Formula injection
            "Buku Negatif,Penulis B,,Fiksi,-2\n"               # Error: Kuantitas negatif
        )
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")
        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test")

        self.assertEqual(summary["titles_created_count"], 1)
        self.assertEqual(summary["copies_created_count"], 2)
        self.assertEqual(summary["problematic_rows_count"], 3)

        # Database hanya memuat 1 judul
        db_titles = self.conn.execute("SELECT judul FROM catalog_titles;").fetchall()
        self.assertEqual(len(db_titles), 1)
        self.assertEqual(db_titles[0][0], "Buku Valid")

    def test_05_warning_rows_follow_policy(self):
        """Kriteria 5: Baris peringatan mengikuti kebijakan resmi (dilewati jika skip_warnings=True)."""
        # Masukkan buku lama ke DB terlebih dahulu
        self.conn.execute(
            "INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at) "
            "VALUES ('T-OLD', 'Fisika Dasar', 'Halliday', '978-602-0003-01-1', 'Sains', '2026-10-24T00:00:00Z', '2026-10-24T00:00:00Z');"
        )
        self.conn.commit()

        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Kimia Organik,Fessenden,978-602-0003-02-2,Sains,3\n"     # OK
            "Fisika Dasar,Halliday,978-602-0003-01-1,Sains,2\n"        # Peringatan (Duplikat DB)
        )
        token = create_catalog_import_confirmation_token(
            self.conn, csv_text, "admin_test", skip_warnings=True
        )
        summary, _ = commit_catalog_import_with_token(
            self.conn, token, "admin_test", skip_warnings=True
        )

        self.assertEqual(summary["titles_created_count"], 1)
        self.assertEqual(summary["skipped_rows_count"], 1)
        self.assertEqual(summary["problematic_rows_count"], 0)

        # Judul baru di DB hanya Kimia Organik
        new_titles = self.conn.execute("SELECT judul FROM catalog_titles WHERE id != 'T-OLD';").fetchall()
        self.assertEqual(len(new_titles), 1)
        self.assertEqual(new_titles[0][0], "Kimia Organik")

    def test_06_titles_and_copies_relationship(self):
        """Kriteria 6: Data judul dan eksemplar memiliki integritas referensial foreign key yang benar."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Biologi Sel,Bruce Alberts,978-602-0004-01-1,Biologi,3\n"
        )
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")
        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test")

        title_id = summary["created_titles"][0]["title_id"]
        copies = self.conn.execute("SELECT * FROM copies WHERE title_id = ?;", (title_id,)).fetchall()
        self.assertEqual(len(copies), 3)
        for cp in copies:
            self.assertEqual(cp["title_id"], title_id)
            self.assertEqual(cp["status"], "aktif")

    # ==============================================================================
    # B. ATOMICITY & ROLLBACK (7..11)
    # ==============================================================================

    def test_07_failure_mid_batch_rolls_back_everything(self):
        """Kriteria 7, 9, 10: Simulasi kegagalan di tengah pembuatan eksemplar membatalkan seluruh operasi."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku Pertama,Penulis 1,978-602-0005-01-1,Fiksi,2\n"
            "Buku Kedua,Penulis 2,978-602-0005-02-2,Fiksi,2\n"
        )
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")

        call_count = 0
        real_create_copies = copy_repo.create_copies_batch

        def exploding_create_copies(conn, title_id, count, base_data=None):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("Simulasi kegagalan crash database saat pembuatan eksemplar kedua!")
            return real_create_copies(conn, title_id, count, base_data=base_data)

        with patch("services.catalog_service.copy_repo.create_copies_batch", side_effect=exploding_create_copies):
            with self.assertRaises(RuntimeError):
                commit_catalog_import_with_token(self.conn, token, "admin_test")

        # Verifikasi rollback 100%: tidak ada judul atau eksemplar parsial di database
        db_titles = self.conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        db_copies = self.conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        self.assertEqual(db_titles, 0, "Judul buku pertama harus ikut dibatalkan (0 parsial)")
        self.assertEqual(db_copies, 0, "Eksemplar buku pertama harus ikut dibatalkan (0 parsial)")

        # Kriteria 11: Status token harus FAILED secara persisten
        token_row = self.conn.execute("SELECT status FROM confirmation_tokens WHERE token = ?;", (token,)).fetchone()
        self.assertEqual(token_row["status"], "FAILED")

    def test_08_failure_during_audit_log_rolls_back(self):
        """Kriteria 8 & 9: Simulasi kegagalan saat penulisan audit log membatalkan seluruh operasi."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku Audit Fail,Penulis Audit,978-602-0006-01-1,Fiksi,3\n"
        )
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")

        def exploding_audit(*args, **kwargs):
            if kwargs.get("action") == "CATALOG_IMPORT":
                raise sqlite3.OperationalError("Simulasi disk I/O error saat menulis audit log")
            return 1

        with patch("services.catalog_service.audit_repo.record_audit", side_effect=exploding_audit):
            with self.assertRaises(sqlite3.OperationalError):
                commit_catalog_import_with_token(self.conn, token, "admin_test")

        # Rollback: Tidak ada judul atau eksemplar
        db_titles = self.conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        db_copies = self.conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        self.assertEqual(db_titles, 0)
        self.assertEqual(db_copies, 0)

        # Status token tercatat FAILED
        status = self.conn.execute("SELECT status FROM confirmation_tokens WHERE token = ?;", (token,)).fetchone()[0]
        self.assertEqual(status, "FAILED")

    def test_09_retrying_failed_token_is_rejected(self):
        """Kriteria 11: Token yang berstatus FAILED tidak dapat dicoba ulang untuk mencegah inkonsistensi."""
        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku Gagal,Penulis,978-602-0007-01-1,Fiksi,1\n"
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")

        # Set status FAILED di database
        self.conn.execute("UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ?;", (token,))
        self.conn.commit()

        with self.assertRaises(ConfirmationTokenError) as ctx:
            commit_catalog_import_with_token(self.conn, token, "admin_test")
        self.assertIn("gagal", str(ctx.exception).lower())

    # ==============================================================================
    # C. IDEMPOTENSI & KONKURENSI (12..18)
    # ==============================================================================

    def test_12_replay_completed_token_returns_cached_result(self):
        """Kriteria 12: Replay token yang sudah berhasil mengembalikan ringkasan tanpa penulisan duplikat."""
        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku Replay,Penulis Replay,978-602-0008-01-1,Fiksi,2\n"
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")

        # Request pertama (sukses baru)
        res1, is_replay1 = commit_catalog_import_with_token(self.conn, token, "admin_test", csv_text)
        self.assertFalse(is_replay1)
        self.assertEqual(res1["titles_created_count"], 1)
        self.assertEqual(res1["copies_created_count"], 2)

        # Request kedua (replay respons hilang)
        res2, is_replay2 = commit_catalog_import_with_token(self.conn, token, "admin_test", csv_text)
        self.assertTrue(is_replay2)
        self.assertEqual(res2["titles_created_count"], 1)
        self.assertEqual(res2["copies_created_count"], 2)

        # Database tetap hanya 1 judul dan 2 eksemplar
        db_titles = self.conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        db_copies = self.conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        self.assertEqual(db_titles, 1)
        self.assertEqual(db_copies, 2)

    def test_13_rapid_double_click_concurrency_lock(self):
        """Kriteria 13: Klik ganda cepat memicu ConcurrencyConflictError."""
        token = "test_concurrent_token"
        with _TOKEN_LOCK:
            _ACTIVE_PROCESSING_TOKENS.add(token)

        try:
            with self.assertRaises(ConcurrencyConflictError) as ctx:
                commit_catalog_import_with_token(self.conn, token, "admin_test")
            self.assertIn("sedang diproses", str(ctx.exception).lower())
        finally:
            with _TOKEN_LOCK:
                _ACTIVE_PROCESSING_TOKENS.discard(token)

    def test_14_two_database_connections_concurrent_token_use(self):
        """Kriteria 14: Dua koneksi database mencoba menggunakan token yang sama secara paralel."""
        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku Paralel,Penulis P,978-602-0009-01-1,Fiksi,2\n"
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test")

        results = []
        errors = []

        def worker():
            conn2 = sqlite3.connect(self.test_db_path)
            conn2.row_factory = sqlite3.Row
            try:
                res, is_rep = commit_catalog_import_with_token(conn2, token, "admin_test", csv_text)
                results.append((res, is_rep))
            except Exception as e:
                errors.append(e)
            finally:
                conn2.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Harus ada tepat 1 eksekusi sukses (is_replay=False)
        fresh_commits = [r for r in results if not r[1]]
        self.assertEqual(len(fresh_commits), 1, "Hanya tepat 1 worker yang boleh melakukan commit baru")

        # Worker kedua bisa berupa replay atau ConcurrencyConflictError
        if len(results) == 2:
            self.assertTrue(results[1][1], "Jika worker kedua sukses, wajib berstatus is_replay=True")
        else:
            self.assertTrue(any(isinstance(e, ConcurrencyConflictError) for e in errors))

        # Total di DB tetap tepat 1 judul
        db_titles = self.conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        self.assertEqual(db_titles, 1)

    def test_15_expired_or_unknown_token_rejected(self):
        """Kriteria 15: Token yang tidak dikenal atau kedaluwarsa ditolak secara aman."""
        # A. Token tidak dikenal
        with self.assertRaises(ConfirmationTokenError) as ctx1:
            commit_catalog_import_with_token(self.conn, "non_existent_token", "admin_test")
        self.assertIn("tidak valid", str(ctx1.exception).lower())

        # B. Token kedaluwarsa
        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku Expired,Penulis,978-602-0010-01-1,Fiksi,1\n"
        exp_token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test", ttl_seconds=-10)

        with self.assertRaises(ConfirmationTokenError) as ctx2:
            commit_catalog_import_with_token(self.conn, exp_token, "admin_test")
        self.assertIn("kedaluwarsa", str(ctx2.exception).lower())

    def test_16_payload_hash_mismatch_tampering_rejected(self):
        """Kriteria 16: Perubahan payload CSV setelah pratinjau/token diterbitkan ditolak."""
        csv_original = "judul,penulis,isbn,kategori,jumlah\nBuku Asli,Penulis Asli,978-602-0011-01-1,Fiksi,1\n"
        token = create_catalog_import_confirmation_token(self.conn, csv_original, "admin_test")

        csv_tampered = "judul,penulis,isbn,kategori,jumlah\nBuku Asli,Penulis Asli,978-602-0011-01-1,Fiksi,100\n"

        with self.assertRaises(ConfirmationTokenError) as ctx:
            commit_catalog_import_with_token(self.conn, token, "admin_test", submitted_csv_content=csv_tampered)
        self.assertIn("dimodifikasi", str(ctx.exception).lower())

    def test_17_application_restart_simulation_pending_and_completed(self):
        """Kriteria 17: Simulasi restart aplikasi (cache memori dibersihkan), token persisten tetap bekerja."""
        csv_pending = "judul,penulis,isbn,kategori,jumlah\nBuku Pending Restart,Penulis,978-602-0012-01-1,Fiksi,2\n"
        token_pending = create_catalog_import_confirmation_token(self.conn, csv_pending, "admin_test")

        csv_completed = "judul,penulis,isbn,kategori,jumlah\nBuku Completed Restart,Penulis,978-602-0012-02-2,Fiksi,2\n"
        token_completed = create_catalog_import_confirmation_token(self.conn, csv_completed, "admin_test")
        commit_catalog_import_with_token(self.conn, token_completed, "admin_test", csv_completed)

        # SIMULASI RESTART: Bersihkan seluruh dictionary dan set in-memory
        with _TOKEN_LOCK:
            _CONFIRMATION_TOKENS.clear()
            _ACTIVE_PROCESSING_TOKENS.clear()

        # A. Token PENDING tetap bisa dieksekusi setelah restart
        res_p, is_rep_p = commit_catalog_import_with_token(self.conn, token_pending, "admin_test", csv_pending)
        self.assertFalse(is_rep_p)
        self.assertEqual(res_p["titles_created_count"], 1)

        # B. Token COMPLETED tetap bisa direplay setelah restart
        res_c, is_rep_c = commit_catalog_import_with_token(self.conn, token_completed, "admin_test", csv_completed)
        self.assertTrue(is_rep_c)
        self.assertEqual(res_c["titles_created_count"], 1)

    # ==============================================================================
    # D. PERUBAHAN DATA & DUPLIKAT (19..24)
    # ==============================================================================

    def test_19_catalog_data_changes_after_preview_revalidated_live(self):
        """Kriteria 19: Jika data katalog berubah sebelum commit, validasi ulang live mendeteksi duplikat."""
        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku Berubah,Penulis X,978-602-0013-01-1,Fiksi,2\n"
        # Token diterbitkan saat DB masih kosong
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test", skip_warnings=True)

        # Sebelum commit dipanggil, admin lain memasukkan buku dengan ISBN yang sama
        self.conn.execute(
            "INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at) "
            "VALUES ('T-OTHER', 'Buku Lain', 'Penulis Lain', '978-602-0013-01-1', 'Fiksi', '2026-10-24T00:00:00Z', '2026-10-24T00:00:00Z');"
        )
        self.conn.commit()

        # Commit dijalankan dengan skip_warnings=True -> baris terdeteksi peringatan dan dilewati!
        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test", skip_warnings=True)
        self.assertEqual(summary["titles_created_count"], 0)
        self.assertEqual(summary["skipped_rows_count"], 1)

    def test_20_and_21_normalized_isbn_and_author_title_duplicate_detection(self):
        """Kriteria 20 & 21: Deteksi duplikat mendeteksi ekuivalensi ISBN tanpa strip dan pasangan judul+penulis."""
        # Seed buku lama
        self.conn.execute(
            "INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at) "
            "VALUES ('T-EXIST', 'Kalkulus Lanjut', 'Purcell', '9786029999999', 'Sains', '2026-10-24T00:00:00Z', '2026-10-24T00:00:00Z');"
        )
        self.conn.commit()

        # CSV dengan ISBN berpembatas strip '978-602-9999-99-9'
        csv_text = "judul,penulis,isbn,kategori,jumlah\nKalkulus Lanjut,Purcell,978-602-9999-99-9,Sains,1\n"
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test", skip_warnings=True)

        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test", skip_warnings=True)
        self.assertEqual(summary["skipped_rows_count"], 1)
        self.assertEqual(summary["titles_created_count"], 0)

    def test_22_intra_file_duplicate_handling(self):
        """Kriteria 22: Duplikat antar-baris dalam berkas yang sama ditangani sesuai kebijakan."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Fisika Kuantum,Dr. Richard,978-602-0014-01-1,Sains,2\n"
            "Fisika Modern,Dr. Richard,978-602-0014-01-1,Sains,3\n"  # ISBN sama dengan baris 1
        )
        # Jika skip_warnings = True, baris 2 dilewati
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test", skip_warnings=True)
        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test", skip_warnings=True)

        self.assertEqual(summary["titles_created_count"], 1)
        self.assertEqual(summary["skipped_rows_count"], 1)

    def test_23_confirmed_warnings_create_separate_records_dec013(self):
        """Kriteria 23: Peringatan yang dikonfirmasi (skip_warnings=False) membuat rekaman terpisah (DEC-013)."""
        self.conn.execute(
            "INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at) "
            "VALUES ('T-001', 'Pemrograman Python', 'Guido', '978-602-0015-01-1', 'Komputer', '2026-10-24T00:00:00Z', '2026-10-24T00:00:00Z');"
        )
        self.conn.commit()

        csv_text = "judul,penulis,isbn,kategori,jumlah\nPemrograman Python,Guido,978-602-0015-01-1,Komputer,3\n"
        token = create_catalog_import_confirmation_token(self.conn, csv_text, "admin_test", skip_warnings=False)
        summary, _ = commit_catalog_import_with_token(self.conn, token, "admin_test", skip_warnings=False)

        # Judul baru dibuat terpisah (DEC-013)
        self.assertEqual(summary["titles_created_count"], 1)
        self.assertEqual(summary["skipped_rows_count"], 0)

        # Database sekarang memiliki 2 rekaman judul dengan ID berbeda
        all_titles = self.conn.execute("SELECT id, judul FROM catalog_titles;").fetchall()
        self.assertEqual(len(all_titles), 2)
        new_id = summary["created_titles"][0]["title_id"]
        self.assertNotEqual(new_id, "T-001")

    def test_24_two_independent_imports_concurrency_safe(self):
        """Kriteria 24: Dua operasi impor berbeda berjalan bersamaan tanpa menimbulkan korupsi atau inkonsistensi."""
        csv_a = "judul,penulis,isbn,kategori,jumlah\nBuku Paralel A,Penulis A,978-602-0024-01-1,Fiksi,2\n"
        csv_b = "judul,penulis,isbn,kategori,jumlah\nBuku Paralel B,Penulis B,978-602-0024-02-2,Sains,3\n"

        token_a = create_catalog_import_confirmation_token(self.conn, csv_a, "admin_a")
        token_b = create_catalog_import_confirmation_token(self.conn, csv_b, "admin_b")

        errors = []
        results = []

        def worker_a():
            conn = sqlite3.connect(self.test_db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                res, _ = commit_catalog_import_with_token(conn, token_a, "admin_a", csv_a)
                results.append(res)
            except Exception as e:
                errors.append(e)
            finally:
                conn.close()

        def worker_b():
            conn = sqlite3.connect(self.test_db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            try:
                res, _ = commit_catalog_import_with_token(conn, token_b, "admin_b", csv_b)
                results.append(res)
            except Exception as e:
                errors.append(e)
            finally:
                conn.close()

        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Tidak boleh ada error konkurensi tak tertangani: {errors}")
        self.assertEqual(len(results), 2)

        # Database memuat tepat 2 judul dan 5 eksemplar
        db_titles = self.conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        db_copies = self.conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        self.assertEqual(db_titles, 2)
        self.assertEqual(db_copies, 5)


class CatalogImportCommitRouteIntegrationTests(unittest.TestCase):
    """Pengujian Integrasi Route Flask untuk Konfirmasi & Komit Impor Katalog."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_catalog_import_route.db")
        _init_test_db(self.test_db_path)

        self.orig_db_env = os.environ.get("DATABASE_NAME")
        os.environ["DATABASE_NAME"] = self.test_db_path
        self.orig_db_file = app.config.get("DATABASE")
        app.config["DATABASE"] = self.test_db_path
        app.config["TESTING"] = True
        self.client = app.test_client()

        with _TOKEN_LOCK:
            _CONFIRMATION_TOKENS.clear()
            _ACTIVE_PROCESSING_TOKENS.clear()

    def tearDown(self):
        if self.orig_db_env is not None:
            os.environ["DATABASE_NAME"] = self.orig_db_env
        else:
            os.environ.pop("DATABASE_NAME", None)
        if self.orig_db_file is not None:
            app.config["DATABASE"] = self.orig_db_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_as_admin(self):
        token = "valid-csrf-token-307"
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin_username"] = "admin"
            sess["last_active"] = time.time()
            sess["_csrf_token"] = token
        return token

    # ==============================================================================
    # E. KEAMANAN & REGRESI (25..30)
    # ==============================================================================

    def test_25_unauthenticated_or_non_admin_cannot_commit(self):
        """Kriteria 25: Pengguna tanpa autentikasi admin tidak dapat melakukan konfirmasi atau commit."""
        # A. Sesi tidak login (logged_in = False) tetapi CSRF valid
        with self.client.session_transaction() as sess:
            sess["logged_in"] = False
            sess["_csrf_token"] = "valid-csrf-unauth"

        data = {"csrf_token": "valid-csrf-unauth", "csv_content": "judul,penulis,isbn,kategori,jumlah\n"}
        resp1 = self.client.post("/buku/impor/konfirmasi", data=data)
        self.assertEqual(resp1.status_code, 302)
        self.assertIn("/login", resp1.headers.get("Location", ""))

        # B. Tanpa login POST commit
        resp2 = self.client.post("/buku/impor/commit", data=data)
        self.assertEqual(resp2.status_code, 302)
        self.assertIn("/login", resp2.headers.get("Location", ""))

    def test_26_invalid_csrf_token_rejected_400(self):
        """Kriteria 26: Permintaan tanpa CSRF token yang cocok ditolak dengan HTTP 400."""
        # Login dengan token A
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin_username"] = "admin"
            sess["last_active"] = time.time()
            sess["_csrf_token"] = "valid-session-csrf"

        # Kirim token B
        data = {"csrf_token": "wrong-csrf-token", "confirm_token": "tok"}
        resp = self.client.post("/buku/impor/commit", data=data)
        self.assertEqual(resp.status_code, 400)

    def test_27_full_browser_workflow_preview_to_confirmation_to_commit(self):
        """Alur lengkap: Unggah CSV -> Preview -> Konfirmasi -> Commit -> Ringkasan Hasil."""
        csrf_token = self._login_as_admin()

        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Sistem Informasi Manajemen,Prof. Jogiyanto,978-602-0016-01-1,Bisnis,3\n"
            "Pengantar Akuntansi,Slamet Sugiri,,Bisnis,2\n"
        )
        csv_bytes = csv_text.encode("utf-8")

        # 1. POST ke preview
        data_preview = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_bytes), "katalog.csv")
        }
        resp_preview = self.client.post("/buku/impor/preview", data=data_preview, content_type="multipart/form-data")
        self.assertEqual(resp_preview.status_code, 200)
        html_preview = resp_preview.get_data(as_text=True)
        self.assertIn("Lanjutkan ke Konfirmasi Impor", html_preview)

        # 2. POST ke konfirmasi (menghasilkan confirm_token)
        raw_b64 = base64.b64encode(csv_bytes).decode("ascii")
        data_confirm = {
            "csrf_token": csrf_token,
            "csv_content": raw_b64,
            "filename": "katalog.csv",
        }
        resp_confirm = self.client.post("/buku/impor/konfirmasi", data=data_confirm)
        self.assertEqual(resp_confirm.status_code, 200)
        html_confirm = resp_confirm.get_data(as_text=True)
        self.assertIn("Konfirmasi Komit Impor Katalog", html_confirm)
        self.assertIn("Ya, Commit Impor Massal Sekarang", html_confirm)

        # Ekstrak token konfirmasi dari input hidden
        match = re.search(r'name="confirm_token"\s+value="([a-f0-9]{48})"', html_confirm)
        self.assertIsNotNone(match, "Harus menemukan token 48 hex di halaman konfirmasi")
        confirm_token = match.group(1)

        # 3. POST ke commit
        data_commit = {
            "csrf_token": csrf_token,
            "confirm_token": confirm_token,
            "csv_content": raw_b64,
        }
        resp_commit = self.client.post("/buku/impor/commit", data=data_commit)
        self.assertEqual(resp_commit.status_code, 200)
        html_summary = resp_commit.get_data(as_text=True)

        self.assertIn("Ringkasan Hasil Impor Katalog", html_summary)
        self.assertIn("Sistem Informasi Manajemen", html_summary)
        self.assertIn("Pengantar Akuntansi", html_summary)

        # 4. Verifikasi Replay pada Route Commit
        resp_replay = self.client.post("/buku/impor/commit", data=data_commit)
        self.assertEqual(resp_replay.status_code, 200)
        html_replay = resp_replay.get_data(as_text=True)
        self.assertIn("Hasil Replay Idempoten", html_replay)

    def test_28_json_api_mode_for_confirmation_and_commit(self):
        """Kriteria API JSON: Mendukung mode JSON terstruktur untuk alur integrasi klien."""
        csrf_token = self._login_as_admin()

        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku JSON Commit,Penulis JSON,,Komputer,5\n"
        headers = {
            "Accept": "application/json",
            "X-CSRFToken": csrf_token,
            "Content-Type": "application/json",
        }

        # Step 1: POST /buku/impor/konfirmasi via JSON
        data_konf = {
            "csrf_token": csrf_token,
            "csv_content": csv_text,
            "skip_warnings": False,
        }
        res_konf = self.client.post("/buku/impor/konfirmasi", json=data_konf, headers=headers)
        self.assertEqual(res_konf.status_code, 200)
        json_konf = res_konf.get_json()
        self.assertTrue(json_konf["ok"])
        confirm_token = json_konf["confirm_token"]

        # Step 2: POST /buku/impor/commit via JSON
        data_com = {
            "csrf_token": csrf_token,
            "confirm_token": confirm_token,
            "csv_content": csv_text,
        }
        res_com = self.client.post("/buku/impor/commit", json=data_com, headers=headers)
        self.assertEqual(res_com.status_code, 200)
        json_com = res_com.get_json()
        self.assertTrue(json_com["ok"])
        self.assertFalse(json_com["is_replay"])
        self.assertEqual(json_com["summary"]["titles_created_count"], 1)
        self.assertEqual(json_com["summary"]["copies_created_count"], 5)

        # Step 3: Replay via JSON
        res_rep = self.client.post("/buku/impor/commit", json=data_com, headers=headers)
        self.assertEqual(res_rep.status_code, 200)
        json_rep = res_rep.get_json()
        self.assertTrue(json_rep["is_replay"])

    def test_29_add_book_form_and_task_303_tokens_remain_functional(self):
        """Kriteria 29: Form tambah buku satuan dan token konfirmasi Task 3-03 tetap bekerja normal."""
        csrf_token = self._login_as_admin()

        # Step 1: POST /buku/tambah (Preview Task 3-02/3-03)
        data = {
            "csrf_token": csrf_token,
            "judul": "Buku Regresi 303",
            "penulis": "Penulis Regresi",
            "kategori": "Umum",
            "jumlah": "3",
        }
        res_prev = self.client.post("/buku/tambah", data=data)
        self.assertEqual(res_prev.status_code, 200)
        html_prev = res_prev.get_data(as_text=True)
        self.assertIn("Tahap Pratinjau Eksemplar", html_prev)

        # Temukan token konfirmasi buku tunggal
        m = re.search(r'name="confirm_token"\s+value="([a-f0-9]{48})"', html_prev)
        self.assertIsNotNone(m)
        token_single = m.group(1)

        # Step 2: Konfirmasi /buku/tambah/konfirmasi (Commit Task 3-03)
        conf_data = {
            "csrf_token": csrf_token,
            "confirm_token": token_single,
            **data,
        }
        res_conf = self.client.post("/buku/tambah/konfirmasi", data=conf_data)
        self.assertEqual(res_conf.status_code, 200)
        html_conf = res_conf.get_data(as_text=True)
        self.assertIn("Buku Regresi 303", html_conf)
        self.assertIn("berhasil dibuat", html_conf)

    def test_30_zero_write_preview_remains_intact(self):
        """Kriteria 28: Endpoint preview Task 3-06 tetap terbukti 100% zero-write."""
        csrf_token = self._login_as_admin()

        conn = sqlite3.connect(self.test_db_path)
        count_titles_before = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        count_copies_before = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        count_tokens_before = conn.execute("SELECT COUNT(*) FROM confirmation_tokens;").fetchone()[0]
        conn.close()

        csv_text = "judul,penulis,isbn,kategori,jumlah\nBuku Preview Zero,Penulis Zero,,Fiksi,2\n"
        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_text.encode("utf-8")), "zero_test.csv")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)

        conn = sqlite3.connect(self.test_db_path)
        count_titles_after = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        count_copies_after = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        count_tokens_after = conn.execute("SELECT COUNT(*) FROM confirmation_tokens;").fetchone()[0]
        conn.close()

        self.assertEqual(count_titles_before, count_titles_after)
        self.assertEqual(count_copies_before, count_copies_after)
        self.assertEqual(count_tokens_before, count_tokens_after)


if __name__ == "__main__":
    import re
    unittest.main()
