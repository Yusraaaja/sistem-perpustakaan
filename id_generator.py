# -*- coding: utf-8 -*-
"""
Modul Generator ID Publik Ramah Manusia (Human-Friendly Crockford Base32).
Memenuhi Requirement LIB-COPY-001, LIB-COPY-002, R2, dan R12.

Aturan Utama:
1. Alfabet Crockford Base32 tanpa karakter ambigu: angka 0, huruf O, angka 1, huruf I, dan huruf L dihilangkan.
   Alfabet terpakai (30 karakter): '23456789ABCDEFGHJKMNPQRSTVWXYZ'
2. Prefix bermakna untuk keterbacaan:
   - T-   : Judul Katalog (catalog_titles)
   - C-   : Eksemplar Fisik (copies)
   - M-   : Anggota (members)
   - L-   : Peminjaman / Transaksi (loans)
   - LI-  : Detail Item Peminjaman (loan_items)
   - AUD- : Audit Log (audit_log)
3. ID tidak pernah dipakai ulang dan dijamin unik melalui mekanisme pemeriksaan tabrakan (collision retry).
"""
import secrets
from typing import Callable, Optional

# Alfabet Base32 Crockford tanpa 0/O, 1/I/L (total 30 karakter)
CROCKFORD_BASE32_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
AMBIGUOUS_CHARACTERS = {"0", "O", "o", "1", "I", "i", "L", "l"}


def generate_id(
    prefix: str,
    length: int = 6,
    is_taken: Optional[Callable[[str], bool]] = None,
    max_retries: int = 10,
    choice_func: Optional[Callable[[str], str]] = None
) -> str:
    """
    Menghasilkan ID publik berformat '{prefix}-{token}' menggunakan alfabet Crockford Base32.
    Jika fungsi is_taken diberikan, akan melakukan retry hingga max_retries jika terjadi tabrakan.
    """
    _choice = choice_func or secrets.choice

    for attempt in range(max_retries):
        token = "".join(_choice(CROCKFORD_BASE32_ALPHABET) for _ in range(length))
        candidate = f"{prefix}-{token}"
        if is_taken is None or not is_taken(candidate):
            return candidate

    raise RuntimeError(
        f"Gagal menghasilkan ID unik untuk prefix '{prefix}' setelah {max_retries} percobaan (terjadi tabrakan berturut-turut)."
    )


def generate_title_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID judul katalog (contoh: T-4K9W2M8V)."""
    return generate_id("T", length=8, is_taken=is_taken)


def generate_copy_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID eksemplar fisik buku (contoh: C-7P3N9Q4X)."""
    return generate_id("C", length=8, is_taken=is_taken)


def generate_member_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID anggota perpustakaan (contoh: M-8D2V5X3P)."""
    return generate_id("M", length=8, is_taken=is_taken)


def generate_loan_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID transaksi peminjaman (contoh: L-3X7K2A9M)."""
    return generate_id("L", length=8, is_taken=is_taken)


def generate_loan_item_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID item peminjaman (contoh: LI-9B4X2F7K)."""
    return generate_id("LI", length=8, is_taken=is_taken)


def generate_audit_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID catatan audit log (contoh: AUD-6W8H2Q5P)."""
    return generate_id("AUD", length=8, is_taken=is_taken)
