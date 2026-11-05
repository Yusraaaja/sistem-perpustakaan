# -*- coding: utf-8 -*-
"""
Rangkaian Pengujian Unit, Keamanan, Integrasi, dan Regresi untuk Task 4-09:
Ekspor Anggota Menyertakan id_anggota (OPEN-011, DEC-023, DEC-020).
Sistem Perpustakaan Digital Sekolah.
"""
import csv
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app as library_app
from policy import (
    MEMBER_EXPORT_HEADERS,
    MEMBER_EXPORT_FILENAME_PREFIX,
    MEMBER_IMPORT_HEADERS,
)
from repositories import member_repo
from services import (
    register_member,
    set_member_status,
    sanitize_export_cell,
    export_members_data,
    generate_members_export_csv,
    get_members_export_download_payload,
    parse_and_validate_member_import_csv,
    preview_member_import_matching,
)


class TestMemberExport(unittest.TestCase):
    """Pengujian komprehensif Task 4-09: Ekspor Data Anggota Menyertakan id_anggota."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_member_export.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        self.secret_key = "test-secret-key-for-task-4-09-export-suite"
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
        """Helper untuk mengeset sesi login admin."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = "admin"
            sess["username"] = username
            sess["admin_username"] = username
            sess["_csrf_token"] = "valid_csrf_token_for_test_4_09"

    def _create_sample_member(self, nama="Budi Santoso", category_id="MC-MURID", status="aktif"):
        """Helper untuk membuat satu anggota uji baru."""
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            m = register_member(conn, nama=nama, category_id=category_id, status=status)
            conn.commit()
            return m
        finally:
            conn.close()

    def _hash_db_file(self) -> str:
        """Menghitung hash SHA-256 file database uji untuk verifikasi Zero-Write."""
        h = hashlib.sha256()
        with open(self.test_db, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().upper()

    # ==========================================================================
    # 1. PENGUJIAN OTORISASI & KEAMANAN AKSES (Section A & C)
    # ==========================================================================

    def test_01_anonymous_user_rejected_on_all_aliases(self):
        """Pengguna anonim (tanpa sesi) ditolak di semua rute dan alias ekspor (302/401)."""
        urls = [
            "/admin/members/export",
            "/admin/members/ekspor",
            "/admin/anggota/export",
            "/admin/anggota/ekspor",
        ]
        with self.client.session_transaction() as sess:
            sess.clear()

        for url in urls:
            # HTML request -> 302 redirect ke /login
            res_html = self.client.get(url, follow_redirects=False)
            self.assertEqual(res_html.status_code, 302, f"GET {url} HTML harus me-redirect ke login")
            self.assertIn("/login", res_html.headers.get("Location", ""))

            # JSON request -> 401 Unauthorized
            res_json = self.client.get(url, headers={"Accept": "application/json"})
            self.assertEqual(res_json.status_code, 401, f"GET {url} JSON harus 401")
            data = res_json.get_json()
            self.assertEqual(data.get("error"), "Unauthorized")

    def test_02_non_admin_roles_rejected(self):
        """Pengguna dengan peran non-admin (misal: 'member', 'guest') ditolak (302/401)."""
        roles = ["member", "guest", "student", "user"]
        for role in roles:
            with self.client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["user_role"] = role

            res_html = self.client.get("/admin/members/export", follow_redirects=False)
            self.assertEqual(res_html.status_code, 302, f"Role {role} harus ditolak ke login")

            res_json = self.client.get("/admin/members/export", headers={"Accept": "application/json"})
            self.assertEqual(res_json.status_code, 401, f"Role {role} harus mengembalikan 401")

    def test_03_missing_empty_invalid_roles_rejected(self):
        """Sesi dengan user_role hilang (None), string kosong, atau tipe data salah ditolak."""
        bad_roles = [None, "", 123, ["admin"], {"role": "admin"}]
        for bad_role in bad_roles:
            with self.client.session_transaction() as sess:
                sess["logged_in"] = True
                if bad_role is not None:
                    sess["user_role"] = bad_role
                else:
                    sess.pop("user_role", None)

            res_html = self.client.get("/admin/members/export", follow_redirects=False)
            self.assertEqual(res_html.status_code, 302)

            res_json = self.client.get("/admin/members/export", headers={"Accept": "application/json"})
            self.assertEqual(res_json.status_code, 401)

    def test_04_legitimate_admin_granted_on_all_aliases(self):
        """Administrator terautentikasi (user_role == 'admin') dapat mengakses semua alias ekspor (200)."""
        self._create_sample_member("Siswa Uji Otorisasi")
        self._login_admin()

        urls = [
            "/admin/members/export",
            "/admin/members/ekspor",
            "/admin/anggota/export",
            "/admin/anggota/ekspor",
        ]
        for url in urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, f"GET {url} harus berhasil (200)")
            self.assertEqual(res.content_type, "text/csv; charset=utf-8")
            self.assertIn("attachment", res.headers.get("Content-Disposition", ""))

    def test_05_login_flow_grants_export_access(self):
        """Admin yang login melalui alur resmi POST /login memperoleh akses ekspor."""
        m = self._create_sample_member("Siswa Alur Login")

        with self.client.session_transaction() as sess:
            sess.clear()
            sess["_csrf_token"] = "valid_csrf_token_test_05"

        login_res = self.client.post(
            "/login",
            data={
                "username": library_app.ADMIN_USERNAME,
                "password": "123",
                "csrf_token": "valid_csrf_token_test_05",
            },
            follow_redirects=False,
        )
        self.assertEqual(login_res.status_code, 302)

        res_export = self.client.get("/admin/members/export")
        self.assertEqual(res_export.status_code, 200)
        self.assertIn(m["id"], res_export.get_data(as_text=True))

    # ==========================================================================
    # 2. PENGUJIAN KONTEN EKSPOR, id_anggota & ZERO PII (DEC-023)
    # ==========================================================================

    def test_06_export_contains_id_anggota_in_header_and_rows(self):
        """Ekspor anggota WAJIB menyertakan kolom id_anggota pada header dan setiap baris data (Task 4-09, OPEN-011)."""
        m1 = self._create_sample_member("Dewi Sartika", category_id="MC-MURID")
        m2 = self._create_sample_member("Ki Hajar Dewantara", category_id="MC-GURU-UMUM")
        self._login_admin()

        res = self.client.get("/admin/members/export")
        self.assertEqual(res.status_code, 200)

        # Parse CSV yang diunduh
        csv_text = res.get_data().decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertGreaterEqual(len(reader), 3)  # 1 header + minimal 2 anggota

        header = [h.strip().lower() for h in reader[0]]
        self.assertIn("id_anggota", header)
        id_idx = header.index("id_anggota")

        exported_ids = [row[id_idx] for row in reader[1:]]
        self.assertIn(m1["id"], exported_ids)
        self.assertIn(m2["id"], exported_ids)

        for mid in exported_ids:
            self.assertTrue(mid.startswith("M-"))
            self.assertEqual(len(mid), 8)

    def test_07_zero_pii_strictly_guaranteed(self):
        """Ekspor sama sekali TIDAK memuat informasi pribadi (nomor telepon/kelas) per DEC-023."""
        self._create_sample_member("Ahmad Subarjo", category_id="MC-MURID")
        self._login_admin()

        res = self.client.get("/admin/members/export")
        csv_text = res.get_data().decode("utf-8-sig")
        header_line = csv_text.splitlines()[0].lower()

        # Tidak boleh ada kolom telepon atau kelas
        forbidden_terms = ["telepon", "no_telp", "no_hp", "phone", "wa", "kelas", "rombel", "tingkat"]
        for term in forbidden_terms:
            self.assertNotIn(term, header_line.split(","))

    def test_08_export_data_matches_database_accurately(self):
        """Data anggota yang diekspor cocok presisi dengan data yang ada di database."""
        m = self._create_sample_member("Joko Widodo", category_id="MC-GURU-JUR", status="aktif")
        self._login_admin()

        res = self.client.get("/admin/members/export")
        csv_text = res.get_data().decode("utf-8-sig")
        reader = list(csv.DictReader(io.StringIO(csv_text)))

        target = next((r for r in reader if r.get("id_anggota") == m["id"]), None)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("nama"), "Joko Widodo")
        self.assertEqual(target.get("jenis"), "guru_jurusan")
        self.assertEqual(target.get("status"), "aktif")

    # ==========================================================================
    # 3. PENGUJIAN SANITASI CSV FORMULA INJECTION (CWE-1236)
    # ==========================================================================

    def test_09_formula_injection_sanitization(self):
        """Karakter pemicu formula spreadsheet (=, +, -, @, \\t, \\r) dinetralisir dengan awalan kutip tunggal (')."""
        self._create_sample_member("=SUM(1,2)", category_id="MC-MURID")
        self._create_sample_member("+62812345678", category_id="MC-MURID")
        self._create_sample_member("@cmd|' /C calc'!A0", category_id="MC-STAF")
        self._create_sample_member("-FormulaNegatif", category_id="MC-TEKNISI")
        self._login_admin()

        res = self.client.get("/admin/members/export")
        csv_text = res.get_data().decode("utf-8-sig")
        reader = list(csv.DictReader(io.StringIO(csv_text)))

        names = [r.get("nama") for r in reader]
        self.assertIn("'=SUM(1,2)", names)
        self.assertIn("'+62812345678", names)
        self.assertIn("'@cmd|' /C calc'!A0", names)
        self.assertIn("'-FormulaNegatif", names)

    def test_10_special_characters_commas_and_quotes_handled(self):
        """Karakter khusus koma, kutip ganda, dan karakter Indonesia ditangani secara valid sesuai RFC 4180."""
        self._create_sample_member('Budi "Hebat", S.Kom.', category_id="MC-GURU-JUR")
        self._create_sample_member("Siti Aisyah, S.Pd., M.Pd.", category_id="MC-GURU-UMUM")
        self._login_admin()

        res = self.client.get("/admin/members/export")
        csv_text = res.get_data().decode("utf-8-sig")
        reader = list(csv.DictReader(io.StringIO(csv_text)))

        names = [r.get("nama") for r in reader]
        self.assertIn('Budi "Hebat", S.Kom.', names)
        self.assertIn("Siti Aisyah, S.Pd., M.Pd.", names)

    # ==========================================================================
    # 4. PENGUJIAN FILTER & KASUS BATAS
    # ==========================================================================

    def test_11_filter_by_status(self):
        """Ekspor dengan filter status hanya menyertakan anggota dengan status yang diminta."""
        m_aktif = self._create_sample_member("Anggota Aktif", status="aktif")
        m_nonaktif = self._create_sample_member("Anggota Nonaktif", status="nonaktif")
        self._login_admin()

        # Filter aktif
        res_aktif = self.client.get("/admin/members/export?status=aktif")
        text_aktif = res_aktif.get_data().decode("utf-8-sig")
        self.assertIn(m_aktif["id"], text_aktif)
        self.assertNotIn(m_nonaktif["id"], text_aktif)

        # Filter nonaktif
        res_nonaktif = self.client.get("/admin/members/export?status=nonaktif")
        text_nonaktif = res_nonaktif.get_data().decode("utf-8-sig")
        self.assertNotIn(m_aktif["id"], text_nonaktif)
        self.assertIn(m_nonaktif["id"], text_nonaktif)

    def test_12_filter_by_category_and_search(self):
        """Ekspor mendukung filter berdasarkan category_id dan query pencarian nama/ID."""
        m_murid = self._create_sample_member("Rani Murid", category_id="MC-MURID")
        m_guru = self._create_sample_member("Bambang Guru", category_id="MC-GURU-UMUM")
        self._login_admin()

        # Filter kategori MC-MURID
        res_cat = self.client.get("/admin/members/export?category_id=MC-MURID")
        text_cat = res_cat.get_data().decode("utf-8-sig")
        self.assertIn(m_murid["id"], text_cat)
        self.assertNotIn(m_guru["id"], text_cat)

        # Filter search query
        res_search = self.client.get("/admin/members/export?q=Bambang")
        text_search = res_search.get_data().decode("utf-8-sig")
        self.assertNotIn(m_murid["id"], text_search)
        self.assertIn(m_guru["id"], text_search)

    def test_13_invalid_status_rejected_400(self):
        """Filter status yang tidak valid menghasilkan penolakan 400 Bad Request untuk API."""
        self._login_admin()
        res = self.client.get("/admin/members/export?status=invalid_status", headers={"Accept": "application/json"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get("ok"))
        self.assertIn("tidak valid", data.get("message", ""))

    def test_14_empty_database_returns_valid_header_only_csv(self):
        """Ketika database belum memiliki anggota, ekspor menghasilkan CSV valid dengan baris header saja."""
        self._login_admin()
        res = self.client.get("/admin/members/export")
        self.assertEqual(res.status_code, 200)

        csv_text = res.get_data().decode("utf-8-sig")
        lines = [l for l in csv_text.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], ",".join(MEMBER_EXPORT_HEADERS))

    # ==========================================================================
    # 5. PENGUJIAN FORMAT BERKAS (CSV, XLSX, JSON) & ZERO-WRITE
    # ==========================================================================

    def test_15_csv_format_utf8_sig_and_headers(self):
        """CSV biner menyertakan UTF-8 BOM, nama file berstempel waktu, dan mimetype benar."""
        self._create_sample_member("Indra Lesmana")
        self._login_admin()

        res = self.client.get("/admin/members/export")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/csv")
        self.assertTrue(res.get_data().startswith(b"\xef\xbb\xbf"))  # BOM UTF-8

        disposition = res.headers.get("Content-Disposition", "")
        self.assertIn("ekspor_anggota_", disposition)
        self.assertTrue(disposition.endswith('.csv"') or disposition.endswith(".csv"))

    def test_16_xlsx_format_support(self):
        """Ekspor dengan format=xlsx menghasilkan berkas Excel valid dengan mimetype yang tepat."""
        self._create_sample_member("Gita Gutawa", category_id="MC-MURID")
        self._login_admin()

        res = self.client.get("/admin/members/export?format=xlsx")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertTrue(len(res.get_data()) > 100)

        disposition = res.headers.get("Content-Disposition", "")
        self.assertIn("ekspor_anggota_", disposition)
        self.assertTrue(disposition.endswith('.xlsx"') or disposition.endswith(".xlsx"))

    def test_17_json_format_support(self):
        """Permintaan dengan Accept application/json atau format=json mengembalikan JSON terstruktur."""
        m = self._create_sample_member("Anisa Rahma", category_id="MC-MURID")
        self._login_admin()

        res = self.client.get("/admin/members/export", headers={"Accept": "application/json"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("total"), 1)
        self.assertEqual(len(data.get("members")), 1)
        self.assertEqual(data.get("members")[0].get("id_anggota"), m["id"])

    def test_18_zero_write_guaranteed(self):
        """Operasi ekspor murni membaca database dan tidak melakukan mutasi apapun (Zero-Write)."""
        self._create_sample_member("Hatta Rajasa")
        self._login_admin()

        hash_before = self._hash_db_file()
        res = self.client.get("/admin/members/export")
        self.assertEqual(res.status_code, 200)
        hash_after = self._hash_db_file()

        self.assertEqual(hash_before, hash_after, "Hash database harus identik sebelum dan setelah ekspor")

    # ==========================================================================
    # 6. PENGUJIAN ROUND-TRIP: HASIL EKSPOR DAPAT DIIMPOR KEMBALI (OPEN-011)
    # ==========================================================================

    def test_19_round_trip_exported_csv_valid_for_import(self):
        """CSV hasil ekspor dapat langsung dibaca dan divalidasi oleh parser impor anggota (Task 4-03/4-04)."""
        m1 = self._create_sample_member("Siti Nurbaya", category_id="MC-MURID")
        m2 = self._create_sample_member("Marah Rusli", category_id="MC-GURU-UMUM")
        self._login_admin()

        # 1. Ekspor CSV
        res = self.client.get("/admin/members/export")
        csv_bytes = res.get_data()

        # 2. Uji parsing impor dengan parse_and_validate_member_import_csv
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            import_res = parse_and_validate_member_import_csv(conn=conn, csv_content=csv_bytes)
            self.assertEqual(import_res["total_rows"], 2)
            self.assertEqual(import_res["error_rows_count"], 0)
            self.assertTrue(import_res["can_proceed"])
            self.assertEqual(import_res["warning_rows_count"], 2)

            # 3. Uji pencocokan pratinjau impor (OPEN-011)
            preview_res = preview_member_import_matching(conn=conn, csv_content=csv_bytes)
            self.assertEqual(len(preview_res["rows"]), 2)
            # Karena id_anggota cocok persis dengan database, status pencocokan harus 'PEMBARUAN'
            for row_preview in preview_res["rows"]:
                self.assertEqual(row_preview["match_status"], "PEMBARUAN")
                self.assertIsNotNone(row_preview["matched_member"])
                self.assertIn(row_preview["matched_member"]["id"], [m1["id"], m2["id"]])
        finally:
            conn.close()

    def test_20_legacy_schema_rejection(self):
        """Database skema legacy P1 ditolak secara aman dengan status 400."""
        legacy_dir = tempfile.mkdtemp()
        legacy_db = os.path.join(legacy_dir, "legacy_p1.db")
        conn = sqlite3.connect(legacy_db)
        conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT);")
        conn.commit()
        conn.close()

        with patch.dict(os.environ, {"DATABASE_NAME": legacy_db}):
            self._login_admin()
            res = self.client.get("/admin/members/export", headers={"Accept": "application/json"})
            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertFalse(data.get("ok"))
            self.assertIn("v2", data.get("message", ""))

        shutil.rmtree(legacy_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

