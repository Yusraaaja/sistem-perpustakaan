# -*- coding: utf-8 -*-
"""
Uji Unit Modul Generator ID Publik Crockford Base32 (id_generator.py).
Memenuhi Requirement LIB-COPY-001, LIB-COPY-002, R2, dan R12.
"""
import unittest
from id_generator import (
    CROCKFORD_BASE32_ALPHABET,
    AMBIGUOUS_CHARACTERS,
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
        """Memastikan format prefix dan struktur ID sesuai spesifikasi."""
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

        # Panjang token: seragam 8 karakter untuk seluruh entitas
        self.assertEqual(len(t_id.split("-")[1]), 8)
        self.assertEqual(len(c_id.split("-")[1]), 8)
        self.assertEqual(len(m_id.split("-")[1]), 8)
        self.assertEqual(len(l_id.split("-")[1]), 8)
        self.assertEqual(len(li_id.split("-")[1]), 8)
        self.assertEqual(len(aud_id.split("-")[1]), 8)

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

    def test_03_no_ambiguous_characters(self):
        """Memastikan karakter ambigu (0, O, 1, I, L) TIDAK PERNAH muncul dalam ID."""
        for _ in range(2000):
            cid = generate_copy_id()
            token = cid.split("-")[1]
            for ch in token:
                self.assertIn(ch, CROCKFORD_BASE32_ALPHABET)
                self.assertNotIn(ch, AMBIGUOUS_CHARACTERS, f"Karakter ambigu '{ch}' ditemukan dalam {cid}")

    def test_04_collision_retry_succeeds(self):
        """Memastikan mekanisme retry berhasil mengatasi tabrakan yang disimulasikan."""
        attempts = 0

        def mock_is_taken(cand: str) -> bool:
            nonlocal attempts
            attempts += 1
            # Anggap 3 percobaan pertama tabrakan, percobaan ke-4 sukses
            return attempts < 4

        result = generate_id("C", length=6, is_taken=mock_is_taken, max_retries=10)
        self.assertTrue(result.startswith("C-"))
        self.assertEqual(attempts, 4)

    def test_05_collision_retry_exhaustion_raises_runtime_error(self):
        """Memastikan jika tabrakan melebihi batas max_retries, sistem menolak secara aman (RuntimeError)."""
        def always_taken(_cand: str) -> bool:
            return True

        with self.assertRaises(RuntimeError) as ctx:
            generate_id("C", length=6, is_taken=always_taken, max_retries=5)
        self.assertIn("Gagal menghasilkan ID unik", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
