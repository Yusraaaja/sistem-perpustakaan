# -*- coding: utf-8 -*-
"""
Uji Unit Modul Generator ID Publik Crockford Base32 (id_generator.py).
Memenuhi Task 1B-04, Requirement LIB-COPY-001, LIB-COPY-002, R2, dan R12.
"""
import re
import unittest
from id_generator import (
    CROCKFORD_BASE32_ALPHABET,
    AMBIGUOUS_CHARACTERS,
    REQUIRED_PUBLIC_PREFIXES,
    ALLOWED_PREFIXES,
    DEFAULT_SUFFIX_LENGTH,
    generate_id,
    generate_title_id,
    generate_copy_id,
    generate_member_id,
    generate_loan_id,
    generate_loan_item_id,
    generate_audit_id
)


class IdGeneratorTests(unittest.TestCase):
    def test_01_id_format_and_prefixes(self):
        """Memastikan format prefix dan struktur ID tepat <PREFIX>-<6 KARAKTER>."""
        t_id = generate_title_id()
        c_id = generate_copy_id()
        m_id = generate_member_id()
        l_id = generate_loan_id()
        li_id = generate_loan_item_id()
        aud_id = generate_audit_id()

        self.assertTrue(t_id.startswith("T-"))
        self.assertTrue(c_id.startswith("C-"))
        self.assertTrue(m_id.startswith("M-"))
        self.assertTrue(l_id.startswith("L-"))
        self.assertTrue(li_id.startswith("LI-"))
        self.assertTrue(aud_id.startswith("AUD-"))

        # Panjang token suffix: tepat 6 karakter sesuai keputusan terbaru pemilik proyek
        self.assertEqual(len(t_id.split("-")[1]), 6)
        self.assertEqual(len(c_id.split("-")[1]), 6)
        self.assertEqual(len(m_id.split("-")[1]), 6)
        self.assertEqual(len(l_id.split("-")[1]), 6)
        self.assertEqual(len(li_id.split("-")[1]), 6)
        self.assertEqual(len(aud_id.split("-")[1]), 6)

        # Pola regex format <PREFIX>-<6 KARAKTER ALFABET BASE32>
        pattern_prefix = re.compile(rf"^[A-Z]{{1,3}}-[{CROCKFORD_BASE32_ALPHABET}]{{6}}$")
        for sample_id in [t_id, c_id, m_id, l_id, li_id, aud_id]:
            self.assertRegex(sample_id, pattern_prefix)

    def test_02_10000_unique_ids_without_collision(self):
        """Pengujian beban keunikan: 10.000 ID berturut-turut harus 100% unik tanpa tabrakan."""
        total_samples = 10000
        seen = set()
        generated = []
        for _ in range(total_samples):
            cid = generate_copy_id(is_taken=seen.__contains__)
            seen.add(cid)
            generated.append(cid)
        self.assertEqual(len(seen), total_samples, "Ditemukan tabrakan ID pada 10.000 sampel!")
        self.assertEqual(len(generated), total_samples)

        # Verifikasi seluruh sampel memiliki suffix 6 karakter
        for cid in generated[:100]:
            parts = cid.split("-")
            self.assertEqual(parts[0], "C")
            self.assertEqual(len(parts[1]), 6)

    def test_03_no_ambiguous_characters(self):
        """Memastikan karakter ambigu (0, O, 1, I, L) TIDAK PERNAH muncul dalam ID."""
        for _ in range(2000):
            cid = generate_copy_id()
            token = cid.split("-")[1]
            for ch in token:
                self.assertIn(ch, CROCKFORD_BASE32_ALPHABET)
                self.assertNotIn(ch, AMBIGUOUS_CHARACTERS, f"Karakter ambigu '{ch}' ditemukan dalam {cid}")

    def test_04_prefix_validation(self):
        """Memastikan semua prefix yang diwajibkan berfungsi dan prefix invalid ditolak (ValueError)."""
        # Prefix yang diwajibkan: T, C, M, L
        for p in REQUIRED_PUBLIC_PREFIXES:
            res = generate_id(p)
            self.assertTrue(res.startswith(f"{p}-"))
            self.assertEqual(len(res.split("-")[1]), DEFAULT_SUFFIX_LENGTH)

        # Prefix tidak valid harus ditolak secara konsisten dengan ValueError
        invalid_prefixes = ["X", "Z", "BOOK", "123", "", "t", "c", None, 999]
        for inv in invalid_prefixes:
            with self.assertRaises(ValueError, msg=f"Prefix '{inv}' seharusnya ditolak dengan ValueError"):
                generate_id(inv)

    def test_05_collision_retry_succeeds(self):
        """Memastikan mekanisme retry berhasil mengatasi tabrakan yang disimulasikan."""
        attempts = 0

        def mock_is_taken(cand: str) -> bool:
            nonlocal attempts
            attempts += 1
            # Anggap 3 percobaan pertama tabrakan, percobaan ke-4 sukses
            return attempts < 4

        result = generate_id("C", length=6, is_taken=mock_is_taken, max_retries=10)
        self.assertTrue(result.startswith("C-"))
        self.assertEqual(len(result.split("-")[1]), 6)
        self.assertEqual(attempts, 4)

    def test_06_collision_retry_exhaustion_raises_runtime_error(self):
        """Memastikan jika tabrakan melebihi batas max_retries, generator gagal terkendali (RuntimeError)."""
        def always_taken(_cand: str) -> bool:
            return True

        with self.assertRaises(RuntimeError) as ctx:
            generate_id("C", length=6, is_taken=always_taken, max_retries=5)
        self.assertIn("Gagal menghasilkan ID unik", str(ctx.exception))

    def test_07_all_required_primary_keys_can_be_generated(self):
        """Memastikan seluruh primary key skema v2 termasuk loan_items dan audit_log dapat dibuat."""
        li_id = generate_loan_item_id()
        self.assertTrue(li_id.startswith("LI-"))
        self.assertEqual(len(li_id.split("-")[1]), 6)

        aud_id = generate_audit_id()
        self.assertTrue(aud_id.startswith("AUD-"))
        self.assertEqual(len(aud_id.split("-")[1]), 6)


if __name__ == "__main__":
    unittest.main()
