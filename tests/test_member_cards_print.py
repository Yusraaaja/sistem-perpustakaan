# -*- coding: utf-8 -*-
"""
Rangkaian Pengujian Unit, Keamanan, Integrasi, dan Regresi untuk Task 4-08:
Kartu Anggota Cetak Hemat Tinta dan Cetak Massal (DEC-008, LIB-QR-004, DEC-020, DEC-023).
Sistem Perpustakaan Digital Sekolah.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app as library_app
from policy import (
    MAX_MEMBER_CARDS_PER_PRINT,
    DEFAULT_MEMBER_CARDS_PAGE_SIZE,
)
from repositories import member_repo, audit_repo
from services import (
    register_member,
    set_member_status,
    get_member_qr,
    reissue_member_qr,
    parse_member_ids,
    format_category_label,
    get_member_card_data,
    get_member_cards_for_printing,
    generate_member_qr_token,
    validate_member_token,
    borrow_copies,
    return_copies,
    create_title_with_copies,
)
from services.exceptions import (
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
)


class TestMemberCardsPrint(unittest.TestCase):
    """Pengujian komprehensif Task 4-08: Cetak Kartu Anggota Hemat Tinta & Massal."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, "test_member_cards_print.db")
        os.environ["DATABASE_NAME"] = self.test_db
        os.environ["SQLITE_TIMEOUT"] = "15.0"
        self.secret_key = "test-secret-key-for-task-4-08-member-cards-suite"
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
            sess["_csrf_token"] = "valid_csrf_token_for_test_4_08"
        return "valid_csrf_token_for_test_4_08"

    def _login_non_admin(self, username="user_biasa"):
        """Helper untuk mengeset sesi login non-admin."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = "member"
            sess["username"] = username
            sess["_csrf_token"] = "valid_csrf_token_non_admin"
        return "valid_csrf_token_non_admin"

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

    # --------------------------------------------------------------------------
    # 1. Autentikasi dan Otorisasi
    # --------------------------------------------------------------------------

    def test_01_authenticated_admin_can_access_single_card_html(self):
        """Admin terautentikasi dapat membuka tampilan cetak kartu tunggal secara HTML (GET)."""
        self._login_admin()
        member = self._create_sample_member("Dewi Sartika", category_id="MC-MURID")

        resp = self.client.get(f"/admin/members/{member['id']}/card")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("KARTU ANGGOTA", html)
        self.assertIn("Perpustakaan Digital Sekolah", html)
        self.assertIn("Dewi Sartika", html)
        self.assertIn(member["id"], html)
        self.assertIn("Murid", html)
        self.assertIn("[Status: Aktif]", html)
        self.assertIn("v1", html)
        self.assertIn("<svg", html)  # Menampilkan QR SVG monokrom
        self.assertIn("btnPrintMemberCards", html)  # Tombol cetak
        self.assertIn("no-print", html)  # Kontrol tersembunyi pada saat cetak

    def test_02_single_card_aliases_work_identically(self):
        """Route alias /admin/anggota/<id>/kartu dan /admin/members/<id>/kartu bekerja identik."""
        self._login_admin()
        member = self._create_sample_member("Ahmad Dahlan", category_id="MC-GURU-UMUM")

        resp1 = self.client.get(f"/admin/anggota/{member['id']}/kartu")
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("Ahmad Dahlan", resp1.data.decode("utf-8"))

        resp2 = self.client.get(f"/admin/members/{member['id']}/kartu")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("Ahmad Dahlan", resp2.data.decode("utf-8"))

    def test_03_unauthenticated_user_redirected_to_login(self):
        """Pengguna tanpa login diarahkan (302) ke halaman login."""
        member = self._create_sample_member("Tanpa Login")

        resp_single = self.client.get(f"/admin/members/{member['id']}/card")
        self.assertEqual(resp_single.status_code, 302)
        self.assertIn("/login", resp_single.headers.get("Location", ""))

        resp_batch = self.client.get("/admin/members/cards")
        self.assertEqual(resp_batch.status_code, 302)
        self.assertIn("/login", resp_batch.headers.get("Location", ""))

    def test_04_unauthenticated_api_request_returns_401(self):
        """Permintaan API tanpa autentikasi mengembalikan status 401 Unauthorized."""
        member = self._create_sample_member("API Member")

        resp = self.client.get(
            f"/admin/members/{member['id']}/card",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_05_non_admin_user_rejected(self):
        """Pengguna dengan peran non-admin (misal: 'member') ditolak."""
        self._login_non_admin()
        member = self._create_sample_member("Target Non Admin")

        resp = self.client.get(f"/admin/members/{member['id']}/card")
        self.assertEqual(resp.status_code, 302)

        resp_json = self.client.get(
            f"/admin/members/{member['id']}/card",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp_json.status_code, 401)

    # --------------------------------------------------------------------------
    # 2. Penanganan ID Anggota dan Data Kartu
    # --------------------------------------------------------------------------

    def test_06_single_card_not_found_returns_404(self):
        """ID anggota yang tidak terdaftar menghasilkan 404 Not Found."""
        self._login_admin()

        resp_html = self.client.get("/admin/members/M-999999/card")
        self.assertEqual(resp_html.status_code, 404)

        resp_json = self.client.get(
            "/admin/members/M-999999/card",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp_json.status_code, 404)
        data = resp_json.get_json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "Not Found")

    def test_07_single_card_json_api_response(self):
        """Respons JSON untuk kartu tunggal memuat field lengkap dan token QR kanonikal."""
        self._login_admin()
        member = self._create_sample_member("Ki Hajar Dewantara", category_id="MC-GURU-JUR")

        resp = self.client.get(
            f"/admin/members/{member['id']}/card",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        card = data.get("card", {})
        self.assertEqual(card.get("member_id"), member["id"])
        self.assertEqual(card.get("nama"), "Ki Hajar Dewantara")
        self.assertEqual(card.get("kategori_label"), "Guru Kejuruan")
        self.assertEqual(card.get("qr_version"), 1)
        self.assertIn("token", card)
        self.assertIn("qr_svg", card)
        self.assertTrue(card.get("token").startswith(f"{member['id']}:1:"))

    # --------------------------------------------------------------------------
    # 3. Cetak Massal (Batch Printing)
    # --------------------------------------------------------------------------

    def test_08_batch_cards_html_view(self):
        """Cetak massal kartu via GET menampilkan seluruh kartu yang diminta dalam grid cetak."""
        self._login_admin()
        m1 = self._create_sample_member("Anggota Satu", category_id="MC-MURID")
        m2 = self._create_sample_member("Anggota Dua", category_id="MC-STAF")

        resp = self.client.get(f"/admin/members/cards?member_ids={m1['id']},{m2['id']}")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Anggota Satu", html)
        self.assertIn(m1["id"], html)
        self.assertIn("Anggota Dua", html)
        self.assertIn(m2["id"], html)
        self.assertIn("2 Kartu", html)

    def test_09_batch_cards_aliases_work(self):
        """Route alias cetak massal /admin/anggota/kartu/massal dan /admin/members/kartu/massal bekerja identik."""
        self._login_admin()
        m = self._create_sample_member("Anggota Alias")

        resp1 = self.client.get(f"/admin/anggota/kartu/massal?member_ids={m['id']}")
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("Anggota Alias", resp1.data.decode("utf-8"))

        resp2 = self.client.get(f"/admin/members/kartu/massal?member_ids={m['id']}")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("Anggota Alias", resp2.data.decode("utf-8"))

    def test_10_batch_cards_post_with_csrf(self):
        """POST /admin/members/cards dengan token CSRF valid berhasil merender kartu terpilih."""
        csrf_token = self._login_admin()
        m1 = self._create_sample_member("Member Post 1")
        m2 = self._create_sample_member("Member Post 2")

        resp = self.client.post(
            "/admin/members/cards",
            data={
                "csrf_token": csrf_token,
                "member_ids": [m1["id"], m2["id"]],
            }
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Member Post 1", html)
        self.assertIn("Member Post 2", html)

    def test_11_batch_cards_post_missing_csrf_rejected(self):
        """POST /admin/members/cards tanpa token CSRF valid ditolak (400 Bad Request)."""
        self._login_admin()
        m = self._create_sample_member("Member Without CSRF")

        resp = self.client.post(
            "/admin/members/cards",
            data={
                "csrf_token": "token_palsu_csrf",
                "member_ids": [m["id"]],
            }
        )
        self.assertEqual(resp.status_code, 400)

    def test_12_batch_cards_deduplication_preserves_order(self):
        """Daftar ID yang memuat duplikasi dide-duplikasi di server dengan mempertahankan urutan pertama."""
        self._login_admin()
        m1 = self._create_sample_member("Pertama", category_id="MC-MURID")
        m2 = self._create_sample_member("Kedua", category_id="MC-GURU-UMUM")

        # Kirim duplikat: m2, m1, m2, m1
        raw_input = f"{m2['id']},{m1['id']},{m2['id']},{m1['id']}"
        resp = self.client.get(
            f"/admin/members/cards?member_ids={raw_input}",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        cards = data.get("cards", [])
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["member_id"], m2["id"])
        self.assertEqual(cards[1]["member_id"], m1["id"])

    def test_13_batch_cards_filters_by_category_and_status(self):
        """Cetak massal tanpa list ID spesifik menggunakan filter kategori dan status."""
        self._login_admin()
        m_murid = self._create_sample_member("Siswa Aktif", category_id="MC-MURID", status="aktif")
        m_guru = self._create_sample_member("Guru Aktif", category_id="MC-GURU-UMUM", status="aktif")
        m_nonaktif = self._create_sample_member("Siswa Cuti", category_id="MC-MURID", status="nonaktif")

        # Filter hanya murid aktif
        resp = self.client.get(
            "/admin/members/cards?category_id=MC-MURID&status=aktif",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        ids = [c["member_id"] for c in data.get("cards", [])]
        self.assertIn(m_murid["id"], ids)
        self.assertNotIn(m_guru["id"], ids)
        self.assertNotIn(m_nonaktif["id"], ids)

    def test_14_batch_cards_handles_non_existent_id_gracefully(self):
        """ID tidak ada dalam daftar cetak massal diabaikan tanpa menggagalkan kartu anggota lain."""
        self._login_admin()
        m_valid = self._create_sample_member("Anggota Valid")

        resp = self.client.get(
            f"/admin/members/cards?member_ids=M-P4LSU1,{m_valid['id']},M-P4LSU2",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        cards = data.get("cards", [])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["member_id"], m_valid["id"])

    def test_15_batch_cards_empty_selection_shows_friendly_message(self):
        """Jika tidak ada anggota yang cocok, halaman menampilkan pesan informatif ramah."""
        self._login_admin()

        resp = self.client.get("/admin/members/cards?member_ids=M-UNKNOWN")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Tidak Ada Kartu yang Dapat Dicetak", html)
        self.assertIn("Kembali ke Kelola Anggota", html)

    # --------------------------------------------------------------------------
    # 4. Status Anggota dan Preservasi Keadaan
    # --------------------------------------------------------------------------

    def test_16_inactive_member_card_retains_status_without_auto_activation(self):
        """Pencetakan kartu anggota nonaktif menampilkan label nonaktif tanpa mengubah status di database."""
        self._login_admin()
        member = self._create_sample_member("Anggota Nonaktif", status="nonaktif")

        # Buka tampilan cetak
        resp = self.client.get(f"/admin/members/{member['id']}/card")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("[Status: Nonaktif]", html)

        # Verifikasi status di database tetap 'nonaktif' (Strict Zero-Write on GET)
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            m_db = member_repo.get_member_by_id(conn, member["id"])
            self.assertEqual(m_db["status"], "nonaktif")
        finally:
            conn.close()

    def test_17_reissued_qr_reflected_on_card(self):
        """Penerbitan ulang QR (Task 4-07) langsung tercermin pada kartu yang dicetak (v1 -> v2)."""
        self._login_admin()
        member = self._create_sample_member("Anggota Ganti Kartu")
        self.assertEqual(member["qr_version"], 1)

        # Kartu awal menampilkan v1
        resp_v1 = self.client.get(
            f"/admin/members/{member['id']}/card",
            headers={"Accept": "application/json"}
        )
        card_v1 = resp_v1.get_json()["card"]
        self.assertEqual(card_v1["qr_version"], 1)
        token_v1 = card_v1["token"]

        # Terbitkan ulang QR (Task 4-07)
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            reissue_member_qr(conn, member["id"], reason="Kartu fisik lama hilang di kantin", actor="admin")
            conn.commit()
        finally:
            conn.close()

        # Kartu yang dicetak setelahnya otomatis menggunakan v2
        resp_v2 = self.client.get(
            f"/admin/members/{member['id']}/card",
            headers={"Accept": "application/json"}
        )
        card_v2 = resp_v2.get_json()["card"]
        self.assertEqual(card_v2["qr_version"], 2)
        token_v2 = card_v2["token"]
        self.assertNotEqual(token_v1, token_v2)
        self.assertTrue(token_v2.startswith(f"{member['id']}:2:"))

    def test_18_old_token_from_revoked_card_is_rejected(self):
        """Token fisik lama v1 ditolak sistem, sedangkan token pada kartu baru v2 valid."""
        member = self._create_sample_member("Anggota Uji Token")
        token_v1 = generate_member_qr_token(member["id"], qr_version=1)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            # Token v1 valid saat qr_version=1
            val_before = validate_member_token(token=token_v1, conn=conn)
            self.assertTrue(val_before["valid"])

            # Terbitkan ulang QR -> qr_version=2
            reissue_member_qr(conn, member["id"], reason="Penerbitan kartu baru pengganti", actor="admin")
            conn.commit()

            # Token fisik lama v1 seketika DITOLAK
            val_after = validate_member_token(token=token_v1, conn=conn)
            self.assertFalse(val_after["valid"])
            self.assertEqual(val_after["code"], "TOKEN_REVOKED")

            # Token fisik baru v2 VALID
            token_v2 = generate_member_qr_token(member["id"], qr_version=2)
            val_new = validate_member_token(token=token_v2, conn=conn)
            self.assertTrue(val_new["valid"])
        finally:
            conn.close()

    def test_19_active_loans_remain_intact_and_returnable(self):
        """Pencetakan kartu tidak mengganggu transaksi pinjaman aktif yang sedang berjalan."""
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            title_res = create_title_with_copies(conn, {"judul": "Laskar Pelangi", "pengarang": "Andrea Hirata"}, initial_copies=1)
            copy_id = title_res["copy_ids"][0]
            member = register_member(conn, nama="Peminjam Aktif", category_id="MC-MURID")
            borrow_res = borrow_copies(conn, member_id=member["id"], copy_ids=[copy_id])
            loan_id = borrow_res["id"]
            conn.commit()
        finally:
            conn.close()

        # Admin membuka dan mencetak kartu anggota peminjam
        self._login_admin()
        resp = self.client.get(f"/admin/members/{member['id']}/card")
        self.assertEqual(resp.status_code, 200)

        # Buku tetap dapat dikembalikan tanpa hambatan
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        try:
            ret_res = return_copies(conn, copy_ids=[copy_id])
            self.assertEqual(len(ret_res), 1)
            self.assertIsNotNone(ret_res[0]["returned_at"])
            conn.commit()
        finally:
            conn.close()

    # --------------------------------------------------------------------------
    # 5. Keamanan, Privasi, dan Integritas Basis Data (Zero-Write & Zero PII)
    # --------------------------------------------------------------------------

    def test_20_zero_write_on_get(self):
        """GET untuk melihat kartu tunggal maupun kartu massal tidak mengubah isi database sama sekali."""
        self._login_admin()
        m1 = self._create_sample_member("ZW Member 1")
        m2 = self._create_sample_member("ZW Member 2")

        hash_before = self._hash_db_file()

        # Eksekusi serangkaian request GET
        self.client.get(f"/admin/members/{m1['id']}/card")
        self.client.get(f"/admin/members/{m2['id']}/card")
        self.client.get(f"/admin/members/cards?member_ids={m1['id']},{m2['id']}")
        self.client.get("/admin/members/cards?status=aktif")

        hash_after = self._hash_db_file()
        self.assertEqual(hash_before, hash_after, "Basis data termutasi oleh permintaan GET!")

    def test_21_zero_pii_in_rendered_html_and_json(self):
        """Kartu tidak memuat nomor telepon, kelas, atau secret key (DEC-023, Zero PII)."""
        self._login_admin()
        member = self._create_sample_member("Zero PII Member", category_id="MC-MURID")

        resp = self.client.get(f"/admin/members/{member['id']}/card")
        html = resp.data.decode("utf-8").lower()

        # Tidak memuat kolom data pribadi terlarang
        self.assertNotIn("telepon", html)
        self.assertNotIn("no_hp", html)
        self.assertNotIn("nomor_telepon", html)
        self.assertNotIn("kelas", html)
        self.assertNotIn("rombel", html)
        # Tidak membocorkan secret key
        self.assertNotIn(self.secret_key.lower(), html)

    def test_22_zero_delete_buttons_in_html(self):
        """Halaman kartu tidak memuat tombol atau form hapus anggota (DEC-020: No Hard Delete)."""
        self._login_admin()
        member = self._create_sample_member("No Delete Member")

        resp = self.client.get(f"/admin/members/{member['id']}/card")
        html = resp.data.decode("utf-8")
        self.assertNotIn("btn-danger", html)
        self.assertNotIn("Hapus Anggota", html)
        self.assertNotIn("delete_member", html)
        self.assertNotIn('action="/admin/members/delete', html)
        self.assertNotIn('action="/admin/anggota/hapus', html)

    def test_23_print_css_and_no_print_elements(self):
        """CSS @media print dan @page A4 portrait terdefinisi untuk layout ramah cetak."""
        self._login_admin()
        member = self._create_sample_member("Print Layout Member")

        resp = self.client.get(f"/admin/members/{member['id']}/card")
        html = resp.data.decode("utf-8")
        self.assertIn("@page", html)
        self.assertIn("A4 portrait", html)
        self.assertIn("@media print", html)
        self.assertIn("page-break-inside: avoid", html)
        self.assertIn("no-print", html)

    # --------------------------------------------------------------------------
    # 6. Pengujian Unit Helper Service
    # --------------------------------------------------------------------------

    def test_24_unit_test_parse_member_ids(self):
        """parse_member_ids memproses berbagai bentuk input string dan list dengan aman."""
        # String dipisahkan koma dan spasi
        res1 = parse_member_ids("M-123456, m-234567,   M-345678")
        self.assertEqual(res1, ["M-123456", "M-234567", "M-345678"])

        # String dipisahkan baris baru
        res2 = parse_member_ids("M-AAAAAA\nM-BBBBBB\r\nM-CCCCCC")
        self.assertEqual(res2, ["M-AAAAAA", "M-BBBBBB", "M-CCCCCC"])

        # List dengan duplikat
        res3 = parse_member_ids(["m-1", "M-2", "m-1", "M-3"])
        self.assertEqual(res3, ["M-1", "M-2", "M-3"])

        # Input kosong atau None
        self.assertEqual(parse_member_ids(""), [])
        self.assertEqual(parse_member_ids(None), [])
        self.assertEqual(parse_member_ids([]), [])

    def test_25_unit_test_format_category_label(self):
        """format_category_label menghasilkan label kategori resmi yang ramah cetak."""
        self.assertEqual(format_category_label("murid"), "Murid")
        self.assertEqual(format_category_label("guru_jurusan"), "Guru Kejuruan")
        self.assertEqual(format_category_label("guru_umum"), "Guru Umum")
        self.assertEqual(format_category_label("staf"), "Staf / Tenaga Kependidikan")
        self.assertEqual(format_category_label("teknisi"), "Teknisi / Laboran")
        self.assertEqual(format_category_label("kategori_khusus"), "Kategori Khusus")
        self.assertEqual(format_category_label(None), "Anggota Perpustakaan")

    def test_26_batch_cards_max_limit_enforced(self):
        """Pencetakan dibatasi maksimal MAX_MEMBER_CARDS_PER_PRINT (100)."""
        self._login_admin()
        # Request limit=9999 harus dibatasi ke MAX_MEMBER_CARDS_PER_PRINT
        resp = self.client.get(
            "/admin/members/cards?limit=9999",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertLessEqual(data.get("limit"), MAX_MEMBER_CARDS_PER_PRINT)

    def test_27_legacy_schema_rejection(self):
        """Database skema legacy (P1) ditolak dengan status 400 atau pesan ramah."""
        legacy_dir = tempfile.mkdtemp()
        legacy_db = os.path.join(legacy_dir, "legacy.db")
        # Buat database hanya dengan tabel legacy P1 (tanpa members v2)
        conn = sqlite3.connect(legacy_db)
        conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT);")
        conn.commit()
        conn.close()

        with patch.dict(os.environ, {"DATABASE_NAME": legacy_db}):
            self._login_admin()
            resp = self.client.get(
                "/admin/members/M-123456/card",
                headers={"Accept": "application/json"}
            )
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertFalse(data.get("ok"))
            self.assertIn("v2", data.get("message", ""))

        shutil.rmtree(legacy_dir, ignore_errors=True)

    def test_28_security_missing_or_none_role_rejected_across_all_routes_and_aliases(self):
        """Sesi dengan role yang hilang (None) ditolak di semua endpoint kartu dan alias (302 untuk HTML, 401 untuk JSON)."""
        m = self._create_sample_member("Siswa A")
        single_urls = [
            f"/admin/members/{m['id']}/card",
            f"/admin/anggota/{m['id']}/kartu",
            f"/admin/members/{m['id']}/kartu",
        ]
        batch_urls = [
            "/admin/members/cards",
            "/admin/anggota/kartu/massal",
            "/admin/members/kartu/massal",
        ]
        all_urls = single_urls + batch_urls

        # Kasus 1: logged_in True tetapi user_role None
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["user_role"] = None
            sess["_csrf_token"] = "mock_csrf"

        for url in all_urls:
            # HTML request -> 302 redirect ke /login
            resp_html = self.client.get(url, follow_redirects=False)
            self.assertEqual(resp_html.status_code, 302, f"HTML request to {url} should redirect to login")
            self.assertIn("/login", resp_html.headers.get("Location", ""))

            # JSON request -> 401 Unauthorized
            resp_json = self.client.get(url, headers={"Accept": "application/json"})
            self.assertEqual(resp_json.status_code, 401, f"JSON request to {url} should return 401")
            data = resp_json.get_json()
            self.assertEqual(data.get("error"), "Unauthorized")

        # Kasus 2: logged_in True tetapi key user_role tidak ada sama sekali di session
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess.pop("user_role", None)

        for url in all_urls:
            resp_html = self.client.get(url, follow_redirects=False)
            self.assertEqual(resp_html.status_code, 302)
            resp_json = self.client.get(url, headers={"Accept": "application/json"})
            self.assertEqual(resp_json.status_code, 401)

    def test_29_security_invalid_and_empty_roles_rejected(self):
        """Sesi dengan role kosong, tidak dikenal, atau tipe data tidak valid ditolak (302/401)."""
        m = self._create_sample_member("Siswa B")
        invalid_roles = ["", "guest", "member", "student", "petugas", 123, ["admin"]]

        for bad_role in invalid_roles:
            with self.client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["user_role"] = bad_role

            # Single card
            resp_single = self.client.get(f"/admin/members/{m['id']}/card", follow_redirects=False)
            self.assertEqual(resp_single.status_code, 302, f"Role {bad_role} should be rejected")

            resp_single_json = self.client.get(f"/admin/members/{m['id']}/card", headers={"Accept": "application/json"})
            self.assertEqual(resp_single_json.status_code, 401, f"Role {bad_role} should return 401 for JSON")

            # Batch print
            resp_batch = self.client.get("/admin/members/cards", follow_redirects=False)
            self.assertEqual(resp_batch.status_code, 302, f"Role {bad_role} should be rejected")

            resp_batch_json = self.client.get("/admin/members/cards", headers={"Accept": "application/json"})
            self.assertEqual(resp_batch_json.status_code, 401, f"Role {bad_role} should return 401 for JSON")

    def test_30_security_anonymous_rejected_across_all_routes_and_aliases(self):
        """Pengguna anonim (tanpa sesi) ditolak di semua route dan alias kartu (302/401)."""
        m = self._create_sample_member("Siswa C")
        urls = [
            f"/admin/members/{m['id']}/card",
            f"/admin/anggota/{m['id']}/kartu",
            f"/admin/members/{m['id']}/kartu",
            "/admin/members/cards",
            "/admin/anggota/kartu/massal",
            "/admin/members/kartu/massal",
        ]
        # Pastikan sesi kosong
        with self.client.session_transaction() as sess:
            sess.clear()

        for url in urls:
            resp_html = self.client.get(url, follow_redirects=False)
            self.assertEqual(resp_html.status_code, 302)
            self.assertIn("/login", resp_html.headers.get("Location", ""))

            resp_json = self.client.get(url, headers={"Accept": "application/json"})
            self.assertEqual(resp_json.status_code, 401)

    def test_31_security_legitimate_admin_granted_on_all_aliases(self):
        """Admin terautentikasi (user_role == 'admin') dapat mengakses semua rute dan alias secara sukses (200)."""
        m = self._create_sample_member("Siswa D")
        self._login_admin()

        single_urls = [
            f"/admin/members/{m['id']}/card",
            f"/admin/anggota/{m['id']}/kartu",
            f"/admin/members/{m['id']}/kartu",
        ]
        for url in single_urls:
            resp_html = self.client.get(url)
            self.assertEqual(resp_html.status_code, 200, f"GET {url} HTML should return 200")
            self.assertIn(m["id"], resp_html.get_data(as_text=True))

            resp_json = self.client.get(url, headers={"Accept": "application/json"})
            self.assertEqual(resp_json.status_code, 200, f"GET {url} JSON should return 200")
            data = resp_json.get_json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("card", {}).get("member_id"), m["id"])

        batch_urls = [
            "/admin/members/cards",
            "/admin/anggota/kartu/massal",
            "/admin/members/kartu/massal",
        ]
        for url in batch_urls:
            resp_html = self.client.get(f"{url}?member_ids={m['id']}")
            self.assertEqual(resp_html.status_code, 200, f"GET {url} HTML should return 200")

            resp_json = self.client.get(f"{url}?member_ids={m['id']}", headers={"Accept": "application/json"})
            self.assertEqual(resp_json.status_code, 200, f"GET {url} JSON should return 200")
            data = resp_json.get_json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("total"), 1)

    def test_32_security_login_endpoint_sets_admin_role_and_grants_access(self):
        """Proses login admin resmi menyetel session['user_role'] = 'admin' dan membuka akses fitur kartu."""
        m = self._create_sample_member("Siswa E")

        # Set CSRF token pada sesi awal
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["_csrf_token"] = "valid_csrf_token_test_32"

        # Login via POST /login
        login_resp = self.client.post(
            "/login",
            data={
                "username": library_app.ADMIN_USERNAME,
                "password": "123",
                "csrf_token": "valid_csrf_token_test_32",
            },
            follow_redirects=False,
        )
        self.assertEqual(login_resp.status_code, 302)

        # Verifikasi session memiliki user_role 'admin'
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("logged_in"))
            self.assertEqual(sess.get("user_role"), "admin")

        # Akses kartu tunggal
        res_card = self.client.get(f"/admin/members/{m['id']}/card")
        self.assertEqual(res_card.status_code, 200)

        # Akses cetak massal
        res_batch = self.client.get("/admin/members/cards")
        self.assertEqual(res_batch.status_code, 200)


if __name__ == "__main__":
    unittest.main()
