# -*- coding: utf-8 -*-
"""
Suite Pengujian Otomatis untuk Task 3-06:
Pratinjau Impor Katalog Tanpa Menulis Database (Preview).

Memverifikasi secara komprehensif:
1. Akses admin ke route preview (/buku/impor/preview dan alias /buku/preview-impor).
2. Penolakan akses tanpa autentikasi admin (redirect ke /login).
3. File CSV valid menghasilkan pratinjau dengan status OK untuk seluruh baris.
4. Header hilang, salah nama, ekstra kolom, atau urutan salah ditolak dengan pesan informatif.
5. UTF-8, BOM, tanda koma, kutip ganda, dan karakter Indonesia diproses secara benar.
6. File kosong, tanpa baris data, melebihi batas ukuran (2 MiB), atau baris ekstrem (>1000) ditolak aman.
7. Field wajib yang kosong (judul, penulis, kategori, jumlah) ditandai sebagai Error.
8. ISBN kosong sah sebagai opsional; ISBN invalid ditandai sebagai Error.
9. Jumlah nol, negatif, desimal, non-numerik, atau melampaui batas ditandai sebagai Error.
10. Deteksi duplikat ISBN intra-file antar-baris ditandai sebagai Peringatan.
11. Deteksi duplikat judul+penulis intra-file antar-baris ditandai sebagai Peringatan.
12. Deteksi duplikat terhadap rekaman katalog di database ditandai sebagai Peringatan read-only.
13. Judul mirip tetapi penulis berbeda TIDAK sembarangan ditandai sebagai duplikat.
14. Upaya formula spreadsheet ('=', '+', '-', '@') pada field teks ditandai sebagai Error dan tidak pernah dieksekusi.
15. Input HTML/JS di-escape secara aman pada template preview.
16. Zero-Write Terbukti: Database, tabel katalog, eksemplar, token, dan audit log tidak pernah berubah.
17. Tidak ada token konfirmasi atau fungsi commit yang dieksekusi pada tahap preview.
"""
import csv
import hashlib
import io
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from app import app
from policy import MAX_CATALOG_IMPORT_FILE_SIZE_BYTES, MAX_CATALOG_IMPORT_ROWS
from services import (
    parse_and_validate_catalog_import_csv,
    is_potential_formula,
    ValidationError,
)


