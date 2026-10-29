# -*- coding: utf-8 -*-
"""
Suite Pengujian Komprehensif Task 4-04:
Pratinjau Pencocokan Impor Anggota (OPEN-011).

Memverifikasi:
1. Pencocokan ID tepat (PEMBARUAN) dengan kalkulasi diff atribut (nama, kategori, status).
2. ID tidak ditemukan di basis data (TIDAK_DITEMUKAN -> status ERROR, hanya boleh LEWATI).
3. Format ID tidak valid (ERROR).
4. Tanpa ID: 0 nama cocok di database -> BARU (BUAT_BARU / LEWATI).
5. Tanpa ID: 1 nama cocok di database -> KEMUNGKINAN_SAMA (PERBARUI / BUAT_BARU / LEWATI).
6. Tanpa ID: >1 nama cocok di database -> AMBIGU (PILIH_KANDIDAT / BUAT_BARU / LEWATI).
7. Konflik duplikasi ID intra-file ditandai error untuk kedua baris.
8. Peringatan duplikasi nama intra-file tanpa ID.
9. Sanitasi potensi injeksi formula spreadsheet.
10. Validasi keputusan petugas (validate_member_import_decisions): keputusan valid lolos.
11. Validasi keputusan petugas: aksi tidak diizinkan atau target kandidat salah ditolak.
12. Validasi keputusan petugas: tabrakan target ganda (target collision) dicegah.
13. Kepatuhan privasi DEC-023: kolom kelas/telepon diabaikan dengan peringatan tanpa mengekspos PII.
14. Akses unauthenticated atau bukan admin ditolak (302 redirect untuk HTML, 401 untuk JSON).
15. Jaminan Zero-Write: Tidak ada penulisan atau perubahan database sama sekali.
16. Kompatibilitas skema legacy P1.
"""
import csv
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

import app as library_app
from policy import (
    MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
    MAX_MEMBER_IMPORT_ROWS,
    MEMBER_MATCH_STATUSES,
    MEMBER_ACTION_CHOICES,
)
from services import (
    ValidationError,
    preview_member_import_matching,
    validate_member_import_decisions,
)


