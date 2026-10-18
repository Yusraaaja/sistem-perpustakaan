# -*- coding: utf-8 -*-
"""
Business Service untuk Manajemen Katalog & Eksemplar Fisik.
Memenuhi Sub-Fase 2B, LIB-COPY-001, LIB-COPY-002, DEC-004, DEC-011, P2-01, dan P2-02 (penonaktifan bukan DELETE).
"""
import sqlite3
from typing import Dict, Any, List, Optional

from repositories import (
    catalog_repo,
    copy_repo,
    loan_repo,
    audit_repo,
)
from .exceptions import (
    ValidationError,
    CopyNotFoundError,
    InvalidOperationError,
)
from .transaction import transaction_scope


def create_title_with_copies(
    conn: sqlite3.Connection,
    title_data: Dict[str, Any],
    initial_copies: int = 0,
    copy_base_data: Optional[Dict[str, Any]] = None,
    actor: str = "admin"
) -> Dict[str, Any]:
    """
    Membuat judul katalog baru beserta sejumlah eksemplar fisik awal dalam satu transaksi atomik.
    Memenuhi DEC-004 & DEC-011: ID dibuat otomatis untuk judul dan tiap eksemplar.
    """
    if not title_data or "judul" not in title_data or not str(title_data["judul"]).strip():
        raise ValidationError("Judul buku wajib diisi dan tidak boleh kosong.")

    if initial_copies < 0:
        raise ValidationError("Jumlah eksemplar awal tidak boleh negatif.")

    with transaction_scope(conn):
        title_id = catalog_repo.create_title(conn, title_data)
        copy_ids = []
        if initial_copies > 0:
            copy_ids = copy_repo.create_copies_batch(
                conn,
                title_id=title_id,
                count=initial_copies,
                base_data=copy_base_data,
            )

        audit_repo.record_audit(
            conn,
            actor=actor,
            action="TITLE_CREATE",
            object_type="catalog_titles",
            object_id=title_id,
            detail_json={
                "judul": title_data["judul"],
                "initial_copies_count": initial_copies,
                "copy_ids": copy_ids,
            },
        )

        title = catalog_repo.get_title_by_id(conn, title_id)
        if title:
            title["copy_ids"] = copy_ids

    return title


def add_copies_to_title(
    conn: sqlite3.Connection,
    title_id: str,
    count: int,
    base_data: Optional[Dict[str, Any]] = None,
    actor: str = "admin"
) -> List[str]:
    """
    Menambahkan sejumlah eksemplar baru ke judul katalog yang sudah ada.
    Memenuhi DEC-013: menambah jumlah buku berarti membuat eksemplar baru dengan ID baru.
    """
    if not title_id or not str(title_id).strip():
        raise ValidationError("ID Judul Katalog wajib diisi.")
    if count <= 0:
        raise ValidationError("Jumlah eksemplar yang ditambahkan minimal 1.")

    title = catalog_repo.get_title_by_id(conn, title_id.strip())
    if not title:
        raise ValidationError(f"Judul katalog dengan ID '{title_id}' tidak ditemukan.")

    with transaction_scope(conn):
        copy_ids = copy_repo.create_copies_batch(
            conn,
            title_id=title_id.strip(),
            count=count,
            base_data=base_data,
        )
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="COPIES_ADD",
            object_type="catalog_titles",
            object_id=title_id.strip(),
            detail_json={"added_count": count, "copy_ids": copy_ids},
        )

    return copy_ids


def deactivate_copy(
    conn: sqlite3.Connection,
    copy_id: str,
    reason: str = "Buku rusak atau ditarik dari peredaran",
    actor: str = "admin"
) -> bool:
    """
    Menonaktifkan eksemplar buku (P2-02: pengganti operasi DELETE yang dilarang trigger R12).
    Menolak penonaktifan jika buku sedang berada dalam peminjaman aktif.
    """
    if not copy_id or not str(copy_id).strip():
        raise ValidationError("ID Eksemplar wajib diisi.")

    copy_obj = copy_repo.get_copy_by_id(conn, copy_id.strip())
    if not copy_obj:
        raise CopyNotFoundError(f"Eksemplar dengan ID '{copy_id}' tidak ditemukan.")

    # Cek apakah sedang dipinjam aktif
    active_loan = loan_repo.get_active_loan_by_copy(conn, copy_id.strip())
    if active_loan:
        raise InvalidOperationError(
            f"Eksemplar '{copy_id}' sedang dipinjam oleh '{active_loan.get('member_nama') or active_loan.get('legacy_nama_peminjam')}'. "
            "Selesaikan proses pengembalian terlebih dahulu sebelum menonaktifkan eksemplar ini."
        )

    with transaction_scope(conn):
        ok = copy_repo.update_copy_status(conn, copy_id.strip(), "nonaktif")
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="COPY_DEACTIVATE",
            object_type="copies",
            object_id=copy_id.strip(),
            reason=reason,
        )

    return ok


def get_title_with_details(conn: sqlite3.Connection, title_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil judul katalog beserta daftar eksemplar dan status ketersediaannya."""
    title = catalog_repo.get_title_by_id(conn, title_id)
    if not title:
        return None

    title["copies"] = copy_repo.get_copy_availability(conn, title_id=title_id)
    avail = catalog_repo.get_title_availability(conn, title_id=title_id)
    title["availability"] = avail[0] if avail else {}
    return title