class CatalogImportPreviewUnitTests(unittest.TestCase):
    """Pengujian Unit untuk Logika Parsing dan Validasi CSV Impor."""

    def test_01_formula_injection_detector(self):
        """Memverifikasi deteksi awalan formula spreadsheet."""
        self.assertTrue(is_potential_formula("=SUM(A1:A10)"))
        self.assertTrue(is_potential_formula("+cmd|' /C calc'!A0"))
        self.assertTrue(is_potential_formula("-10"))
        self.assertTrue(is_potential_formula("@username"))
        self.assertTrue(is_potential_formula("  =1+1"))
        self.assertTrue(is_potential_formula("\t@admin"))

        # String normal
        self.assertFalse(is_potential_formula("Laskar Pelangi"))
        self.assertFalse(is_potential_formula("978-602-03-8591-4"))
        self.assertFalse(is_potential_formula("Buku Pelajaran"))
        self.assertFalse(is_potential_formula(""))
        self.assertFalse(is_potential_formula(None))

    def test_02_valid_csv_unit_parsing(self):
        """Memverifikasi parsing string CSV valid menjadi list baris status OK."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku A,Penulis A,978-602-03-8591-4,Fiksi,5\n"
            "Buku B,Penulis B,,Referensi,2\n"
        )
        res = parse_and_validate_catalog_import_csv(conn=None, csv_content=csv_text)
        self.assertEqual(res["total_rows"], 2)
        self.assertEqual(res["valid_rows_count"], 2)
        self.assertEqual(res["warning_rows_count"], 0)
        self.assertEqual(res["error_rows_count"], 0)

        # Baris 1
        row1 = res["rows"][0]
        self.assertEqual(row1["row_num"], 2)
        self.assertEqual(row1["status"], "OK")
        self.assertEqual(row1["clean_data"]["jumlah"], 5)

        # Baris 2 (ISBN kosong sah)
        row2 = res["rows"][1]
        self.assertEqual(row2["row_num"], 3)
        self.assertEqual(row2["status"], "OK")
        self.assertIsNone(row2["clean_data"]["isbn"])
        self.assertEqual(row2["clean_data"]["jumlah"], 2)

    def test_03_invalid_headers_raise_validation_error(self):
        """Memverifikasi bahwa header yang tidak sesuai kontrak langsung melempar ValidationError."""
        # Salah nama kolom
        with self.assertRaises(ValidationError) as ctx:
            parse_and_validate_catalog_import_csv(conn=None, csv_content="title,penulis,isbn,kategori,jumlah\nBook,Author,,Fiksi,1\n")
        self.assertIn("Header CSV tidak sesuai", str(ctx.exception))

        # Kolom kurang
        with self.assertRaises(ValidationError):
            parse_and_validate_catalog_import_csv(conn=None, csv_content="judul,penulis,isbn,kategori\nBook,Author,,Fiksi\n")

        # Kolom lebih
        with self.assertRaises(ValidationError):
            parse_and_validate_catalog_import_csv(conn=None, csv_content="judul,penulis,isbn,kategori,jumlah,penerbit\nBook,Author,,Fiksi,1,Gramedia\n")

        # Urutan terbalik
        with self.assertRaises(ValidationError):
            parse_and_validate_catalog_import_csv(conn=None, csv_content="penulis,judul,isbn,kategori,jumlah\nAuthor,Book,,Fiksi,1\n")

    def test_04_empty_and_header_only_csv_raise(self):
        """Memverifikasi penolakan file kosong dan file tanpa data baris."""
        with self.assertRaises(ValidationError) as ctx1:
            parse_and_validate_catalog_import_csv(conn=None, csv_content="")
        self.assertIn("kosong", str(ctx1.exception).lower())

        with self.assertRaises(ValidationError) as ctx2:
            parse_and_validate_catalog_import_csv(conn=None, csv_content="   \n  \n")
        self.assertIn("kosong", str(ctx2.exception).lower())

        with self.assertRaises(ValidationError) as ctx3:
            parse_and_validate_catalog_import_csv(conn=None, csv_content="judul,penulis,isbn,kategori,jumlah\n")
        self.assertIn("tidak memiliki baris data", str(ctx3.exception).lower())

    def test_05_oversized_rows_limit_raise(self):
        """Memverifikasi penolakan jika jumlah baris melebihi batas maksimum."""
        lines = ["judul,penulis,isbn,kategori,jumlah"]
        for i in range(15):
            lines.append(f"Judul {i},Penulis {i},,Fiksi,1")
        csv_text = "\n".join(lines)

        # Uji dengan batas buatan max_rows = 10
        with self.assertRaises(ValidationError) as ctx:
            parse_and_validate_catalog_import_csv(conn=None, csv_content=csv_text, max_rows=10)
        self.assertIn("melebihi batas maksimum", str(ctx.exception).lower())

    def test_06_row_level_field_validation_errors(self):
        """Memverifikasi identifikasi error pada tingkat field per baris."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            ",Penulis Ada,,Fiksi,5\n"                      # Baris 2: Judul kosong
            "Judul Ada,,,Fiksi,5\n"                         # Baris 3: Penulis kosong
            "Judul Ada,Penulis Ada,, ,5\n"                  # Baris 4: Kategori kosong
            "Judul Ada,Penulis Ada,,Fiksi,\n"               # Baris 5: Jumlah kosong
            "Judul Ada,Penulis Ada,,Fiksi,0\n"              # Baris 6: Jumlah 0
            "Judul Ada,Penulis Ada,,Fiksi,-2\n"             # Baris 7: Jumlah negatif
            "Judul Ada,Penulis Ada,,Fiksi,3.5\n"            # Baris 8: Jumlah desimal
            "Judul Ada,Penulis Ada,,Fiksi,banyak\n"         # Baris 9: Jumlah teks
            "Judul Ada,Penulis Ada,12345,Fiksi,2\n"         # Baris 10: ISBN invalid (5 digit)
            "=SUM(A1),Penulis Ada,,Fiksi,2\n"               # Baris 11: Formula pada judul
            "Judul Ada,@hacker,,Fiksi,2\n"                  # Baris 12: Formula pada penulis
            "Judul Ada,Penulis Ada,,+Kategori,2\n"          # Baris 13: Formula pada kategori
        )
        res = parse_and_validate_catalog_import_csv(conn=None, csv_content=csv_text)
        self.assertEqual(res["total_rows"], 12)
        self.assertEqual(res["error_rows_count"], 12)
        self.assertEqual(res["valid_rows_count"], 0)

        for row in res["rows"]:
            self.assertEqual(row["status"], "ERROR")
            self.assertGreater(len(row["errors"]), 0)

    def test_07_intra_file_duplicate_detection(self):
        """Memverifikasi deteksi duplikat intra-file (ISBN dan Judul+Penulis)."""
        csv_text = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Fisika Dasar,Prof. Yohanes,978-602-03-8591-4,Pelajaran,5\n"
            "Kimia Dasar,Dr. Sutrisno,978-602-298-967-7,Pelajaran,3\n"
            "Fisika Lanjutan,Prof. Anton,9786020385914,Pelajaran,2\n"     # ISBN sama dengan baris 2 (setelah normalisasi)
            "Fisika Dasar,Prof. Yohanes,,Pelajaran,4\n"                    # Judul+Penulis sama dengan baris 2
            "Fisika Dasar,Drs. Budi,,Pelajaran,1\n"                         # Judul sama tetapi penulis beda -> BUKAN duplikat
        )
        res = parse_and_validate_catalog_import_csv(conn=None, csv_content=csv_text)
        self.assertEqual(res["total_rows"], 5)
        self.assertEqual(res["error_rows_count"], 0)

        # Baris 2 (index 0): OK
        self.assertEqual(res["rows"][0]["status"], "OK")

        # Baris 3 (index 1): OK
        self.assertEqual(res["rows"][1]["status"], "OK")

        # Baris 4 (index 2): Peringatan duplikat ISBN terhadap baris 2
        self.assertEqual(res["rows"][2]["status"], "PERINGATAN")
        self.assertTrue(any("identik dengan baris 2" in w for w in res["rows"][2]["warnings"]))

        # Baris 5 (index 3): Peringatan duplikat Judul+Penulis terhadap baris 2
        self.assertEqual(res["rows"][3]["status"], "PERINGATAN")
        self.assertTrue(any("serupa dengan baris 2" in w for w in res["rows"][3]["warnings"]))

        # Baris 6 (index 4): OK (penulis berbeda tidak memicu false positive)
        self.assertEqual(res["rows"][4]["status"], "OK")


