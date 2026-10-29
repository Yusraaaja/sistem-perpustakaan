# -*- coding: utf-8 -*-
"""
Repositori Eksemplar Fisik Buku (copies, legacy_copy_map, & v_copy_availability).
Memenuhi Sub-Fase 2A, LIB-COPY-001, LIB-COPY-002, R2, R8, R9, R12.
"""
import sqlite3
from typing import Optional, List, Dict, Any, Set

import id_generator
import timeutil

VALID_COPY_STATUSES = {"aktif", "nonaktif", "hilang", "rusak", "dalam_penanganan"}


def exists_by_id(conn: sqlite3.Connection, copy_id: str) -> bool:
    """Memeriksa keberadaan eksemplar fisik berdasarkan ID."""
    if not copy_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM copies WHERE id = ? LIMIT 1;", (copy_id,)
    ).fetchone()
    return row is not None


def create_copy(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    seen_ids: Optional[Set[str]] = None
) -> str:
    """
    Membuat satu eksemplar fisik buku di tabel `copies`.
    Menggunakan ID Generator Crockford Base32 dengan prefix 'C-' dan verifikasi tabrakan dua lapis.
    """
    if "title_id" not in data or not str(data["title_id"]).strip():
        raise ValueError("Field 'title_id' wajib diisi.")

    status = data.get("status") or "aktif"
    if status not in VALID_COPY_STATUSES:
        raise ValueError(f"Status eksemplar tidak valid: {status}. Pilihan: {VALID_COPY_STATUSES}")

    copy_id = data.get("id")
    if not copy_id:
        def is_taken(candidate: str) -> bool:
            return (seen_ids is not None and candidate in seen_ids) or exists_by_id(conn, candidate)

        copy_id = id_generator.generate_copy_id(is_taken=is_taken)

    if seen_ids is not None:
        seen_ids.add(copy_id)

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    created_at = data.get("created_at") or now_iso

    conn.execute(
        """
        INSERT INTO copies (
            id, title_id, call_number, status, lokasi_rak,
            tanggal_masuk, sumber, harga, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            copy_id,
            str(data["title_id"]).strip(),
            data.get("call_number"),
            status,
            data.get("lokasi_rak"),
            data.get("tanggal_masuk"),
            data.get("sumber"),
            int(data.get("harga") or 0),
            created_at,
        ),
    )
    return copy_id


def create_copies_batch(
    conn: sqlite3.Connection,
    title_id: str,
    count: int,
    base_data: Optional[Dict[str, Any]] = None,
    seen_ids: Optional[Set[str]] = None
) -> List[str]:
    """
    Membuat sejumlah `count` eksemplar baru secara massal untuk satu judul katalog.
    Memenuhi P2-01: mengelola cache set lokal `seen_ids` + DB lookup untuk pencegahan tabrakan batch.
    """
    if count <= 0:
        return []

    local_seen = seen_ids if seen_ids is not None else set()
    base = base_data.copy() if base_data else {}
    base["title_id"] = title_id

    created_ids: List[str] = []
    for _ in range(count):
        new_id = create_copy(conn, base, seen_ids=local_seen)
        created_ids.append(new_id)

    return created_ids


def get_copy_by_id(conn: sqlite3.Connection, copy_id: str) -> Optional[Dict[str, Any]]:
    """
    Mengambil satu eksemplar fisik berdasarkan ID, disertai data judul buku.
    """
    sql = """
        SELECT 
            c.*,
            t.judul AS title_judul,
            t.penulis AS title_penulis,
            t.isbn AS title_isbn
        FROM copies c
        JOIN catalog_titles t ON c.title_id = t.id
        WHERE c.id = ?;
    """
    cur = conn.cursor()
    row = cur.execute(sql, (copy_id,)).fetchone()
    if not row:
        return None
    if isinstance(row, (sqlite3.Row, dict)):
        return dict(row)
    col_names = [col[0] for col in cur.description]
    return dict(zip(col_names, row))


def list_copies_by_title(
    conn: sqlite3.Connection,
    title_id: str,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Mendaftar semua eksemplar untuk judul katalog tertentu."""
    if status:
        rows = conn.execute(
            "SELECT * FROM copies WHERE title_id = ? AND status = ? ORDER BY id ASC;",
            (title_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM copies WHERE title_id = ? ORDER BY id ASC;",
            (title_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_copy_status(conn: sqlite3.Connection, copy_id: str, status: str) -> bool:
    """
    Memperbarui status eksemplar fisik ('aktif', 'nonaktif', 'hilang', 'rusak', 'dalam_penanganan').
    Memenuhi P2-02: penghapusan buku dilakukan via penonaktifan status, bukan DELETE.
    """
    if status not in VALID_COPY_STATUSES:
        raise ValueError(f"Status tidak valid: '{status}'. Pilihan: {VALID_COPY_STATUSES}")

    cur = conn.execute(
        "UPDATE copies SET status = ? WHERE id = ?;", (status, copy_id)
    )
    return cur.rowcount > 0


def update_copy_location(
    conn: sqlite3.Connection,
    copy_id: str,
    lokasi_rak: Optional[str] = None,
    call_number: Optional[str] = None
) -> bool:
    """Memperbarui lokasi rak dan/atau nomor panggil eksemplar."""
    set_clauses = []
    params: List[Any] = []

    if lokasi_rak is not None:
        set_clauses.append("lokasi_rak = ?")
        params.append(lokasi_rak)
    if call_number is not None:
        set_clauses.append("call_number = ?")
        params.append(call_number)

    if not set_clauses:
        return False

    params.append(copy_id)
    sql = f"UPDATE copies SET {', '.join(set_clauses)} WHERE id = ?;"
    cur = conn.execute(sql, tuple(params))
    return cur.rowcount > 0


def get_copy_availability(
    conn: sqlite3.Connection,
    copy_id: Optional[str] = None,
    title_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Mengambil data ketersediaan eksemplar dari VIEW `v_copy_availability`.
    Kolom: copy_id, title_id, copy_status, availability_status, active_loan_id, borrowed_at, due_at.
    """
    conditions = []
    params: List[Any] = []

    if copy_id:
        conditions.append("copy_id = ?")
        params.append(copy_id)
    if title_id:
        conditions.append("title_id = ?")
        params.append(title_id)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM v_copy_availability {where_sql} ORDER BY copy_id ASC;"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def get_copy_by_legacy_ref(conn: sqlite3.Connection, old_ref: str) -> Optional[Dict[str, Any]]:
    """
    Mencari eksemplar baru berdasarkan nomor registrasi lama dari `legacy_copy_map` (R9).
    """
    sql = """
        SELECT c.*, lcm.old_ref, lcm.legacy_buku_id
        FROM legacy_copy_map lcm
        JOIN copies c ON lcm.copy_id = c.id
        WHERE lcm.old_ref = ?;
    """
    row = conn.execute(sql, (old_ref,)).fetchone()
    return dict(row) if row else None


def map_legacy_copy(
    conn: sqlite3.Connection,
    old_ref: str,
    copy_id: str,
    legacy_buku_id: Optional[int] = None
) -> None:
    """Mencatat pemetaan nomor registrasi lama ke eksemplar v2 (R9)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO legacy_copy_map (old_ref, copy_id, legacy_buku_id)
        VALUES (?, ?, ?);
        """,
        (old_ref, copy_id, legacy_buku_id),
    )


def get_copies_for_labels(
    conn: sqlite3.Connection,
    title_id: Optional[str] = None,
    copy_ids: Optional[Sequence[str]] = None,
    search: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Mengambil data eksemplar beserta detail katalog untuk cetak label QR (Task 3-08).
    Mendukung skema v2 (copies JOIN catalog_titles) dan fallback aman ke skema legacy (buku).
    MURNI BACA (READ-ONLY) - Tidak mengubah state database sama sekali.
    """
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    if "copies" in tables and "catalog_titles" in tables:
        conditions = []
        params: List[Any] = []

        if copy_ids:
            seen_ids: Set[str] = set()
            clean_ids: List[str] = []
            for cid in copy_ids:
                scid = str(cid).strip()
                if scid and scid not in seen_ids:
                    seen_ids.add(scid)
                    clean_ids.append(scid)
            if clean_ids:
                placeholders = ",".join(["?"] * len(clean_ids))
                conditions.append(f"c.id IN ({placeholders})")
                params.extend(clean_ids)
            else:
                return []
        elif title_id:
            conditions.append("c.title_id = ? AND c.status = 'aktif'")
            params.append(str(title_id).strip())
        else:
            conditions.append("c.status = 'aktif'")

        if search and str(search).strip():
            s = f"%{str(search).strip()}%"
            conditions.append("(c.id LIKE ? OR t.judul LIKE ? OR t.penulis LIKE ?)")
            params.extend([s, s, s])

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(max(1, min(int(limit), 500)))

        query = f"""
            SELECT 
                c.id AS copy_id,
                c.title_id,
                c.status AS copy_status,
                c.call_number,
                c.lokasi_rak,
                c.created_at AS copy_created_at,
                t.judul,
                t.penulis,
                t.isbn,
                t.kategori
            FROM copies c
            JOIN catalog_titles t ON c.title_id = t.id
            {where_clause}
            ORDER BY c.created_at DESC, c.id ASC
            LIMIT ?;
        """
        cursor.execute(query, tuple(params))
        col_names = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        results: List[Dict[str, Any]] = []
        for r in rows:
            if isinstance(r, sqlite3.Row):
                results.append(dict(r))
            elif isinstance(r, dict):
                results.append(r)
            else:
                results.append(dict(zip(col_names, r)))
        return results

    if "buku" in tables:
        import json
        query = "SELECT id, judul, penulis, isbn, kategori, lokasi_rak, id_buku_fisik FROM buku"
        params = []
        conds = []
        if title_id:
            conds.append("id = ?")
            params.append(title_id)
        if search and str(search).strip():
            s = f"%{str(search).strip()}%"
            conds.append("(judul LIKE ? OR penulis LIKE ? OR id_buku_fisik LIKE ?)")
            params.extend([s, s, s])
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))

        cursor.execute(query, tuple(params))
        col_names = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        results = []
        target_copy_ids = set(str(cid).strip() for cid in copy_ids) if copy_ids else None

        for raw_r in rows:
            r = dict(raw_r) if isinstance(raw_r, (sqlite3.Row, dict)) else dict(zip(col_names, raw_r))
            b_id = str(r["id"])
            judul = r["judul"] or ""
            penulis = r["penulis"] or ""
            isbn = r["isbn"]
            kategori = r["kategori"]
            lokasi = r["lokasi_rak"]
            raw_ids = r["id_buku_fisik"]
            copy_list = []
            if raw_ids:
                try:
                    parsed = json.loads(raw_ids)
                    if isinstance(parsed, list):
                        copy_list = [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    pass
            if not copy_list:
                copy_list = [f"C-{b_id}"]

            for cid in copy_list:
                if target_copy_ids is not None and cid not in target_copy_ids:
                    continue
                results.append({
                    "copy_id": cid,
                    "title_id": b_id,
                    "copy_status": "aktif",
                    "call_number": None,
                    "lokasi_rak": lokasi,
                    "copy_created_at": None,
                    "judul": judul,
                    "penulis": penulis,
                    "isbn": isbn,
                    "kategori": kategori,
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return results

    return []


def get_unlabeled_candidate_copies(
    conn: sqlite3.Connection,
    search: Optional[str] = None,
    lokasi_rak: Optional[str] = None,
    legacy_only: bool = False,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Mengambil data eksemplar buku lama / kandidat di rak yang perlu diverifikasi fisik labelnya (Task 3-09).
    Sistem tidak mencatat penempelan fisik label di database; fungsi ini menyajikan kandidat eksemplar
    berdasarkan integritas data historis (legacy_copy_map / legacy_buku_id) dan eksemplar aktif di rak.
    MURNI BACA (READ-ONLY) - Tidak menulis ke database sama sekali.
    """
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    if "copies" in tables and "catalog_titles" in tables:
        conditions = ["c.status = 'aktif'"]
        params: List[Any] = []

        if legacy_only:
            conditions.append("(lcm.copy_id IS NOT NULL OR t.legacy_buku_id IS NOT NULL)")

        if search and str(search).strip():
            s = f"%{str(search).strip()}%"
            conditions.append("(c.id LIKE ? OR lcm.old_ref LIKE ? OR t.judul LIKE ? OR t.penulis LIKE ?)")
            params.extend([s, s, s, s])

        if lokasi_rak and str(lokasi_rak).strip():
            conditions.append("c.lokasi_rak = ?")
            params.append(str(lokasi_rak).strip())

        where_clause = "WHERE " + " AND ".join(conditions)
        params.append(max(1, min(int(limit), 500)))

        query = f"""
            SELECT 
                c.id AS copy_id,
                c.title_id,
                c.status AS copy_status,
                c.call_number,
                c.lokasi_rak,
                c.tanggal_masuk,
                c.sumber,
                c.created_at AS copy_created_at,
                t.judul,
                t.penulis,
                t.isbn,
                t.kategori,
                lcm.old_ref AS legacy_ref,
                t.legacy_buku_id
            FROM copies c
            JOIN catalog_titles t ON c.title_id = t.id
            LEFT JOIN legacy_copy_map lcm ON c.id = lcm.copy_id
            {where_clause}
            ORDER BY 
                CASE WHEN c.lokasi_rak IS NOT NULL AND c.lokasi_rak != '' THEN 0 ELSE 1 END,
                c.lokasi_rak ASC,
                t.judul ASC,
                c.id ASC
            LIMIT ?;
        """
        cursor.execute(query, tuple(params))
        col_names = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        results: List[Dict[str, Any]] = []
        for r in rows:
            if isinstance(r, sqlite3.Row):
                results.append(dict(r))
            elif isinstance(r, dict):
                results.append(r)
            else:
                results.append(dict(zip(col_names, r)))
        return results

    if "buku" in tables:
        import json
        query = "SELECT id, judul, penulis, isbn, kategori, lokasi_rak, tanggal_masuk, id_buku_fisik FROM buku"
        params = []
        conds = []
        if search and str(search).strip():
            s = f"%{str(search).strip()}%"
            conds.append("(judul LIKE ? OR penulis LIKE ? OR id_buku_fisik LIKE ?)")
            params.extend([s, s, s])
        if lokasi_rak and str(lokasi_rak).strip():
            conds.append("lokasi_rak = ?")
            params.append(str(lokasi_rak).strip())
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY lokasi_rak ASC, id ASC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))

        cursor.execute(query, tuple(params))
        col_names = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        results = []

        for raw_r in rows:
            r = dict(raw_r) if isinstance(raw_r, (sqlite3.Row, dict)) else dict(zip(col_names, raw_r))
            b_id = str(r["id"])
            judul = r["judul"] or ""
            penulis = r["penulis"] or ""
            isbn = r["isbn"]
            kategori = r["kategori"]
            lokasi = r["lokasi_rak"]
            tgl_masuk = r["tanggal_masuk"]
            raw_ids = r["id_buku_fisik"]
            copy_list = []
            if raw_ids:
                try:
                    parsed = json.loads(raw_ids)
                    if isinstance(parsed, list):
                        copy_list = [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    pass
            # Aturan: Tidak membuat label palsu jika tidak ada ID eksemplar yang valid
            for cid in copy_list:
                results.append({
                    "copy_id": cid,
                    "title_id": b_id,
                    "copy_status": "aktif",
                    "call_number": None,
                    "lokasi_rak": lokasi,
                    "tanggal_masuk": tgl_masuk,
                    "sumber": None,
                    "copy_created_at": None,
                    "judul": judul,
                    "penulis": penulis,
                    "isbn": isbn,
                    "kategori": kategori,
                    "legacy_ref": cid,
                    "legacy_buku_id": int(b_id) if b_id.isdigit() else None,
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return results

    return []



