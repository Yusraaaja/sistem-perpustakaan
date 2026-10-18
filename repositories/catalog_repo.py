# -*- coding: utf-8 -*-
"""
Repositori Judul Katalog (catalog_titles & v_title_availability).
Memenuhi Sub-Fase 2A, DEC-004, R2, R5, R10.
"""
import sqlite3
import json
from typing import Optional, List, Dict, Any, Set

import id_generator
import timeutil


def exists_by_id(conn: sqlite3.Connection, title_id: str) -> bool:
    """Memeriksa keberadaan judul katalog berdasarkan ID."""
    if not title_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM catalog_titles WHERE id = ? LIMIT 1;", (title_id,)
    ).fetchone()
    return row is not None


def create_title(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None
) -> str:
    """
    Membuat judul katalog baru di tabel `catalog_titles`.
    Menggunakan ID Generator Crockford Base32 dengan prefix 'T-' dan verifikasi tabrakan dua lapis.
    """
    if "judul" not in data or not str(data["judul"]).strip():
        raise ValueError("Field 'judul' wajib diisi dan tidak boleh kosong.")

    # Generator ID dengan collision retry dua lapis
    title_id = data.get("id")
    if not title_id:
        def is_taken(candidate: str) -> bool:
            return (seen_ids is not None and candidate in seen_ids) or exists_by_id(conn, candidate)

        title_id = id_generator.generate_title_id(is_taken=is_taken)

    if seen_ids is not None:
        seen_ids.add(title_id)

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    created_at = data.get("created_at") or now_iso
    updated_at = data.get("updated_at") or now_iso

    metadata_json = data.get("metadata_json")
    if isinstance(metadata_json, (dict, list)):
        metadata_json = json.dumps(metadata_json, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO catalog_titles (
            id, judul, subjudul, penulis, penerbit, tahun, isbn,
            kategori, ddc, sinopsis, cover_path, harga_buku,
            metadata_json, legacy_buku_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            title_id,
            str(data["judul"]).strip(),
            data.get("subjudul"),
            data.get("penulis"),
            data.get("penerbit"),
            data.get("tahun"),
            data.get("isbn"),
            data.get("kategori"),
            data.get("ddc"),
            data.get("sinopsis"),
            data.get("cover_path"),
            int(data.get("harga_buku") or 0),
            metadata_json,
            data.get("legacy_buku_id"),
            created_at,
            updated_at,
        ),
    )
    return title_id


def get_title_by_id(conn: sqlite3.Connection, title_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil satu judul katalog berdasarkan ID."""
    row = conn.execute(
        "SELECT * FROM catalog_titles WHERE id = ?;", (title_id,)
    ).fetchone()
    return dict(row) if row else None


def get_title_by_legacy_id(conn: sqlite3.Connection, legacy_buku_id: int) -> Optional[Dict[str, Any]]:
    """Mengambil satu judul katalog berdasarkan legacy_buku_id."""
    row = conn.execute(
        "SELECT * FROM catalog_titles WHERE legacy_buku_id = ?;", (legacy_buku_id,)
    ).fetchone()
    return dict(row) if row else None


def list_titles(
    conn: sqlite3.Connection,
    search: Optional[str] = None,
    kategori: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Mencari dan mendaftar judul katalog.
    Mendukung filter pencarian kata kunci (judul, penulis, isbn) dan kategori.
    """
    conditions = []
    params: List[Any] = []

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(judul LIKE ? OR penulis LIKE ? OR isbn LIKE ?)")
        params.extend([term, term, term])

    if kategori and kategori.strip():
        conditions.append("kategori = ?")
        params.append(kategori.strip())

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT * FROM catalog_titles
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])

    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def update_title(conn: sqlite3.Connection, title_id: str, data: Dict[str, Any]) -> bool:
    """
    Memperbarui atribut judul katalog.
    Secara otomatis memperbarui kolom `updated_at`.
    """
    allowed_columns = {
        "judul", "subjudul", "penulis", "penerbit", "tahun", "isbn",
        "kategori", "ddc", "sinopsis", "cover_path", "harga_buku",
        "metadata_json"
    }
    set_clauses = []
    params: List[Any] = []

    for key, val in data.items():
        if key in allowed_columns:
            if key == "metadata_json" and isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            elif key == "harga_buku" and val is not None:
                val = int(val)
            set_clauses.append(f"{key} = ?")
            params.append(val)

    if not set_clauses:
        return False

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    set_clauses.append("updated_at = ?")
    params.append(now_iso)

    params.append(title_id)
    sql = f"UPDATE catalog_titles SET {', '.join(set_clauses)} WHERE id = ?;"
    cur = conn.execute(sql, tuple(params))
    return cur.rowcount > 0


def get_title_availability(
    conn: sqlite3.Connection,
    title_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Mengambil data agregasi stok ketersediaan judul dari VIEW `v_title_availability` (R10).
    Mengembalikan kolom: title_id, judul, total_semua, total_aktif, available_copies, borrowed_copies.
    """
    if title_id:
        rows = conn.execute(
            "SELECT * FROM v_title_availability WHERE title_id = ?;", (title_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM v_title_availability ORDER BY judul ASC;"
        ).fetchall()
    return [dict(r) for r in rows]

