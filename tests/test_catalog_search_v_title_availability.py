# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-12: Pencarian Katalog Publik Menggunakan v_title_availability.
Memverifikasi:
1. Pencarian menggunakan view `v_title_availability` untuk data ketersediaan aktual.
2. Hasil pencarian dan ketersediaan konsisten dengan kontrak view (available_copies, total_semua, total_aktif, borrowed_copies).
3. Input kosong ditangani sesuai kontrak (menampilkan katalog penuh tanpa filter).
4. Input whitespace ditangani sesuai kontrak (diperlakukan sama seperti kosong).
5. Input sangat panjang ditangani aman via pemotongan batas MAX_CATALOG_SEARCH_QUERY_LENGTH.
6. Tanda kutip dan karakter SQL tidak menimbulkan error atau injeksi SQL.
7. Wildcard LIKE (% dan _) di-escape secara deterministik untuk pencarian substring literal.
8. Input teks Unicode dan aksen (é, ü, 日本語, dsb.) ditangani secara tepat.
9. Pencarian tanpa hasil menampilkan empty state ramah pengguna.
10. Operasi pencarian terbukti 100% zero-write (tanpa mutasi database).
11. Eksemplar nonaktif, rusak, hilang, dan dalam penanganan tidak pernah dihitung sebagai tersedia.
12. Katalog publik dapat diakses tanpa login (HTTP 200).
13. Pagination dan filter kategori berfungsi dengan benar.
14. Pencarian kata kunci mencocokkan ID eksemplar (C-XXXXXX) dan ID judul (T-XXXXXX).
15. Dukungan fallback skema legacy P1 tetap berjalan aman.
16. Halaman detail buku /buku/<id> mengambil stok dari v_title_availability.
17. Endpoint /api/search_suggestions mendukung skema v2 & ketersediaan publik.
"""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
from policy import MAX_CATALOG_SEARCH_QUERY_LENGTH
from repositories import (
    catalog_repo,
    copy_repo,
    member_repo,
    loan_repo,
)
from services import (
    search_catalog_public,
    clean_catalog_search_query,
    escape_like_query,
)


class TestCatalogSearchVTitleAvailability(unittest.TestCase):
    """Pengujian Unit & Integrasi Pencarian Katalog Berbasis v_title_availability."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_search.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        library_app.app.config['WTF_CSRF_ENABLED'] = False
        self.client = library_app.app.test_client()

        # Inisialisasi skema database v2
        self._init_v2_schema()
        self._seed_data()

    def tearDown(self):
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_v2_schema(self):
        conn = self._get_connection()
        migration_file = os.path.join(ROOT, 'migrations', '0001_initial_v2_schema.sql')
        with open(migration_file, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

    def _seed_data(self):
        conn = self._get_connection()
        # Seed kategori & anggota
        conn.execute(
            "INSERT INTO member_categories (id, jenis) VALUES (?, ?);",
            ("CAT-SISWA", "Siswa")
        )
        conn.execute(
            """
            INSERT INTO members (id, nama, status, category_id, qr_version, created_at, updated_at)
            VALUES (?, ?, 'aktif', ?, 1, '2026-10-27T00:00:00Z', '2026-10-27T00:00:00Z');
            """,
            ("M-S00001", "Ahmad Siswa", "CAT-SISWA")
        )

        # Seed judul buku
        self.t1_id = catalog_repo.create_title(conn, {
            "id": "T-PY0001",
            "judul": "Pemrograman Python Modern 100%",
            "subjudul": "Panduan Praktis dari Dasar",
            "penulis": "Guido van Rossum",
            "penerbit": "Informatika Press",
            "tahun": "2024",
            "isbn": "978-602-0001-01-1",
            "kategori": "Pemrograman",
            "sinopsis": "Buku komprehensif tentang Python modern.",
            "harga_buku": 120000,
        })

        self.t2_id = catalog_repo.create_title(conn, {
            "id": "T-SQL002",
            "judul": "Database Relasional & SQL_Advanced",
            "subjudul": "Kueri Tingkat Lanjut",
            "penulis": "Edgar Codd",
            "penerbit": "Data Press",
            "tahun": "2023",
            "isbn": "978-602-0002-02-2",
            "kategori": "Database",
            "sinopsis": "Membahas normalisasi dan relasional database.",
            "harga_buku": 95000,
        })

        self.t3_id = catalog_repo.create_title(conn, {
            "id": "T-UNI003",
            "judul": "Karya Sastra Dunia: L'Étranger & Café Paris",
            "subjudul": "Eksistensialisme Klasik",
            "penulis": "Albert Camus",
            "penerbit": "Pustaka Sastra",
            "tahun": "2021",
            "isbn": "978-602-0003-03-3",
            "kategori": "Sastra",
            "sinopsis": "Novel klasik berlatar Aljazair dan Prancis.",
            "harga_buku": 80000,
        })

        self.t4_id = catalog_repo.create_title(conn, {
            "id": "T-EMPTY4",
            "judul": "Buku Arsip Tanpa Eksemplar",
            "subjudul": "Judul Referensi",
            "penulis": "Penulis Anonim",
            "kategori": "Referensi",
            "harga_buku": 50000,
        })

        # Seed eksemplar fisik untuk T1 (3 aktif)
        self.c1_1 = copy_repo.create_copy(conn, {
            "id": "C-PY01-01",
            "title_id": self.t1_id,
            "status": "aktif",
            "lokasi_rak": "Rak A-1",
        })
        self.c1_2 = copy_repo.create_copy(conn, {
            "id": "C-PY01-02",
            "title_id": self.t1_id,
            "status": "aktif",
            "lokasi_rak": "Rak A-1",
        })
        self.c1_3 = copy_repo.create_copy(conn, {
            "id": "C-PY01-03",
            "title_id": self.t1_id,
            "status": "aktif",
            "lokasi_rak": "Rak A-1",
        })

        # Seed eksemplar fisik untuk T2 dengan berbagai status
        # (1 aktif, 1 nonaktif, 1 rusak, 1 hilang, 1 dalam_penanganan)
        self.c2_aktif = copy_repo.create_copy(conn, {
            "id": "C-SQL-01",
            "title_id": self.t2_id,
            "status": "aktif",
            "lokasi_rak": "Rak B-2",
        })
        self.c2_nonaktif = copy_repo.create_copy(conn, {
            "id": "C-SQL-02",
            "title_id": self.t2_id,
            "status": "nonaktif",
            "lokasi_rak": "Gudang",
        })
        self.c2_rusak = copy_repo.create_copy(conn, {
            "id": "C-SQL-03",
            "title_id": self.t2_id,
            "status": "rusak",
            "lokasi_rak": "Ruang Reparasi",
        })
        self.c2_hilang = copy_repo.create_copy(conn, {
            "id": "C-SQL-04",
            "title_id": self.t2_id,
            "status": "hilang",
            "lokasi_rak": "Tak Diketahui",
        })
        self.c2_penanganan = copy_repo.create_copy(conn, {
            "id": "C-SQL-05",
            "title_id": self.t2_id,
            "status": "dalam_penanganan",
            "lokasi_rak": "Meja Petugas",
        })

        # Seed eksemplar fisik untuk T3 (1 aktif)
        self.c3_1 = copy_repo.create_copy(conn, {
            "id": "C-UNI-01",
            "title_id": self.t3_id,
            "status": "aktif",
            "lokasi_rak": "Rak C-3",
        })

        conn.commit()
        conn.close()

    def _get_db_hash(self) -> str:
        h = hashlib.sha256()
        with open(self.test_db, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    # ==========================================================================
    # 1. PENCARIAN MENGGUNAKAN v_title_availability
    # ==========================================================================
    def test_01_search_uses_v_title_availability_view(self):
        """Kriteria 1: Memverifikasi pencarian katalog menggunakan v_title_availability."""
        conn = self._get_connection()
        try:
            res = search_catalog_public(conn, query="Python")
            self.assertEqual(len(res["items"]), 1)
            item = res["items"][0]

            # Field dari v_title_availability wajib ada
            self.assertEqual(item["id"], self.t1_id)
            self.assertIn("available_copies", item)
            self.assertIn("total_semua", item)
            self.assertIn("total_aktif", item)
            self.assertIn("borrowed_copies", item)
            self.assertEqual(item["total_semua"], 3)
            self.assertEqual(item["total_aktif"], 3)
            self.assertEqual(item["available_copies"], 3)
            self.assertEqual(item["borrowed_copies"], 0)
            self.assertEqual(item["stok"], 3)
        finally:
            conn.close()

    # ==========================================================================
    # 2. HASIL DAN KETERSEDIAAN KONSISTEN DENGAN DATA VIEW SETELAH PINJAM
    # ==========================================================================
    def test_02_availability_consistent_with_loans_via_view(self):
        """Kriteria 2: Ketersediaan konsisten saat ada eksemplar dipinjam."""
        conn = self._get_connection()
        try:
            # Pinjamkan C-PY01-01
            conn.execute(
                """
                INSERT INTO loans (id, member_id, created_at)
                VALUES (?, ?, '2026-10-27T10:00:00Z');
                """,
                ("L-000001", "M-S00001")
            )
            conn.execute(
                """
                INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at)
                VALUES (?, ?, ?, '2026-10-27T10:00:00Z', '2026-11-03T10:00:00Z');
                """,
                ("LI-00001", "L-000001", self.c1_1)
            )
            conn.commit()

            # Verifikasi langsung ke view
            view_row = conn.execute(
                "SELECT * FROM v_title_availability WHERE title_id = ?;", (self.t1_id,)
            ).fetchone()
            self.assertEqual(view_row["total_semua"], 3)
            self.assertEqual(view_row["total_aktif"], 3)
            self.assertEqual(view_row["available_copies"], 2)
            self.assertEqual(view_row["borrowed_copies"], 1)

            # Verifikasi via service pencarian
            res = search_catalog_public(conn, query="Python")
            item = res["items"][0]
            self.assertEqual(item["available_copies"], 2)
            self.assertEqual(item["stok"], 2)
            self.assertEqual(item["borrowed_copies"], 1)
        finally:
            conn.close()

    # ==========================================================================
    # 3. INPUT KOSONG DITANGANI SESUAI KONTRAK
    # ==========================================================================
    def test_03_empty_input_handled_according_to_contract(self):
        """Kriteria 3: Input kosong mengembalikan seluruh katalog tanpa filter."""
        conn = self._get_connection()
        try:
            res = search_catalog_public(conn, query="")
            self.assertEqual(res["query"], "")
            self.assertEqual(len(res["items"]), 4)  # 4 judul terdaftar
            self.assertEqual(res["total_count"], 4)

            # None query juga menghasilkan perilaku yang sama
            res_none = search_catalog_public(conn, query=None)
            self.assertEqual(res_none["query"], "")
            self.assertEqual(len(res_none["items"]), 4)
        finally:
            conn.close()

    # ==========================================================================
    # 4. INPUT WHITESPACE DITANGANI SESUAI KONTRAK
    # ==========================================================================
    def test_04_whitespace_input_treated_as_empty(self):
        """Kriteria 4: Input hanya whitespace (spasi, tab, newline) diperlakukan sebagai kosong."""
        conn = self._get_connection()
        try:
            res_spaces = search_catalog_public(conn, query="    ")
            self.assertEqual(res_spaces["query"], "")
            self.assertEqual(len(res_spaces["items"]), 4)

            res_mixed = search_catalog_public(conn, query="\t\n  \r\n ")
            self.assertEqual(res_mixed["query"], "")
            self.assertEqual(len(res_mixed["items"]), 4)
        finally:
            conn.close()

    # ==========================================================================
    # 5. INPUT PANJANG DITANGANI DENGAN AMAN (TRUNCATION)
    # ==========================================================================
    def test_05_long_input_handled_safely_and_truncated(self):
        """Kriteria 5: Input sangat panjang (>200 char) dipotong aman tanpa crash."""
        conn = self._get_connection()
        try:
            long_prefix = "Python "
            long_query = long_prefix + ("A" * 500)
            cleaned = clean_catalog_search_query(long_query)
            self.assertEqual(len(cleaned), MAX_CATALOG_SEARCH_QUERY_LENGTH)
            self.assertTrue(cleaned.startswith(long_prefix))

            # Eksekusi pencarian tidak menimbulkan error
            res = search_catalog_public(conn, query=long_query)
            self.assertEqual(len(res["query"]), MAX_CATALOG_SEARCH_QUERY_LENGTH)
            self.assertIsInstance(res["items"], list)
        finally:
            conn.close()

    # ==========================================================================
    # 6. TANDA KUTIP & KARAKTER SQL TIDAK MENYEBABKAN ERROR ATAU INJEKSI
    # ==========================================================================
    def test_06_quotes_and_sql_injection_payloads_safe(self):
        """Kriteria 6: Tanda kutip tunggal/ganda dan payload SQL injection ditangani aman."""
        conn = self._get_connection()
        try:
            sql_payloads = [
                "' OR '1'='1",
                "\" OR \"1\"=\"1",
                "'; DROP TABLE catalog_titles; --",
                "admin'--",
                "UNION SELECT * FROM members",
                "1'; SELECT * FROM copies; --",
                "\\'; DROP VIEW v_title_availability; --",
            ]

            for payload in sql_payloads:
                with self.subTest(payload=payload):
                    res = search_catalog_public(conn, query=payload)
                    self.assertIsInstance(res["items"], list)
                    # Pastikan tabel masih utuh (tidak terkena drop)
                    check = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()
                    self.assertEqual(check[0], 4)
        finally:
            conn.close()

    # ==========================================================================
    # 7. % DAN _ MENGIKUTI ATURAN PENCARIAN LITERAL
    # ==========================================================================
    def test_07_percent_and_underscore_escaped_for_literal_match(self):
        """Kriteria 7: Karakter % dan _ dicocokkan secara harfiah, bukan sebagai wildcard."""
        conn = self._get_connection()
        try:
            # Judul T1 memuat "100%"
            res_percent = search_catalog_public(conn, query="100%")
            self.assertEqual(len(res_percent["items"]), 1)
            self.assertEqual(res_percent["items"][0]["id"], self.t1_id)

            # Judul T2 memuat "SQL_Advanced"
            res_underscore = search_catalog_public(conn, query="SQL_Advanced")
            self.assertEqual(len(res_underscore["items"]), 1)
            self.assertEqual(res_underscore["items"][0]["id"], self.t2_id)

            # Mencari "SQLXAdvanced" (huruf pengganti underscore) tidak boleh mencocokkan T2
            res_mismatch = search_catalog_public(conn, query="SQLXAdvanced")
            self.assertEqual(len(res_mismatch["items"]), 0)

            # Mencari "%" secara terisolasi hanya mencocokkan buku yang memiliki tanda % di judulnya
            res_only_percent = search_catalog_public(conn, query="%")
            self.assertEqual(len(res_only_percent["items"]), 1)
            self.assertEqual(res_only_percent["items"][0]["id"], self.t1_id)
        finally:
            conn.close()

    # ==========================================================================
    # 8. INPUT UNICODE DAN AKSEN DITANGANI SECARA TEPAT
    # ==========================================================================
    def test_08_unicode_and_accented_input_handled_properly(self):
        """Kriteria 8: Teks beraksen (Étranger, Café) dan karakter non-ASCII dicocokkan dengan benar."""
        conn = self._get_connection()
        try:
            res_etranger = search_catalog_public(conn, query="Étranger")
            self.assertEqual(len(res_etranger["items"]), 1)
            self.assertEqual(res_etranger["items"][0]["id"], self.t3_id)

            res_cafe = search_catalog_public(conn, query="Café")
            self.assertEqual(len(res_cafe["items"]), 1)
            self.assertEqual(res_cafe["items"][0]["id"], self.t3_id)

            # Pencarian Unicode multibahasa tidak menimbulkan error
            res_jp = search_catalog_public(conn, query="日本語の教科書")
            self.assertEqual(len(res_jp["items"]), 0)

            res_emoji = search_catalog_public(conn, query="📚 Belajar")
            self.assertEqual(len(res_emoji["items"]), 0)
        finally:
            conn.close()

    # ==========================================================================
    # 9. PENCARIAN TANPA HASIL MENAMPILKAN EMPTY STATE
    # ==========================================================================
    def test_09_no_match_returns_empty_items_cleanly(self):
        """Kriteria 9: Pencarian tanpa hasil mengembalikan list kosong dan total_count 0."""
        conn = self._get_connection()
        try:
            res = search_catalog_public(conn, query="KatakunciPalsuYangTidakMungkinAda12345")
            self.assertEqual(res["items"], [])
            self.assertEqual(res["total_count"], 0)
        finally:
            conn.close()

        # Uji juga rendering empty state pada route /koleksi
        resp = self.client.get("/koleksi?query=KatakunciPalsuYangTidakMungkinAda12345")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Data Koleksi Tidak Ditemukan", html)
        self.assertIn("Kata kunci pencarian tidak cocok dengan judul", html)

    # ==========================================================================
    # 10. QUERY PENCARIAN TIDAK MEMODIFIKASI DATABASE (ZERO-WRITE)
    # ==========================================================================
    def test_10_search_queries_are_strictly_read_only_zero_write(self):
        """Kriteria 10: Operasi pencarian tidak melakukan mutasi database apa pun."""
        hash_before = self._get_db_hash()

        # Jalankan serangkaian pencarian
        self.client.get("/koleksi?query=Python")
        self.client.get("/koleksi?query=")
        self.client.get("/koleksi?query=' OR '1'='1")
        self.client.get("/koleksi?query=100%")
        self.client.get("/api/search_suggestions?q=Python")

        hash_after = self._get_db_hash()
        self.assertEqual(hash_before, hash_after)

    # ==========================================================================
    # 11. EKSEMPLAR NONAKTIF, RUSAK, HILANG, & DALAM PENANGANAN TIDAK DIHITUNG TERSEDIA
    # ==========================================================================
    def test_11_deactivated_damaged_lost_handling_not_counted_as_available(self):
        """Kriteria 11: Hanya eksemplar status 'aktif' tanpa pinjaman aktif yang dihitung available."""
        conn = self._get_connection()
        try:
            # Judul T2 memiliki 5 eksemplar total: 1 aktif, 1 nonaktif, 1 rusak, 1 hilang, 1 dalam_penanganan
            res = search_catalog_public(conn, query="SQL_Advanced")
            self.assertEqual(len(res["items"]), 1)
            item = res["items"][0]

            self.assertEqual(item["total_semua"], 5)
            self.assertEqual(item["total_aktif"], 1)
            self.assertEqual(item["available_copies"], 1)
            self.assertEqual(item["stok"], 1)
            self.assertEqual(item["borrowed_copies"], 0)

            # Bila eksemplar aktif satu-satunya dinonaktifkan
            copy_repo.update_copy_status(conn, self.c2_aktif, "nonaktif")
            conn.commit()

            res_after = search_catalog_public(conn, query="SQL_Advanced")
            item_after = res_after["items"][0]
            self.assertEqual(item_after["total_semua"], 5)
            self.assertEqual(item_after["total_aktif"], 0)
            self.assertEqual(item_after["available_copies"], 0)
            self.assertEqual(item_after["stok"], 0)
        finally:
            conn.close()

    # ==========================================================================
    # 12. KATALOG PUBLIK DAPAT DIAKSES TANPA LOGIN (HTTP 200)
    # ==========================================================================
    def test_12_public_catalog_accessible_without_auth(self):
        """Kriteria 12: Route /koleksi dan /search dapat diakses publik tanpa login admin."""
        resp = self.client.get("/koleksi")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Sistem Manajemen Aset & Inventaris", html)
        self.assertIn("Pemrograman Python Modern 100%", html)

        # Route /search me-redirect ke /koleksi?query=
        resp_search = self.client.get("/search?query=Python")
        self.assertEqual(resp_search.status_code, 302)
        self.assertIn("/koleksi?query=Python", resp_search.headers.get("Location", ""))

    # ==========================================================================
    # 13. PAGINATION & FILTER KATEGORI BERFUNGSI DENGAN BENAR
    # ==========================================================================
    def test_13_pagination_and_category_filter(self):
        """Kriteria 13: Limit, offset, dan filter kategori membatasi hasil secara akurat."""
        conn = self._get_connection()
        try:
            # Filter kategori Pemrograman
            res_cat = search_catalog_public(conn, kategori="Pemrograman")
            self.assertEqual(len(res_cat["items"]), 1)
            self.assertEqual(res_cat["items"][0]["kategori"], "Pemrograman")

            # Filter kategori tidak ada
            res_empty_cat = search_catalog_public(conn, kategori="Astronomi")
            self.assertEqual(len(res_empty_cat["items"]), 0)

            # Pagination: limit 2 offset 0
            res_page1 = search_catalog_public(conn, limit=2, offset=0)
            self.assertEqual(len(res_page1["items"]), 2)
            self.assertEqual(res_page1["total_count"], 4)

            # Pagination: limit 2 offset 2
            res_page2 = search_catalog_public(conn, limit=2, offset=2)
            self.assertEqual(len(res_page2["items"]), 2)
            self.assertNotEqual(res_page1["items"][0]["id"], res_page2["items"][0]["id"])
        finally:
            conn.close()

    # ==========================================================================
    # 14. PENCARIAN BERDASARKAN ID EKSEMPLAR & NOMOR REGISTRASI
    # ==========================================================================
    def test_14_search_by_copy_id_and_legacy_ref(self):
        """Kriteria 14: Pencarian kata kunci mencocokkan ID eksemplar (C-XXXXXX) dan ID judul."""
        conn = self._get_connection()
        try:
            # Cari berdasarkan ID eksemplar C-PY01-02
            res_copy = search_catalog_public(conn, query="C-PY01-02")
            self.assertEqual(len(res_copy["items"]), 1)
            self.assertEqual(res_copy["items"][0]["id"], self.t1_id)

            # Cari berdasarkan Title ID T-SQL002
            res_title_id = search_catalog_public(conn, query="T-SQL002")
            self.assertEqual(len(res_title_id["items"]), 1)
            self.assertEqual(res_title_id["items"][0]["id"], self.t2_id)
        finally:
            conn.close()

    # ==========================================================================
    # 15. DUKUNGAN FALLBACK SKEMA LEGACY P1
    # ==========================================================================
    def test_15_legacy_p1_fallback_handling(self):
        """Kriteria 15: Skema legacy P1 (tabel buku) tetap ditangani aman oleh route /koleksi."""
        legacy_dir = tempfile.mkdtemp()
        legacy_db = os.path.join(legacy_dir, 'legacy_test.db')
        legacy_conn = sqlite3.connect(legacy_db)
        legacy_conn.execute("""
            CREATE TABLE buku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                judul TEXT NOT NULL,
                sub_judul TEXT,
                penulis TEXT,
                penerbit TEXT,
                tahun_terbit TEXT,
                isbn TEXT,
                kategori TEXT,
                sinopsis TEXT,
                cover_img TEXT,
                stok INTEGER DEFAULT 0,
                id_buku_fisik TEXT,
                lokasi_rak TEXT
            );
        """)
        legacy_conn.execute("""
            CREATE TABLE peminjaman (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_buku INTEGER,
                status TEXT
            );
        """)
        legacy_conn.execute("""
            CREATE TABLE peminjaman_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_buku INTEGER,
                status TEXT
            );
        """)

        legacy_conn.execute(
            """
            INSERT INTO buku (judul, penulis, kategori, stok, id_buku_fisik)
            VALUES (?, ?, ?, ?, ?);
            """,
            ("Buku Legacy P1", "Penulis Lama", "Sejarah", 2, '["LEG-001", "LEG-002"]')
        )
        legacy_conn.commit()
        legacy_conn.close()

        old_env_db = os.environ.get('DATABASE_NAME')
        try:
            os.environ['DATABASE_NAME'] = legacy_db
            resp = self.client.get("/koleksi?query=Legacy")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn("Buku Legacy P1", html)

            # Tes pencarian karakter aneh di legacy tidak crash
            resp_sql = self.client.get("/koleksi?query=' OR '1'='1")
            self.assertEqual(resp_sql.status_code, 200)
        finally:
            if old_env_db:
                os.environ['DATABASE_NAME'] = old_env_db
            else:
                os.environ.pop('DATABASE_NAME', None)
            if os.path.exists(legacy_dir):
                shutil.rmtree(legacy_dir, ignore_errors=True)

    # ==========================================================================
    # 16. DETAIL BUKU /buku/<id> MEMAKAI v_title_availability
    # ==========================================================================
    def test_16_detail_buku_route_uses_v_title_availability(self):
        """Kriteria 16: Halaman detail buku /buku/<id> mengambil stok dari v_title_availability."""
        resp = self.client.get(f"/buku/{self.t1_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Pemrograman Python Modern 100%", html)
        self.assertIn("3 Eksemplar", html)

    # ==========================================================================
    # 17. API SEARCH SUGGESTIONS MENDUKUNG SKEMA v2 & v_title_availability
    # ==========================================================================
    def test_17_api_search_suggestions_v2(self):
        """Kriteria 17: /api/search_suggestions mengembalikan data ketersediaan publik v2."""
        resp = self.client.get("/api/search_suggestions?q=Python")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        item = data[0]
        self.assertEqual(item["id"], self.t1_id)
        self.assertEqual(item["judul"], "Pemrograman Python Modern 100%")
        self.assertEqual(item["available_copies"], 3)


if __name__ == "__main__":
    unittest.main()

