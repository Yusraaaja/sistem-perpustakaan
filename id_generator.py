# -*- coding: utf-8 -*-
"""
Modul Generator ID Publik Ramah Manusia (Human-Friendly Crockford Base32).
Memenuhi Task 1B-04, Requirement LIB-COPY-001, LIB-COPY-002, R2, dan R12.

Aturan Utama:
1. Alfabet Crockford Base32 tanpa karakter ambigu: angka 0, huruf O, angka 1, huruf I, dan huruf L dihilangkan.
   Alfabet terpakai (30 karakter): '23456789ABCDEFGHJKMNPQRSTVWXYZ'
2. Prefix entitas yang diwajibkan:
   - T-   : Judul Katalog (catalog_titles)
   - C-   : Eksemplar Fisik (copies)
   - M-   : Anggota (members)
   - L-   : Peminjaman / Transaksi (loans)
   Entitas pendukung skema v2:
   - LI-  : Detail Item Peminjaman (loan_items)
   - AUD- : Catatan Audit Log (audit_log)
3. Panjang Suffix: tepat 6 karakter (<PREFIX>-<6 KARAKTER>).
4. Penanganan Kesalahan: prefix di luar daftar yang diizinkan ditolak dengan ValueError.
5. Penanganan Tabrakan (Collision Retry): dapat dicoba ulang hingga batas aman (max_retries),
   dan gagal secara terkendali (RuntimeError) jika tabrakan terus berlanjut.
"""
import secrets
from typing import Callable, Optional, Set

# Alfabet Base32 Crockford tanpa 0/O, 1/I/L (total 30 karakter)
CROCKFORD_BASE32_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
AMBIGUOUS_CHARACTERS = {"0", "O", "o", "1", "I", "i", "L", "l"}

# Prefix entitas domain publik utama yang diwajibkan checklist
REQUIRED_PUBLIC_PREFIXES = {"T", "C", "M", "L"}

# Seluruh prefix yang diizinkan untuk primary key aplikasi skema v2
ALLOWED_PREFIXES = {"T", "C", "M", "L", "LI", "AUD"}

# Panjang default suffix ID (Task 1B-04: wajib 6 karakter)
DEFAULT_SUFFIX_LENGTH = 6
DEFAULT_MAX_RETRIES = 10


def generate_id(
    prefix: str,
    length: int = DEFAULT_SUFFIX_LENGTH,
    is_taken: Optional[Callable[[str], bool]] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    choice_func: Optional[Callable[[str], str]] = None
) -> str:
    """
    Menghasilkan ID publik berformat '{prefix}-{token}' menggunakan alfabet Crockford Base32.
    - Suffix tepat 'length' karakter (default 6 karakter).
    - Memvalidasi prefix terhadap ALLOWED_PREFIXES (menolak prefix invalid dengan ValueError).
    - Jika fungsi is_taken diberikan, mencoba ulang hingga max_retries jika terjadi tabrakan.
    - Jika collision berlanjut melebihi max_retries, me-raise RuntimeError terkendali.
    """
    if not isinstance(prefix, str) or prefix not in ALLOWED_PREFIXES:
        raise ValueError(
            f"Prefix '{prefix}' tidak valid. Prefix yang diizinkan adalah: {sorted(list(ALLOWED_PREFIXES))}"
        )

    if not isinstance(length, int) or length <= 0:
        raise ValueError("Panjang suffix harus berupa integer positif.")

    if not isinstance(max_retries, int) or max_retries <= 0:
        raise ValueError("max_retries harus berupa integer positif.")

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
    """Menghasilkan ID judul katalog format T-XXXXXX (contoh: T-7K3M9Q)."""
    return generate_id("T", length=DEFAULT_SUFFIX_LENGTH, is_taken=is_taken)


def generate_copy_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID eksemplar fisik buku format C-XXXXXX (contoh: C-2F8N5W)."""
    return generate_id("C", length=DEFAULT_SUFFIX_LENGTH, is_taken=is_taken)


def generate_member_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID anggota perpustakaan format M-XXXXXX (contoh: M-6J4R7K)."""
    return generate_id("M", length=DEFAULT_SUFFIX_LENGTH, is_taken=is_taken)


def generate_loan_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID transaksi peminjaman format L-XXXXXX (contoh: L-9P3X5D)."""
    return generate_id("L", length=DEFAULT_SUFFIX_LENGTH, is_taken=is_taken)


def generate_loan_item_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID item peminjaman format LI-XXXXXX (contoh: LI-4B7N2X)."""
    return generate_id("LI", length=DEFAULT_SUFFIX_LENGTH, is_taken=is_taken)


def generate_audit_id(is_taken: Optional[Callable[[str], bool]] = None) -> str:
    """Menghasilkan ID catatan audit log format AUD-XXXXXX (contoh: AUD-8M3Q5W)."""
    return generate_id("AUD", length=DEFAULT_SUFFIX_LENGTH, is_taken=is_taken)
