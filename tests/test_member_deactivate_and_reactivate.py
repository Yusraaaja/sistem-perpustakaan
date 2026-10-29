# -*- coding: utf-8 -*-
"""
Rangkaian Pengujian Unit, Keamanan, Integrasi, dan Regresi untuk Task 4-06:
Nonaktifkan dan Aktifkan Kembali Anggota (DEC-020 & DEC-023).
Sistem Perpustakaan Digital Sekolah.
"""
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
    MIN_MEMBER_STATUS_REASON_LENGTH,
    MAX_MEMBER_STATUS_REASON_LENGTH,
    OFFICIAL_MEMBER_STATUSES,
)
from repositories import member_repo, audit_repo
from services import (
    register_member,
    set_member_status,
    deactivate_member,
    reactivate_member,
    get_member_audit_history,
    borrow_copies,
    return_copies,
    create_title_with_copies,
    generate_member_qr_token,
    verify_member_qr_token,
)
from services.exceptions import (
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
    InvalidOperationError,
)


class TestMemberDeactivateAndReactivate(unittest.TestCase):
    """Pengujian menyeluruh Task 4-06: Nonaktifkan dan Aktifkan Kembali Anggota."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_member_status.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        os.environ["SECRET_KEY"] = "test-secret-key-for-task-4-06-deactivate-reactivate-suite"

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
            sess["_csrf_token"] = "valid_csrf_token_for_test_4_06"
        return "valid_csrf_token_for_test_4_06"

    def _create_sample_member(self, nama="Ahmad Fauzi", category_id="MC-MURID", status="aktif"):
        """Helper untuk membuat satu rekaman anggota baru."""
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            m = register_member(conn, nama=nama, category_id=category_id, status=status)
            conn.commit()
            return m
        finally:
            conn.close()

    # ==========================================================================
    # 1. PENGUJIAN ROUTE & KONTROL AKSES (KEAMANAN & GET READ-ONLY)
    # ==========================================================================

    def test_01_authenticated_admin_can_access_status_page_html(self):
        """Admin terautentikasi dapat membuka halaman kelola status anggota secara HTML (GET)."""
        csrf = self._login_admin()
        member = self._create_sample_member(nama="Budi Santoso")

        resp = self.client.get(f"/admin/members/{member['id']}/status")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Budi Santoso", html)
        self.assertIn(member["id"], html)
        self.assertIn("Kelola Status & Riwayat Anggota", html)
        self.assertIn("Nonaktifkan Anggota", html)
        self.assertIn(csrf, html)

    def test_02_authenticated_admin_can_access_alias_urls(self):
        """Admin dapat mengakses seluruh route alias resmi (Indonesia / Inggris)."""
        self._login_admin()
        member = self._create_sample_member(nama="Dewi Sartika")

        for url in [
            f"/admin/anggota/{member['id']}/status",
            f"/admin/members/{member['id']}/deactivate",
            f"/admin/anggota/{member['id']}/nonaktifkan",
            f"/admin/members/{member['id']}/activate",
            f"/admin/anggota/{member['id']}/aktifkan",
        ]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"Gagal mengakses alias {url}")
            html = resp.get_data(as_text=True)
            self.assertIn("Dewi Sartika", html)

    def test_03_authenticated_admin_get_json_metadata(self):
        """Permintaan GET dengan header JSON mengembalikan representasi metadata anggota dan riwayat audit."""
        self._login_admin()
        member = self._create_sample_member(nama="Hendra Kurniawan")

        resp = self.client.get(
            f"/admin/members/{member['id']}/status",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["member"]["id"], member["id"])
        self.assertEqual(data["member"]["status"], "aktif")
        self.assertIn("active_loans", data)
        self.assertIn("audit_history", data)
        self.assertEqual(data["suggested_target_status"], "nonaktif")

    def test_04_unauthenticated_user_redirected_to_login(self):
        """Pengguna tanpa autentikasi ditolak dan dialihkan ke login (HTTP 302)."""
        member = self._create_sample_member(nama="Rahasia Negara")

        # GET
        resp_get = self.client.get(f"/admin/members/{member['id']}/status")
        self.assertEqual(resp_get.status_code, 302)
        self.assertIn("/login", resp_get.headers.get("Location", ""))

        # POST
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "valid_csrf_for_unauth_test"
            sess["logged_in"] = False
        resp_post = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={"reason": "Penonaktifan tanpa login", "csrf_token": "valid_csrf_for_unauth_test"}
        )
        self.assertEqual(resp_post.status_code, 302)
        self.assertIn("/login", resp_post.headers.get("Location", ""))

    def test_05_unauthenticated_api_returns_401(self):
        """Permintaan API tanpa autentikasi admin mengembalikan 401 Unauthorized."""
        member = self._create_sample_member(nama="Rahasia API")

        resp = self.client.get(
            f"/admin/members/{member['id']}/status",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_06_non_admin_role_rejected(self):
        """Pengguna yang bukan admin (misal role siswa/anggota) ditolak aksesnya."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = "siswa"
            sess["username"] = "siswa_1"

        member = self._create_sample_member(nama="Target Siswa")
        resp = self.client.get(f"/admin/members/{member['id']}/status")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_07_post_without_csrf_token_rejected_400(self):
        """Permintaan POST tanpa CSRF token yang valid ditolak dengan HTTP 400."""
        self._login_admin()
        member = self._create_sample_member(nama="Korban CSRF")

        # Tanpa CSRF sama sekali
        resp = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={"reason": "Alasan penonaktifan tanpa csrf", "target_status": "nonaktif"}
        )
        self.assertEqual(resp.status_code, 400)

        # Dengan CSRF palsu
        resp_bad = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={"reason": "Alasan penonaktifan", "csrf_token": "invalid_fake_token"}
        )
        self.assertEqual(resp_bad.status_code, 400)

    def test_08_non_existent_member_returns_404(self):
        """ID anggota yang tidak terdaftar menghasilkan HTTP 404 Not Found."""
        csrf = self._login_admin()

        resp_get = self.client.get("/admin/members/M-ZZZZZZ/status")
        self.assertEqual(resp_get.status_code, 404)

        resp_post = self.client.post(
            "/admin/members/M-ZZZZZZ/status",
            data={"reason": "Alasan penonaktifan", "csrf_token": csrf}
        )
        self.assertEqual(resp_post.status_code, 404)

    # ==========================================================================
    # 2. VALIDASI BISNIS: ALASAN, STATUS TARGET, & IDEMPOTENSI
    # ==========================================================================

    def test_09_empty_or_whitespace_reason_rejected_400(self):
        """Alasan kosong, whitespace saja, atau string kosong wajib ditolak (HTTP 400)."""
        csrf = self._login_admin()
        member = self._create_sample_member(nama="Uji Alasan Kosong")

        for bad_reason in ["", "   ", "\t\n  \t"]:
            resp = self.client.post(
                f"/admin/members/{member['id']}/status",
                data={"reason": bad_reason, "csrf_token": csrf, "target_status": "nonaktif"}
            )
            self.assertEqual(resp.status_code, 400)
            html = resp.get_data(as_text=True)
            self.assertIn("Alasan perubahan status anggota wajib diisi", html)

    def test_10_reason_length_bounds_rejected_400(self):
        """Alasan yang terlalu pendek (< 5 karakter) atau terlalu panjang (> 500 karakter) ditolak."""
        csrf = self._login_admin()
        member = self._create_sample_member(nama="Uji Batas Alasan")

        # Terlalu pendek (< 5 karakter)
        resp_short = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={"reason": "pend", "csrf_token": csrf, "target_status": "nonaktif"}
        )
        self.assertEqual(resp_short.status_code, 400)
        self.assertIn("minimal 5 karakter", resp_short.get_data(as_text=True))

        # Terlalu panjang (> 500 karakter)
        too_long = "X" * 501
        resp_long = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={"reason": too_long, "csrf_token": csrf, "target_status": "nonaktif"}
        )
        self.assertEqual(resp_long.status_code, 400)
        self.assertIn("maksimal 500 karakter", resp_long.get_data(as_text=True))

    def test_11_invalid_target_status_rejected_400(self):
        """Status target yang tidak sah (misal 'dihapus', 'banned', 'pending') ditolak keras."""
        csrf = self._login_admin()
        member = self._create_sample_member(nama="Uji Status Liar")

        for invalid_st in ["dihapus", "banned", "pending", "hapus_permanen", ""]:
            resp = self.client.post(
                f"/admin/members/{member['id']}/status",
                data={"reason": "Alasan pengujian status", "csrf_token": csrf, "target_status": invalid_st}
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("tidak valid", resp.get_data(as_text=True))

    # ==========================================================================
    # 3. PENONAKTIFAN & PENGAKTIFAN KEMBALI (MUTASI BERHASIL)
    # ==========================================================================

    def test_12_deactivate_success_updates_status_in_db(self):
        """Anggota aktif berhasil dinonaktifkan dengan alasan yang sah."""
        csrf = self._login_admin(username="petugas_perpustakaan")
        member = self._create_sample_member(nama="Citra Lestari", status="aktif")

        resp = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={
                "reason": "Siswa telah lulus tahun ajaran 2026",
                "csrf_token": csrf,
                "target_status": "nonaktif",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("berhasil dinonaktifkan", html)
        self.assertIn("Siswa telah lulus tahun ajaran 2026", html)

        # Verifikasi langsung ke database
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            m_db = member_repo.get_member_by_id(conn, member["id"])
            self.assertIsNotNone(m_db)
            self.assertEqual(m_db["status"], "nonaktif")
        finally:
            conn.close()

    def test_13_reactivate_success_updates_status_in_db(self):
        """Anggota nonaktif berhasil diaktifkan kembali dengan alasan yang sah."""
        csrf = self._login_admin(username="kepala_perpustakaan")
        member = self._create_sample_member(nama="Eko Prasetyo", status="nonaktif")

        resp = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={
                "reason": "Siswa telah menyelesaikan masa cuti dan aktif kembali",
                "csrf_token": csrf,
                "target_status": "aktif",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("berhasil diaktifkan kembali", html)

        # Verifikasi langsung ke database
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            m_db = member_repo.get_member_by_id(conn, member["id"])
            self.assertIsNotNone(m_db)
            self.assertEqual(m_db["status"], "aktif")
        finally:
            conn.close()

    def test_14_resubmission_or_repeated_deactivation_rejected_idempotent(self):
        """Percobaan menonaktifkan anggota yang sudah nonaktif ditolak (mencegah audit duplikat palsu)."""
        csrf = self._login_admin()
        member = self._create_sample_member(nama="Fandi Ahmad", status="nonaktif")

        resp = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={
                "reason": "Mencoba menonaktifkan lagi",
                "csrf_token": csrf,
                "target_status": "nonaktif",
            }
        )
        self.assertEqual(resp.status_code, 400)
        html = resp.get_data(as_text=True)
        self.assertIn("sudah berstatus &#39;nonaktif&#39;", html)

    def test_15_resubmission_or_repeated_reactivation_rejected_idempotent(self):
        """Percobaan mengaktifkan anggota yang sudah aktif ditolak."""
        csrf = self._login_admin()
        member = self._create_sample_member(nama="Gita Gutawa", status="aktif")

        resp = self.client.post(
            f"/admin/members/{member['id']}/status",
            data={
                "reason": "Mencoba mengaktifkan lagi",
                "csrf_token": csrf,
                "target_status": "aktif",
            }
        )
        self.assertEqual(resp.status_code, 400)
        html = resp.get_data(as_text=True)
        self.assertIn("sudah berstatus &#39;aktif&#39;", html)

    # ==========================================================================
    # 4. INTEGRITAS AUDIT LOG & ATOMISITAS TRANSAKSI
    # ==========================================================================

    def test_16_audit_log_created_with_full_details(self):
        """Perubahan status menghasilkan catatan audit log lengkap sesuai skema resmi."""
        self._login_admin(username="petugas_audit")
        member = self._create_sample_member(nama="Hadi Santoso", status="aktif")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            result = set_member_status(
                conn=conn,
                member_id=member["id"],
                target_status="nonaktif",
                reason="Pindah domisili ke luar kota",
                actor="petugas_audit"
            )
            conn.commit()

            self.assertTrue(result["ok"])
            self.assertEqual(result["previous_status"], "aktif")
            self.assertEqual(result["new_status"], "nonaktif")
            self.assertEqual(result["reason"], "Pindah domisili ke luar kota")
            self.assertEqual(result["actor"], "petugas_audit")

            # Periksa tabel audit_log
            audit = audit_repo.get_by_id(conn, result["audit_id"])
            self.assertIsNotNone(audit)
            self.assertEqual(audit["actor"], "petugas_audit")
            self.assertEqual(audit["action"], "MEMBER_DEACTIVATE")
            self.assertEqual(audit["object_type"], "members")
            self.assertEqual(audit["object_id"], member["id"])
            self.assertEqual(audit["reason"], "Pindah domisili ke luar kota")

            detail = json.loads(audit["detail_json"])
            self.assertEqual(detail["previous_status"], "aktif")
            self.assertEqual(detail["new_status"], "nonaktif")
            self.assertEqual(detail["nama"], "Hadi Santoso")

            # Riwayat audit anggota
            history = get_member_audit_history(conn, member["id"])
            self.assertGreaterEqual(len(history), 2)  # Termasuk MEMBER_REGISTER
            actions = [h["action"] for h in history]
            self.assertIn("MEMBER_DEACTIVATE", actions)
            self.assertIn("MEMBER_REGISTER", actions)
        finally:
            conn.close()

    def test_17_atomic_rollback_if_audit_fails(self):
        """Jika penulisan audit log gagal di tengah jalan, perubahan status di-rollback 100%."""
        member = self._create_sample_member(nama="Uji Rollback Status", status="aktif")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            # Mock audit_repo.record_audit untuk melempar exception sengaja
            with patch("repositories.audit_repo.record_audit", side_effect=sqlite3.OperationalError("Simulasi disk penuh")):
                with self.assertRaises(sqlite3.OperationalError):
                    set_member_status(
                        conn=conn,
                        member_id=member["id"],
                        target_status="nonaktif",
                        reason="Alasan yang seharusnya di-rollback",
                        actor="admin"
                    )

            # Verifikasi status anggota TIDAK BERUBAH (tetap 'aktif')
            m_db = member_repo.get_member_by_id(conn, member["id"])
            self.assertEqual(m_db["status"], "aktif", "Status anggota seharusnya tetap aktif karena transaksi di-rollback!")
        finally:
            conn.close()

    def test_18_no_hard_delete_total_member_count_strictly_preserved(self):
        """Memverifikasi bahwa penonaktifan tidak melakukan hard delete (jumlah baris tetap utuh per DEC-020)."""
        member = self._create_sample_member(nama="Indra Sjafri", status="aktif")

        conn = sqlite3.connect(self.test_db)
        try:
            count_before = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]

            deactivate_member(conn, member["id"], reason="Nonaktifkan tanpa hapus fisik")
            conn.commit()

            count_after = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
            self.assertEqual(count_before, count_after, "Jumlah baris anggota berkurang! Hard delete dilarang!")
        finally:
            conn.close()

    # ==========================================================================
    # 5. INTEGRASI PEMINJAMAN, SIRKULASI, & QR TOKEN
    # ==========================================================================

    def test_19_inactive_member_cannot_borrow_books(self):
        """Anggota nonaktif tidak dapat memulai transaksi peminjaman baru (DEC-020)."""
        member = self._create_sample_member(nama="Joko Kendil", status="aktif")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            # Buat buku contoh
            title = create_title_with_copies(conn, title_data={"judul": "Pemrograman Python", "penulis": "Guido"}, initial_copies=2)
            conn.commit()
            copy_id = title["copy_ids"][0]

            # Nonaktifkan anggota
            deactivate_member(conn, member["id"], reason="Akun dinonaktifkan sementara")
            conn.commit()

            # Percobaan meminjam buku harus melempar MemberInactiveError
            with self.assertRaises(MemberInactiveError) as ctx:
                borrow_copies(conn, member_id=member["id"], copy_ids=[copy_id])

            self.assertIn("berstatus nonaktif", str(ctx.exception))
        finally:
            conn.close()

    def test_20_active_loans_remain_intact_and_can_be_returned_when_member_deactivated(self):
        """
        Anggota yang memiliki pinjaman aktif dapat dinonaktifkan tanpa membatalkan/menghapus
        transaksi peminjaman yang ada, dan buku tetap dapat dikembalikan (DEC-020).
        """
        member = self._create_sample_member(nama="Kartika Sari", status="aktif")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            # 1. Peminjaman saat anggota masih aktif
            title = create_title_with_copies(conn, title_data={"judul": "Fisika Modern", "penulis": "Einstein"}, initial_copies=1)
            copy_id = title["copy_ids"][0]
            borrow_result = borrow_copies(conn, member_id=member["id"], copy_ids=[copy_id])
            conn.commit()

            # 2. Nonaktifkan anggota
            deactivate_member(conn, member["id"], reason="Lulus sekolah dengan tanggungan buku")
            conn.commit()

            # 3. Transaksi peminjaman tetap utuh dan aktif
            active_item = conn.execute(
                "SELECT * FROM loan_items WHERE copy_id = ? AND returned_at IS NULL;",
                (copy_id,)
            ).fetchone()
            self.assertIsNotNone(active_item, "Pinjaman aktif tidak boleh dihapus atau dibatalkan otomatis!")

            # 4. Pengembalian buku tetap berhasil dilakukan
            return_result = return_copies(conn, copy_ids=[copy_id])
            conn.commit()
            self.assertIsInstance(return_result, list)
            self.assertEqual(len(return_result), 1)
        finally:
            conn.close()

    def test_21_qr_token_verification_behavior_for_inactive_member(self):
        """
        Token QR anggota nonaktif tetap valid secara kriptografis & identitas,
        namun melempar MemberInactiveError jika opsi check_active=True diaktifkan.
        """
        member = self._create_sample_member(nama="Lukman Hakim", status="aktif")
        token = generate_member_qr_token(member_id=member["id"], qr_version=1)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            # Nonaktifkan anggota
            deactivate_member(conn, member["id"], reason="Penonaktifan kartu fisik")
            conn.commit()

            # 1. Verifikasi tanpa check_active: Sukses membaca identitas, status terbaca nonaktif
            data_no_check = verify_member_qr_token(conn, token, check_active=False)
            self.assertEqual(data_no_check["id"], member["id"])
            self.assertEqual(data_no_check["status"], "nonaktif")

            # 2. Verifikasi dengan check_active=True: Ditolak dengan MemberInactiveError
            with self.assertRaises(MemberInactiveError):
                verify_member_qr_token(conn, token, check_active=True)
        finally:
            conn.close()

    def test_22_search_and_admin_members_interface_reflects_updated_status(self):
        """Antarmuka daftar anggota /admin/members menampilkan status nonaktif dan mendukung filter status."""
        self._login_admin()
        member = self._create_sample_member(nama="Mega Mustika", status="aktif")

        # Nonaktifkan
        conn = sqlite3.connect(self.test_db)
        try:
            deactivate_member(conn, member["id"], reason="Status cuti akademik")
            conn.commit()
        finally:
            conn.close()

        # Akses filter status=nonaktif
        resp = self.client.get("/admin/members?status=nonaktif")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Mega Mustika", html)
        self.assertIn("Nonaktif", html)

    def test_23_zero_write_on_get_request(self):
        """Permintaan GET ke rute status tidak melakukan mutasi apa pun ke database (Zero-Write)."""
        self._login_admin()
        member = self._create_sample_member(nama="Nadia Vega")

        conn = sqlite3.connect(self.test_db)
        audit_count_before = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        member_before = conn.execute("SELECT * FROM members WHERE id = ?;", (member["id"],)).fetchone()
        conn.close()

        # Eksekusi GET
        resp = self.client.get(f"/admin/members/{member['id']}/status")
        self.assertEqual(resp.status_code, 200)

        conn = sqlite3.connect(self.test_db)
        audit_count_after = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        member_after = conn.execute("SELECT * FROM members WHERE id = ?;", (member["id"],)).fetchone()
        conn.close()

        self.assertEqual(audit_count_before, audit_count_after)
        self.assertEqual(member_before, member_after)

    def test_24_legacy_p1_schema_fallback(self):
        """Pada skema legacy P1 (tanpa tabel members), route status menangani gracefully tanpa unhandled crash."""
        self._login_admin()

        # Buat database sementara skema legacy (hanya buku dan peminjaman)
        legacy_db = os.path.join(self.test_dir, "legacy_p1.db")
        conn_legacy = sqlite3.connect(legacy_db)
        conn_legacy.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT);")
        conn_legacy.execute("CREATE TABLE peminjaman (id INTEGER PRIMARY KEY, status TEXT);")
        conn_legacy.commit()
        conn_legacy.close()

        with patch("app.get_db_connection", side_effect=lambda: sqlite3.connect(legacy_db)):
            # 1. HTML request dialihkan secara aman ke /koleksi
            resp = self.client.get("/admin/members/M-LEGACY/status", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/koleksi", resp.headers.get("Location", ""))

            # 2. JSON request mengembalikan 400 Not Supported
            resp_json = self.client.get("/admin/members/M-LEGACY/status", headers={"Accept": "application/json"})
            self.assertEqual(resp_json.status_code, 400)
            self.assertIn("Fitur anggota hanya didukung pada skema v2", resp_json.get_json()["message"])

    def test_25_no_delete_button_or_action_in_rendered_html(self):
        """
        Pemeriksaan kepatuhan ketat: TIDAK ADA tombol hapus, form hapus,
        maupun aksi DELETE pada halaman manajemen dan status anggota.
        """
        self._login_admin()
        member = self._create_sample_member(nama="Oki Setiana")

        for url in [
            "/admin/members",
            f"/admin/members/{member['id']}/status",
        ]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True).lower()

            # Pastikan tidak ada tombol atau kata aksi hapus anggota
            self.assertNotIn("hapus anggota", html)
            self.assertNotIn("delete_member", html)
            self.assertNotIn("btn-danger\">hapus", html)
            self.assertNotIn("action=\"/admin/members/delete", html)


if __name__ == "__main__":
    unittest.main()

