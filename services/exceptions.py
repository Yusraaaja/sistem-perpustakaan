# -*- coding: utf-8 -*-
"""
Modul Domain Exceptions untuk Service Layer.
Menerapkan DEC-022: Pesan kesalahan berbahasa Indonesia yang jelas, sederhana,
dan memberikan panduan tindakan berikutnya kepada pengguna.
"""


class ServiceError(Exception):
    """Base class untuk seluruh exception pada Business Service Layer."""
    pass


class ValidationError(ServiceError):
    """Terjadi ketika parameter input tidak memenuhi validasi format/aturan dasar."""
    pass


class MemberNotFoundError(ServiceError):
    """Terjadi ketika data anggota tidak ditemukan di database."""
    pass


class MemberInactiveError(ServiceError):
    """
    Terjadi ketika anggota berstatus nonaktif mencoba melakukan transaksi peminjaman.
    Memenuhi DEC-020.
    """
    pass


class CopyNotFoundError(ServiceError):
    """Terjadi ketika eksemplar fisik buku tidak ditemukan di database."""
    pass


class CopyNotAvailableError(ServiceError):
    """
    Terjadi ketika eksemplar buku sedang dipinjam orang lain, berstatus nonaktif, rusak, atau hilang.
    Memenuhi LIB-LOAN-002 dan DEC-019.
    """
    pass


class LoanNotFoundError(ServiceError):
    """Terjadi ketika header transaksi peminjaman tidak ditemukan."""
    pass


class LoanItemNotFoundError(ServiceError):
    """Terjadi ketika detail item peminjaman tidak ditemukan."""
    pass


class LoanItemAlreadyReturnedError(ServiceError):
    """Terjadi ketika mencoba mengembalikan atau memperpanjang buku yang sudah berstatus kembali."""
    pass


class LoanExtensionLimitReachedError(ServiceError):
    """
    Terjadi ketika perpanjangan melebihi batas maksimal 1 kali.
    Memenuhi DEC-005.
    """
    pass


class InvalidOperationError(ServiceError):
    """Terjadi ketika suatu operasi dilarang oleh logika bisnis perpustakaan."""
    pass


class ConfirmationTokenError(ValidationError):
    """Terjadi ketika token konfirmasi sekali pakai tidak valid, kedaluwarsa, atau tidak cocok."""
    pass


class ConcurrencyConflictError(InvalidOperationError):
    """Terjadi ketika permintaan konfirmasi bersamaan (race condition) terdeteksi."""
    pass


class StorageError(ServiceError):
    """Terjadi ketika operasi penyimpanan atau penghapusan file gagal (Task 3-11)."""
    pass


class SecretKeyError(ServiceError):
    """Terjadi ketika kunci rahasia aplikasi tidak tersedia atau tidak valid (Task 4-01)."""
    pass


class InvalidMemberTokenError(ValidationError):
    """Terjadi ketika token QR anggota tidak valid, rusak, atau tanda tangan tidak cocok (Task 4-01)."""
    pass


class MemberTokenRevokedError(ValidationError):
    """
    Terjadi ketika versi token QR anggota sudah tidak sesuai dengan versi di database
    karena telah dicabut atau diterbitkan ulang (Task 4-01, Task 4-07).
    """
    pass



