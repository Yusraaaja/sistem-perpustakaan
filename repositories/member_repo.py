# -*- coding: utf-8 -*-
"""
Repositori Anggota Perpustakaan (members & member_categories).
Memenuhi Sub-Fase 2A, LIB-MEMBER-001, DEC-020, DEC-023 (tanpa kolom kelas & telepon), R2.
"""
import sqlite3
from typing import Optional, List, Dict, Any, Set

import id_generator
import timeutil

VALID_MEMBER_STATUSES = {"aktif", "nonaktif"}


def exists_by_id(conn: sqlite3.Connection, member_id: str) -> bool:
    """Memeriksa keberadaan anggota berdasarkan ID."""
    if not member_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM members WHERE id = ? LIMIT 1;", (member_id,)
    ).fetchone()
    return row is not None


def category_exists(conn: sqlite3.Connection, category_id: str) -> bool:
    """Memeriksa keberadaan kategori anggota berdasarkan ID."""
    if not category_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM member_categories WHERE id = ? LIMIT 1;", (category_id,)
    ).fetchone()
    return row is not None


def create_category(
    conn: sqlite3.Connection,
    category_id: str,
    jenis: str,
    keterangan: Optional[str] = None
) -> str:
    """Membuat kategori anggota baru di tabel `member_categories`."""
    if not category_id or not jenis:
        raise ValueError("ID dan jenis kategori wajib diisi.")

    conn.execute(
        """
        INSERT INTO member_categories (id, jenis, keterangan)
        VALUES (?, ?, ?);
        """,
        (category_id.strip(), jenis.strip(), keterangan),
    )
    return category_id.strip()


def get_category_by_id(conn: sqlite3.Connection, category_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil satu kategori anggota berdasarkan ID."""
    row = conn.execute(
        "SELECT * FROM member_categories WHERE id = ?;", (category_id,)
    ).fetchone()
    return dict(row) if row else None


def list_categories(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Mendaftar semua kategori anggota perpustakaan."""
    rows = conn.execute(
        "SELECT * FROM member_categories ORDER BY id ASC;"
    ).fetchall()
    return [dict(r) for r in rows]


def create_member(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None
) -> str:
    """
    Membuat anggota baru di tabel `members`.
    Menerapkan DEC-023: Tanpa kolom kelas dan tanpa nomor telepon.
    Menggunakan ID Generator Crockford Base32 dengan prefix 'M-' dan verifikasi tabrakan dua lapis.
    """
    if "nama" not in data or not str(data["nama"]).strip():
        raise ValueError("Field 'nama' wajib diisi dan tidak boleh kosong.")

    category_id = data.get("category_id")
    if not category_id or not str(category_id).strip():
        raise ValueError("Field 'category_id' wajib diisi.")

    status = data.get("status") or "aktif"
    if status not in VALID_MEMBER_STATUSES:
        raise ValueError(f"Status anggota tidak valid: {status}. Pilihan: {VALID_MEMBER_STATUSES}")

    member_id = data.get("id")
    if not member_id:
        def is_taken(candidate: str) -> bool:
            return (seen_ids is not None and candidate in seen_ids) or exists_by_id(conn, candidate)

        member_id = id_generator.generate_member_id(is_taken=is_taken)

    if seen_ids is not None:
        seen_ids.add(member_id)

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    created_at = data.get("created_at") or now_iso
    updated_at = data.get("updated_at") or now_iso
    qr_version = int(data.get("qr_version") or 1)

    conn.execute(
        """
        INSERT INTO members (
            id, nama, status, category_id, qr_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            member_id,
            str(data["nama"]).strip(),
            status,
            str(category_id).strip(),
            qr_version,
            created_at,
            updated_at,
        ),
    )
    return member_id


def get_member_by_id(conn: sqlite3.Connection, member_id: str) -> Optional[Dict[str, Any]]:
    """
    Mengambil satu anggota berdasarkan ID, lengkap dengan nama jenis kategorinya.
    """
    sql = """
        SELECT 
            m.*,
            mc.jenis AS category_jenis,
            mc.keterangan AS category_keterangan
        FROM members m
        JOIN member_categories mc ON m.category_id = mc.id
        WHERE m.id = ?;
    """
    row = conn.execute(sql, (member_id,)).fetchone()
    return dict(row) if row else None


def list_members(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Mendaftar anggota perpustakaan dengan filter status, kategori, atau pencarian nama.
    """
    conditions = []
    params: List[Any] = []

    if status:
        if status not in VALID_MEMBER_STATUSES:
            raise ValueError(f"Filter status tidak valid: {status}")
        conditions.append("m.status = ?")
        params.append(status)

    if category_id:
        conditions.append("m.category_id = ?")
        params.append(category_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(m.nama LIKE ? OR m.id LIKE ?)")
        params.extend([term, term])

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT 
            m.*,
            mc.jenis AS category_jenis,
            mc.keterangan AS category_keterangan
        FROM members m
        JOIN member_categories mc ON m.category_id = mc.id
        {where_sql}
        ORDER BY m.created_at DESC
        LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def update_member_status(conn: sqlite3.Connection, member_id: str, status: str) -> bool:
    """
    Memperbarui status anggota (aktif / nonaktif). Memenuhi DEC-020.
    """
    if status not in VALID_MEMBER_STATUSES:
        raise ValueError(f"Status tidak valid: {status}. Pilihan: {VALID_MEMBER_STATUSES}")

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    cur = conn.execute(
        """
        UPDATE members 
        SET status = ?, updated_at = ?
        WHERE id = ?;
        """,
        (status, now_iso, member_id),
    )
    return cur.rowcount > 0


def update_member(conn: sqlite3.Connection, member_id: str, data: Dict[str, Any]) -> bool:
    """Memperbarui atribut nama atau kategori anggota."""
    allowed = {"nama", "category_id"}
    set_clauses = []
    params: List[Any] = []

    for key in allowed:
        if key in data and data[key] is not None:
            set_clauses.append(f"{key} = ?")
            params.append(str(data[key]).strip())

    if not set_clauses:
        return False

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    set_clauses.append("updated_at = ?")
    params.append(now_iso)

    params.append(member_id)
    sql = f"UPDATE members SET {', '.join(set_clauses)} WHERE id = ?;"
    cur = conn.execute(sql, tuple(params))
    return cur.rowcount > 0


def increment_qr_version(conn: sqlite3.Connection, member_id: str) -> int:
    """
    Menaikkan versi QR anggota untuk membatalkan QR lama jika kartu hilang atau dicetak ulang.
    """
    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    conn.execute(
        """
        UPDATE members
        SET qr_version = qr_version + 1, updated_at = ?
        WHERE id = ?;
        """,
        (now_iso, member_id),
    )
    row = conn.execute("SELECT qr_version FROM members WHERE id = ?;", (member_id,)).fetchone()
    if not row:
        raise ValueError(f"Anggota dengan ID {member_id} tidak ditemukan.")
    return int(row["qr_version"])