class CatalogImportPreviewRouteIntegrationTests(unittest.TestCase):
    """Pengujian Integrasi Route Flask untuk Preview Impor Katalog."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_catalog_preview.db")

        # Inisialisasi basis data uji mandiri dengan skema v2
        conn = sqlite3.connect(self.test_db_path)
        conn.execute("""
            CREATE TABLE catalog_titles (
                id TEXT PRIMARY KEY,
                judul TEXT NOT NULL,
                penulis TEXT NOT NULL,
                isbn TEXT,
                kategori TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE copies (
                id TEXT PRIMARY KEY,
                title_id TEXT NOT NULL,
                barcode TEXT,
                status TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE confirmation_tokens (
                token TEXT PRIMARY KEY,
                admin_username TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                result_summary TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            );
        """)

        # Masukkan 1 rekaman acuan di database untuk menguji deteksi duplikat database
        conn.execute(
            "INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori) VALUES (?, ?, ?, ?, ?);",
            ("T-0001", "Biologi Molekuler", "Dr. Subroto", "978-602-0000-01-1", "Sains")
        )
        conn.commit()
        conn.close()

        # Patch app
        self.orig_db_env = os.environ.get("DATABASE_NAME")
        os.environ["DATABASE_NAME"] = self.test_db_path
        self.orig_db_file = app.config.get("DATABASE")
        app.config["DATABASE"] = self.test_db_path
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        if self.orig_db_env is not None:
            os.environ["DATABASE_NAME"] = self.orig_db_env
        else:
            os.environ.pop("DATABASE_NAME", None)
        if self.orig_db_file is not None:
            app.config["DATABASE"] = self.orig_db_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_as_admin(self):
        token = "test-valid-csrf-preview-306"
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin_username"] = "admin"
            sess["last_active"] = time.time()
            sess["_csrf_token"] = token
        return token

    def _get_db_state(self):
        conn = sqlite3.connect(self.test_db_path)
        titles = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        copies = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        tokens = conn.execute("SELECT COUNT(*) FROM confirmation_tokens;").fetchone()[0]
        audits = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        conn.close()

        with open(self.test_db_path, "rb") as f:
            db_hash = hashlib.sha256(f.read()).hexdigest()

        return {
            "titles": titles,
            "copies": copies,
            "tokens": tokens,
            "audits": audits,
            "hash": db_hash,
        }

    def test_01_authenticated_admin_can_access_preview(self):
        """Kriteria 1 & 3: Admin yang terautentikasi dapat mengunggah CSV dan melihat pratinjau."""
        csrf_token = self._login_as_admin()

        csv_content = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Algoritma Pemrograman,Rinaldi Munir,978-602-8758-00-0,Informatika,5\n"
            "Struktur Data,Kurniawan,,Informatika,3\n"
        ).encode("utf-8")

        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_content), "katalog_uji.csv")
        }

        # POST ke route primer
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("Hasil Pratinjau &amp; Validasi Impor Katalog", html)
        self.assertIn("Algoritma Pemrograman", html)
        self.assertIn("Rinaldi Munir", html)
        self.assertIn("Struktur Data", html)
        self.assertIn("Zero-Write (Database 100% Utuh)", html)

        # Uji route alias
        data_alias = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_content), "katalog_uji_alias.csv")
        }
        resp_alias = self.client.post("/buku/preview-impor", data=data_alias, content_type="multipart/form-data")
        self.assertEqual(resp_alias.status_code, 200)

        # GET request diarahkan ke panduan
        resp_get = self.client.get("/buku/impor/preview")
        self.assertEqual(resp_get.status_code, 302)
        self.assertIn("/buku/impor/panduan", resp_get.headers.get("Location", ""))

    def test_02_unauthenticated_user_rejected_and_redirected_to_login(self):
        """Kriteria 2: Pengguna tanpa autentikasi ditolak dan dialihkan ke /login."""
        # A. GET tanpa login -> redirect ke login
        resp_get = self.client.get("/buku/impor/preview", follow_redirects=False)
        self.assertEqual(resp_get.status_code, 302)
        self.assertIn("/login", resp_get.headers.get("Location", ""))

        # B. POST dengan valid CSRF token di session tetapi logged_in = False
        with self.client.session_transaction() as sess:
            sess["logged_in"] = False
            sess["_csrf_token"] = "unauth-csrf-token"

        data = {
            "csrf_token": "unauth-csrf-token",
            "csv_file": (io.BytesIO(b"judul,penulis,isbn,kategori,jumlah\n"), "test.csv")
        }
        resp_post = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp_post.status_code, 302)
        self.assertIn("/login", resp_post.headers.get("Location", ""))

        # C. POST tanpa CSRF token sama sekali -> 400 ditolak
        resp_no_csrf = self.client.post("/buku/impor/preview", data={}, content_type="multipart/form-data")
        self.assertEqual(resp_no_csrf.status_code, 400)

    def test_03_non_csv_extension_rejected(self):
        """Kriteria 6: File dengan ekstensi non-CSV ditolak secara ramah."""
        csrf_token = self._login_as_admin()
        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(b"data"), "buku.xlsx")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Format file tidak didukung", html)

    def test_04_oversized_file_rejected(self):
        """Kriteria 6: File yang melebihi batas ukuran ditolak secara aman."""
        csrf_token = self._login_as_admin()
        large_bytes = b"judul,penulis,isbn,kategori,jumlah\n" + (b"A" * (MAX_CATALOG_IMPORT_FILE_SIZE_BYTES + 500))
        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(large_bytes), "large.csv")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(resp.status_code, (200, 413))
        html = resp.get_data(as_text=True)
        self.assertIn("melebihi batas maksimum", html.lower())

    def test_05_utf8_bom_and_commas_in_fields_handled_properly(self):
        """Kriteria 5: UTF-8 dengan BOM serta tanda koma di dalam tanda kutip berhasil diproses."""
        csrf_token = self._login_as_admin()

        csv_str = (
            "judul,penulis,isbn,kategori,jumlah\n"
            '"Ensiklopedia Sains, Teknologi, dan Lingkungan",Tim Penulis,,Referensi,2\n'
        )
        csv_bytes = csv_str.encode("utf-8-sig")

        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_bytes), "bom_test.csv")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("Ensiklopedia Sains, Teknologi, dan Lingkungan", html)
        self.assertIn("Tim Penulis", html)
        self.assertIn("OK", html)

    def test_06_database_duplicate_triggers_warning_banner(self):
        """Kriteria 12: Judul yang mirip dengan database memicu peringatan (bukan error)."""
        csrf_token = self._login_as_admin()

        # Biologi Molekuler oleh Dr. Subroto sudah ada di DB
        csv_content = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Biologi Molekuler,Dr. Subroto,978-602-0000-01-1,Sains,3\n"
        ).encode("utf-8")

        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_content), "db_dup.csv")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("Peringatan", html)
        self.assertIn("Potensi duplikat katalog", html)
        self.assertIn("T-0001", html)

    def test_07_html_injection_is_escaped_in_preview(self):
        """Kriteria 14 & 15: Input HTML / XSS pada field di-escape dan tidak dieksekusi browser."""
        csrf_token = self._login_as_admin()

        csv_content = (
            "judul,penulis,isbn,kategori,jumlah\n"
            '"<script>alert(1)</script>",<b>Penulis Tebal</b>,,Fiksi,1\n'
        ).encode("utf-8")

        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_content), "xss.csv")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Di-escape oleh Jinja2
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;Penulis Tebal&lt;/b&gt;", html)

    def test_08_formula_injection_cells_flagged_as_error(self):
        """Kriteria 14: Sel dengan awalan formula spreadsheet ditolak sebagai Error."""
        csrf_token = self._login_as_admin()

        csv_content = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "=cmd|' /C calc'!A0,Normal Author,,Fiksi,2\n"
            "Normal Title,+AuthorFormula,,Fiksi,2\n"
            "Normal Title,Normal Author,,@KategoriFormula,2\n"
        ).encode("utf-8")

        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_content), "formula.csv")
        }
        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("karakter formula spreadsheet", html)
        self.assertIn("Error", html)

    def test_09_zero_write_strictly_guaranteed_across_mixed_rows(self):
        """Kriteria 16 & 17: Uji Zero-Write: Memastikan database 100% tidak pernah berubah sebelum dan sesudah preview."""
        csrf_token = self._login_as_admin()

        initial_state = self._get_db_state()

        # CSV campuran: ada baris OK, baris Peringatan, dan baris Error
        csv_content = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku Baru Bersih,Penulis Bersih,,Fiksi,3\n"                           # OK
            "Biologi Molekuler,Dr. Subroto,978-602-0000-01-1,Sains,2\n"            # Peringatan (Duplikat DB)
            ",Penulis Tanpa Judul,,Fiksi,1\n"                                       # Error (Judul kosong)
            "Buku Normal,Penulis Normal,,Fiksi,0\n"                                 # Error (Jumlah 0)
        ).encode("utf-8")

        # Panggil endpoint preview berkali-kali
        for _ in range(3):
            data = {
                "csrf_token": csrf_token,
                "csv_file": (io.BytesIO(csv_content), "mixed_test.csv")
            }
            resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data")
            self.assertEqual(resp.status_code, 200)

        final_state = self._get_db_state()

        # Verifikasi seluruh tabel dan file database
        self.assertEqual(initial_state["titles"], final_state["titles"], "Jumlah judul tidak boleh berubah")
        self.assertEqual(initial_state["copies"], final_state["copies"], "Jumlah eksemplar tidak boleh berubah")
        self.assertEqual(initial_state["tokens"], final_state["tokens"], "Tidak boleh membuat token konfirmasi")
        self.assertEqual(initial_state["audits"], final_state["audits"], "Tidak boleh menulis audit log bisnis")
        self.assertEqual(initial_state["hash"], final_state["hash"], "Hash byte database wajib 100% identik")

    def test_10_json_api_mode_supported(self):
        """Kriteria JSON: Mendukung respons JSON untuk AJAX/klien terprogram."""
        csrf_token = self._login_as_admin()

        csv_content = (
            "judul,penulis,isbn,kategori,jumlah\n"
            "Buku JSON,Penulis JSON,,Fiksi,4\n"
        ).encode("utf-8")

        data = {
            "csrf_token": csrf_token,
            "csv_file": (io.BytesIO(csv_content), "json_test.csv")
        }
        headers = {
            "Accept": "application/json",
            "X-CSRFToken": csrf_token,
        }

        resp = self.client.post("/buku/impor/preview", data=data, content_type="multipart/form-data", headers=headers)
        self.assertEqual(resp.status_code, 200)
        json_data = resp.get_json()
        self.assertTrue(json_data["ok"])
        self.assertEqual(json_data["preview"]["total_rows"], 1)
        self.assertEqual(json_data["preview"]["valid_rows_count"], 1)
        self.assertEqual(json_data["preview"]["rows"][0]["status"], "OK")


if __name__ == "__main__":
    unittest.main()

