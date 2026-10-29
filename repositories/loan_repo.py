# -*- coding: utf-8 -*-
"""
Repositori Peminjaman Buku (loans, loan_items, & legacy_loan_item_extra).
Memenuhi Sub-Fase 2A, LIB-LOAN-002, DEC-004, DEC-005, DEC-024, R2, R4, R12.
"""
import sqlite3
from typing import Optional, List, Dict, Any, Set

import id_generator
import timeutil

VALID_RETURN_CONDITIONS = {"baik", "rusak", "lainnya", "hilang"}
VALID_RETURN_VIAS = {"jalur_a", "jalur_b", "manual", "penyelesaian", "legacy"}


def loan_exists_by_id(conn: sqlite3.Connection, loan_id: str) -> bool:
    """Memeriksa keberadaan header peminjaman berdasarkan ID."""
    if not loan_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM loans WHERE id = ? LIMIT 1;", (loan_id,)
    ).fetchone()
    return row is not None


def item_exists_by_id(conn: sqlite3.Connection, item_id: str) -> bool:
    """Memeriksa keberadaan item peminjaman berdasarkan ID."""
    if not item_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM loan_items WHERE id = ? LIMIT 1;", (item_id,)
    ).fetchone()
    return row is not None


def create_loan(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None
) -> str:
    """
    Membuat header transaksi peminjaman baru di tabel `loans`.
    Mendukung `member_id` formal atau `legacy_nama_peminjam` untuk arsip migrasi.
    Menggunakan ID Generator Crockford Base32 dengan prefix 'L-' dan verifikasi tabrakan dua lapis.
    """
    loan_id = data.get("id")
    if not loan_id:
        def is_taken(candidate: str) -> bool:
            return (seen_ids is not None and candidate in seen_ids) or loan_exists_by_id(conn, candidate)

        loan_id = id_generator.generate_loan_id(is_taken=is_taken)

    if seen_ids is not None:
        seen_ids.add(loan_id)

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    created_at = data.get("created_at") or now_iso

    conn.execute(
        """
        INSERT INTO loans (
            id, member_id, legacy_nama_peminjam, created_at,
            idempotency_key, legacy_peminjaman_id
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            loan_id,
            data.get("member_id"),
            data.get("legacy_nama_peminjam"),
            created_at,
            data.get("idempotency_key"),
            data.get("legacy_peminjaman_id"),
        ),
    )
    return loan_id


def add_loan_item(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None
) -> str:
    """
    Menambahkan satu detail item peminjaman di tabel `loan_items`.
    Diproteksi oleh indeks parsial unik `idx_loan_items_active_copy`:
    jika copy_id masih memiliki peminjaman aktif (returned_at IS NULL), SQLite akan me-raise sqlite3.IntegrityError.
    """
    loan_id = data.get("loan_id")
    copy_id = data.get("copy_id")
    borrowed_at = data.get("borrowed_at")
    due_at = data.get("due_at")

    if not loan_id or not copy_id or not borrowed_at or not due_at:
        raise ValueError("Field 'loan_id', 'copy_id', 'borrowed_at', dan 'due_at' wajib diisi.")

    item_id = data.get("id")
    if not item_id:
        def is_taken(candidate: str) -> bool:
            return (seen_ids is not None and candidate in seen_ids) or item_exists_by_id(conn, candidate)

        item_id = id_generator.generate_loan_item_id(is_taken=is_taken)

    if seen_ids is not None:
        seen_ids.add(item_id)

    return_condition = data.get("return_condition")
    if return_condition and return_condition not in VALID_RETURN_CONDITIONS:
        raise ValueError(f"Kondisi pengembalian tidak valid: {return_condition}")

    returned_via = data.get("returned_via")
    if returned_via and returned_via not in VALID_RETURN_VIAS:
        raise ValueError(f"Jalur pengembalian tidak valid: {returned_via}")

    conn.execute(
        """
        INSERT INTO loan_items (
            id, loan_id, copy_id, borrowed_at, due_at,
            extended_at, extension_count, returned_at,
            return_condition, returned_via, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            item_id,
            str(loan_id).strip(),
            str(copy_id).strip(),
            str(borrowed_at).strip(),
            str(due_at).strip(),
            data.get("extended_at"),
            int(data.get("extension_count") or 0),
            data.get("returned_at"),
            return_condition,
            returned_via,
            data.get("notes"),
        ),
    )
    return item_id


