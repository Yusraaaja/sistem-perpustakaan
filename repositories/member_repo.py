# -*- coding: utf-8 -*-
"""
Repositori Anggota Perpustakaan (members & member_categories).
Memenuhi Sub-Fase 2A, LIB-MEMBER-001, DEC-020, DEC-023 (tanpa kolom kelas & telepon), R2, dan Task 4-02.
"""
import sqlite3
from typing import Optional, List, Dict, Any, Set

import id_generator
import timeutil
from policy import OFFICIAL_MEMBER_CATEGORIES
from .catalog_repo import escape_like_pattern

VALID_MEMBER_STATUSES = {"aktif", "nonaktif"}


def _row_to_dict(row: Any, cur: Optional[sqlite3.Cursor] = None) -> Optional[Dict[str, Any]]:
    """Helper konversi baris database menjadi dict, tahan variasi row_factory."""
    if row is None:
        return None
    if isinstance(row, sqlite3.Row) or isinstance(row, dict):
        return dict(row)
    if cur and cur.description:
        col_names = [c[0] for c in cur.description]
        return dict(zip(col_names, row))
    try:
        return dict(row)
    except Exception:
        return {}


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
    cur = conn.execute(
        "SELECT * FROM member_categories WHERE id = ?;", (category_id,)
    )
    row = cur.fetchone()
    return _row_to_dict(row, cur)


def list_categories(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Mendaftar semua kategori anggota perpustakaan."""
    cur = conn.execute(
        "SELECT * FROM member_categories ORDER BY id ASC;"
    )
    rows = cur.fetchall()
    return [_row_to_dict(r, cur) for r in rows]


def seed_default_categories(conn: sqlite3.Connection) -> int:
    """
    Melakukan seeding 5 kategori anggota resmi (Task 4-02 & MIGRASI_F1B):
    1. MC-MURID: murid (Siswa / Murid berdasarkan jurusan)
    2. MC-GURU-JUR: guru_jurusan (Guru kejuruan berdasarkan program keahlian)
    3. MC-GURU-UMUM: guru_umum (Guru mata pelajaran umum)
    4. MC-STAF: staf (Tenaga kependidikan / staf tata usaha)
    5. MC-TEKNISI: teknisi (Laboran / teknisi bengkel/lab)
    
    Bersifat idempoten (menjalankannya kembali tidak menimbulkan duplikasi atau error).
    Jika kategori sudah ada, dibiarkan utuh (DO NOTHING) agar tidak menimpa penyesuaian lokal.
    Mengembalikan total kategori di tabel.
    """
    for cat_id, jenis, keterangan in OFFICIAL_MEMBER_CATEGORIES:
        conn.execute(
            """
            INSERT INTO member_categories (id, jenis, keterangan)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO NOTHING;
            """,
            (cat_id, jenis, keterangan),
        )
    row = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()
    return int(row[0]) if row else 0



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
    cur = conn.execute(sql, (member_id,))
    row = cur.fetchone()
    return _row_to_dict(row, cur)


def list_members(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Mendaftar anggota perpustakaan dengan filter status, kategori, atau pencarian nama/ID.
    Mendukung paginasi via limit dan offset serta escaping wildcard LIKE (% dan _) secara aman.
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
        term = f"%{escape_like_pattern(search.strip())}%"
        conditions.append("(m.nama LIKE ? ESCAPE '\\' OR m.id LIKE ? ESCAPE '\\')")
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
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])
    cur = conn.execute(sql, tuple(params))
    rows = cur.fetchall()
    return [_row_to_dict(r, cur) for r in rows]


def count_members(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    search: Optional[str] = None
) -> int:
    """
    Menghitung total baris anggota berdasarkan filter status, kategori, atau pencarian (Task 4-02).
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
        term = f"%{escape_like_pattern(search.strip())}%"
        conditions.append("(m.nama LIKE ? ESCAPE '\\' OR m.id LIKE ? ESCAPE '\\')")
        params.extend([term, term])

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT COUNT(*)
        FROM members m
        JOIN member_categories mc ON m.category_id = mc.id
        {where_sql};
    """
    row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0]) if row else 0


def get_member_summary_metrics(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengambil metrik ringkasan data anggota untuk antarmuka admin (Task 4-02):
    - total_anggota: total seluruh anggota terdaftar
    - total_aktif: jumlah anggota berstatus aktif
    - total_nonaktif: jumlah anggota berstatus nonaktif
    - total_kategori: jumlah kategori terdefinisi
    - kategori_breakdown: distribusi jumlah anggota per kategori
    """
    total_anggota = conn.execute("SELECT COUNT(*) FROM members;").fetchone()[0]
    total_aktif = conn.execute("SELECT COUNT(*) FROM members WHERE status = 'aktif';").fetchone()[0]
    total_nonaktif = conn.execute("SELECT COUNT(*) FROM members WHERE status = 'nonaktif';").fetchone()[0]
    total_kategori = conn.execute("SELECT COUNT(*) FROM member_categories;").fetchone()[0]

    cur_cat = conn.execute(
        """
        SELECT mc.id, mc.jenis, mc.keterangan, COUNT(m.id) AS member_count
        FROM member_categories mc
        LEFT JOIN members m ON mc.id = m.category_id
        GROUP BY mc.id
        ORDER BY mc.id ASC;
        """
    )
    cat_rows = cur_cat.fetchall()

    return {
        "total_anggota": int(total_anggota),
        "total_aktif": int(total_aktif),
        "total_nonaktif": int(total_nonaktif),
        "total_kategori": int(total_kategori),
        "kategori_breakdown": [_row_to_dict(r, cur_cat) for r in cat_rows],
    }



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
    """Memperbarui atribut nama, kategori, atau status anggota."""
    allowed = {"nama", "category_id", "status"}
    set_clauses = []
    params: List[Any] = []

    for key in allowed:
        if key in data and data[key] is not None:
            if key == "status":
                st = str(data[key]).strip().lower()
                if st not in VALID_MEMBER_STATUSES:
                    raise ValueError(f"Status anggota tidak valid: {st}. Pilihan: {VALID_MEMBER_STATUSES}")
                set_clauses.append("status = ?")
                params.append(st)
            elif key == "nama":
                nm = str(data[key]).strip()
                if not nm:
                    raise ValueError("Field 'nama' tidak boleh kosong.")
                set_clauses.append("nama = ?")
                params.append(nm)
            elif key == "category_id":
                cat = str(data[key]).strip()
                if not cat:
                    raise ValueError("Field 'category_id' tidak boleh kosong.")
                set_clauses.append("category_id = ?")
                params.append(cat)

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
    cur = conn.execute(
        """
        UPDATE members
        SET qr_version = qr_version + 1, updated_at = ?
        WHERE id = ?;
        """,
        (now_iso, member_id),
    )
    if cur.rowcount == 0:
        raise ValueError(f"Anggota dengan ID '{member_id}' tidak ditemukan.")
    row = conn.execute("SELECT qr_version FROM members WHERE id = ?;", (member_id,)).fetchone()
    if not row:
        raise ValueError(f"Anggota dengan ID '{member_id}' tidak ditemukan.")
    return int(row[0] if isinstance(row, (tuple, list)) else row["qr_version"])

