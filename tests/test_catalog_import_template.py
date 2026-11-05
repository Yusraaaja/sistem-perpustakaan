# -*- coding: utf-8 -*-
"""
Suite Pengujian Otomatis untuk Task 3-05:
Template Impor Katalog + Halaman Panduan.

Memverifikasi:
1. Akses admin terautentikasi ke halaman panduan dan unduhan template.
2. Penolakan akses tanpa autentikasi (redirect ke /login).
3. Unduhan template berhasil dengan nama file dan content-type yang sesuai.
4. Header CSV tepat 'judul, penulis, isbn, kategori, jumlah' dalam urutan yang benar.
5. CSV dapat dibaca kembali oleh parser CSV standar (csv.reader & csv.DictReader).
6. Baris contoh terformat benar, menangani koma/tanda kutip, memiliki ISBN kosong yang sah, dan jumlah integer positif.
7. Isi panduan memuat seluruh instruksi wajib (tujuan, kolom, aplikasi spreadsheet, UTF-8, hapus contoh, konsep eksemplar fisik, dsb.).
8. Zero-write: Mengakses panduan atau mengunduh template TIDAK pernah memodifikasi database.
9. Tautan navigasi tersedia dari halaman koleksi dan tambah buku.
10. Fungsi unit service katalog bekerja sesuai spesifikasi.
"""
import csv
import io
import os
import re
import shutil
import sqlite3
import tempfile
import unittest

from app import app
from services import (
    CATALOG_IMPORT_HEADERS,
    CATALOG_IMPORT_FILENAME,
    CATALOG_IMPORT_SAMPLE_DATA,
    get_catalog_import_sample_data,
    generate_catalog_import_template_csv,
    get_catalog_import_template_download_payload,
)


class CatalogImportTemplateUnitTests(unittest.TestCase):
    """Pengujian Unit untuk Fungsi dan Konstanta Service Template Impor."""

    def test_01_headers_and_filename_constants(self):
        """Memverifikasi header wajib, urutan kolom, dan nama file template."""
        self.assertEqual(
            CATALOG_IMPORT_HEADERS,
            ["judul", "penulis", "isbn", "kategori", "jumlah"],
            "Header CSV harus persis: judul, penulis, isbn, kategori, jumlah"
        )
        self.assertEqual(CATALOG_IMPORT_FILENAME, "template_impor_katalog.csv")

    def test_02_sample_data_structure(self):
        """Memverifikasi struktur dan validitas baris-baris data contoh."""
        sample_data = get_catalog_import_sample_data()
        self.assertIsInstance(sample_data, list)
        self.assertGreaterEqual(len(sample_data), 3, "Harus menyediakan minimal 3 baris data contoh")

        has_empty_isbn = False
        has_comma_in_field = False

        for row in sample_data:
            self.assertIn("judul", row)
            self.assertIn("penulis", row)
            self.assertIn("isbn", row)
            self.assertIn("kategori", row)
            self.assertIn("jumlah", row)

            # Judul harus memuat label (Contoh)
            self.assertIn("(Contoh)", row["judul"])

            # Jumlah harus integer positif >= 1
            self.assertIsInstance(row["jumlah"], int)
            self.assertGreaterEqual(row["jumlah"], 1)

            # Cek keberadaan contoh ISBN kosong yang sah
            if not row.get("isbn"):
                has_empty_isbn = True

            # Cek keberadaan koma di dalam field untuk menguji escaping CSV
            if "," in row["judul"] or "," in row["penulis"]:
                has_comma_in_field = True

        self.assertTrue(has_empty_isbn, "Harus menyertakan setidaknya satu contoh baris dengan ISBN kosong")
        self.assertTrue(has_comma_in_field, "Harus menyertakan contoh field yang mengandung koma")

    def test_03_generate_csv_string_and_parsing(self):
        """Memverifikasi bahwa output generate_catalog_import_template_csv adalah CSV valid yang dapat dibaca csv.reader."""
        csv_text = generate_catalog_import_template_csv()
        self.assertIsInstance(csv_text, str)

        lines = [line for line in csv_text.splitlines() if line.strip()]
        reader = list(csv.reader(lines))

        # Baris pertama harus header
        self.assertEqual(reader[0], CATALOG_IMPORT_HEADERS)

        # Seluruh baris harus memiliki tepat 5 kolom
        for i, row in enumerate(reader):
            self.assertEqual(
                len(row), 5,
                f"Baris ke-{i} memiliki {len(row)} kolom, seharusnya tepat 5 kolom"
            )

        # Verifikasi parsing menggunakan csv.DictReader
        dict_reader = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(dict_reader), len(CATALOG_IMPORT_SAMPLE_DATA))
        for row in dict_reader:
            self.assertEqual(list(row.keys()), CATALOG_IMPORT_HEADERS)
            self.assertTrue(row["judul"].endswith("(Contoh)"))
            self.assertTrue(int(row["jumlah"]) >= 1)

    def test_04_download_payload_contract(self):
        """Memverifikasi kontrak fungsi payload unduhan (bytes, filename, mimetype)."""
        csv_bytes, filename, mimetype = get_catalog_import_template_download_payload()
        self.assertIsInstance(csv_bytes, bytes)
        self.assertEqual(filename, "template_impor_katalog.csv")
        self.assertIn("text/csv", mimetype)
        self.assertIn("utf-8", mimetype.lower())

        # Memastikan bytes dapat didecode sebagai UTF-8 tanpa error
        decoded_text = csv_bytes.decode("utf-8")
        self.assertTrue(decoded_text.startswith("judul,penulis,isbn,kategori,jumlah"))


