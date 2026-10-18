# -*- coding: utf-8 -*-
"""
Business Service untuk Pengelolaan Anggota Perpustakaan.
Memenuhi Sub-Fase 2B, DEC-020 (penonaktifan anggota, bukan penghapusan),
dan DEC-023 (data anggota minimal tanpa kelas/telepon).
"""
import sqlite3
from typing import Dict, Any, Optional

from repositories import (
    member_repo,
    audit_repo,
)
from .exceptions import (
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
)
from .transaction import transaction_scope


def validate_member_for_borrowing(conn: sqlite3.Connection, member_id: str) -> Dict[str, Any]:
    """
    Memeriksa kelayakan anggota untuk meminjam buku.
    - Anggota harus terdaftar di database.
    - Status anggota harus 'aktif' (DEC-020).
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")

    member = member_repo.get_member_by_id(conn, member_id.strip())
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{member_id}' tidak ditemukan.")

    if member["status"] != "aktif":
        raise MemberInactiveError(
            f"Anggota '{member['nama']}' berstatus nonaktif. "
            "Peminjaman baru hanya dapat dilakukan oleh anggota aktif. "
            "Silakan hubungi petugas untuk mengaktifkan kembali akun."
        )

    return member


def register_member(
    conn: sqlite3.Connection,
    nama: str,
    category_id: str,
    status: str = "aktif",
    actor: str = "admin"
) -> Dict[str, Any]:
    """
    Mendaftarkan anggota baru ke sistem dan mencatat audit log.
    Seluruh operasi berjalan dalam satu transaksi atomik.
    """
    if not nama or not str(nama).strip():
        raise ValidationError("Nama anggota wajib diisi.")
    if not category_id or not str(category_id).strip():
        raise ValidationError("Kategori anggota wajib dipilih.")

    if not member_repo.category_exists(conn, category_id.strip()):
        raise ValidationError(f"Kategori anggota dengan ID '{category_id}' tidak valid.")

    if status not in {"aktif", "nonaktif"}:
        raise ValidationError(f"Status '{status}' tidak valid. Pilihan: 'aktif' atau 'nonaktif'.")

    with transaction_scope(conn):
        member_id = member_repo.create_member(
            conn,
            {
                "nama": str(nama).strip(),
                "category_id": str(category_id).strip(),
                "status": status,
            },
        )
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="MEMBER_REGISTER",
            object_type="members",
            object_id=member_id,
            detail_json={"nama": str(nama).strip(), "category_id": str(category_id).strip()},
        )
        member = member_repo.get_member_by_id(conn, member_id)

    return member


def deactivate_member(
    conn: sqlite3.Connection,
    member_id: str,
    reason: str = "Penonaktifan akun anggota",
    actor: str = "admin"
) -> bool:
    """
    Menonaktifkan anggota tanpa menghapus riwayat transaksi (DEC-020).
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")

    member = member_repo.get_member_by_id(conn, member_id.strip())
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{member_id}' tidak ditemukan.")

    with transaction_scope(conn):
        ok = member_repo.update_member_status(conn, member_id.strip(), "nonaktif")
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="MEMBER_DEACTIVATE",
            object_type="members",
            object_id=member_id.strip(),
            reason=reason,
        )

    return ok


def reactivate_member(
    conn: sqlite3.Connection,
    member_id: str,
    reason: str = "Pengaktifan kembali akun anggota",
    actor: str = "admin"
) -> bool:
    """
    Mengaktifkan kembali anggota yang sebelumnya dinonaktifkan (DEC-020).
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")

    member = member_repo.get_member_by_id(conn, member_id.strip())
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{member_id}' tidak ditemukan.")

    with transaction_scope(conn):
        ok = member_repo.update_member_status(conn, member_id.strip(), "aktif")
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="MEMBER_REACTIVATE",
            object_type="members",
            object_id=member_id.strip(),
            reason=reason,
        )

    return ok

