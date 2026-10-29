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
            data.get("subjudul") or data.get("sub_judul"),
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


def escape_like_pattern(text: str, escape_char: str = "\\") -> str:
    """
    Meng-escape karakter khusus LIKE (% dan _) serta karakter escape itu sendiri
    agar pencarian substring bersifat literal (Task 3-12).
    """
    return (
        text.replace(escape_char, escape_char + escape_char)
            .replace("%", escape_char + "%")
            .replace("_", escape_char + "_")
    )


def search_catalog_titles_with_availability(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    kategori: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Mencari dan mendaftar judul katalog publik menggunakan view `v_title_availability` (Task 3-12 / R10).
    - Menghubungkan `catalog_titles` secara langsung dengan `v_title_availability`.
    - Ketersediaan stok (`available_copies`, `total_aktif`, `total_semua`, `borrowed_copies`)
      diambil langsung dari database view aktual.
    - Eksemplar nonaktif, rusak, hilang, dan dalam penanganan tidak pernah dihitung sebagai tersedia.
    - Query berparameter dengan LIKE ESCAPE untuk mencegah SQL injection dan wildcard injection.
    - Mendukung pencarian multi-kolom: judul, subjudul, penulis, penerbit, isbn, kategori,
      ID judul (T-XXXXXX), ID eksemplar (C-XXXXXX), nomor registrasi lama, dan legacy_buku_id.
    - MURNI BACA (READ-ONLY) - Tidak mengubah data database.
    """
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    has_legacy_copy_map = "legacy_copy_map" in tables

    conditions = []
    params: List[Any] = []

    clean_query = str(query or "").strip()
    if clean_query:
        escaped_term = f"%{escape_like_pattern(clean_query)}%"
        
        search_clauses = [
            "t.judul LIKE ? ESCAPE '\\'",
            "t.subjudul LIKE ? ESCAPE '\\'",
            "t.penulis LIKE ? ESCAPE '\\'",
            "t.penerbit LIKE ? ESCAPE '\\'",
            "t.isbn LIKE ? ESCAPE '\\'",
            "t.kategori LIKE ? ESCAPE '\\'",
            "t.id LIKE ? ESCAPE '\\'",
            "CAST(t.legacy_buku_id AS TEXT) LIKE ? ESCAPE '\\'",
            "EXISTS (SELECT 1 FROM copies c WHERE c.title_id = t.id AND c.id LIKE ? ESCAPE '\\')",
        ]
        term_params = [escaped_term] * 9

        if has_legacy_copy_map:
            search_clauses.append(
                "EXISTS (SELECT 1 FROM copies c JOIN legacy_copy_map lcm ON c.id = lcm.copy_id WHERE c.title_id = t.id AND lcm.old_ref LIKE ? ESCAPE '\\')"
            )
            term_params.append(escaped_term)

        conditions.append(f"({' OR '.join(search_clauses)})")
        params.extend(term_params)

    clean_kat = str(kategori or "").strip()
    if clean_kat:
        conditions.append("t.kategori = ?")
        params.append(clean_kat)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    limit_sql = ""
    if limit is not None and limit > 0:
        limit_sql = "LIMIT ? OFFSET ?"
        params.extend([int(limit), int(max(0, offset))])

    sql = f"""
        SELECT 
            t.id,
            t.judul,
            t.subjudul,
            t.penulis,
            t.penerbit,
            t.tahun,
            t.isbn,
            t.kategori,
            t.ddc,
            t.sinopsis,
            t.cover_path,
            t.harga_buku,
            t.metadata_json,
            t.legacy_buku_id,
            t.created_at,
            t.updated_at,
            v.total_semua,
            v.total_aktif,
            v.available_copies,
            v.borrowed_copies,
            (SELECT c.lokasi_rak FROM copies c WHERE c.title_id = t.id AND c.lokasi_rak IS NOT NULL AND c.lokasi_rak != '' LIMIT 1) AS lokasi_rak,
            (SELECT GROUP_CONCAT(c.id, ', ') FROM copies c WHERE c.title_id = t.id) AS id_buku_fisik
        FROM catalog_titles t
        JOIN v_title_availability v ON t.id = v.title_id
        {where_sql}
        ORDER BY t.created_at DESC, t.id DESC
        {limit_sql};
    """
    rows = conn.execute(sql, tuple(params)).fetchall()
    
    results = []
    for r in rows:
        d = dict(r)
        d["stok"] = d["available_copies"]
        d["sub_judul"] = d.get("subjudul") or ""
        d["tahun_terbit"] = d.get("tahun") or ""
        d["cover_img"] = d.get("cover_path") or ""
        results.append(d)

    return results


def count_search_catalog_titles(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    kategori: Optional[str] = None
) -> int:
    """
    Menghitung total judul katalog yang sesuai dengan kriteria pencarian (untuk pagination).
    MURNI BACA (READ-ONLY).
    """
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    has_legacy_copy_map = "legacy_copy_map" in tables

    conditions = []
    params: List[Any] = []

    clean_query = str(query or "").strip()
    if clean_query:
        escaped_term = f"%{escape_like_pattern(clean_query)}%"
        
        search_clauses = [
            "t.judul LIKE ? ESCAPE '\\'",
            "t.subjudul LIKE ? ESCAPE '\\'",
            "t.penulis LIKE ? ESCAPE '\\'",
            "t.penerbit LIKE ? ESCAPE '\\'",
            "t.isbn LIKE ? ESCAPE '\\'",
            "t.kategori LIKE ? ESCAPE '\\'",
            "t.id LIKE ? ESCAPE '\\'",
            "CAST(t.legacy_buku_id AS TEXT) LIKE ? ESCAPE '\\'",
            "EXISTS (SELECT 1 FROM copies c WHERE c.title_id = t.id AND c.id LIKE ? ESCAPE '\\')",
        ]
        term_params = [escaped_term] * 9

        if has_legacy_copy_map:
            search_clauses.append(
                "EXISTS (SELECT 1 FROM copies c JOIN legacy_copy_map lcm ON c.id = lcm.copy_id WHERE c.title_id = t.id AND lcm.old_ref LIKE ? ESCAPE '\\')"
            )
            term_params.append(escaped_term)

        conditions.append(f"({' OR '.join(search_clauses)})")
        params.extend(term_params)

    clean_kat = str(kategori or "").strip()
    if clean_kat:
        conditions.append("t.kategori = ?")
        params.append(clean_kat)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT COUNT(t.id)
        FROM catalog_titles t
        JOIN v_title_availability v ON t.id = v.title_id
        {where_sql};
    """
    row = conn.execute(sql, tuple(params)).fetchone()
    return row[0] if row else 0


def get_catalog_metrics_v2(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengambil metrik ringkasan katalog publik untuk dashboard koleksi (skema v2).
    - total_buku: jumlah seluruh eksemplar aktif yang tersedia untuk dipinjam di rak (SUM available_copies).
    - total_judul: total variasi judul dalam katalog (COUNT catalog_titles).
    - total_dipinjam: total eksemplar yang sedang berada dalam peminjaman aktif (SUM borrowed_copies).
    - buku_populer: 5 judul paling sering dipinjam sepanjang riwayat sirkulasi.
    MURNI BACA (READ-ONLY).
    """
    row_avail = conn.execute("""
        SELECT 
            COALESCE(SUM(available_copies), 0) AS total_tersedia,
            COALESCE(SUM(borrowed_copies), 0) AS total_dipinjam,
            COALESCE(SUM(total_aktif), 0) AS total_aktif,
            COALESCE(SUM(total_semua), 0) AS total_semua
        FROM v_title_availability;
    """).fetchone()

    total_buku = row_avail["total_tersedia"] if row_avail else 0
    total_dipinjam = row_avail["total_dipinjam"] if row_avail else 0

    row_titles = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()
    total_judul = row_titles[0] if row_titles else 0

    buku_populer_rows = conn.execute("""
        SELECT 
            t.judul, 
            t.kategori, 
            COUNT(li.id) AS total_dipinjam
        FROM catalog_titles t
        JOIN copies c ON t.id = c.title_id
        JOIN loan_items li ON c.id = li.copy_id
        GROUP BY t.id
        ORDER BY total_dipinjam DESC
        LIMIT 5;
    """).fetchall()

    buku_populer = [dict(r) for r in buku_populer_rows]

    return {
        "total_buku": total_buku,
        "total_judul": total_judul,
        "total_dipinjam": total_dipinjam,
        "buku_populer": buku_populer,
    }



def list_all_titles_for_duplicate_check(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Mengambil seluruh daftar judul katalog untuk keperluan pengecekan potensi duplikat (Task 3-04).
    Mendukung skema v2 (tabel catalog_titles) dan fallback skema legacy (tabel buku).
    """
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    if "catalog_titles" in tables:
        cols = [c[1] for c in cursor.execute("PRAGMA table_info(catalog_titles)").fetchall()]
        sel_cols = ["id", "judul", "penulis", "isbn", "kategori"]
        for opt in ["subjudul", "penerbit", "tahun", "created_at"]:
            if opt in cols:
                sel_cols.append(opt)
        col_sql = ", ".join(sel_cols)
        order_sql = "ORDER BY created_at DESC" if "created_at" in cols else "ORDER BY rowid DESC"
        rows = conn.execute(f"SELECT {col_sql} FROM catalog_titles {order_sql};").fetchall()
        return [dict(r) for r in rows]

    if "buku" in tables:
        rows = conn.execute(
            """
            SELECT CAST(id AS TEXT) AS id, judul, penulis, isbn, kategori
            FROM buku
            ORDER BY id DESC;
            """
        ).fetchall()
        return [dict(r) for r in rows]

    return []


