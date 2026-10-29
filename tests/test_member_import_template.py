# -*- coding: utf-8 -*-
"""
Suite Pengujian Komprehensif Task 4-03:
Template Impor Anggota (nama, jenis, keterangan, status, id_anggota opsional)
dan Pengabaian Kolom Kelas/Telepon dengan Peringatan (DEC-023).
"""
import csv
import io
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

import app as library_app
from policy import (
    MEMBER_IMPORT_FILENAME,
    MEMBER_IMPORT_HEADERS,
    MEMBER_REQUIRED_HEADERS,
    MEMBER_IGNORED_COLUMN_NAMES,
    MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
    MAX_MEMBER_IMPORT_ROWS,
)
from services import (
    ValidationError,
    get_member_import_sample_data,
    generate_member_import_template_csv,
    get_member_import_template_download_payload,
    normalize_member_jenis,
    validate_member_id_format,
    validate_member_import_header,
    parse_and_validate_member_import_csv,
)


class TestMemberImportTemplate(unittest.TestCase):
    """Pengujian Task 4-03: Template impor anggota, panduan, dan validasi."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_member_import.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        os.environ["SECRET_KEY"] = "test-secret-key-for-member-import-suite-2026"

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
        """Membuat struktur tabel v2 yang bersih dari migrations/0001_initial_v2_schema.sql."""
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
        """Helper login admin untuk session test client."""
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess["logged_in"] = True
            sess["admin_username"] = library_app.ADMIN_USERNAME
            sess["user_role"] = "admin"
            sess["last_active"] = time.time()
            sess["_csrf_token"] = "valid-csrf-token-test"

    # --------------------------------------------------------------------------
    # 1. STRUKTUR & KONTRAK TEMPLATE CSV
    # --------------------------------------------------------------------------
    def test_01_template_headers_and_structure(self):
        """Memverifikasi bahwa template memiliki 5 header resmi dengan urutan tepat."""
        csv_text = generate_member_import_template_csv()
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)

        expected_header = ["nama", "jenis", "keterangan", "status", "id_anggota"]
        self.assertEqual(header, expected_header)
        self.assertEqual(list(MEMBER_IMPORT_HEADERS), expected_header)

    def test_02_sample_data_is_valid_and_synthetic(self):
        """Memverifikasi bahwa data contoh realistis, sintetis, dan mencakup 5 peran sekolah."""
        sample_data = get_member_import_sample_data()
        self.assertGreaterEqual(len(sample_data), 5)

        roles_present = {item["jenis"] for item in sample_data}
        expected_roles = {"murid", "guru_jurusan", "guru_umum", "staf", "teknisi"}
        self.assertTrue(expected_roles.issubset(roles_present))

        # Seluruh nama harus ditandai '(Contoh)' untuk kepatuhan privasi data sintetis
        for item in sample_data:
            self.assertIn("(Contoh)", item["nama"])
            self.assertIn(item["status"], {"aktif", "nonaktif"})
            if item["id_anggota"]:
                self.assertTrue(validate_member_id_format(item["id_anggota"]))

    def test_03_download_payload_generation(self):
        """Memverifikasi payload unduhan template: bytes UTF-8, nama file, dan mimetype."""
        csv_bytes, filename, mimetype = get_member_import_template_download_payload()

        self.assertIsInstance(csv_bytes, bytes)
        self.assertEqual(filename, MEMBER_IMPORT_FILENAME)
        self.assertEqual(mimetype, "text/csv; charset=utf-8")

        # Cek apakah dapat didekode dengan UTF-8
        decoded = csv_bytes.decode("utf-8")
        self.assertIn("nama,jenis,keterangan,status,id_anggota", decoded)

    # --------------------------------------------------------------------------
    # 2. AKSES RUTE & PROTEKSI AUTENTIKASI ADMIN
    # --------------------------------------------------------------------------
    def test_04_download_route_unauthenticated_redirects(self):
        """Memverifikasi akses rute download template tanpa login diredirect ke /login."""
        res = self.client.get("/admin/members/impor/template")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

        # Alias /admin/anggota/impor/template
        res_alias = self.client.get("/admin/anggota/impor/template")
        self.assertEqual(res_alias.status_code, 302)

    def test_05_download_route_json_unauthenticated_returns_401(self):
        """Memverifikasi request JSON tanpa login ditolak dengan 401 Unauthorized."""
        res = self.client.get(
            "/admin/members/impor/template",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_06_download_route_authenticated_success(self):
        """Memverifikasi admin terautentikasi dapat mengunduh template CSV dengan header attachment."""
        self._login_admin()

        res = self.client.get("/admin/members/impor/template")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers.get("Content-Type", ""))
        self.assertIn(MEMBER_IMPORT_FILENAME, res.headers.get("Content-Disposition", ""))

        content = res.get_data(as_text=True)
        self.assertIn("nama,jenis,keterangan,status,id_anggota", content)
        self.assertIn("Ahmad Fauzi (Contoh)", content)

    def test_07_guide_route_unauthenticated_redirects(self):
        """Memverifikasi akses rute panduan impor tanpa login diredirect ke /login."""
        res = self.client.get("/admin/members/impor/panduan")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_08_guide_route_authenticated_renders(self):
        """Memverifikasi rute panduan menampilkan penjelasan lengkap dan kebijakan DEC-023."""
        self._login_admin()

        res = self.client.get("/admin/members/impor/panduan")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn("Panduan &amp; Template Impor Anggota", html)
        self.assertIn("DEC-023", html)
        self.assertIn("tidak menyimpan nomor telepon", html.lower())
        self.assertIn("Unduh Template CSV", html)

    # --------------------------------------------------------------------------
    # 3. VALIDASI HEADER & PENGABAIAN KOLOM KELAS/TELEPON (DEC-023)
    # --------------------------------------------------------------------------
    def test_09_header_validation_success_standard(self):
        """Memverifikasi header resmi standar dipetakan tanpa warning."""
        header = ["nama", "jenis", "keterangan", "status", "id_anggota"]
        h_map, warnings = validate_member_import_header(header)

        self.assertEqual(h_map["nama"], 0)
        self.assertEqual(h_map["jenis"], 1)
        self.assertEqual(h_map["keterangan"], 2)
        self.assertEqual(h_map["status"], 3)
        self.assertEqual(h_map["id_anggota"], 4)
        self.assertEqual(len(warnings), 0)

    def test_10_header_validation_missing_required_columns(self):
        """Memverifikasi kegagalan jika kolom wajib (nama atau jenis) hilang."""
        # Tanpa jenis
        with self.assertRaises(ValidationError) as ctx:
            validate_member_import_header(["nama", "keterangan", "status"])
        self.assertIn("jenis", str(ctx.exception).lower())

        # Tanpa nama
        with self.assertRaises(ValidationError) as ctx2:
            validate_member_import_header(["jenis", "keterangan"])
        self.assertIn("nama", str(ctx2.exception).lower())

    def test_11_header_validation_duplicate_columns_rejected(self):
        """Memverifikasi kegagalan jika terdapat header duplikat."""
        with self.assertRaises(ValidationError) as ctx:
            validate_member_import_header(["nama", "jenis", "nama", "status"])
        self.assertIn("duplikat", str(ctx.exception).lower())

    def test_12_ignored_columns_kelas_and_telepon_produce_warnings(self):
        """DEC-023: Memverifikasi kolom kelas dan telepon diabaikan dan menghasilkan peringatan eksplisit."""
        headers = ["nama", "kelas", "telepon", "jenis", "keterangan", "status"]
        h_map, warnings = validate_member_import_header(headers)

        # Indeks kelas dan telepon TIDAK boleh dipetakan ke record anggota
        self.assertNotIn("kelas", h_map)
        self.assertNotIn("telepon", h_map)
        self.assertEqual(h_map["nama"], 0)
        self.assertEqual(h_map["jenis"], 3)

        # Harus menghasilkan 2 peringatan privasi DEC-023
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("kelas" in w.lower() and "DEC-023" in w for w in warnings))
        self.assertTrue(any("telepon" in w.lower() and "DEC-023" in w for w in warnings))

    def test_13_ignored_columns_do_not_leak_values_or_import(self):
        """DEC-023: Memverifikasi isi nilai kelas dan telepon sama sekali tidak diimpor atau dibocorkan."""
        csv_content = (
            "nama,kelas,telepon,jenis,keterangan,status\n"
            "Siti Aisyah,XII RPL 2,081234567890,murid,Rekayasa Perangkat Lunak,aktif\n"
            "Joko Susilo,X TKJ 1,085799998888,murid,Teknik Komputer dan Jaringan,aktif\n"
        )
        conn = library_app.get_db_connection()
        try:
            result = parse_and_validate_member_import_csv(conn, csv_content)
        finally:
            conn.close()

        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["error_rows_count"], 0)
        self.assertTrue(result["can_proceed"])

        # File warnings memuat peringatan DEC-023
        self.assertEqual(len(result["file_warnings"]), 2)
        self.assertTrue(any("kelas" in w for w in result["file_warnings"]))
        self.assertTrue(any("telepon" in w for w in result["file_warnings"]))

        # Verifikasi tiap baris hasil parse: TIDAK ADA key kelas atau telepon
        for r in result["rows"]:
            self.assertNotIn("kelas", r)
            self.assertNotIn("telepon", r)
            # Nilai nomor telepon dan nama kelas tidak boleh ada di string representasi rincian
            self.assertNotIn("081234567890", str(r))
            self.assertNotIn("085799998888", str(r))
            self.assertNotIn("XII RPL 2", str(r))
            self.assertNotIn("X TKJ 1", str(r))
            self.assertEqual(r["status_code"], "OK")

    # --------------------------------------------------------------------------
    # 4. VALIDASI BARIS DATA & KEAMANAN INPUT
    # --------------------------------------------------------------------------
    def test_14_formula_injection_cells_rejected(self):
        """Memverifikasi penolakan formula spreadsheet ('=', '+', '-', '@') pada baris data."""
        csv_content = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "=cmd|' /C calc'!A0,murid,TKJ,aktif,\n"
            "Budi,+guru_umum,Matematika,aktif,\n"
        )
        conn = library_app.get_db_connection()
        try:
            result = parse_and_validate_member_import_csv(conn, csv_content)
        finally:
            conn.close()

        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["error_rows_count"], 2)
        self.assertFalse(result["can_proceed"])

        self.assertEqual(result["rows"][0]["status_code"], "ERROR")
        self.assertIn("formula", result["rows"][0]["errors"][0].lower())

    def test_15_empty_or_whitespace_file_rejected(self):
        """Memverifikasi file kosong atau whitespace memunculkan ValidationError."""
        conn = library_app.get_db_connection()
        try:
            with self.assertRaises(ValidationError) as ctx:
                parse_and_validate_member_import_csv(conn, "   \n\n  \t ")
            self.assertIn("kosong", str(ctx.exception).lower())

            with self.assertRaises(ValidationError):
                parse_and_validate_member_import_csv(conn, b"")
        finally:
            conn.close()

    def test_16_file_exceeding_max_size_rejected(self):
        """Memverifikasi file melebihi batas ukuran maksimum (>2 MiB) ditolak."""
        big_content = b"a" * (MAX_MEMBER_IMPORT_FILE_SIZE_BYTES + 1024)
        conn = library_app.get_db_connection()
        try:
            with self.assertRaises(ValidationError) as ctx:
                parse_and_validate_member_import_csv(conn, big_content)
            self.assertIn("melebihi batas", str(ctx.exception).lower())
        finally:
            conn.close()

    def test_17_file_exceeding_max_rows_rejected(self):
        """Memverifikasi file dengan jumlah baris > MAX_MEMBER_IMPORT_ROWS ditolak."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["nama", "jenis", "keterangan", "status", "id_anggota"])
        for i in range(MAX_MEMBER_IMPORT_ROWS + 5):
            writer.writerow([f"Siswa {i}", "murid", "TKJ", "aktif", ""])

        conn = library_app.get_db_connection()
        try:
            with self.assertRaises(ValidationError) as ctx:
                parse_and_validate_member_import_csv(conn, output.getvalue())
            self.assertIn("melebihi batas", str(ctx.exception).lower())
        finally:
            conn.close()

    def test_18_valid_and_invalid_member_jenis(self):
        """Memverifikasi penanganan jenis anggota yang valid (termasuk alias) dan tidak valid."""
        csv_content = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad,murid,TKJ,aktif,\n"
            "Bambang,siswa,RPL,aktif,\n"
            "Candra,guru kejuruan,Mesin,aktif,\n"
            "Dedi,guru umum,Bahasa,aktif,\n"
            "Eko,staf,Tata Usaha,aktif,\n"
            "Fahmi,laboran,Lab Komputer,aktif,\n"
            "Gani,presiden,Pemerintahan,aktif,\n"  # Invalid role
        )
        conn = library_app.get_db_connection()
        try:
            result = parse_and_validate_member_import_csv(conn, csv_content)
        finally:
            conn.close()

        self.assertEqual(result["total_rows"], 7)
        self.assertEqual(result["valid_rows_count"], 6)
        self.assertEqual(result["error_rows_count"], 1)

        # Baris terakhir harus error karena role 'presiden' tidak didukung
        last_row = result["rows"][6]
        self.assertEqual(last_row["status_code"], "ERROR")
        self.assertIn("tidak valid", last_row["errors"][0].lower())

    def test_19_valid_and_invalid_member_id_format(self):
        """Memverifikasi validasi format ID anggota opsional (Crockford Base32 M-XXXXXX)."""
        csv_content = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Hani,murid,TKJ,aktif,M-2K9X7W\n"   # Valid Crockford Base32
            "Indra,murid,TKJ,aktif,M-INVALID\n"  # Invalid (too long)
            "Joko,murid,TKJ,aktif,C-2K9X7W\n"    # Invalid prefix (C- is for copies)
        )
        conn = library_app.get_db_connection()
        try:
            result = parse_and_validate_member_import_csv(conn, csv_content)
        finally:
            conn.close()

        self.assertEqual(result["total_rows"], 3)
        self.assertEqual(result["error_rows_count"], 2)

        row1 = result["rows"][0]
        self.assertEqual(row1["id_anggota"], "M-2K9X7W")
        # Row 1 warnings indicates ID not yet registered (which is fine for preview)
        self.assertEqual(row1["status_code"], "PERINGATAN")

        row2 = result["rows"][1]
        self.assertEqual(row2["status_code"], "ERROR")
        self.assertIn("format id anggota", row2["errors"][0].lower())

        row3 = result["rows"][2]
        self.assertEqual(row3["status_code"], "ERROR")
        self.assertIn("format id anggota", row3["errors"][0].lower())

    # --------------------------------------------------------------------------
    # 5. JAMINAN ZERO-WRITE & KOMPATIBILITAS
    # --------------------------------------------------------------------------
    def test_20_zero_write_guarantee_on_template_and_validation(self):
        """Memverifikasi bahwa pengunduhan template dan parsing CSV murni zero-write."""
        conn = library_app.get_db_connection()
        try:
            # Hitung jumlah anggota sebelum operasi
            count_before = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
        finally:
            conn.close()

        self._login_admin()

        # Unduh template
        self.client.get("/admin/members/impor/template")

        # Parse CSV
        csv_content = generate_member_import_template_csv()
        conn = library_app.get_db_connection()
        try:
            parse_and_validate_member_import_csv(conn, csv_content)
            count_after = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(count_before, count_after)

    def test_21_legacy_p1_compatibility(self):
        """Memverifikasi kompatibilitas ketika terhubung ke database skema legacy P1."""
        legacy_dir = tempfile.mkdtemp()
        legacy_db = os.path.join(legacy_dir, "legacy_p1_test.db")
        try:
            conn = sqlite3.connect(legacy_db)
            conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT, stok INTEGER);")
            conn.execute("CREATE TABLE peminjaman (id INTEGER PRIMARY KEY, nama_peminjam TEXT);")
            conn.close()

            os.environ["DATABASE_NAME"] = legacy_db
            self._login_admin()

            # Rute panduan tetap render tanpa crash
            res_guide = self.client.get("/admin/members/impor/panduan")
            self.assertEqual(res_guide.status_code, 200)
            self.assertIn("Skema Lama (P1)", res_guide.get_data(as_text=True))

            # Rute download template tetap berjalan 200
            res_tmpl = self.client.get("/admin/members/impor/template")
            self.assertEqual(res_tmpl.status_code, 200)
        finally:
            os.environ["DATABASE_NAME"] = self.test_db
            shutil.rmtree(legacy_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