def get_loan_by_id(conn: sqlite3.Connection, loan_id: str) -> Optional[Dict[str, Any]]:
    """
    Mengambil header peminjaman berdasarkan ID, disertai data anggota jika ada.
    """
    sql = """
        SELECT 
            l.*,
            m.nama AS member_nama,
            m.status AS member_status,
            mc.jenis AS member_category_jenis
        FROM loans l
        LEFT JOIN members m ON l.member_id = m.id
        LEFT JOIN member_categories mc ON m.category_id = mc.id
        WHERE l.id = ?;
    """
    row = conn.execute(sql, (loan_id,)).fetchone()
    return dict(row) if row else None


def get_loan_items(conn: sqlite3.Connection, loan_id: str) -> List[Dict[str, Any]]:
    """
    Mengambil semua item untuk sebuah transaksi peminjaman, disertai info eksemplar & judul buku.
    """
    sql = """
        SELECT 
            li.*,
            c.title_id,
            c.call_number,
            c.status AS copy_status,
            c.lokasi_rak,
            t.judul AS title_judul,
            t.penulis AS title_penulis,
            t.isbn AS title_isbn
        FROM loan_items li
        JOIN copies c ON li.copy_id = c.id
        JOIN catalog_titles t ON c.title_id = t.id
        WHERE li.loan_id = ?
        ORDER BY li.id ASC;
    """
    rows = conn.execute(sql, (loan_id,)).fetchall()
    return [dict(r) for r in rows]


def get_loan_with_items(conn: sqlite3.Connection, loan_id: str) -> Optional[Dict[str, Any]]:
    """
    Mengambil header peminjaman beserta list itemnya dalam satu struktur dict lengkap.
    """
    loan = get_loan_by_id(conn, loan_id)
    if not loan:
        return None
    loan["items"] = get_loan_items(conn, loan_id)
    return loan


