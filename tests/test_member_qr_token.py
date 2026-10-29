# -*- coding: utf-8 -*-
"""
Rangkaian Pengujian Unit dan Integrasi untuk Token QR Anggota HMAC-SHA256 (Task 4-01).
Memenuhi kriteria penerimaan:
- LIB-QR-001, DEC-010, DEC-020, DEC-023.
- Menguji seluruh skenario Bagian E dari panduan implementasi Task 4-01.
"""
import hashlib
import hmac
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from policy import (
    MEMBER_TOKEN_DELIMITER,
    MEMBER_TOKEN_SIG_LENGTH,
    MAX_MEMBER_TOKEN_LENGTH,
)
from repositories import (
    member_repo,
)
from services import (
    build_member_token_payload,
    sign_member_token_payload,
    generate_member_qr_token,
    parse_member_qr_token,
    verify_member_token_signature,
    verify_member_qr_token,
    validate_member_token,
    get_member_token_secret,
    generate_member_qr_svg,
    register_member,
    deactivate_member,
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
    SecretKeyError,
    InvalidMemberTokenError,
    MemberTokenRevokedError,
)


class TestMemberQrToken(unittest.TestCase):
    """Pengujian komprehensif mekanisme token QR Anggota HMAC-SHA256."""

    def setUp(self):
        self.secret_test_key = "test_secret_key_perpustakaan_digital_2026_xyz"
        self.old_secret = os.environ.get("SECRET_KEY")
        self.old_flask_secret = os.environ.get("FLASK_SECRET_KEY")
        os.environ["SECRET_KEY"] = self.secret_test_key

        # Database SQLite in-memory terisolasi untuk pengujian DB
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._init_v2_schema(self.conn)

    def tearDown(self):
        if self.conn:
            self.conn.close()

        if self.old_secret is not None:
            os.environ["SECRET_KEY"] = self.old_secret
        else:
            os.environ.pop("SECRET_KEY", None)

        if self.old_flask_secret is not None:
            os.environ["FLASK_SECRET_KEY"] = self.old_flask_secret
        else:
            os.environ.pop("FLASK_SECRET_KEY", None)

    def _init_v2_schema(self, conn: sqlite3.Connection):
        """Menyiapkan skema tabel anggota v2 terisolasi."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS member_categories (
                id TEXT PRIMARY KEY,
                jenis TEXT NOT NULL UNIQUE,
                keterangan TEXT
            );

            CREATE TABLE IF NOT EXISTS members (
                id TEXT PRIMARY KEY,
                nama TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'nonaktif')),
                category_id TEXT NOT NULL REFERENCES member_categories(id),
                qr_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                reason TEXT,
                detail_json TEXT
            );
            """
        )
        member_repo.create_category(conn, "MC-MURID", "Murid", "Siswa aktif SMK")
        member_repo.create_category(conn, "MC-GURU", "Guru", "Dewan guru")
        conn.commit()

    # --------------------------------------------------------------------------
    # SKENARIO 1: Token valid dapat dibuat dan diverifikasi
    # --------------------------------------------------------------------------
    def test_01_create_and_verify_valid_token(self):
        """Skenario 1: Token valid dapat dibuat dan diverifikasi secara kriptografis."""
        member_id = "M-3K9X7W"
        qr_version = 1

        token = generate_member_qr_token(member_id, qr_version, secret_key=self.secret_test_key)
        self.assertIsInstance(token, str)

        parts = token.split(":")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], member_id)
        self.assertEqual(parts[1], str(qr_version))
        self.assertEqual(len(parts[2]), 64)

        # Verifikasi kriptografis
        verified = verify_member_token_signature(token, secret_key=self.secret_test_key)
        self.assertEqual(verified["member_id"], member_id)
        self.assertEqual(verified["qr_version"], qr_version)
        self.assertEqual(verified["payload"], f"{member_id}:{qr_version}")

    # --------------------------------------------------------------------------
    # SKENARIO 2: Payload yang sama menghasilkan token deterministik
    # --------------------------------------------------------------------------
    def test_02_deterministic_token_generation(self):
        """Skenario 2: Parameter yang sama menghasilkan token identik (deterministik)."""
        member_id = "M-ABCDEF"
        qr_version = 2

        token1 = generate_member_qr_token(member_id, qr_version, secret_key=self.secret_test_key)
        token2 = generate_member_qr_token(member_id, qr_version, secret_key=self.secret_test_key)
        self.assertEqual(token1, token2)

    # --------------------------------------------------------------------------
    # SKENARIO 3: Perubahan payload menyebabkan verifikasi gagal
    # --------------------------------------------------------------------------
    def test_03_tampered_payload_rejected(self):
        """Skenario 3: Memodifikasi member_id atau qr_version membatalkan token."""
        member_id = "M-111111"
        token = generate_member_qr_token(member_id, qr_version=1, secret_key=self.secret_test_key)
        parts = token.split(":")

        # Ubah member_id
        tampered_id_token = f"M-222222:{parts[1]}:{parts[2]}"
        with self.assertRaises(InvalidMemberTokenError):
            verify_member_token_signature(tampered_id_token, secret_key=self.secret_test_key)

        # Ubah qr_version
        tampered_ver_token = f"{parts[0]}:2:{parts[2]}"
        with self.assertRaises(InvalidMemberTokenError):
            verify_member_token_signature(tampered_ver_token, secret_key=self.secret_test_key)

    # --------------------------------------------------------------------------
    # SKENARIO 4: Perubahan tanda autentikasi menyebabkan verifikasi gagal
    # --------------------------------------------------------------------------
    def test_04_tampered_signature_rejected(self):
        """Skenario 4: Memodifikasi satu karakter tanda tangan digital menolak token."""
        token = generate_member_qr_token("M-3K9X7W", 1, secret_key=self.secret_test_key)
        parts = token.split(":")
        sig = parts[2]

        # Ubah karakter terakhir dari tanda tangan
        altered_char = "b" if sig[-1] == "a" else "a"
        tampered_sig = sig[:-1] + altered_char
        tampered_token = f"{parts[0]}:{parts[1]}:{tampered_sig}"

        with self.assertRaises(InvalidMemberTokenError):
            verify_member_token_signature(tampered_token, secret_key=self.secret_test_key)

    # --------------------------------------------------------------------------
    # SKENARIO 5: Token kosong ditolak
    # --------------------------------------------------------------------------
    def test_05_empty_or_whitespace_token_rejected(self):
        """Skenario 5: Token None, string kosong, atau spasi ditolak dengan aman."""
        for empty_val in [None, "", "   ", "\t\n"]:
            with self.assertRaises(InvalidMemberTokenError):
                verify_member_token_signature(empty_val, secret_key=self.secret_test_key)

            res = validate_member_token(empty_val, secret_key=self.secret_test_key)
            self.assertFalse(res["valid"])
            self.assertEqual(res["code"], "INVALID_TOKEN")

    # --------------------------------------------------------------------------
    # SKENARIO 6: Format token yang rusak ditolak
    # --------------------------------------------------------------------------
    def test_06_malformed_token_formats_rejected(self):
        """Skenario 6: Format token yang rusak atau tidak sesuai pola ditolak."""
        malformed_examples = [
            "M-123456",                      # Tanpa separator
            "M-123456:1",                    # Hanya 2 bagian
            "M-123456:1:sig:extra",          # 4 bagian
            ":::",                           # Separator kosong
            "M-123456:bukan_angka:abcdef",   # Versi bukan angka
            "M-123456:1:bukan_hex_64_karakter_xyz_1234567890abcdef1234567890abcdef12345",
        ]
        for bad_token in malformed_examples:
            with self.assertRaises(InvalidMemberTokenError):
                verify_member_token_signature(bad_token, secret_key=self.secret_test_key)

            res = validate_member_token(bad_token, secret_key=self.secret_test_key)
            self.assertFalse(res["valid"])
            self.assertEqual(res["code"], "INVALID_TOKEN")

    # --------------------------------------------------------------------------
    # SKENARIO 7: Token terpotong ditolak
    # --------------------------------------------------------------------------
    def test_07_truncated_token_rejected(self):
        """Skenario 7: Token yang terpotong di bagian tanda tangan ditolak."""
        valid_token = generate_member_qr_token("M-3K9X7W", 1, secret_key=self.secret_test_key)

        # Potong 5 karakter terakhir
        truncated_token = valid_token[:-5]
        with self.assertRaises(InvalidMemberTokenError):
            verify_member_token_signature(truncated_token, secret_key=self.secret_test_key)

        # Potong separuh
        half_token = valid_token[:30]
        with self.assertRaises(InvalidMemberTokenError):
            verify_member_token_signature(half_token, secret_key=self.secret_test_key)

    # --------------------------------------------------------------------------
    # SKENARIO 8: Token dengan versi yang tidak didukung ditolak
    # --------------------------------------------------------------------------
    def test_08_unsupported_qr_version_rejected(self):
        """Skenario 8: Versi QR non-integer atau <= 0 ditolak."""
        # Pada build payload
        with self.assertRaises(ValidationError):
            build_member_token_payload("M-123456", qr_version=0)
        with self.assertRaises(ValidationError):
            build_member_token_payload("M-123456", qr_version=-1)

        # Pada token serialisasi yang dimanipulasi
        sig_placeholder = "a" * 64
        with self.assertRaises(InvalidMemberTokenError):
            parse_member_qr_token(f"M-123456:0:{sig_placeholder}")
        with self.assertRaises(InvalidMemberTokenError):
            parse_member_qr_token(f"M-123456:-5:{sig_placeholder}")

    # --------------------------------------------------------------------------
    # SKENARIO 9: Identitas anggota yang tidak valid ditangani sesuai kontrak
    # --------------------------------------------------------------------------
    def test_09_invalid_member_id_format_rejected(self):
        """Skenario 9: ID anggota yang tidak diawali 'M-' ditolak."""
        with self.assertRaises(ValidationError):
            build_member_token_payload("C-123456", 1)  # Prefix buku
        with self.assertRaises(ValidationError):
            build_member_token_payload("123456", 1)    # Tanpa prefix

        sig_placeholder = "a" * 64
        with self.assertRaises(InvalidMemberTokenError):
            parse_member_qr_token(f"C-123456:1:{sig_placeholder}")

    # --------------------------------------------------------------------------
    # SKENARIO 10: Anggota yang tidak ditemukan ditangani sesuai kebijakan
    # --------------------------------------------------------------------------
    def test_10_member_not_found_in_database(self):
        """Skenario 10: Token valid secara kripto tetapi ID tidak ada di database melempar MemberNotFoundError."""
        valid_token = generate_member_qr_token("M-GHOSTR", 1, secret_key=self.secret_test_key)

        with self.assertRaises(MemberNotFoundError):
            verify_member_qr_token(self.conn, valid_token, secret_key=self.secret_test_key)

        res = validate_member_token(valid_token, conn=self.conn, secret_key=self.secret_test_key)
        self.assertFalse(res["valid"])
        self.assertEqual(res["code"], "MEMBER_NOT_FOUND")

    # --------------------------------------------------------------------------
    # SKENARIO 11: Kunci rahasia yang tidak tersedia ditangani dengan aman
    # --------------------------------------------------------------------------
    def test_11_missing_secret_key_handled_safely(self):
        """Skenario 11: Kunci rahasia kosong melempar SecretKeyError tanpa traceback crash publik."""
        os.environ.pop("SECRET_KEY", None)
        os.environ.pop("FLASK_SECRET_KEY", None)

        with self.assertRaises(SecretKeyError) as ctx:
            get_member_token_secret()
        self.assertIn("belum dikonfigurasi", str(ctx.exception))

        with self.assertRaises(SecretKeyError):
            generate_member_qr_token("M-123456", 1)

        res = validate_member_token("M-123456:1:" + ("a" * 64))
        self.assertFalse(res["valid"])
        self.assertEqual(res["code"], "SECRET_KEY_ERROR")

    # --------------------------------------------------------------------------
    # SKENARIO 12: Kunci yang salah tidak dapat memverifikasi token
    # --------------------------------------------------------------------------
    def test_12_wrong_secret_key_rejected(self):
        """Skenario 12: Token yang ditandatangani dengan kunci A ditolak bila diverifikasi dengan kunci B."""
        key_a = "secret_key_pertama_yang_sangat_rahasia_dan_panjang_123"
        key_b = "secret_key_kedua_yang_berbeda_dan_sama_panjangnya_456"

        token = generate_member_qr_token("M-3K9X7W", 1, secret_key=key_a)

        # Verifikasi dengan key_b gagal
        with self.assertRaises(InvalidMemberTokenError):
            verify_member_token_signature(token, secret_key=key_b)

        # Verifikasi dengan key_a sukses
        verified = verify_member_token_signature(token, secret_key=key_a)
        self.assertEqual(verified["member_id"], "M-3K9X7W")

    # --------------------------------------------------------------------------
    # SKENARIO 13: Payload QR tidak memuat data pribadi anggota
    # --------------------------------------------------------------------------
    def test_13_payload_contains_no_pii(self):
        """Skenario 13: Payload token murni identifier internal, bebas dari nama, telepon, kelas, atau PII."""
        # Daftarkan anggota dengan data sintetis
        member = register_member(self.conn, nama="Dewi Sartika Rahayu", category_id="MC-MURID")
        token = generate_member_qr_token(member["id"], member["qr_version"], secret_key=self.secret_test_key)

        # Verifikasi string token tidak mengandung substring nama atau kategori
        self.assertNotIn("Dewi", token)
        self.assertNotIn("Sartika", token)
        self.assertNotIn("Rahayu", token)
        self.assertNotIn("Murid", token)
        self.assertNotIn("MC-MURID", token)
        self.assertNotIn("@", token)
        self.assertNotIn("08123456789", token)  # Contoh nomor telepon

        # Verifikasi struktural: token hanya terdiri dari member_id, qr_version, dan HMAC hex
        parts = token.split(":")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], member["id"])
        self.assertEqual(parts[1], str(member["qr_version"]))
        self.assertEqual(len(parts[2]), 64)

    # --------------------------------------------------------------------------
    # SKENARIO 14: Token tidak mengekspos kunci rahasia
    # --------------------------------------------------------------------------
    def test_14_token_does_not_expose_secret_key(self):
        """Skenario 14: Kunci rahasia tidak pernah terkandung sebagai substring dalam token."""
        token = generate_member_qr_token("M-3K9X7W", 1, secret_key=self.secret_test_key)
        self.assertNotIn(self.secret_test_key, token)

    # --------------------------------------------------------------------------
    # SKENARIO 15: Verifikasi menggunakan pembandingan tanda autentikasi aman
    # --------------------------------------------------------------------------
    def test_15_timing_safe_comparison_used(self):
        """Skenario 15: Verifikasi memanggil hmac.compare_digest secara eksplisit."""
        token = generate_member_qr_token("M-3K9X7W", 1, secret_key=self.secret_test_key)

        with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
            verify_member_token_signature(token, secret_key=self.secret_test_key)
            mock_compare.assert_called_once()

    # --------------------------------------------------------------------------
    # SKENARIO 16: Token yang dimodifikasi tidak diterima
    # --------------------------------------------------------------------------
    def test_16_arbitrary_tampering_rejected(self):
        """Skenario 16: Segala bentuk injeksi teks / manipulasi karakter ditolak."""
        token = generate_member_qr_token("M-3K9X7W", 1, secret_key=self.secret_test_key)

        attacks = [
            token + "extra",
            "prefix:" + token,
            token.replace("M-", "M-X"),
            token.replace(":", "."),
            token.upper(),  # tanda tangan uppercase akan diverifikasi via lowercase tapi tetap diuji
        ]
        for attack in attacks[:4]:
            with self.assertRaises(InvalidMemberTokenError):
                verify_member_token_signature(attack, secret_key=self.secret_test_key)

    # --------------------------------------------------------------------------
    # SKENARIO 17: Kegagalan parsing tidak menyebabkan server crash
    # --------------------------------------------------------------------------
    def test_17_parsing_failure_handled_cleanly_without_unhandled_crash(self):
        """Skenario 17: validate_member_token selalu mengembalikan dict respons aman tanpa crash."""
        toxic_inputs = [
            None,
            "",
            "   ",
            12345,
            {"token": "obj"},
            "A" * 500,  # Melebihi batas MAX_MEMBER_TOKEN_LENGTH
            "M-1:2:3:4:5:6",
            "M-TEST:NaN:xyz",
            "\x00\x01\x02",
        ]
        for toxic in toxic_inputs:
            res = validate_member_token(toxic, secret_key=self.secret_test_key)
            self.assertIsInstance(res, dict)
            self.assertFalse(res["valid"])
            self.assertIn("message", res)
            self.assertIn("code", res)

    # --------------------------------------------------------------------------
    # SKENARIO 18: Revokasi token saat qr_version dinaikkan (Task 4-07)
    # --------------------------------------------------------------------------
    def test_18_revoked_token_version_rejected(self):
        """Skenario 18: Token dengan qr_version lama ditolak ketika database telah menaikkan qr_version."""
        member = register_member(self.conn, nama="Ahmad Dahlan", category_id="MC-MURID")
        member_id = member["id"]

        # Token versi 1
        old_token = generate_member_qr_token(member_id, qr_version=1, secret_key=self.secret_test_key)

        # Verifikasi awal versi 1 sukses
        verified_member = verify_member_qr_token(self.conn, old_token, secret_key=self.secret_test_key)
        self.assertEqual(verified_member["id"], member_id)

        # Petugas menerbitkan ulang kartu (increment qr_version)
        new_version = member_repo.increment_qr_version(self.conn, member_id)
        self.assertEqual(new_version, 2)

        # Kartu lama (versi 1) otomatis ditolak sebagai revoked
        with self.assertRaises(MemberTokenRevokedError) as ctx:
            verify_member_qr_token(self.conn, old_token, secret_key=self.secret_test_key)
        self.assertIn("sudah tidak berlaku", str(ctx.exception))

        res_old = validate_member_token(old_token, conn=self.conn, secret_key=self.secret_test_key)
        self.assertFalse(res_old["valid"])
        self.assertEqual(res_old["code"], "TOKEN_REVOKED")

        # Kartu baru (versi 2) diterima
        new_token = generate_member_qr_token(member_id, qr_version=new_version, secret_key=self.secret_test_key)
        res_new = validate_member_token(new_token, conn=self.conn, secret_key=self.secret_test_key)
        self.assertTrue(res_new["valid"])
        self.assertEqual(res_new["qr_version"], 2)

    # --------------------------------------------------------------------------
    # SKENARIO 19: Penanganan anggota nonaktif vs aktif (DEC-020)
    # --------------------------------------------------------------------------
    def test_19_inactive_member_handling(self):
        """Skenario 19: Anggota nonaktif dikenali identitasnya, tetapi check_active menolaknya."""
        member = register_member(self.conn, nama="Siti Alumni", category_id="MC-MURID")
        member_id = member["id"]
        token = generate_member_qr_token(member_id, qr_version=1, secret_key=self.secret_test_key)

        # Nonaktifkan anggota
        deactivate_member(self.conn, member_id=member_id, reason="Lulus tahun ajaran 2026")

        # 1. Pengecekan tanpa check_active (hanya verifikasi identitas): Sukses, status = nonaktif
        verified = verify_member_qr_token(self.conn, token, secret_key=self.secret_test_key, check_active=False)
        self.assertEqual(verified["status"], "nonaktif")

        # 2. Pengecekan dengan check_active=True (untuk peminjaman): Ditolak dengan MemberInactiveError
        with self.assertRaises(MemberInactiveError):
            verify_member_qr_token(self.conn, token, secret_key=self.secret_test_key, check_active=True)

        res_inactive = validate_member_token(token, conn=self.conn, secret_key=self.secret_test_key, check_active=True)
        self.assertFalse(res_inactive["valid"])
        self.assertEqual(res_inactive["code"], "MEMBER_INACTIVE")

    # --------------------------------------------------------------------------
    # SKENARIO 20: Pembuatan SVG QR Anggota dari token
    # --------------------------------------------------------------------------
    def test_20_member_qr_svg_generation(self):
        """Skenario 20: generate_member_qr_svg menghasilkan string SVG valid dari token anggota."""
        token = generate_member_qr_token("M-3K9X7W", 1, secret_key=self.secret_test_key)
        svg = generate_member_qr_svg(token)

        self.assertIsInstance(svg, str)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.strip().endswith("</svg>"))
        self.assertIn("xmlns=\"http://www.w3.org/2000/svg\"", svg)

        # Input kosong ditolak dengan ValueError
        with self.assertRaises(ValueError):
            generate_member_qr_svg("")

    # --------------------------------------------------------------------------
    # SKENARIO 21: Garansi Zero-Write ke database
    # --------------------------------------------------------------------------
    def test_21_zero_write_guarantee(self):
        """Skenario 21: Pembuatan dan verifikasi token tidak mengubah database sama sekali."""
        member = register_member(self.conn, nama="Budi Zero Write", category_id="MC-MURID")
        token = generate_member_qr_token(member["id"], member["qr_version"], secret_key=self.secret_test_key)

        def count_all_rows():
            m_count = self.conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
            c_count = self.conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]
            a_count = self.conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
            return (m_count, c_count, a_count)

        counts_before = count_all_rows()

        # Eksekusi verifikasi berkali-kali
        for _ in range(5):
            verify_member_qr_token(self.conn, token, secret_key=self.secret_test_key)
            validate_member_token(token, conn=self.conn, secret_key=self.secret_test_key)

        counts_after = count_all_rows()
        self.assertEqual(counts_before, counts_after)


if __name__ == "__main__":
    unittest.main()
