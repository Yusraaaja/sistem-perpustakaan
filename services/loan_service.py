# -*- coding: utf-8 -*-
"""
Business Service untuk Alur Transaksi Peminjaman, Pengembalian, dan Perpanjangan.
Memenuhi Sub-Fase 2B, LIB-LOAN-002, DEC-005, DEC-006, DEC-007, DEC-019, DEC-020, DEC-024.
"""
import sqlite3
from typing import Dict, Any, List, Optional

import timeutil
from repositories import (
    loan_repo,
    copy_repo,
    audit_repo,
)
from .exceptions import (
    ValidationError,
    CopyNotFoundError,
    CopyNotAvailableError,
    LoanItemNotFoundError,
    LoanItemAlreadyReturnedError,
    LoanExtensionLimitReachedError,
)
from .member_service import validate_member_for_borrowing
from .transaction import transaction_scope


def borrow_copies(
    conn: sqlite3.Connection,
    member_id: str,
    copy_ids: List[str],
    actor: str = "self_service",
    loan_hours: int = 168,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Melakukan peminjaman multi-item dalam satu transaksi atomik.
    - Validasi kelayakan anggota (DEC-020: harus aktif).
    - Validasi ketersediaan setiap eksemplar fisik.
    - Menolak daftar eksemplar kosong atau duplikat di keranjang yang sama.
    - Jika SALAH SATU eksemplar gagal/tidak tersedia, SELURUH transaksi di-rollback secara atomik.
    - Mencatat audit log di dalam transaksi yang sama.
    """
    if not copy_ids:
        raise ValidationError("Daftar buku yang dipinjam tidak boleh kosong.")

    # Cegah scan buku yang sama dua kali di keranjang yang sama
    cleaned_copy_ids = [str(cid).strip() for cid in copy_ids if str(cid).strip()]
    if len(cleaned_copy_ids) != len(set(cleaned_copy_ids)):
        raise ValidationError("Daftar buku berisi eksemplar duplikat. Satu eksemplar fisik hanya dapat dimasukkan satu kali.")

    # 1. Validasi anggota aktif
    validate_member_for_borrowing(conn, member_id)

    # 2. Transaksi atomik peminjaman
    with transaction_scope(conn):
        # Periksa keberadaan dan ketersediaan semua eksemplar sebelum mutasi
        for copy_id in cleaned_copy_ids:
            copy_obj = copy_repo.get_copy_by_id(conn, copy_id)
            if not copy_obj:
                raise CopyNotFoundError(f"Eksemplar dengan ID '{copy_id}' tidak ditemukan di sistem.")

            avail_list = copy_repo.get_copy_availability(conn, copy_id=copy_id)
            if not avail_list:
                raise CopyNotFoundError(f"Eksemplar dengan ID '{copy_id}' tidak ditemukan.")

            avail = avail_list[0]
            if avail["copy_status"] != "aktif" or avail["availability_status"] != "tersedia":
                judul_buku = copy_obj.get("title_judul") or "Buku"
                raise CopyNotAvailableError(
                    f"Eksemplar '{copy_id}' ({judul_buku}) tidak dapat dipinjam "
                    f"karena berstatus '{avail['availability_status']}'."
                )

        # Buat header peminjaman
        loan_id = loan_repo.create_loan(
            conn,
            {
                "member_id": member_id.strip(),
                "idempotency_key": idempotency_key,
            },
        )

        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        due_iso = timeutil.format_iso_utc(timeutil.calculate_due_datetime(now_iso, hours=loan_hours))

        # Tambahkan semua item peminjaman
        for copy_id in cleaned_copy_ids:
            loan_repo.add_loan_item(
                conn,
                {
                    "loan_id": loan_id,
                    "copy_id": copy_id,
                    "borrowed_at": now_iso,
                    "due_at": due_iso,
                },
            )

        # Catat audit log di dalam transaksi yang sama
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="LOAN_CREATE",
            object_type="loans",
            object_id=loan_id,
            detail_json={
                "member_id": member_id.strip(),
                "copy_ids": cleaned_copy_ids,
                "due_at": due_iso,
            },
        )

        loan = loan_repo.get_loan_with_items(conn, loan_id)

    return loan


def return_copies(
    conn: sqlite3.Connection,
    copy_ids: Optional[List[str]] = None,
    item_ids: Optional[List[str]] = None,
    return_condition: str = "baik",
    returned_via: str = "manual",
    actor: str = "self_service",
    notes: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Menyelesaikan pengembalian satu atau banyak eksemplar buku.
    - Memenuhi DEC-006: Pengembalian tidak harus dilakukan oleh peminjam asli.
    - Memenuhi DEC-007: Mendukung pengembalian penuh maupun parsial.
    - Jika kondisi 'rusak' atau 'hilang', status eksemplar diupdate otomatis.
    - Seluruh operasi berjalan di dalam satu transaksi atomik.
    """
    if not copy_ids and not item_ids:
        raise ValidationError("Harus menyertakan setidaknya satu ID eksemplar atau ID item peminjaman.")

    with transaction_scope(conn):
        items_to_return: List[Dict[str, Any]] = []

        if copy_ids:
            for copy_id in copy_ids:
                cid = str(copy_id).strip()
                active = loan_repo.get_active_loan_by_copy(conn, cid)
                if not active:
                    raise CopyNotAvailableError(
                        f"Eksemplar '{cid}' tidak sedang berada dalam transaksi peminjaman aktif."
                    )
                items_to_return.append(active)

        if item_ids:
            for item_id in item_ids:
                iid = str(item_id).strip()
                item = loan_repo.get_loan_item_by_id(conn, iid)
                if not item:
                    raise LoanItemNotFoundError(f"Item peminjaman dengan ID '{iid}' tidak ditemukan.")
                if item.get("returned_at") is not None:
                    raise LoanItemAlreadyReturnedError(
                        f"Item '{iid}' sudah dikembalikan sebelumnya pada {item.get('returned_at')}."
                    )
                # Hindari duplikasi jika copy_ids dan item_ids merujuk item yang sama
                if not any(x["id"] == item["id"] for x in items_to_return):
                    items_to_return.append(item)

        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        returned_results: List[Dict[str, Any]] = []

        for item in items_to_return:
            loan_repo.return_loan_item(
                conn,
                item_id=item["id"],
                return_condition=return_condition,
                returned_via=returned_via,
                returned_at=now_iso,
                notes=notes,
            )

            # Jika kondisi rusak atau hilang, perbarui status fisik eksemplar
            if return_condition in {"rusak", "hilang"}:
                copy_repo.update_copy_status(conn, item["copy_id"], return_condition)

            audit_repo.record_audit(
                conn,
                actor=actor,
                action="LOAN_RETURN",
                object_type="loan_items",
                object_id=item["id"],
                detail_json={
                    "copy_id": item["copy_id"],
                    "return_condition": return_condition,
                    "returned_via": returned_via,
                },
            )
            returned_results.append(loan_repo.get_loan_item_by_id(conn, item["id"]))

    return returned_results


def extend_loan(
    conn: sqlite3.Connection,
    item_id: str,
    actor: str = "member",
    extension_hours: int = 168
) -> Dict[str, Any]:
    """
    Memperpanjang masa pinjam satu eksemplar.
    - Memenuhi DEC-005: Maksimal 1 kali perpanjangan (168 jam / 7 hari tambahan).
    """
    if not item_id or not str(item_id).strip():
        raise ValidationError("ID Item Peminjaman wajib diisi.")

    with transaction_scope(conn):
        item = loan_repo.get_loan_item_by_id(conn, item_id.strip())
        if not item:
            raise LoanItemNotFoundError(f"Item peminjaman dengan ID '{item_id}' tidak ditemukan.")

        if item.get("returned_at") is not None:
            raise LoanItemAlreadyReturnedError("Buku sudah dikembalikan dan tidak dapat diperpanjang.")

        if item.get("extension_count", 0) >= 1:
            raise LoanExtensionLimitReachedError(
                "Batas perpanjangan maksimal 1 kali telah tercapai sesuai aturan perpustakaan (DEC-005). "
                "Silakan kembalikan buku ke perpustakaan."
            )

        # Hitung jatuh tempo baru: jatuh tempo sebelumnya + durasi perpanjangan
        new_due_dt = timeutil.calculate_due_datetime(item["due_at"], hours=extension_hours)
        new_due_iso = timeutil.format_iso_utc(new_due_dt)

        loan_repo.extend_loan_item(conn, item_id=item_id.strip(), new_due_at=new_due_iso)

        audit_repo.record_audit(
            conn,
            actor=actor,
            action="LOAN_EXTEND",
            object_type="loan_items",
            object_id=item_id.strip(),
            detail_json={
                "old_due_at": item["due_at"],
                "new_due_at": new_due_iso,
                "extension_count": item.get("extension_count", 0) + 1,
            },
        )

        updated_item = loan_repo.get_loan_item_by_id(conn, item_id.strip())

    return updated_item


def resolve_lost_or_damaged(
    conn: sqlite3.Connection,
    item_id: str,
    replacement_type: str,
    notes: Optional[str] = None,
    actor: str = "admin"
) -> Dict[str, Any]:
    """
    Menyelesaikan kasus buku hilang atau rusak dengan penggantian buku fisik (kamus/Al-Qur'an).
    - Memenuhi DEC-024: Tanpa denda uang, penyelesaian berupa penggantian fisik.
    """
    if not item_id or not str(item_id).strip():
        raise ValidationError("ID Item Peminjaman wajib diisi.")
    if not replacement_type or not str(replacement_type).strip():
        raise ValidationError("Jenis penggantian buku wajib diisi (contoh: 'Kamus' atau 'Al-Qur\\'an').")

    with transaction_scope(conn):
        item = loan_repo.get_loan_item_by_id(conn, item_id.strip())
        if not item:
            raise LoanItemNotFoundError(f"Item peminjaman dengan ID '{item_id}' tidak ditemukan.")

        condition = "hilang" if "hilang" in str(notes or "").lower() or "hilang" in replacement_type.lower() else "rusak"
        now_iso = timeutil.format_iso_utc(timeutil.now_utc())

        # Selesaikan pengembalian dengan jalur penyelesaian
        loan_repo.return_loan_item(
            conn,
            item_id=item_id.strip(),
            return_condition=condition,
            returned_via="penyelesaian",
            returned_at=now_iso,
            notes=f"Diselesaikan dengan penggantian {replacement_type}. Catatan: {notes or '-'}",
        )

        # Ubah status eksemplar
        copy_repo.update_copy_status(conn, item["copy_id"], condition)

        # Catat detail penggantian ke arsip extra (DEC-024)
        loan_repo.save_legacy_extra(
            conn,
            item_id=item_id.strip(),
            fine_overdue=0,
            fine_condition=0,
            status_penggantian="selesai",
            catatan_penggantian=f"Penggantian {replacement_type}: {notes or ''}",
        )

        audit_repo.record_audit(
            conn,
            actor=actor,
            action="RESOLVE_LOST_OR_DAMAGED",
            object_type="loan_items",
            object_id=item_id.strip(),
            detail_json={
                "replacement_type": replacement_type,
                "copy_id": item["copy_id"],
                "notes": notes,
            },
        )

        resolved_item = loan_repo.get_loan_item_by_id(conn, item_id.strip())

    return resolved_item