class TestMemberImportPreview(unittest.TestCase):
    """Pengujian Unit & Integrasi Task 4-04 (OPEN-011)."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_member_preview.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        os.environ["SECRET_KEY"] = "test-secret-key-for-member-preview-suite-2026"

        library_app.app.config["TESTING"] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2 terisolasi dengan data uji
        self._init_v2_db(self.test_db)

    def tearDown(self):
        os.environ.pop("DATABASE_NAME", None)
        os.environ.pop("SQLITE_TIMEOUT", None)
        os.environ.pop("SECRET_KEY", None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _init_v2_db(self, db_path: str):
        """Membuat struktur tabel v2 bersih dan data awal anggota uji."""
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

        # Seed data kategori default
        from services import seed_member_categories
        seed_member_categories(conn)

        # Seed anggota database untuk pengujian pencocokan OPEN-011 (format Crockford Base32 M-XXXXXX):
        # 1. M-222222: Ahmad Fauzi (MC-MURID, aktif) -> untuk uji PEMBARUAN ID tepat
        # 2. M-222223: Citra Lestari (MC-GURU-UMUM, aktif) -> untuk uji 1 nama cocok (KEMUNGKINAN_SAMA)
        # 3. M-222224 & M-222225: Dewi Sartika (MC-MURID & MC-GURU-JUR) -> untuk uji >1 nama cocok (AMBIGU)
        # 4. M-222226: Eko Prasetyo (MC-MURID, nonaktif) -> untuk uji perubahan status
        conn.execute("""
            INSERT INTO members (id, nama, status, category_id, qr_version, created_at, updated_at)
            VALUES 
            ('M-222222', 'Ahmad Fauzi', 'aktif', 'MC-MURID', 1, datetime('now'), datetime('now')),
            ('M-222223', 'Citra Lestari', 'aktif', 'MC-GURU-UMUM', 1, datetime('now'), datetime('now')),
            ('M-222224', 'Dewi Sartika', 'aktif', 'MC-MURID', 1, datetime('now'), datetime('now')),
            ('M-222225', 'Dewi Sartika', 'aktif', 'MC-GURU-JUR', 1, datetime('now'), datetime('now')),
            ('M-222226', 'Eko Prasetyo', 'nonaktif', 'MC-MURID', 1, datetime('now'), datetime('now'))
        """)
        conn.commit()
        conn.close()

    def _login_admin(self):
        """Helper login admin untuk session test client."""
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess["logged_in"] = True
            sess["admin_username"] = library_app.ADMIN_USERNAME
            sess["user_role"] = "admin"
            sess["last_active"] = time.time()
            sess["_csrf_token"] = "valid-csrf-token-preview-test"

    # ==========================================================================
    # BAGIAN 1: PENCOCOKAN DENGAN ID (PEMBARUAN & TIDAK DITEMUKAN)
    # ==========================================================================

    def test_01_exact_id_match_classified_as_pembaruan_with_diff(self):
        """ID cocok di database -> PEMBARUAN, menghitung diff, aksi PERBARUI / LEWATI."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi Updated,guru_umum,Keterangan baru,nonaktif,M-222222\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["total_rows"], 1)
            self.assertEqual(res["pembaruan_count"], 1)
            self.assertEqual(res["baru_count"], 0)
            self.assertEqual(res["error_rows_count"], 0)

            row = res["rows"][0]
            self.assertEqual(row["match_status"], "PEMBARUAN")
            self.assertEqual(row["status_code"], "OK" if not row["diff"] else "PERINGATAN")
            self.assertEqual(row["available_actions"], ["PERBARUI", "LEWATI"])
            self.assertEqual(row["selected_action"], "PERBARUI")

            # Memeriksa diff
            self.assertIsNotNone(row["matched_member"])
            self.assertEqual(row["matched_member"]["id"], "M-222222")
            diff = row["diff"]
            self.assertIn("nama", diff)
            self.assertEqual(diff["nama"]["db_val"], "Ahmad Fauzi")
            self.assertEqual(diff["nama"]["csv_val"], "Ahmad Fauzi Updated")
            self.assertIn("status", diff)
            self.assertEqual(diff["status"]["db_val"], "aktif")
            self.assertEqual(diff["status"]["csv_val"], "nonaktif")
            self.assertIn("category_id", diff)
            self.assertEqual(diff["category_id"]["db_val"], "murid")
            self.assertEqual(diff["category_id"]["csv_val"], "guru_umum")
        finally:
            conn.close()

    def test_02_id_not_found_classified_as_tidak_ditemukan_and_error(self):
        """ID format valid tetapi tidak ada di database -> TIDAK_DITEMUKAN, status ERROR, hanya boleh LEWATI."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Baru,murid,,aktif,M-999999\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["total_rows"], 1)
            self.assertEqual(res["tidak_ditemukan_count"], 1)
            self.assertEqual(res["pembaruan_count"], 0)

            row = res["rows"][0]
            self.assertEqual(row["match_status"], "TIDAK_DITEMUKAN")
            self.assertEqual(row["status_code"], "ERROR")
            self.assertEqual(row["available_actions"], ["LEWATI"])
            self.assertEqual(row["selected_action"], "LEWATI")
            self.assertTrue(any("tidak ditemukan" in err.lower() for err in row["errors"]))
        finally:
            conn.close()

    def test_03_invalid_id_format_marked_as_error(self):
        """Format ID salah (bukan M-XXXXXX Crockford Base32) -> ERROR, hanya boleh LEWATI."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Test,murid,,aktif,CUSTOM-123\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            row = res["rows"][0]
            self.assertEqual(row["match_status"], "ERROR")
            self.assertEqual(row["status_code"], "ERROR")
            self.assertEqual(row["available_actions"], ["LEWATI"])
            self.assertTrue(any("format id anggota" in err.lower() for err in row["errors"]))
        finally:
            conn.close()

    # ==========================================================================
    # BAGIAN 2: PENCOCOKAN TANPA ID (BARU, KEMUNGKINAN SAMA, AMBIGU)
    # ==========================================================================

    def test_04_no_id_zero_matches_classified_as_baru(self):
        """Tanpa ID dan 0 nama cocok di database -> BARU (BUAT_BARU / LEWATI)."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Gilang Ramadhan,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["baru_count"], 1)
            self.assertEqual(res["pembaruan_count"], 0)

            row = res["rows"][0]
            self.assertEqual(row["match_status"], "BARU")
            self.assertEqual(row["status_code"], "OK")
            self.assertEqual(row["available_actions"], ["BUAT_BARU", "LEWATI"])
            self.assertEqual(row["selected_action"], "BUAT_BARU")
            self.assertEqual(len(row["candidates"]), 0)
        finally:
            conn.close()

    def test_05_no_id_one_name_match_classified_as_kemungkinan_sama(self):
        """Tanpa ID dan tepat 1 nama cocok di database -> KEMUNGKINAN_SAMA."""
        # 'citra lestari' huruf kecil, di DB 'Citra Lestari' -> case-insensitive match
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "citra lestari,guru_umum,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["kemungkinan_sama_count"], 1)

            row = res["rows"][0]
            self.assertEqual(row["match_status"], "KEMUNGKINAN_SAMA")
            self.assertEqual(row["status_code"], "PERINGATAN")
            self.assertEqual(row["available_actions"], ["PERBARUI", "BUAT_BARU", "LEWATI"])
            self.assertEqual(row["selected_action"], "PERBARUI")
            self.assertEqual(len(row["candidates"]), 1)
            self.assertEqual(row["candidates"][0]["id"], "M-222223")
        finally:
            conn.close()

    def test_06_no_id_multiple_name_matches_classified_as_ambigu(self):
        """Tanpa ID dan >1 nama cocok di database -> AMBIGU dengan semua kandidat."""
        # 'Dewi Sartika' ada 2 orang di DB (M-222224 dan M-222225)
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Dewi Sartika,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["ambigu_count"], 1)

            row = res["rows"][0]
            self.assertEqual(row["match_status"], "AMBIGU")
            self.assertEqual(row["status_code"], "PERINGATAN")
            self.assertEqual(row["available_actions"], ["PILIH_KANDIDAT", "BUAT_BARU", "LEWATI"])
            self.assertEqual(row["selected_action"], "PILIH_KANDIDAT")
            self.assertEqual(len(row["candidates"]), 2)
            candidate_ids = [c["id"] for c in row["candidates"]]
            self.assertIn("M-222224", candidate_ids)
            self.assertIn("M-222225", candidate_ids)
        finally:
            conn.close()

    # ==========================================================================
    # BAGIAN 3: KONFLIK INTRA-FILE & SANITASI
    # ==========================================================================

    def test_07_duplicate_id_in_file_causes_in_file_conflict_error(self):
        """ID ganda pada file yang sama ditandai sebagai in-file conflict error pada kedua baris."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi 1,murid,,aktif,M-222222\n"
            "Ahmad Fauzi 2,murid,,aktif,M-222222\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["error_rows_count"], 2)

            for row in res["rows"]:
                self.assertEqual(row["match_status"], "ERROR")
                self.assertEqual(row["status_code"], "ERROR")
                self.assertEqual(row["available_actions"], ["LEWATI"])
                self.assertTrue(any("konflik berkas: id anggota" in err.lower() for err in row["errors"]))
        finally:
            conn.close()

    def test_08_duplicate_name_in_file_adds_warning(self):
        """Nama ganda tanpa ID dalam file yang sama memicu peringatan, bukan error."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Kembar,murid,,aktif,\n"
            "Siswa Kembar,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["warning_rows_count"], 2)
            self.assertEqual(res["baru_count"], 2)

            for row in res["rows"]:
                self.assertEqual(row["match_status"], "BARU")
                self.assertTrue(any("muncul berulang" in w.lower() for w in row["warnings"]))
        finally:
            conn.close()

    def test_09_formula_injection_row_marked_as_error(self):
        """Karakter berbahaya awalan formula spreadsheet ditolak dengan status ERROR."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "=cmd|' /C calc'!A0,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            row = res["rows"][0]
            self.assertEqual(row["match_status"], "ERROR")
            self.assertEqual(row["status_code"], "ERROR")
            self.assertEqual(row["available_actions"], ["LEWATI"])
        finally:
            conn.close()

    # ==========================================================================
    # BAGIAN 4: VALIDASI KEPUTUSAN PETUGAS (validate_member_import_decisions)
    # ==========================================================================

    def test_10_validate_member_import_decisions_valid_pass(self):
        """Keputusan valid sesuai available_actions berhasil diverifikasi."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi,murid,,aktif,M-222222\n"
            "Siswa Baru,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            decisions = {
                2: {"action": "PERBARUI"},
                3: {"action": "BUAT_BARU"},
            }
            is_valid, errors, validated = validate_member_import_decisions(res, decisions)
            self.assertTrue(is_valid)
            self.assertEqual(len(errors), 0)
            self.assertEqual(validated[2]["action"], "PERBARUI")
            self.assertEqual(validated[2]["target_member_id"], "M-222222")
            self.assertEqual(validated[3]["action"], "BUAT_BARU")
        finally:
            conn.close()

    def test_11_validate_member_import_decisions_invalid_action_rejected(self):
        """Aksi tidak sah untuk suatu baris ditolak."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Siswa Baru,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            # Baris BARU tidak punya opsi PERBARUI
            decisions = {
                2: {"action": "PERBARUI"}
            }
            is_valid, errors, _ = validate_member_import_decisions(res, decisions)
            self.assertFalse(is_valid)
            self.assertTrue(any("tidak tersedia untuk baris 2" in e.lower() for e in errors))
        finally:
            conn.close()

    def test_12_validate_member_import_decisions_target_collision_rejected(self):
        """Dua baris mengarahkan pembaruan ke ID anggota database yang sama ditolak (target collision)."""
        # Baris 1 mengupdate M-222222 via ID
        # Baris 2 KEMUNGKINAN_SAMA (nama Ahmad Fauzi tanpa ID) memilih mengupdate M-222222 juga
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi,murid,,aktif,M-222222\n"
            "Ahmad Fauzi,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            decisions = {
                2: {"action": "PERBARUI", "target_member_id": "M-222222"},
                3: {"action": "PERBARUI", "target_member_id": "M-222222"},
            }
            is_valid, errors, _ = validate_member_import_decisions(res, decisions)
            self.assertFalse(is_valid)
            self.assertTrue(any("konflik target pembaruan" in e.lower() for e in errors))
        finally:
            conn.close()

    # ==========================================================================
    # BAGIAN 5: KEBIJAKAN PRIVASI DEC-023 (PENGABAIAN KELAS & TELEPON)
    # ==========================================================================

    def test_13_ignored_pii_columns_kelas_and_telepon_safe(self):
        """Kolom kelas dan telepon diabaikan aman, tidak disimpan, dan memicu warning DEC-023."""
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota,kelas,telepon\n"
            "Siswa Rahasia,murid,Catatan,aktif,,XII-RPL-1,08123456789\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["total_rows"], 1)
            row = res["rows"][0]
            self.assertEqual(row["match_status"], "BARU")
            # Tidak ada PII di raw_data maupun clean_data
            self.assertNotIn("telepon", row["raw_data"])
            self.assertNotIn("kelas", row["raw_data"])
            self.assertNotIn("telepon", row["clean_data"])
            self.assertNotIn("kelas", row["clean_data"])
            # Peringatan muncul di file_warnings
            self.assertTrue(any("diabaikan" in w.lower() for w in res["file_warnings"]))
        finally:
            conn.close()

    # ==========================================================================
    # BAGIAN 6: INTEGRASI ROUTE & AUTENTIKASI ADMIN
    # ==========================================================================

    def test_14_unauthenticated_access_rejected(self):
        """Akses tanpa autentikasi admin ditolak: 302 redirect untuk HTML, 401 untuk JSON."""
        # GET tanpa login -> 302 ke login
        res_get = self.client.get("/admin/members/impor/preview")
        self.assertEqual(res_get.status_code, 302)
        self.assertIn("/login", res_get.headers.get("Location", ""))

        # POST JSON tanpa session login (dengan CSRF token) -> 401 Unauthorized
        with self.client.session_transaction() as sess:
            sess["logged_in"] = False
            sess["_csrf_token"] = "valid-csrf-token-preview-test"

        res_post_json = self.client.post(
            "/admin/members/impor/preview",
            json={"raw_csv_b64": "bmFtYSxqZW5pcyxrZXRlcmFuZ2FuLHN0YXR1cyxpZF9hbmdnb3RhCg=="},
            headers={
                "Accept": "application/json",
                "X-CSRFToken": "valid-csrf-token-preview-test",
            },
        )
        self.assertEqual(res_post_json.status_code, 401)

    def test_15_authenticated_get_redirects_to_panduan(self):
        """GET request oleh admin dialihkan ke panduan impor."""
        self._login_admin()
        res = self.client.get("/admin/members/impor/preview")
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.headers.get("Location", "").endswith("/panduan"))

    def test_16_authenticated_post_returns_preview_view(self):
        """POST file CSV oleh admin menampilkan template pratinjau."""
        self._login_admin()
        csv_bytes = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi,murid,,aktif,M-222222\n"
            "Siswa Anyar,murid,,aktif,\n"
        ).encode("utf-8")

        res = self.client.post(
            "/admin/members/impor/preview",
            data={
                "csv_file": (io.BytesIO(csv_bytes), "test_anggota.csv"),
                "csrf_token": "valid-csrf-token-preview-test",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")
        self.assertIn("Hasil Pratinjau &amp; Pencocokan Impor Anggota", content)
        self.assertIn("M-222222", content)
        self.assertIn("Siswa Anyar", content)
        self.assertIn("PEMBARUAN", content)
        self.assertIn("BARU", content)

    def test_17_authenticated_post_json_returns_data_and_supports_decision_validation(self):
        """POST JSON mengembalikan ringkasan data dan memvalidasi keputusan petugas."""
        self._login_admin()
        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi,murid,,aktif,M-222222\n"
        )
        res = self.client.post(
            "/admin/members/impor/preview",
            json={
                "csv_content": csv_text,
                "decisions": {
                    "2": {"action": "PERBARUI"}
                }
            },
            headers={
                "Accept": "application/json",
                "X-CSRFToken": "valid-csrf-token-preview-test",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("validated_decisions", data)
        self.assertEqual(data["validated_decisions"]["2"]["action"], "PERBARUI")

    # ==========================================================================
    # BAGIAN 7: JAMINAN ZERO-WRITE & KOMPATIBILITAS SKEMA
    # ==========================================================================

    def test_18_zero_write_guarantee_db_untouched(self):
        """Memverifikasi bahwa eksekusi preview sama sekali tidak mengubah baris dalam tabel database."""
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        members_before = cursor.execute("SELECT id, nama, status, category_id FROM members ORDER BY id").fetchall()
        count_before = cursor.execute("SELECT count(*) FROM members").fetchone()[0]
        conn.close()

        csv_text = (
            "nama,jenis,keterangan,status,id_anggota\n"
            "Ahmad Fauzi Baru,murid,edit,nonaktif,M-222222\n"
            "Anggota Baru 1,murid,,aktif,\n"
            "Anggota Baru 2,murid,,aktif,\n"
        )
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            preview_member_import_matching(conn, csv_text)
        finally:
            conn.close()

        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        members_after = cursor.execute("SELECT id, nama, status, category_id FROM members ORDER BY id").fetchall()
        count_after = cursor.execute("SELECT count(*) FROM members").fetchone()[0]
        conn.close()

        self.assertEqual(count_before, count_after)
        self.assertEqual(members_before, members_after)

    def test_19_legacy_p1_schema_fallback(self):
        """Memverifikasi bahwa database skema lama (P1: tabel user / buku tanpa members) tidak crash."""
        p1_db = os.path.join(self.test_dir, "legacy_p1.db")
        conn = sqlite3.connect(p1_db)
        # Buat tabel skema P1
        conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT);")
        conn.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, nama TEXT, username TEXT);")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(p1_db)
        conn.row_factory = sqlite3.Row
        try:
            csv_text = (
                "nama,jenis,keterangan,status,id_anggota\n"
                "Siswa P1,murid,,aktif,\n"
            )
            res = preview_member_import_matching(conn, csv_text)
            self.assertEqual(res["total_rows"], 1)
            # Pada P1, karena tidak ada tabel members, nama tidak ditemukan -> BARU
            self.assertEqual(res["rows"][0]["match_status"], "BARU")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
