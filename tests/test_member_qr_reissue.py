# -*- coding: utf-8 -*-
"""
Rangkaian Pengujian Unit, Keamanan, Integrasi, dan Regresi untuk Task 4-07:
Cabut dan Terbitkan Ulang QR Anggota (LIB-QR-001, DEC-010, DEC-023).
Sistem Perpustakaan Digital Sekolah.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import app as library_app
from policy import (
    MIN_MEMBER_QR_REISSUE_REASON_LENGTH,
    MAX_MEMBER_QR_REISSUE_REASON_LENGTH,
)
from repositories import member_repo, audit_repo
from services import (
    register_member,
    set_member_status,
    get_member_qr,
    reissue_member_qr,
    revoke_and_reissue_member_qr,
    get_member_audit_history,
    borrow_copies,
    return_copies,
    create_title_with_copies,
    generate_member_qr_token,
    verify_member_qr_token,
    validate_member_token,
)
from services.exceptions import (
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
    MemberTokenRevokedError,
    InvalidOperationError,
)


class TestMemberQrReissue(unittest.TestCase):
    """Pengujian menyeluruh Task 4-07: Cabut dan Terbitkan Ulang QR Anggota."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_member_qr_reissue.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        self.secret_key = "test-secret-key-for-task-4-07-reissue-qr-suite"
        os.environ["SECRET_KEY"] = self.secret_key

        library_app.app.config["TESTING"] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2 terisolasi
        self._init_v2_db(self.test_db)

    def tearDown(self):
        os.environ.pop("DATABASE_NAME", None)
        os.environ.pop("SQLITE_TIMEOUT", None)
        os.environ.pop("SECRET_KEY", None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _init_v2_db(self, db_path: str):
        """Membuat struktur tabel v2 yang bersih dan terisolasi."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        migration_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations",
            "0001_initial_v2_schema.sql",
        )
        with open(migration_file, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        member_repo.seed_default_categories(conn)
        conn.commit()
        conn.close()

    def _login_admin(self, username="admin_perpus"):
        """Helper untuk mengeset sesi login admin dan mengembalikan token CSRF valid."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = "admin"
            sess["username"] = username
            sess["admin_username"] = username
            sess["_csrf_token"] = "valid_csrf_token_for_test_4_07"
        return "valid_csrf_token_for_test_4_07"

    def _create_sample_member(self, nama="Budi Santoso", category_id="MC-MURID", status="aktif"):
        """Helper untuk membuat satu rekaman anggota baru dengan qr_version=1."""
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            m = register_member(conn, nama=nama, category_id=category_id, status=status)
            conn.commit()
            return m
        finally:
            conn.close()

    def test_01_authenticated_admin_can_access_qr_page_html(self):
        """Admin terautentikasi dapat membuka halaman kartu QR anggota secara HTML (GET)."""
        self._login_admin()
        member = self._create_sample_member("Siti Rahmawati")

        resp = self.client.get(f"/admin/members/{member['id']}/qr")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Kartu & Token QR Anggota", html)
        self.assertIn("Siti Rahmawati", html)
        self.assertIn(member["id"], html)
        self.assertIn("v1", html)
        self.assertIn("<svg", html)  # Menampilkan QR SVG murni
        self.assertIn("Cabut & Terbitkan Ulang QR", html)

    def test_02_authenticated_admin_can_access_alias_urls(self):
        """Admin dapat mengakses seluruh route alias resmi (Indonesia / Inggris)."""
        self._login_admin()
        member = self._create_sample_member("Dewi Sartika")

        aliases = [
            f"/admin/members/{member['id']}/qr",
            f"/admin/anggota/{member['id']}/qr",
            f"/admin/members/{member['id']}/reissue-qr",
            f"/admin/anggota/{member['id']}/terbitkan-ulang-qr",
            f"/admin/members/{member['id']}/revoke-qr",
            f"/admin/anggota/{member['id']}/cabut-qr",
        ]
        for url in aliases:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"Gagal mengakses URL alias: {url}")
            self.assertIn(member["id"], resp.data.decode("utf-8"))

    def test_03_authenticated_admin_get_json_metadata(self):
        """Permintaan GET dengan header JSON mengembalikan representasi metadata anggota dan token QR."""
        self._login_admin()
        member = self._create_sample_member("Rian Hidayat")

        resp = self.client.get(
            f"/admin/members/{member['id']}/qr",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("member_id"), member["id"])
        self.assertEqual(data.get("qr_version"), 1)
        self.assertIn("token", data)
        self.assertTrue(data["token"].startswith(f"{member['id']}:1:"))
        self.assertIn("<svg", data.get("qr_svg", ""))
        self.assertIn("audits", data)

    def test_04_unauthenticated_user_redirected_to_login(self):
        """Pengguna tanpa autentikasi ditolak dan dialihkan ke login (HTTP 302)."""
        member = self._create_sample_member("Farhan Pratama")

        # GET
        resp_get = self.client.get(f"/admin/members/{member['id']}/qr")
        self.assertEqual(resp_get.status_code, 302)
        self.assertIn("/login", resp_get.headers.get("Location", ""))

        # POST
        with self.client.session_transaction() as sess:
            sess["logged_in"] = False
            sess["_csrf_token"] = "valid_csrf_for_unauth_test"

        resp_post = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": "Kartu fisik hilang dilaporkan oleh wali kelas", "csrf_token": "valid_csrf_for_unauth_test"},
        )
        self.assertEqual(resp_post.status_code, 302)
        self.assertIn("/login", resp_post.headers.get("Location", ""))

    def test_05_unauthenticated_api_returns_401(self):
        """Permintaan API tanpa autentikasi admin mengembalikan 401 Unauthorized."""
        member = self._create_sample_member("Lina Permata")

        resp = self.client.get(
            f"/admin/members/{member['id']}/qr",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 401)
        data = json.loads(resp.data.decode("utf-8"))
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_06_non_admin_role_rejected(self):
        """Pengguna yang bukan admin (misal role siswa/anggota) ditolak aksesnya."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = "siswa"
            sess["username"] = "siswa_andi"
            sess["_csrf_token"] = "csrf_token_siswa"

        member = self._create_sample_member("Andi Wijaya")
        resp = self.client.get(f"/admin/members/{member['id']}/qr")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_07_post_without_csrf_token_rejected_400(self):
        """Permintaan POST tanpa CSRF token yang valid ditolak dengan HTTP 400."""
        self._login_admin()
        member = self._create_sample_member("Eko Prasetyo")

        resp = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": "Kartu anggota hilang di ruang kelas X"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_08_non_existent_member_returns_404(self):
        """ID anggota yang tidak terdaftar menghasilkan HTTP 404 Not Found."""
        csrf_token = self._login_admin()

        resp_get = self.client.get("/admin/members/M-999999/qr")
        self.assertEqual(resp_get.status_code, 404)

        resp_post = self.client.post(
            "/admin/members/M-999999/reissue-qr",
            data={"reason": "Kartu fisik hilang dilaporkan oleh wali kelas", "csrf_token": csrf_token},
        )
        self.assertEqual(resp_post.status_code, 404)

    def test_09_empty_or_whitespace_reason_rejected_400(self):
        """Alasan kosong, whitespace saja, atau string kosong wajib ditolak (HTTP 400)."""
        csrf_token = self._login_admin()
        member = self._create_sample_member("Maya Indah")

        for bad_reason in ["", "   ", "\t\n  "]:
            resp = self.client.post(
                f"/admin/members/{member['id']}/reissue-qr",
                data={"reason": bad_reason, "csrf_token": csrf_token},
            )
            self.assertEqual(resp.status_code, 400, f"Alasan '{bad_reason}' seharusnya ditolak.")

    def test_10_reason_length_bounds_rejected_400(self):
        """Alasan yang terlalu pendek (< 5 karakter) atau terlalu panjang (> 500 karakter) ditolak."""
        csrf_token = self._login_admin()
        member = self._create_sample_member("Hendra Gunawan")

        # Terlalu pendek (< 5 karakter)
        resp_short = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": "hlg", "csrf_token": csrf_token},
        )
        self.assertEqual(resp_short.status_code, 400)
        self.assertIn("minimal", resp_short.data.decode("utf-8").lower())

        # Terlalu panjang (> 500 karakter)
        long_reason = "Alasan kartu hilang yang sangat panjang " * 15  # ~600 karakter
        self.assertGreater(len(long_reason), MAX_MEMBER_QR_REISSUE_REASON_LENGTH)
        resp_long = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": long_reason, "csrf_token": csrf_token},
        )
        self.assertEqual(resp_long.status_code, 400)
        self.assertIn("maksimal", resp_long.data.decode("utf-8").lower())

    def test_11_reissue_success_increments_qr_version_by_one(self):
        """Penerbitan ulang menaikkan qr_version tepat +1 dari nilai sebelumnya."""
        csrf_token = self._login_admin()
        member = self._create_sample_member("Taufik Hidayat")

        # Versi awal = 1
        self.assertEqual(member.get("qr_version", 1), 1)

        # Penerbitan ulang pertama: 1 -> 2
        resp1 = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": "Kartu fisik pertama hilang dilaporkan siswa", "csrf_token": csrf_token},
            follow_redirects=True,
        )
        self.assertEqual(resp1.status_code, 200)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        updated_member1 = member_repo.get_member_by_id(conn, member["id"])
        self.assertEqual(updated_member1["qr_version"], 2)

        # Penerbitan ulang kedua: 2 -> 3
        resp2 = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": "Kartu kedua patah saat disimpan di saku", "csrf_token": csrf_token},
            follow_redirects=True,
        )
        self.assertEqual(resp2.status_code, 200)

        updated_member2 = member_repo.get_member_by_id(conn, member["id"])
        self.assertEqual(updated_member2["qr_version"], 3)
        conn.close()

    def test_12_old_token_rejected_after_reissue(self):
        """Token QR lama otomatis ditolak setelah qr_version bertambah di database (LIB-QR-001)."""
        member = self._create_sample_member("Nadia Vega")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        # Buat token versi 1
        token_v1 = generate_member_qr_token(member["id"], qr_version=1, secret_key=self.secret_key)

        # Validasi sebelum penerbitan ulang: token_v1 valid
        verified_before = verify_member_qr_token(conn, token_v1, secret_key=self.secret_key)
        self.assertEqual(verified_before["qr_version"], 1)

        # Terbitkan ulang QR (v1 -> v2)
        reissue_result = reissue_member_qr(
            conn=conn,
            member_id=member["id"],
            reason="Kartu fisik hilang dilaporkan oleh wali kelas",
            actor="admin_perpus",
            secret_key=self.secret_key,
        )
        self.assertEqual(reissue_result["new_qr_version"], 2)

        # Token lama (v1) sekarang HARUS ditolak dengan MemberTokenRevokedError
        with self.assertRaises(MemberTokenRevokedError) as ctx:
            verify_member_qr_token(conn, token_v1, secret_key=self.secret_key)
        self.assertIn("tidak berlaku", str(ctx.exception).lower())

        # Pemeriksaan via validate_member_token (wrapper kiosk/API)
        res_v1 = validate_member_token(token=token_v1, conn=conn, secret_key=self.secret_key)
        self.assertFalse(res_v1["valid"])
        self.assertEqual(res_v1["code"], "TOKEN_REVOKED")

        conn.close()

    def test_13_new_token_valid_after_reissue(self):
        """Token QR baru bertanda tangan sah dan dapat diverifikasi penuh di database."""
        member = self._create_sample_member("Dian Pelangi")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        reissue_result = reissue_member_qr(
            conn=conn,
            member_id=member["id"],
            reason="Kartu fisik lama rusak terkena air",
            actor="admin_perpus",
            secret_key=self.secret_key,
        )
        token_v2 = reissue_result["token"]

        # Verifikasi token v2 berhasil
        verified = verify_member_qr_token(conn, token_v2, secret_key=self.secret_key)
        self.assertEqual(verified["id"], member["id"])
        self.assertEqual(verified["qr_version"], 2)
        self.assertEqual(verified["status"], "aktif")

        # Pemeriksaan via validate_member_token (kiosk)
        res_v2 = validate_member_token(token=token_v2, conn=conn, secret_key=self.secret_key)
        self.assertTrue(res_v2["valid"])
        self.assertEqual(res_v2["code"], "OK")
        self.assertEqual(res_v2["qr_version"], 2)

        conn.close()

    def test_14_member_id_and_identity_strictly_preserved(self):
        """ID anggota, nama, kategori, tanggal pembuatan, dan status tidak termutasi."""
        member = self._create_sample_member("Rizky Ramadhan", category_id="MC-MURID", status="aktif")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        reissue_member_qr(
            conn=conn,
            member_id=member["id"],
            reason="Penggantian kartu fisik hilang semester baru",
            actor="admin_perpus",
            secret_key=self.secret_key,
        )

        member_after = member_repo.get_member_by_id(conn, member["id"])
        self.assertEqual(member_after["id"], member["id"])
        self.assertEqual(member_after["nama"], "Rizky Ramadhan")
        self.assertEqual(member_after["category_id"], "MC-MURID")
        self.assertEqual(member_after["status"], "aktif")
        self.assertEqual(member_after["created_at"], member["created_at"])
        self.assertEqual(member_after["qr_version"], 2)

        conn.close()

    def test_15_audit_log_created_with_full_details(self):
        """Penerbitan ulang mencatat log audit terstruktur tanpa kebocoran secret atau token."""
        member = self._create_sample_member("Citra Kirana")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        reason_text = "Kartu hilang dilaporkan oleh wali kelas X-RPL-1"
        res = reissue_member_qr(
            conn=conn,
            member_id=member["id"],
            reason=reason_text,
            actor="petugas_audit",
            secret_key=self.secret_key,
        )

        audits = audit_repo.list_by_object(conn, "members", member["id"])
        reissue_audits = [a for a in audits if a["action"] == "MEMBER_QR_REISSUE"]
        self.assertEqual(len(reissue_audits), 1)
        audit_entry = reissue_audits[0]

        self.assertEqual(audit_entry["actor"], "petugas_audit")
        self.assertEqual(audit_entry["action"], "MEMBER_QR_REISSUE")
        self.assertEqual(audit_entry["object_id"], member["id"])
        self.assertEqual(audit_entry["reason"], reason_text)

        # Pemeriksaan detail_json
        detail = audit_entry.get("detail_json")
        if isinstance(detail, str):
            detail = json.loads(detail)
        self.assertEqual(detail["old_qr_version"], 1)
        self.assertEqual(detail["new_qr_version"], 2)
        self.assertEqual(detail["nama"], "Citra Kirana")

        # Verifikasi ZERO secret & token leak di detail_json
        detail_str = str(detail).lower()
        self.assertNotIn(self.secret_key.lower(), detail_str)
        self.assertNotIn("secret", detail_str)

        conn.close()

    def test_16_atomic_rollback_if_audit_fails(self):
        """Jika penulisan audit_log gagal, kenaikan qr_version di-rollback 100% (atomik)."""
        member = self._create_sample_member("Galih Pratama")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        token_v1 = generate_member_qr_token(member["id"], qr_version=1, secret_key=self.secret_key)

        # Mock audit_repo.record_audit agar melempar error
        with patch("repositories.audit_repo.record_audit", side_effect=sqlite3.OperationalError("Simulasi disk I/O error pada audit_log")):
            with self.assertRaises(sqlite3.OperationalError):
                reissue_member_qr(
                    conn=conn,
                    member_id=member["id"],
                    reason="Kartu hilang dilaporkan siswa",
                    actor="admin_perpus",
                    secret_key=self.secret_key,
                )

        # Periksa database: qr_version HARUS tetap 1
        m_current = member_repo.get_member_by_id(conn, member["id"])
        self.assertEqual(m_current["qr_version"], 1)

        # Token v1 HARUS tetap valid karena transaksi dibatalkan (rollback)
        verified = verify_member_qr_token(conn, token_v1, secret_key=self.secret_key)
        self.assertEqual(verified["qr_version"], 1)

        conn.close()

    def test_17_no_hard_delete_total_member_count_strictly_preserved(self):
        """Jumlah total anggota di database tetap utuh (tanpa hard delete per DEC-020)."""
        member1 = self._create_sample_member("Anggota Satu")
        member2 = self._create_sample_member("Anggota Dua")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        count_before = conn.execute("SELECT COUNT(*) as cnt FROM members;").fetchone()["cnt"]

        # Reissue berkali-kali
        reissue_member_qr(conn, member1["id"], "Alasan reissue 1", "admin", self.secret_key)
        reissue_member_qr(conn, member2["id"], "Alasan reissue 2", "admin", self.secret_key)
        reissue_member_qr(conn, member1["id"], "Alasan reissue 3", "admin", self.secret_key)

        count_after = conn.execute("SELECT COUNT(*) as cnt FROM members;").fetchone()["cnt"]
        self.assertEqual(count_before, count_after)
        conn.close()

    def test_18_inactive_member_can_be_reissued_without_auto_activating(self):
        """Anggota nonaktif dapat diterbitkan ulang QR-nya; statusnya TETAP nonaktif."""
        member = self._create_sample_member("Siswa Tidak Aktif", status="nonaktif")
        self.assertEqual(member["status"], "nonaktif")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        res = reissue_member_qr(
            conn=conn,
            member_id=member["id"],
            reason="Penerbitan ulang kartu sebelum aktifasi kembali",
            actor="admin",
            secret_key=self.secret_key,
        )
        self.assertEqual(res["new_qr_version"], 2)
        self.assertEqual(res["status"], "nonaktif")

        # Cek database
        m_db = member_repo.get_member_by_id(conn, member["id"])
        self.assertEqual(m_db["status"], "nonaktif")
        self.assertEqual(m_db["qr_version"], 2)

        # Token baru valid secara kriptografis & versi, tapi saat check_active=True melempar MemberInactiveError
        token_v2 = res["token"]
        with self.assertRaises(MemberInactiveError):
            verify_member_qr_token(conn, token_v2, secret_key=self.secret_key, check_active=True)

        # Namun jika check_active=False, identitas berhasil diverifikasi
        verified_ident = verify_member_qr_token(conn, token_v2, secret_key=self.secret_key, check_active=False)
        self.assertEqual(verified_ident["qr_version"], 2)

        conn.close()

    def test_19_active_loans_remain_intact_when_qr_reissued(self):
        """Pinjaman aktif tidak dibatalkan atau terganggu saat kartu QR diterbitkan ulang."""
        member = self._create_sample_member("Peminjam Buku")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        # Buat buku dan eksemplar
        title_res = create_title_with_copies(
            conn,
            title_data={"judul": "Fisika Dasar Terapan", "pengarang": "Tim Fisika", "kategori": "Sains"},
            initial_copies=1,
        )
        copy_id = title_res["copy_ids"][0]
        conn.commit()

        # Pinjam buku
        borrow_res = borrow_copies(conn, member_id=member["id"], copy_ids=[copy_id])
        conn.commit()

        # Reissue QR anggota
        reissue_res = reissue_member_qr(
            conn=conn,
            member_id=member["id"],
            reason="Kartu fisik lama hilang di perpustakaan",
            actor="admin",
            secret_key=self.secret_key,
        )
        self.assertEqual(reissue_res["new_qr_version"], 2)

        # Verifikasi item peminjaman tetap aktif dan belum kembali
        active_item = conn.execute(
            "SELECT * FROM loan_items WHERE copy_id = ? AND returned_at IS NULL;",
            (copy_id,)
        ).fetchone()
        self.assertIsNotNone(active_item, "Pinjaman aktif tidak boleh dihapus atau dibatalkan!")

        # Eksemplar tetap dapat dikembalikan secara normal
        return_res = return_copies(conn, copy_ids=[copy_id])
        conn.commit()
        self.assertIsInstance(return_res, list)
        self.assertEqual(len(return_res), 1)

        conn.close()

    def test_20_zero_write_on_get_request(self):
        """Permintaan GET ke rute QR atau reissue tidak melakukan mutasi database apa pun."""
        self._login_admin()
        member = self._create_sample_member("Pengguna Uji Zero Write")

        # Snapshot checksum database sebelum GET
        with open(self.test_db, "rb") as f:
            hash_before = hashlib.sha256(f.read()).hexdigest()

        resp1 = self.client.get(f"/admin/members/{member['id']}/qr")
        self.assertEqual(resp1.status_code, 200)

        resp2 = self.client.get(f"/admin/members/{member['id']}/reissue-qr")
        self.assertEqual(resp2.status_code, 200)

        with open(self.test_db, "rb") as f:
            hash_after = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(hash_before, hash_after, "Permintaan GET memutasi database!")

    def test_21_repeated_and_concurrent_reissue_consistency(self):
        """Penerbitan ulang berurutan secara konsisten menaikkan versi QR tanpa lompatan salah."""
        member = self._create_sample_member("Uji Konkurensi")
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        for expected_ver in range(2, 6):
            res = reissue_member_qr(
                conn=conn,
                member_id=member["id"],
                reason=f"Penerbitan ulang kartu tahap {expected_ver}",
                actor="admin",
                secret_key=self.secret_key,
            )
            self.assertEqual(res["new_qr_version"], expected_ver)
            m_db = member_repo.get_member_by_id(conn, member["id"])
            self.assertEqual(m_db["qr_version"], expected_ver)

        conn.close()

    def test_22_legacy_p1_schema_fallback(self):
        """Pada skema legacy P1 (tanpa tabel members), rute QR menangani gracefully tanpa unhandled crash."""
        legacy_db = os.path.join(self.test_dir, "test_legacy_p1.db")
        conn = sqlite3.connect(legacy_db)
        conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT);")
        conn.execute("CREATE TABLE peminjaman (id INTEGER PRIMARY KEY, status TEXT);")
        conn.commit()
        conn.close()

        with patch.dict(os.environ, {"DATABASE_NAME": legacy_db}):
            self._login_admin()
            resp = self.client.get("/admin/members/M-XXXXXX/qr", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/koleksi", resp.headers.get("Location", ""))

            # API request
            resp_api = self.client.get("/admin/members/M-XXXXXX/qr", headers={"Accept": "application/json"})
            self.assertEqual(resp_api.status_code, 400)
            data = json.loads(resp_api.data.decode("utf-8"))
            self.assertIn("v2", data.get("message", "").lower())

    def test_23_no_delete_button_or_action_in_rendered_html(self):
        """Pemeriksaan kepatuhan ketat DEC-020: TIDAK ADA tombol hapus atau form delete di HTML."""
        self._login_admin()
        member = self._create_sample_member("Uji Tanpa Tombol Hapus")

        resp = self.client.get(f"/admin/members/{member['id']}/qr")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8").lower()

        # Dilarang ada tombol/form hapus anggota
        self.assertNotIn("hapus anggota", html)
        self.assertNotIn("delete member", html)
        self.assertNotIn("btn-danger", html)
        self.assertNotIn("method=\"delete\"", html)

    def test_24_secret_key_not_exposed_in_html_or_json(self):
        """Secret key aplikasi TIDAK PERNAH dibocorkan dalam HTML atau JSON respon."""
        self._login_admin()
        member = self._create_sample_member("Uji Rahasia Kunci")

        # GET HTML
        resp_html = self.client.get(f"/admin/members/{member['id']}/qr")
        self.assertNotIn(self.secret_key, resp_html.data.decode("utf-8"))

        # GET JSON
        resp_json = self.client.get(f"/admin/members/{member['id']}/qr", headers={"Accept": "application/json"})
        self.assertNotIn(self.secret_key, resp_json.data.decode("utf-8"))

        # POST JSON
        csrf = "valid_csrf_for_secret_check"
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = "admin"
            sess["_csrf_token"] = csrf

        resp_post = self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            headers={"Accept": "application/json", "X-CSRF-Token": csrf},
            json={"reason": "Penggantian kartu baru oleh petugas", "csrf_token": csrf},
        )
        self.assertEqual(resp_post.status_code, 200)
        self.assertNotIn(self.secret_key, resp_post.data.decode("utf-8"))

    def test_25_admin_members_view_displays_updated_qr_version(self):
        """Halaman daftar anggota /admin/members menampilkan versi QR terbaru setelah reissue."""
        csrf = self._login_admin()
        member = self._create_sample_member("Zaskia Adya")

        # Sebelum reissue: v1
        resp_before = self.client.get("/admin/members")
        self.assertIn("v1", resp_before.data.decode("utf-8"))

        # Eksekusi reissue via POST
        self.client.post(
            f"/admin/members/{member['id']}/reissue-qr",
            data={"reason": "Penggantian kartu fisik hilang tahun ajaran baru", "csrf_token": csrf},
            follow_redirects=True,
        )

        # Setelah reissue: v2
        resp_after = self.client.get("/admin/members")
        self.assertIn("v2", resp_after.data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