def get_loan_item_by_id(conn: sqlite3.Connection, item_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil satu item peminjaman berdasarkan item_id beserta info buku dan transaksi."""
    sql = """
        SELECT 
            li.*,
            c.title_id,
            c.call_number,
            c.status AS copy_status,
            t.judul AS title_judul,
            t.penulis AS title_penulis,
            l.member_id,
            l.legacy_nama_peminjam,
            m.nama AS member_nama
        FROM loan_items li
        JOIN copies c ON li.copy_id = c.id
        JOIN catalog_titles t ON c.title_id = t.id
        JOIN loans l ON li.loan_id = l.id
        LEFT JOIN members m ON l.member_id = m.id
        WHERE li.id = ?;
    """
    row = conn.execute(sql, (item_id,)).fetchone()
    return dict(row) if row else None


def get_active_loan_by_copy(conn: sqlite3.Connection, copy_id: str) -> Optional[Dict[str, Any]]:
    """
    Mengambil detail peminjaman aktif untuk eksemplar tertentu (returned_at IS NULL).
    """
    sql = """
        SELECT 
            li.*,
            l.member_id,
            l.legacy_nama_peminjam,
            m.nama AS member_nama
        FROM loan_items li
        JOIN loans l ON li.loan_id = l.id
        LEFT JOIN members m ON l.member_id = m.id
        WHERE li.copy_id = ? AND li.returned_at IS NULL
        LIMIT 1;
    """
    row = conn.execute(sql, (copy_id,)).fetchone()
    return dict(row) if row else None


def return_loan_item(
    conn: sqlite3.Connection,
    item_id: str,
    return_condition: str = "baik",
    returned_via: str = "manual",
    returned_at: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """
    Menyelesaikan pengembalian satu item peminjaman (returned_at IS NULL -> returned_at terisi).
    Mendukung pengembalian parsial per eksemplar (DEC-007).
    """
    if return_condition not in VALID_RETURN_CONDITIONS:
        raise ValueError(f"Kondisi pengembalian tidak valid: {return_condition}")
    if returned_via not in VALID_RETURN_VIAS:
        raise ValueError(f"Jalur pengembalian tidak valid: {returned_via}")

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    ret_time = returned_at or now_iso

    cur = conn.execute(
        """
        UPDATE loan_items
        SET returned_at = ?,
            return_condition = ?,
            returned_via = ?,
            notes = COALESCE(?, notes)
        WHERE id = ? AND returned_at IS NULL;
        """,
        (ret_time, return_condition, returned_via, notes, item_id),
    )
    return cur.rowcount > 0


def extend_loan_item(
    conn: sqlite3.Connection,
    item_id: str,
    new_due_at: str,
    extended_at: Optional[str] = None
) -> bool:
    """
    Memperpanjang jatuh tempo item peminjaman aktif.
    """
    if not new_due_at:
        raise ValueError("Field 'new_due_at' wajib diisi.")

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    ext_time = extended_at or now_iso

    cur = conn.execute(
        """
        UPDATE loan_items
        SET due_at = ?,
            extended_at = ?,
            extension_count = extension_count + 1
        WHERE id = ? AND returned_at IS NULL;
        """,
        (new_due_at, ext_time, item_id),
    )
    return cur.rowcount > 0


def list_loans(
    conn: sqlite3.Connection,
    member_id: Optional[str] = None,
    active_only: bool = False,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Mendaftar transaksi peminjaman disertai hitungan total item dan item aktif.
    Menampilkan nama peminjam dari `members.nama` atau `legacy_nama_peminjam` jika member_id IS NULL.
    """
    conditions = []
    params: List[Any] = []

    if member_id:
        conditions.append("l.member_id = ?")
        params.append(member_id)

    if active_only:
        conditions.append("EXISTS (SELECT 1 FROM loan_items li WHERE li.loan_id = l.id AND li.returned_at IS NULL)")

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT 
            l.*,
            COALESCE(m.nama, l.legacy_nama_peminjam) AS peminjam_display_name,
            m.status AS member_status,
            (SELECT COUNT(*) FROM loan_items li WHERE li.loan_id = l.id) AS total_items,
            (SELECT COUNT(*) FROM loan_items li WHERE li.loan_id = l.id AND li.returned_at IS NULL) AS active_items
        FROM loans l
        LEFT JOIN members m ON l.member_id = m.id
        {where_sql}
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def list_active_loan_items(
    conn: sqlite3.Connection,
    member_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Mendaftar semua item buku yang saat ini sedang dipinjam (returned_at IS NULL).
    """
    conditions = ["li.returned_at IS NULL"]
    params: List[Any] = []

    if member_id:
        conditions.append("l.member_id = ?")
        params.append(member_id)

    where_sql = f"WHERE {' AND '.join(conditions)}"
    sql = f"""
        SELECT 
            li.*,
            c.title_id,
            c.call_number,
            t.judul AS title_judul,
            t.penulis AS title_penulis,
            l.member_id,
            COALESCE(m.nama, l.legacy_nama_peminjam) AS peminjam_display_name
        FROM loan_items li
        JOIN copies c ON li.copy_id = c.id
        JOIN catalog_titles t ON c.title_id = t.id
        JOIN loans l ON li.loan_id = l.id
        LEFT JOIN members m ON l.member_id = m.id
        {where_sql}
        ORDER BY li.due_at ASC
        LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def get_legacy_extra(conn: sqlite3.Connection, item_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil catatan denda/penggantian lama dari `legacy_loan_item_extra` (R4, DEC-024)."""
    row = conn.execute(
        "SELECT * FROM legacy_loan_item_extra WHERE loan_item_id = ?;", (item_id,)
    ).fetchone()
    return dict(row) if row else None


def save_legacy_extra(
    conn: sqlite3.Connection,
    item_id: str,
    fine_overdue: int = 0,
    fine_condition: int = 0,
    status_penggantian: Optional[str] = None,
    catatan_penggantian: Optional[str] = None
) -> None:
    """Menyimpan data denda/penggantian lama ke tabel arsip `legacy_loan_item_extra`."""
    conn.execute(
        """
        INSERT OR REPLACE INTO legacy_loan_item_extra (
            loan_item_id, fine_overdue, fine_condition,
            status_penggantian, catatan_penggantian
        ) VALUES (?, ?, ?, ?, ?);
        """,
        (item_id, fine_overdue, fine_condition, status_penggantian, catatan_penggantian),
    )