class CatalogImportTemplateRouteIntegrationTests(unittest.TestCase):
    """Pengujian Integrasi Route Flask untuk Halaman Panduan dan Unduhan Template."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_catalog_import.db")

        # Inisialisasi basis data uji mandiri
        conn = sqlite3.connect(self.test_db_path)
        conn.execute("CREATE TABLE catalog_titles (id TEXT PRIMARY KEY, judul TEXT, penulis TEXT, isbn TEXT, kategori TEXT);")
        conn.execute("CREATE TABLE copies (id TEXT PRIMARY KEY, title_id TEXT, status TEXT);")
        conn.commit()
        conn.close()

        # Patch app
        self.orig_db_file = app.config.get("DATABASE")
        app.config["DATABASE"] = self.test_db_path
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def tearDown(self):
        if self.orig_db_file is not None:
            app.config["DATABASE"] = self.orig_db_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_as_admin(self):
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin_username"] = "admin"

    def test_01_authenticated_admin_can_access_guide_page(self):
        """Kriteria 1: Admin yang terautentikasi dapat membuka halaman panduan."""
        self._login_as_admin()

        # Route primer
        resp = self.client.get("/buku/impor/panduan")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Panduan &amp; Template Impor Koleksi Buku", html)
        self.assertIn("template_impor_katalog.csv", html)
        self.assertIn("/buku/impor/template", html)

        # Route alias
        resp_alias = self.client.get("/buku/panduan-impor")
        self.assertEqual(resp_alias.status_code, 200)

    def test_02_unauthenticated_user_cannot_access_guide_page(self):
        """Kriteria 2: Pengguna tanpa login ditolak dan dialihkan ke /login saat membuka panduan."""
        resp = self.client.get("/buku/impor/panduan", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

        resp_alias = self.client.get("/buku/panduan-impor", follow_redirects=False)
        self.assertEqual(resp_alias.status_code, 302)
        self.assertIn("/login", resp_alias.headers.get("Location", ""))

    def test_03_authenticated_admin_can_download_template(self):
        """Kriteria 3: Unduhan template berhasil dengan nama file dan content-type yang sesuai."""
        self._login_as_admin()

        resp = self.client.get("/buku/impor/template")
        self.assertEqual(resp.status_code, 200)

        # Content-Type
        content_type = resp.headers.get("Content-Type", "")
        self.assertIn("text/csv", content_type)

        # Content-Disposition
        content_disp = resp.headers.get("Content-Disposition", "")
        self.assertIn("attachment", content_disp)
        self.assertIn("template_impor_katalog.csv", content_disp)

        # Route alias
        resp_alias = self.client.get("/buku/template-impor")
        self.assertEqual(resp_alias.status_code, 200)
        self.assertIn("template_impor_katalog.csv", resp_alias.headers.get("Content-Disposition", ""))

    def test_04_unauthenticated_user_cannot_download_template(self):
        """Kriteria 4: Pengguna tanpa login ditolak dan dialihkan ke /login saat mengunduh template."""
        resp = self.client.get("/buku/impor/template", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

        resp_alias = self.client.get("/buku/template-impor", follow_redirects=False)
        self.assertEqual(resp_alias.status_code, 302)
        self.assertIn("/login", resp_alias.headers.get("Location", ""))

    def test_05_downloaded_csv_header_exact_match(self):
        """Kriteria 5: Header CSV unduhan persis 'judul, penulis, isbn, kategori, jumlah' dalam urutan benar."""
        self._login_as_admin()
        resp = self.client.get("/buku/impor/template")
        self.assertEqual(resp.status_code, 200)

        csv_text = resp.get_data(as_text=True)
        first_line = csv_text.splitlines()[0]
        self.assertEqual(first_line, "judul,penulis,isbn,kategori,jumlah")

    def test_06_downloaded_csv_parseable_by_standard_csv_reader(self):
        """Kriteria 6: CSV hasil unduhan dapat dibaca kembali oleh parser CSV standar."""
        self._login_as_admin()
        resp = self.client.get("/buku/impor/template")
        self.assertEqual(resp.status_code, 200)

        csv_text = resp.get_data(as_text=True)
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertEqual(reader[0], ["judul", "penulis", "isbn", "kategori", "jumlah"])
        self.assertGreaterEqual(len(reader), 4, "Minimal ada 1 header + 3 baris contoh")

        for row in reader:
            self.assertEqual(len(row), 5)

    def test_07_downloaded_csv_sample_rows_intact_with_commas_and_quotes(self):
        """Kriteria 7: Baris contoh tidak rusak oleh koma, tanda kutip, atau karakter UTF-8."""
        self._login_as_admin()
        resp = self.client.get("/buku/impor/template")
        self.assertEqual(resp.status_code, 200)

        csv_text = resp.get_data(as_text=True)
        dict_reader = list(csv.DictReader(io.StringIO(csv_text)))

        # Cari baris yang memuat judul dengan koma
        comma_row = next(
            (r for r in dict_reader if "Ensiklopedia Sains, Teknologi, dan Lingkungan" in r["judul"]),
            None
        )
        self.assertIsNotNone(comma_row, "Baris dengan koma di dalam judul harus berhasil diparse")
        self.assertEqual(comma_row["penulis"], "Tim Pusat Perbukuan")
        self.assertEqual(comma_row["isbn"], "")  # ISBN kosong
        self.assertEqual(comma_row["kategori"], "Referensi")
        self.assertEqual(comma_row["jumlah"], "2")

    def test_08_guide_page_mandatory_instruction_contents(self):
        """Kriteria 8: Isi panduan memuat seluruh instruksi wajib sesuai kriteria penerimaan."""
        self._login_as_admin()
        resp = self.client.get("/buku/impor/panduan")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # 1. Tujuan template & kapan digunakan
        self.assertIn("Kapan Sebaiknya Menggunakan Fitur Impor Massal?", html)
        self.assertIn("Pengadaan buku baru", html)

        # 2. Cara mengunduh template
        self.assertIn("Unduh Template CSV", html)
        self.assertIn("template_impor_katalog.csv", html)

        # 3. Fungsi setiap kolom
        self.assertIn("judul", html)
        self.assertIn("penulis", html)
        self.assertIn("isbn", html)
        self.assertIn("kategori", html)
        self.assertIn("jumlah", html)

        # 4. Aplikasi spreadsheet
        self.assertIn("Microsoft Excel", html)
        self.assertIn("Google Sheets", html)
        self.assertIn("LibreOffice Calc", html)

        # 5. Mempertahankan header
        self.assertIn("Pertahankan Header", html)

        # 6. Jumlah bilangan bulat positif
        self.assertIn("Bilangan bulat", html)

        # 7. Penanganan ISBN kosong
        self.assertIn("biarkan sel ini kosong", html.lower())
        self.assertIn("jangan pernah mengarang isbn palsu", html.lower())

        # 8. Simpan format CSV UTF-8
        self.assertIn("CSV UTF-8", html)

        # 9. Hapus data contoh
        self.assertIn("Hapus Data Contoh Sebelum Digunakan!", html)
        self.assertIn("(Contoh)", html)

        # 10. Konsep eksemplar fisik (jumlah = 5 -> 5 eksemplar)
        self.assertIn("jumlah = 5", html)
        self.assertIn("5 eksemplar fisik terpisah", html)

        # 11. Periksa ulang sebelum impor
        self.assertIn("Periksa Ulang", html)

        # 12. Ketiadaan mutasi database saat ini (zero-write / preview di task berikutnya)
        self.assertIn("sama sekali tidak memodifikasi database", html)
        self.assertIn("Task 3-06", html)
        self.assertIn("Task 3-07", html)

        # 13. Tanggung jawab validasi server
        self.assertIn("server perpustakaan akan tetap melakukan validasi ketat", html)

    def test_09_guide_and_download_do_not_mutate_database_zero_write(self):
        """Kriteria 9: Mengakses panduan atau mengunduh template terbukti TIDAK memodifikasi database (zero-write)."""
        self._login_as_admin()

        conn = sqlite3.connect(self.test_db_path)
        initial_titles_count = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        initial_copies_count = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        conn.close()

        # Akses berkali-kali halaman panduan dan unduhan
        self.client.get("/buku/impor/panduan")
        self.client.get("/buku/panduan-impor")
        self.client.get("/buku/impor/template")
        self.client.get("/buku/template-impor")

        conn = sqlite3.connect(self.test_db_path)
        after_titles_count = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        after_copies_count = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        conn.close()

        self.assertEqual(initial_titles_count, after_titles_count, "Jumlah judul tidak boleh berubah")
        self.assertEqual(initial_copies_count, after_copies_count, "Jumlah eksemplar tidak boleh berubah")

    def test_10_navigation_links_present_in_koleksi_and_tambah_buku(self):
        """Kriteria 10: Tautan ke panduan impor tersedia di halaman koleksi dan tambah buku."""
        self._login_as_admin()

        # Di halaman tambah buku
        resp_tambah = self.client.get("/buku/tambah")
        self.assertEqual(resp_tambah.status_code, 200)
        html_tambah = resp_tambah.get_data(as_text=True)
        self.assertIn("/buku/impor/panduan", html_tambah)
        self.assertIn("Panduan &amp; Template Impor", html_tambah)

        # Di halaman koleksi (database)
        resp_koleksi = self.client.get("/koleksi")
        self.assertEqual(resp_koleksi.status_code, 200)
        html_koleksi = resp_koleksi.get_data(as_text=True)
        self.assertIn("/buku/impor/panduan", html_koleksi)
        self.assertIn("Panduan &amp; Template Impor", html_koleksi)


if __name__ == "__main__":
    unittest.main()

