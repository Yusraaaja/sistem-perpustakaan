# -*- coding: utf-8 -*-
"""
Rangkaian Pengujian Unit dan Integrasi untuk Task 4-02:
Seed Kategori Anggota dan Antarmuka Admin Anggota (Daftar & Pencarian).
Sistem Perpustakaan Digital Sekolah.
"""
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

import app as library_app
from policy import OFFICIAL_MEMBER_CATEGORIES
from repositories import member_repo
from services import (
    seed_member_categories,
    get_all_categories,
    clean_member_search_query,
    search_members_admin,
    get_member_management_metrics,
    register_member,
    deactivate_member,
    generate_member_qr_token,
    verify_member_qr_token,
)


class TestAdminMembers(unittest.TestCase):
    """Pengujian komprehensif Task 4-02: Seeding kategori & antarmuka admin anggota."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_admin_members.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        os.environ["SECRET_KEY"] = "test-secret-key-for-admin-members-suite-2026"

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
        """Membuat struktur tabel v2 yang bersih dan terisolasi dari migrations/0001_initial_v2_schema.sql."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        migration_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations",
            "0001_initial_v2_schema.sql",
        )
        if os.path.exists(migration_file):
            with open(migration_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        conn.close()

    def _login_admin(self):
        """Helper login admin untuk test client."""
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess["logged_in"] = True
            sess["admin_username"] = library_app.ADMIN_USERNAME
            sess["user_role"] = "admin"
            sess["last_active"] = time.time()
            sess["_csrf_token"] = "valid-csrf-token-test"

    # --------------------------------------------------------------------------
    # 1. SEEDING KATEGORI & IDEMPOTENSI
    # --------------------------------------------------------------------------
    def test_01_seed_categories_creates_all_official_categories(self):
        """Memverifikasi bahwa seeding menghasilkan 5 kategori resmi proyek."""
        conn = library_app.get_db_connection()
        try:
            # Sebelum seed, kategori kosong
            self.assertEqual(len(member_repo.list_categories(conn)), 0)

            # Eksekusi seed
            cats = seed_member_categories(conn)
            self.assertEqual(len(cats), 5)

            cat_ids = {c["id"] for c in cats}
            expected_ids = {"MC-MURID", "MC-GURU-JUR", "MC-GURU-UMUM", "MC-STAF", "MC-TEKNISI"}
            self.assertEqual(cat_ids, expected_ids)

            # Cek detail setiap kategori
            murid = next(c for c in cats if c["id"] == "MC-MURID")
            self.assertEqual(murid["jenis"], "murid")
            self.assertIn("jurusan", murid["keterangan"].lower())

            guru_jur = next(c for c in cats if c["id"] == "MC-GURU-JUR")
            self.assertEqual(guru_jur["jenis"], "guru_jurusan")

            guru_um = next(c for c in cats if c["id"] == "MC-GURU-UMUM")
            self.assertEqual(guru_um["jenis"], "guru_umum")

            staf = next(c for c in cats if c["id"] == "MC-STAF")
            self.assertEqual(staf["jenis"], "staf")

            teknisi = next(c for c in cats if c["id"] == "MC-TEKNISI")
            self.assertEqual(teknisi["jenis"], "teknisi")
        finally:
            conn.close()

    def test_02_seed_categories_is_idempotent(self):
        """Memverifikasi bahwa eksekusi seed berkali-kali tidak menggandakan data atau error."""
        conn = library_app.get_db_connection()
        try:
            # Seed pertama
            seed_member_categories(conn)
            count1 = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]
            self.assertEqual(count1, 5)

            # Seed kedua
            seed_member_categories(conn)
            count2 = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]
            self.assertEqual(count2, 5)

            # Seed ketiga
            seed_member_categories(conn)
            count3 = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]
            self.assertEqual(count3, 5)

            # Memodifikasi keterangan kategori lokal (kustomisasi admin)
            conn.execute(
                "UPDATE member_categories SET keterangan = 'Keterangan Khusus Sekolah' WHERE id = 'MC-MURID';"
            )
            conn.commit()

            # Seed ulang tidak boleh menimpa keterangan kustom (DO NOTHING)
            seed_member_categories(conn)
            custom_cat = member_repo.get_category_by_id(conn, "MC-MURID")
            self.assertEqual(custom_cat["keterangan"], "Keterangan Khusus Sekolah")
        finally:
            conn.close()

    def test_03_foreign_key_consistency(self):
        """Memverifikasi relasi foreign key antara members dan member_categories."""
        conn = library_app.get_db_connection()
        try:
            seed_member_categories(conn)

            # Pendaftaran anggota dengan kategori resmi valid
            m1 = register_member(conn, nama="Ahmad Siswa", category_id="MC-MURID")
            self.assertTrue(m1["id"].startswith("M-"))

            # Pendaftaran anggota dengan kategori tidak dikenal ditolak
            with self.assertRaises(Exception):
                register_member(conn, nama="Hantu", category_id="MC-TIDAKADA")
        finally:
            conn.close()

    # --------------------------------------------------------------------------
    # 2. AUTENTIKASI ADMIN & AKSES KONTROL
    # --------------------------------------------------------------------------
    def test_04_unauthenticated_access_rejected(self):
        """Memverifikasi akses tanpa login admin ditolak dengan 302 redirect ke /login."""
        # Route utama
        res1 = self.client.get("/admin/members", follow_redirects=False)
        self.assertEqual(res1.status_code, 302)
        self.assertIn("/login", res1.headers.get("Location", ""))

        # Alias route
        res2 = self.client.get("/admin/anggota", follow_redirects=False)
        self.assertEqual(res2.status_code, 302)
        self.assertIn("/login", res2.headers.get("Location", ""))

    def test_05_unauthenticated_json_request_returns_401(self):
        """Memverifikasi request JSON tanpa login ditolak dengan 401 Unauthorized."""
        res = self.client.get("/admin/members", headers={"Accept": "application/json"})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_06_authenticated_admin_can_access(self):
        """Memverifikasi admin terautentikasi dapat mengakses halaman anggota dengan status 200."""
        self._login_admin()
        res = self.client.get("/admin/members")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Daftar & Pencarian Anggota", res.get_data(as_text=True))
        self.assertIn("Task 4-02: Manajemen Anggota", res.get_data(as_text=True))

    # --------------------------------------------------------------------------
    # 3. DAFTAR & PENCARIAN ANGGOTA
    # --------------------------------------------------------------------------
    def _seed_sample_members(self):
        """Helper untuk menambahkan anggota uji lintas kategori dan status."""
        conn = library_app.get_db_connection()
        try:
            seed_member_categories(conn)
            # 1. Siswa Aktif
            m1 = register_member(conn, nama="Budi Prakoso", category_id="MC-MURID")
            # 2. Siswa Nonaktif (Alumni)
            m2 = register_member(conn, nama="Citra Kirana", category_id="MC-MURID")
            deactivate_member(conn, member_id=m2["id"], reason="Lulus tahun 2026")
            # 3. Guru Kejuruan
            m3 = register_member(conn, nama="Dedi Hidayat, S.T.", category_id="MC-GURU-JUR")
            # 4. Guru Umum
            m4 = register_member(conn, nama="Eka Yuliana, S.Pd.", category_id="MC-GURU-UMUM")
            # 5. Staf TU
            m5 = register_member(conn, nama="Fajar Subekti", category_id="MC-STAF")
            # 6. Teknisi Lab
            m6 = register_member(conn, nama="Gunawan Bengkel", category_id="MC-TEKNISI")
            return [m1, m2, m3, m4, m5, m6]
        finally:
            conn.close()

    def test_07_list_members_displays_seeded_members(self):
        """Memverifikasi seluruh anggota sampel ditampilkan lengkap pada halaman admin."""
        samples = self._seed_sample_members()
        self._login_admin()

        res = self.client.get("/admin/members")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        for s in samples:
            self.assertIn(s["id"], html)
            self.assertIn(s["nama"], html)

    def test_08_search_by_name(self):
        """Memverifikasi pencarian nama anggota (pencocokan persis maupun parsial)."""
        self._seed_sample_members()
        self._login_admin()

        # Cari "Budi"
        res = self.client.get("/admin/members?q=Budi")
        html = res.get_data(as_text=True)
        self.assertIn("Budi Prakoso", html)
        self.assertNotIn("Citra Kirana", html)
        self.assertNotIn("Dedi Hidayat", html)

        # Cari "Yuliana"
        res2 = self.client.get("/admin/members?q=Yuliana")
        html2 = res2.get_data(as_text=True)
        self.assertIn("Eka Yuliana, S.Pd.", html2)
        self.assertNotIn("Budi Prakoso", html2)

    def test_09_search_by_member_id(self):
        """Memverifikasi pencarian berdasarkan ID anggota Crockford Base32 ('M-XXXXXX')."""
        samples = self._seed_sample_members()
        target = samples[2]  # Dedi
        self._login_admin()

        res = self.client.get(f"/admin/members?q={target['id']}")
        html = res.get_data(as_text=True)
        self.assertIn(target["nama"], html)
        self.assertIn(target["id"], html)

    def test_10_empty_search_returns_all_members(self):
        """Memverifikasi kueri kosong atau whitespace mengembalikan seluruh anggota tanpa filter."""
        self._seed_sample_members()
        self._login_admin()

        res = self.client.get("/admin/members?q=   ")
        html = res.get_data(as_text=True)
        self.assertIn("Budi Prakoso", html)
        self.assertIn("Gunawan Bengkel", html)
        self.assertIn("6 data", html)

    def test_11_filter_by_category(self):
        """Memverifikasi penyaringan anggota berdasarkan kategori tertentu."""
        self._seed_sample_members()
        self._login_admin()

        # Filter Teknisi
        res = self.client.get("/admin/members?category_id=MC-TEKNISI")
        html = res.get_data(as_text=True)
        self.assertIn("Gunawan Bengkel", html)
        self.assertNotIn("Budi Prakoso", html)
        self.assertNotIn("Dedi Hidayat", html)

        # Filter Murid (harus ada Budi dan Citra)
        res_murid = self.client.get("/admin/members?category_id=MC-MURID")
        html_murid = res_murid.get_data(as_text=True)
        self.assertIn("Budi Prakoso", html_murid)
        self.assertIn("Citra Kirana", html_murid)
        self.assertNotIn("Gunawan Bengkel", html_murid)

    def test_12_filter_by_status(self):
        """Memverifikasi penyaringan status anggota ('aktif' vs 'nonaktif')."""
        self._seed_sample_members()
        self._login_admin()

        # Filter Nonaktif
        res_nonaktif = self.client.get("/admin/members?status=nonaktif")
        html_nonaktif = res_nonaktif.get_data(as_text=True)
        self.assertIn("Citra Kirana", html_nonaktif)
        self.assertNotIn("Budi Prakoso", html_nonaktif)

        # Filter Aktif
        res_aktif = self.client.get("/admin/members?status=aktif")
        html_aktif = res_aktif.get_data(as_text=True)
        self.assertIn("Budi Prakoso", html_aktif)
        self.assertNotIn("Citra Kirana", html_aktif)

    def test_13_combined_search_and_filters(self):
        """Memverifikasi kombinasi kueri teks, kategori, dan status secara bersamaan."""
        self._seed_sample_members()
        self._login_admin()

        # Cari "Citra" di kategori MC-MURID dengan status nonaktif -> Ditemukan
        res1 = self.client.get("/admin/members?q=Citra&category_id=MC-MURID&status=nonaktif")
        html1 = res1.get_data(as_text=True)
        self.assertIn("Citra Kirana", html1)

        # Cari "Citra" di kategori MC-MURID tapi status aktif -> Tidak ditemukan
        res2 = self.client.get("/admin/members?q=Citra&category_id=MC-MURID&status=aktif")
        html2 = res2.get_data(as_text=True)
        self.assertIn("Anggota Tidak Ditemukan", html2)
        self.assertNotIn("Citra Kirana", html2)

    def test_14_search_special_characters_handled_safely(self):
        """Memverifikasi karakter khusus (% _ ' \" \\) di-escape secara aman dan tidak menyebabkan error SQL."""
        conn = library_app.get_db_connection()
        try:
            seed_member_categories(conn)
            # Daftarkan anggota dengan karakter literal khusus
            register_member(conn, nama="Siti_Rahma 100% OK", category_id="MC-MURID")
            register_member(conn, nama="Normal Siswa", category_id="MC-MURID")
        finally:
            conn.close()

        self._login_admin()

        # Pencarian literal "%"
        res_pct = self.client.get("/admin/members?q=%")
        self.assertEqual(res_pct.status_code, 200)
        html_pct = res_pct.get_data(as_text=True)
        self.assertIn("Siti_Rahma 100% OK", html_pct)
        self.assertNotIn("Normal Siswa", html_pct)

        # Pencarian literal "_"
        res_und = self.client.get("/admin/members?q=_")
        self.assertEqual(res_und.status_code, 200)
        html_und = res_und.get_data(as_text=True)
        self.assertIn("Siti_Rahma 100% OK", html_und)
        self.assertNotIn("Normal Siswa", html_und)

        # Input SQL injection attempt
        res_sqli = self.client.get("/admin/members?q=' OR 1=1 --")
        self.assertEqual(res_sqli.status_code, 200)
        self.assertIn("Anggota Tidak Ditemukan", res_sqli.get_data(as_text=True))

    def test_15_long_search_query_truncated_safely(self):
        """Memverifikasi kueri panjang (>100 karakter) dipotong aman tanpa crash server."""
        self._seed_sample_members()
        self._login_admin()

        long_query = "A" * 250
        res = self.client.get(f"/admin/members?q={long_query}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Anggota Tidak Ditemukan", res.get_data(as_text=True))

    def test_16_pagination(self):
        """Memverifikasi paginasi data anggota berfungsi dengan batas per_page yang tepat."""
        conn = library_app.get_db_connection()
        try:
            seed_member_categories(conn)
            for i in range(25):
                register_member(conn, nama=f"Anggota Urut {i+1:02d}", category_id="MC-MURID")
        finally:
            conn.close()

        self._login_admin()

        # Halaman 1 (per_page=10)
        res1 = self.client.get("/admin/members?page=1&per_page=10")
        self.assertEqual(res1.status_code, 200)
        html1 = res1.get_data(as_text=True)
        self.assertIn("halaman <strong>1</strong> dari <strong>3</strong>", html1)
        self.assertIn("Berikutnya", html1)

        # Halaman 2
        res2 = self.client.get("/admin/members?page=2&per_page=10")
        self.assertEqual(res2.status_code, 200)
        html2 = res2.get_data(as_text=True)
        self.assertIn("halaman <strong>2</strong> dari <strong>3</strong>", html2)

    def test_17_empty_database_state(self):
        """Memverifikasi keadaan kosong saat belum ada anggota di database."""
        conn = library_app.get_db_connection()
        try:
            seed_member_categories(conn)
        finally:
            conn.close()

        self._login_admin()
        res = self.client.get("/admin/members")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Belum Ada Data Anggota", html)

    def test_18_legacy_p1_database_compatibility(self):
        """Memverifikasi kompatibilitas ketika aplikasi terhubung ke database skema legacy P1."""
        legacy_dir = tempfile.mkdtemp()
        legacy_db = os.path.join(legacy_dir, "legacy_p1_test.db")
        try:
            conn = sqlite3.connect(legacy_db)
            conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT);")
            conn.commit()
            conn.close()

            os.environ["DATABASE_NAME"] = legacy_db
            self._login_admin()

            res = self.client.get("/admin/members")
            self.assertEqual(res.status_code, 200)
            html = res.get_data(as_text=True)
            self.assertIn("Database Berada pada Skema Lama (P1)", html)
        finally:
            if os.path.exists(legacy_dir):
                shutil.rmtree(legacy_dir, ignore_errors=True)
            os.environ["DATABASE_NAME"] = self.test_db

    def test_19_privacy_no_pii_exposed(self):
        """DEC-023: Memverifikasi antarmuka admin tidak mengekspos nomor telepon, kelas, atau PII."""
        self._seed_sample_members()
        self._login_admin()

        res = self.client.get("/admin/members")
        html = res.get_data(as_text=True)
        self.assertNotIn("Telepon", html)
        self.assertNotIn("No. HP", html)
        self.assertNotIn("Kelas XI", html)

    def test_20_zero_write_on_get_request(self):
        """Memverifikasi bahwa permintaan GET pada daftar anggota bersifat murni read-only."""
        self._seed_sample_members()
        self._login_admin()

        conn = library_app.get_db_connection()
        try:
            count_members_before = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
            count_cats_before = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]
            count_audit_before = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        finally:
            conn.close()

        # Eksekusi GET berulang
        for _ in range(5):
            res = self.client.get("/admin/members?q=Budi")
            self.assertEqual(res.status_code, 200)

        conn = library_app.get_db_connection()
        try:
            count_members_after = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
            count_cats_after = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]
            count_audit_after = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(count_members_before, count_members_after)
        self.assertEqual(count_cats_before, count_cats_after)
        self.assertEqual(count_audit_before, count_audit_after)

    def test_21_qr_token_compatibility_with_listed_members(self):
        """Task 4-01 & 4-02: Memverifikasi token QR dapat dibuat dan diverifikasi untuk anggota yang terdaftar."""
        samples = self._seed_sample_members()
        m = samples[0]

        token = generate_member_qr_token(m["id"], m["qr_version"])
        conn = library_app.get_db_connection()
        try:
            verified = verify_member_qr_token(conn, token)
            self.assertEqual(verified["id"], m["id"])
            self.assertEqual(verified["nama"], m["nama"])
            self.assertEqual(verified["category_id"], m["category_id"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
