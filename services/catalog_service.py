# -*- coding: utf-8 -*-
"""
Business Service untuk Manajemen Katalog & Eksemplar Fisik.
Memenuhi Sub-Fase 2B, LIB-COPY-001, LIB-COPY-002, DEC-004, DEC-011, P2-01, dan P2-02 (penonaktifan bukan DELETE).
"""
import csv
import difflib
import hashlib
import io
import json
import re
import secrets
import sqlite3
import threading
import time
from typing import Dict, Any, List, Optional, Tuple, Union

import timeutil

from policy import (
    CONFIRMATION_THRESHOLD_COPIES,
    MAX_COPIES_PER_ADD,
    CONFIRMATION_TOKEN_TTL_SECONDS,
    MAX_CATALOG_IMPORT_FILE_SIZE_BYTES,
    MAX_CATALOG_IMPORT_ROWS,
    MAX_CATALOG_SEARCH_QUERY_LENGTH,
    DEFAULT_CATALOG_PAGE_SIZE,
    MAX_CATALOG_PAGE_SIZE,
)
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
    ConfirmationTokenError,
    ConcurrencyConflictError,
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
    reason: str,
    actor: str = "admin",
    target_status: str = "nonaktif",
) -> Dict[str, Any]:
    """
    Menonaktifkan atau menandai eksemplar buku secara individual disertai alasan dan audit log (Task 3-10).
    - Memenuhi P2-02 & R12: data eksemplar fisik tetap tersimpan permanen di database (tanpa hard delete).
    - Validasi server-side: alasan wajib diisi, bermakna (5-500 karakter), ID eksemplar wajib valid.
    - Konsistensi status: menolak penonaktifan eksemplar yang sedang berada dalam peminjaman aktif (LIB-LOAN-002).
    - Idempotensi & anti-duplikasi audit: menolak penonaktifan berulang jika eksemplar sudah berstatus nonaktif.
    - Atomik: perubahan status eksemplar dan pencatatan audit_log dieksekusi dalam satu transaksi database.
    """
    if not copy_id or not str(copy_id).strip():
        raise ValidationError("ID Eksemplar wajib diisi.")
    clean_copy_id = str(copy_id).strip()

    if not reason or not str(reason).strip():
        raise ValidationError("Alasan penonaktifan wajib diisi.")
    clean_reason = str(reason).strip()
    if len(clean_reason) < 5:
        raise ValidationError("Alasan penonaktifan minimal 5 karakter.")
    if len(clean_reason) > 500:
        raise ValidationError("Alasan penonaktifan maksimal 500 karakter.")

    valid_targets = ("nonaktif", "rusak", "hilang", "dalam_penanganan")
    clean_target = str(target_status).strip().lower() if target_status else "nonaktif"
    if clean_target not in valid_targets:
        raise ValidationError(f"Status target '{target_status}' tidak valid. Pilihan yang diizinkan: {valid_targets}")

    clean_actor = str(actor).strip() if actor and str(actor).strip() else "admin"

    # Periksa tabel yang tersedia di basis data (mendukung v2 dan fallback legacy P1)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    if "copies" in tables:
        copy_obj = copy_repo.get_copy_by_id(conn, clean_copy_id)
        if not copy_obj:
            raise CopyNotFoundError(f"Eksemplar dengan ID '{clean_copy_id}' tidak ditemukan.")

        current_status = copy_obj.get("status", "aktif")
        if current_status == clean_target:
            raise InvalidOperationError(
                f"Eksemplar '{clean_copy_id}' sudah berstatus '{clean_target}'. Tidak ada perubahan yang dilakukan."
            )
        if current_status != "aktif":
            raise InvalidOperationError(
                f"Eksemplar '{clean_copy_id}' sudah berstatus '{current_status}' (tidak aktif). Hanya eksemplar aktif yang dapat dinonaktifkan."
            )

        # Cek apakah sedang berada dalam peminjaman aktif
        active_loan = loan_repo.get_active_loan_by_copy(conn, clean_copy_id)
        if active_loan:
            peminjam = active_loan.get("member_nama") or active_loan.get("legacy_nama_peminjam") or "Anggota"
            raise InvalidOperationError(
                f"Eksemplar '{clean_copy_id}' sedang dipinjam oleh '{peminjam}'. "
                "Selesaikan proses pengembalian terlebih dahulu sebelum menonaktifkan eksemplar ini."
            )

        action_name = "COPY_DEACTIVATE" if clean_target == "nonaktif" else f"COPY_MARK_{clean_target.upper()}"
        detail = {
            "previous_status": current_status,
            "new_status": clean_target,
            "title_id": copy_obj["title_id"],
            "judul": copy_obj.get("title_judul"),
        }

        with transaction_scope(conn):
            copy_repo.update_copy_status(conn, clean_copy_id, clean_target)
            audit_id = audit_repo.record_audit(
                conn,
                actor=clean_actor,
                action=action_name,
                object_type="copies",
                object_id=clean_copy_id,
                reason=clean_reason,
                detail_json=detail,
            )

        return {
            "ok": True,
            "copy_id": clean_copy_id,
            "previous_status": current_status,
            "new_status": clean_target,
            "reason": clean_reason,
            "actor": clean_actor,
            "audit_id": audit_id,
            "title_id": copy_obj["title_id"],
            "judul": copy_obj.get("title_judul"),
        }

    if "buku" in tables:
        import json
        row = conn.execute(
            "SELECT * FROM buku WHERE id = ? OR id_buku_fisik LIKE ?;",
            (clean_copy_id, f'%"{clean_copy_id}"%')
        ).fetchone()
        if not row:
            raise CopyNotFoundError(f"Eksemplar dengan ID '{clean_copy_id}' tidak ditemukan.")
        buku_dict = dict(row)

        if "peminjaman_detail" in tables:
            active_pd = conn.execute(
                "SELECT * FROM peminjaman_detail WHERE no_registrasi = ? AND status = 'Dipinjam';",
                (clean_copy_id,)
            ).fetchone()
            if active_pd:
                raise InvalidOperationError(
                    f"Eksemplar '{clean_copy_id}' sedang berada dalam peminjaman aktif. "
                    "Selesaikan proses pengembalian terlebih dahulu sebelum menonaktifkan eksemplar ini."
                )

        raw_fisik = buku_dict.get("id_buku_fisik")
        no_reg_list = []
        if raw_fisik:
            try:
                parsed = json.loads(raw_fisik)
                if isinstance(parsed, list):
                    no_reg_list = [str(x) for x in parsed]
            except Exception:
                pass

        if clean_copy_id in no_reg_list:
            no_reg_list.remove(clean_copy_id)
        new_stok = max(0, int(buku_dict.get("stok", 1)) - 1)

        with transaction_scope(conn):
            conn.execute(
                "UPDATE buku SET id_buku_fisik = ?, stok = ? WHERE id = ?;",
                (json.dumps(no_reg_list), new_stok, buku_dict["id"])
            )
            audit_id = None
            if "audit_log" in tables:
                audit_id = audit_repo.record_audit(
                    conn,
                    actor=clean_actor,
                    action="COPY_DEACTIVATE",
                    object_type="buku",
                    object_id=clean_copy_id,
                    reason=clean_reason,
                    detail_json={
                        "previous_status": "aktif",
                        "new_status": clean_target,
                        "buku_id": buku_dict["id"],
                        "judul": buku_dict.get("judul"),
                    }
                )

        return {
            "ok": True,
            "copy_id": clean_copy_id,
            "previous_status": "aktif",
            "new_status": clean_target,
            "reason": clean_reason,
            "actor": clean_actor,
            "audit_id": audit_id,
            "title_id": str(buku_dict["id"]),
            "judul": buku_dict.get("judul"),
        }

    raise CopyNotFoundError("Tabel katalog eksemplar tidak ditemukan di database.")


def get_title_with_details(conn: sqlite3.Connection, title_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil judul katalog beserta daftar eksemplar dan status ketersediaannya."""
    title = catalog_repo.get_title_by_id(conn, title_id)
    if not title:
        return None

    title["copies"] = copy_repo.get_copy_availability(conn, title_id=title_id)
    avail = catalog_repo.get_title_availability(conn, title_id=title_id)
    title["availability"] = avail[0] if avail else {}
    return title


def validate_add_book_input(
    form_data: Dict[str, Any],
    confirmation_threshold: int = CONFIRMATION_THRESHOLD_COPIES,
    max_copies: int = MAX_COPIES_PER_ADD,
) -> Dict[str, Any]:
    """
    Memvalidasi data input formulir tambah buku (Task 3-02).
    
    Kriteria Validasi:
    - Judul buku: Wajib diisi, non-empty, maksimal 255 karakter.
    - Penulis: Wajib diisi, non-empty, maksimal 255 karakter.
    - Kategori: Wajib diisi, non-empty, maksimal 100 karakter.
    - ISBN: Opsional. Jika diisi, harus valid 10 atau 13 digit angka (dengan/tanpa tanda hubung).
    - Jumlah eksemplar: Wajib diisi, integer positif (>= 1, <= max_copies).
    - Proteksi > 100 eksemplar: Jika jumlah > confirmation_threshold (100),
      wajib mengisi `jumlah_konfirmasi` yang nilainya cocok persis dengan `jumlah`.
      Untuk jumlah <= 100, konfirmasi tidak diwajibkan.
    
    Mengembalikan dict data tervalidasi dan teks pratinjau jika valid.
    Melempar ValidationError jika ada aturan yang dilanggar.
    """
    if not isinstance(form_data, dict):
        raise ValidationError("Format data formulir tidak valid.")

    # 1. Validasi Judul Buku
    judul = form_data.get("judul")
    if judul is None or not str(judul).strip():
        raise ValidationError("Judul buku wajib diisi dan tidak boleh kosong.")
    judul_str = str(judul).strip()
    if len(judul_str) > 255:
        raise ValidationError("Judul buku terlalu panjang (maksimal 255 karakter).")

    # 2. Validasi Nama Penulis
    penulis = form_data.get("penulis")
    if penulis is None or not str(penulis).strip():
        raise ValidationError("Nama penulis wajib diisi dan tidak boleh kosong.")
    penulis_str = str(penulis).strip()
    if len(penulis_str) > 255:
        raise ValidationError("Nama penulis terlalu panjang (maksimal 255 karakter).")

    # 3. Validasi Kategori Buku
    kategori = form_data.get("kategori")
    if kategori is None or not str(kategori).strip():
        raise ValidationError("Kategori buku wajib diisi dan tidak boleh kosong.")
    kategori_str = str(kategori).strip()
    if len(kategori_str) > 100:
        raise ValidationError("Kategori terlalu panjang (maksimal 100 karakter).")

    # 4. Validasi ISBN (Opsional)
    isbn = form_data.get("isbn")
    isbn_clean = None
    if isbn is not None and str(isbn).strip():
        isbn_raw = str(isbn).strip()
        if len(isbn_raw) > 30:
            raise ValidationError("Format ISBN tidak valid (terlalu panjang).")
        digits_only = isbn_raw.replace("-", "").replace(" ", "").strip()
        if len(digits_only) not in (10, 13):
            raise ValidationError("Format ISBN tidak valid. ISBN harus memiliki 10 atau 13 digit angka.")
        if len(digits_only) == 10:
            if not digits_only[:9].isdigit() or digits_only[9].upper() not in "0123456789X":
                raise ValidationError("Format ISBN-10 tidak valid (9 digit angka diikuti angka atau 'X').")
        elif len(digits_only) == 13:
            if not digits_only.isdigit():
                raise ValidationError("Format ISBN-13 tidak valid (harus 13 digit angka).")
        isbn_clean = isbn_raw

    # 5. Validasi Jumlah Eksemplar
    jumlah_raw = form_data.get("jumlah")
    if jumlah_raw is None or str(jumlah_raw).strip() == "":
        raise ValidationError("Jumlah eksemplar wajib diisi.")
    
    jumlah_str = str(jumlah_raw).strip()
    try:
        if "." in jumlah_str or "," in jumlah_str:
            raise ValueError()
        jumlah = int(jumlah_str)
    except (ValueError, TypeError):
        raise ValidationError("Jumlah eksemplar harus berupa angka bulat positif.")

    if jumlah < 1:
        raise ValidationError("Jumlah eksemplar minimal 1.")

    if jumlah > max_copies:
        raise ValidationError(f"Jumlah eksemplar tidak boleh melebihi batas maksimal {max_copies} eksemplar.")

    # 6. Proteksi Konfirmasi untuk Jumlah > 100
    jumlah_konfirmasi = None
    if jumlah > confirmation_threshold:
        konfirmasi_raw = form_data.get("jumlah_konfirmasi")
        if konfirmasi_raw is None or str(konfirmasi_raw).strip() == "":
            raise ValidationError("Jumlah eksemplar lebih dari 100 memerlukan konfirmasi pengetikan ulang.")
        
        konfirmasi_str = str(konfirmasi_raw).strip()
        try:
            if "." in konfirmasi_str or "," in konfirmasi_str:
                raise ValueError()
            jumlah_konfirmasi = int(konfirmasi_str)
        except (ValueError, TypeError):
            raise ValidationError("Jumlah konfirmasi harus berupa angka bulat positif.")

        if jumlah_konfirmasi != jumlah:
            raise ValidationError(
                f"Jumlah konfirmasi ({jumlah_konfirmasi}) tidak cocok dengan jumlah yang diminta ({jumlah})."
            )
    else:
        konfirmasi_raw = form_data.get("jumlah_konfirmasi")
        if konfirmasi_raw is not None and str(konfirmasi_raw).strip():
            try:
                jumlah_konfirmasi = int(str(konfirmasi_raw).strip())
            except (ValueError, TypeError):
                pass

    # 7. Metadata Opsional
    sub_judul = str(form_data.get("sub_judul", "")).strip()[:255] or None
    penerbit = str(form_data.get("penerbit", "")).strip()[:255] or None
    tahun = str(form_data.get("tahun", "")).strip()[:10] or None
    sinopsis = str(form_data.get("sinopsis", "")).strip()[:2000] or None

    preview_message = f"Anda akan membuat {jumlah} eksemplar."

    return {
        "valid": True,
        "judul": judul_str,
        "penulis": penulis_str,
        "kategori": kategori_str,
        "isbn": isbn_clean,
        "jumlah": jumlah,
        "jumlah_konfirmasi": jumlah_konfirmasi,
        "requires_confirmation": jumlah > confirmation_threshold,
        "preview_message": preview_message,
        "sub_judul": sub_judul,
        "penerbit": penerbit,
        "tahun": tahun,
        "sinopsis": sinopsis,
    }


# ==============================================================================
# DETEKSI JUDUL MIRIP & PENCEGAHAN DUPLIKAT (TASK 3-04)
# ==============================================================================

def normalize_text(text: Optional[str]) -> str:
    """
    Menormalisasi string teks (judul/penulis) untuk pencocokan yang adil:
    - Lowercase
    - Menghilangkan tanda baca tidak substantif (titik, koma, kutip, tanda hubung, titik dua, dsb)
    - Meratakan spasi berlebih menjadi satu spasi
    - Menghilangkan whitespace di awal/akhir
    """
    if text is None:
        return ""
    # Lowercase & bersihkan karakter non-alphanumeric (hanya pertahankan huruf, angka, dan spasi)
    cleaned = re.sub(r'[^\w\s]', ' ', str(text).lower(), flags=re.UNICODE)
    # Ratakan spasi
    return re.sub(r'\s+', ' ', cleaned).strip()


def normalize_isbn(isbn: Optional[str]) -> Optional[str]:
    """
    Menormalisasi nomor ISBN:
    - Menghapus tanda hubung (-), spasi, dan whitespace
    - Mengubah digit cek 'x' menjadi huruf besar 'X'
    - Mengembalikan string bersih (10 atau 13 digit) atau None jika kosong
    """
    if isbn is None:
        return None
    cleaned = re.sub(r'[\s\-]+', '', str(isbn)).strip()
    if not cleaned:
        return None
    if cleaned[-1:].lower() == 'x':
        cleaned = cleaned[:-1] + 'X'
    return cleaned


def are_isbns_matching(isbn_a: Optional[str], isbn_b: Optional[str]) -> bool:
    """
    Memeriksa apakah dua ISBN cocok setelah normalisasi.
    ATURAN MUTLAK:
    - Dua ISBN yang sama-sama kosong/None TIDAK PERNAH dianggap cocok.
    - Perbedaan tanda hubung/spasi diabaikan (978-602-000-099-2 == 9786020000992).
    """
    norm_a = normalize_isbn(isbn_a)
    norm_b = normalize_isbn(isbn_b)
    if not norm_a or not norm_b:
        return False
    return norm_a == norm_b


def are_titles_and_authors_matching(
    judul_a: str, penulis_a: str,
    judul_b: str, penulis_b: str,
    fuzzy_title_threshold: float = 0.92,
    fuzzy_author_threshold: float = 0.90
) -> Tuple[bool, Optional[str]]:
    """
    Membandingkan pasangan judul dan penulis setelah normalisasi teks.
    ATURAN MUTLAK:
    - Dibandingkan sebagai pasangan (judul sama dengan penulis beda TIDAK dianggap duplikat).
    - Judul yang memuat angka berbeda (misal: 'Kelas 1' vs 'Kelas 2') TIDAK dianggap duplikat.
    - Perbedaan kapitalisasi, tanda baca, dan spasi berlebih diabaikan.
    - Ambang fuzzy similarity judul >= 0.92 dengan penulis sama untuk menangkap typo minor.
    """
    norm_t_a = normalize_text(judul_a)
    norm_t_b = normalize_text(judul_b)
    norm_p_a = normalize_text(penulis_a)
    norm_p_b = normalize_text(penulis_b)

    if not norm_t_a or not norm_t_b:
        return False, None

    # Jika salah satu penulis tidak ada, tidak dapat dipastikan kecocokan pasangan
    if not norm_p_a or not norm_p_b:
        return False, None

    # Cek digit angka di dalam judul (misal: jilid 1 vs jilid 2, kelas 1 vs kelas 2)
    digits_a = re.findall(r'\d+', norm_t_a)
    digits_b = re.findall(r'\d+', norm_t_b)
    if digits_a != digits_b:
        return False, None

    # 1. Kasus Identik Penuh setelah Normalisasi
    if norm_t_a == norm_t_b and norm_p_a == norm_p_b:
        return True, "Judul dan penulis sama persis (setelah normalisasi)"

    # 2. Kasus Penulis Identik, Judul Sangat Mirip (Typo Minor / Varian)
    if norm_p_a == norm_p_b:
        ratio = difflib.SequenceMatcher(None, norm_t_a, norm_t_b).ratio()
        if ratio >= fuzzy_title_threshold:
            pct = int(ratio * 100)
            return True, f"Judul sangat mirip ({pct}%) dengan penulis yang sama"

    # 3. Kasus Judul Identik, Penulis Sangat Mirip (Typo Nama Penulis)
    if norm_t_a == norm_t_b:
        p_ratio = difflib.SequenceMatcher(None, norm_p_a, norm_p_b).ratio()
        if p_ratio >= fuzzy_author_threshold:
            pct = int(p_ratio * 100)
            return True, f"Judul sama dengan nama penulis sangat mirip ({pct}%)"

    # 4. Kasus Keduanya Memiliki Variasi Sangat Kecil
    t_ratio = difflib.SequenceMatcher(None, norm_t_a, norm_t_b).ratio()
    p_ratio = difflib.SequenceMatcher(None, norm_p_a, norm_p_b).ratio()
    if t_ratio >= 0.95 and p_ratio >= 0.92:
        pct = int(t_ratio * 100)
        return True, f"Judul dan penulis sangat mirip (kemiripan judul {pct}%)"

    return False, None


def find_similar_catalog_titles(
    conn: sqlite3.Connection,
    judul: str,
    penulis: str,
    isbn: Optional[str] = None,
    exclude_title_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Mendeteksi potensi buku duplikat atau judul mirip di katalog (Task 3-04).
    Kriteria:
    1. ISBN sama (dengan normalisasi format)
    2. Judul dan penulis sama atau sangat mirip setelah normalisasi
    Mengembalikan daftar kandidat beserta alasan kecocokan.
    """
    candidates = catalog_repo.list_all_titles_for_duplicate_check(conn)
    if not candidates:
        return []

    results = []
    seen_ids = set()

    for cand in candidates:
        cand_id = str(cand.get("id"))
        if exclude_title_id and cand_id == str(exclude_title_id):
            continue
        if cand_id in seen_ids:
            continue

        reasons = []

        # Kriteria A: ISBN sama
        if isbn and cand.get("isbn"):
            if are_isbns_matching(isbn, cand.get("isbn")):
                reasons.append(f"ISBN sama persis ({normalize_isbn(isbn)})")

        # Kriteria B: Pasangan judul dan penulis sama/sangat mirip
        matched, reason_text = are_titles_and_authors_matching(
            judul_a=judul,
            penulis_a=penulis,
            judul_b=cand.get("judul", ""),
            penulis_b=cand.get("penulis") or ""
        )
        if matched and reason_text:
            reasons.append(reason_text)

        if reasons:
            seen_ids.add(cand_id)
            is_isbn_match = any("ISBN" in r for r in reasons)
            is_title_match = any("Judul" in r for r in reasons)
            if is_isbn_match and is_title_match:
                match_type = "ISBN_DAN_JUDUL_PENULIS"
            elif is_isbn_match:
                match_type = "ISBN"
            else:
                match_type = "JUDUL_PENULIS"

            results.append({
                "id": cand_id,
                "judul": cand.get("judul"),
                "penulis": cand.get("penulis"),
                "isbn": cand.get("isbn"),
                "kategori": cand.get("kategori"),
                "reasons": reasons,
                "match_type": match_type,
            })

    return results


# ==============================================================================
# MANAJEMEN TOKEN KONFIRMASI SEKALI PAKAI & COMMIT ATOMIK (TASK 3-03)
# ==============================================================================

_TOKEN_LOCK = threading.Lock()
_ACTIVE_PROCESSING_TOKENS = set()
_CONFIRMATION_TOKENS: Dict[str, Dict[str, Any]] = {}


def ensure_confirmation_tokens_table(conn: sqlite3.Connection) -> None:
    """Memastikan tabel persisten confirmation_tokens dan index-nya tersedia di database."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS confirmation_tokens (
            token TEXT PRIMARY KEY,
            admin_username TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
            created_at TEXT NOT NULL,
            expires_at REAL NOT NULL,
            created_title_id TEXT REFERENCES catalog_titles(id),
            result_json TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_confirmation_tokens_expires ON confirmation_tokens(expires_at);")


def canonicalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Menghasilkan representasi kanonikal dari payload formulir untuk hashing."""
    return {
        "judul": str(payload.get("judul", "")).strip(),
        "penulis": str(payload.get("penulis", "")).strip(),
        "kategori": str(payload.get("kategori", "")).strip(),
        "isbn": str(payload.get("isbn") or "").replace("-", "").replace(" ", "").strip() or None,
        "jumlah": int(payload.get("jumlah", 0)),
        "sub_judul": str(payload.get("sub_judul") or "").strip() or None,
        "penerbit": str(payload.get("penerbit") or "").strip() or None,
        "tahun": str(payload.get("tahun") or "").strip() or None,
        "sinopsis": str(payload.get("sinopsis") or "").strip() or None,
    }


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Menghitung hash SHA-256 kanonikal dari payload untuk proteksi anti-tampering."""
    clean = canonicalize_payload(payload)
    serialized = json.dumps(clean, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_confirmation_token(
    *args,
    **kwargs
) -> str:
    """
    Menerbitkan token konfirmasi acak sekali pakai yang terikat pada payload dan sesi admin.
    Disimpan secara persisten di database (tabel confirmation_tokens) sehingga tahan restart
    dan aman lintas worker/proses.
    Mendukung pemanggilan:
    - create_confirmation_token(conn, payload, admin_username, ttl_seconds)
    - create_confirmation_token(payload, admin_username=admin_username, ttl_seconds=ttl_seconds)
    """
    conn = None
    payload = None
    admin_username = None
    ttl_seconds = kwargs.get("ttl_seconds", CONFIRMATION_TOKEN_TTL_SECONDS)

    if len(args) >= 1 and isinstance(args[0], sqlite3.Connection):
        conn = args[0]
        if len(args) >= 2:
            payload = args[1]
        if len(args) >= 3:
            admin_username = args[2]
        if len(args) >= 4:
            ttl_seconds = args[3]
    else:
        if len(args) >= 1:
            payload = args[0]
        if len(args) >= 2 and isinstance(args[1], str):
            admin_username = args[1]
        if len(args) >= 3 and isinstance(args[2], (int, float)):
            ttl_seconds = int(args[2])

    if payload is None:
        payload = kwargs.get("payload")
    if admin_username is None:
        admin_username = kwargs.get("admin_username")

    if not admin_username:
        raise ValidationError("Sesi admin tidak teridentifikasi untuk penerbitan token.")
    if not payload or not isinstance(payload, dict):
        raise ValidationError("Payload buku wajib disertakan untuk penerbitan token.")

    token = secrets.token_hex(24)
    now_epoch = time.time()
    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    expires_at = now_epoch + ttl_seconds
    payload_hash = compute_payload_hash(payload)
    payload_clean = canonicalize_payload(payload)
    payload_json = json.dumps(payload_clean, ensure_ascii=False)

    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        target_conn = get_connection()
        should_close = True

    try:
        ensure_confirmation_tokens_table(target_conn)
        target_conn.execute("DELETE FROM confirmation_tokens WHERE expires_at < ?;", (now_epoch - 3600,))
        target_conn.execute(
            """
            INSERT INTO confirmation_tokens (
                token, admin_username, payload_hash, payload_json, status, created_at, expires_at
            ) VALUES (?, ?, ?, ?, 'PENDING', ?, ?);
            """,
            (token, admin_username, payload_hash, payload_json, now_iso, expires_at)
        )
        target_conn.commit()
    finally:
        if should_close:
            target_conn.close()

    with _TOKEN_LOCK:
        _CONFIRMATION_TOKENS[token] = {
            "token": token,
            "admin_username": admin_username,
            "payload": payload,
            "payload_hash": payload_hash,
            "created_at": now_epoch,
            "expires_at": expires_at,
            "status": "PENDING",
            "result": None,
        }

    return token


def consume_confirmation_token(
    token: str,
    admin_username: str,
    submitted_payload: Optional[Dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None
) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Memeriksa dan memvalidasi token konfirmasi dari database persisten.
    Mengembalikan tuple: (status, token_entry, cached_result)
    - Jika status == 'COMPLETED': permintaan berulang (replay/idempoten), mengembalikan hasil tersimpan.
    - Jika status == 'PENDING': valid untuk diakuisisi oleh transaksi.
    - Jika status == 'PROCESSING': melempar ConcurrencyConflictError.
    - Jika token tidak valid/expired/mismatched: melempar ConfirmationTokenError.
    """
    if not token or not str(token).strip():
        raise ConfirmationTokenError("Token konfirmasi wajib disertakan.")

    clean_token = str(token).strip()
    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        target_conn = get_connection()
        should_close = True

    try:
        ensure_confirmation_tokens_table(target_conn)
        row = target_conn.execute(
            "SELECT * FROM confirmation_tokens WHERE token = ?;", (clean_token,)
        ).fetchone()

        if not row:
            raise ConfirmationTokenError("Token konfirmasi tidak valid atau tidak ditemukan.")

        entry = dict(row)
        now_epoch = time.time()

        if entry["status"] == "COMPLETED":
            cached_result = None
            if entry.get("result_json"):
                try:
                    cached_result = json.loads(entry["result_json"])
                except Exception:
                    pass
            return "COMPLETED", entry, cached_result

        with _TOKEN_LOCK:
            if clean_token in _ACTIVE_PROCESSING_TOKENS or entry["status"] == "PROCESSING":
                raise ConcurrencyConflictError(
                    "Permintaan konfirmasi sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
                )

        if now_epoch > float(entry.get("expires_at", 0)):
            raise ConfirmationTokenError(
                "Token konfirmasi telah kedaluwarsa (batas waktu 15 menit). Silakan lakukan pratinjau ulang."
            )

        if entry.get("admin_username") != admin_username:
            raise ConfirmationTokenError("Token konfirmasi tidak sah untuk sesi admin yang aktif.")

        if submitted_payload is not None:
            submitted_hash = compute_payload_hash(submitted_payload)
            if submitted_hash != entry.get("payload_hash"):
                raise ConfirmationTokenError(
                    "Data buku telah dimodifikasi sejak pratinjau. Harap lakukan validasi ulang."
                )

        if entry.get("status") == "FAILED":
            raise ConfirmationTokenError(
                "Proses konfirmasi sebelumnya gagal. Silakan lakukan pratinjau ulang formulir."
            )

        return "ACQUIRED", entry, None

    finally:
        if should_close:
            target_conn.close()


def complete_confirmation_token(token: str, result_summary: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> None:
    """Menandai token konfirmasi sebagai COMPLETED di database dan cache memori."""
    clean_token = str(token).strip()
    with _TOKEN_LOCK:
        entry = _CONFIRMATION_TOKENS.get(clean_token)
        if entry:
            entry["status"] = "COMPLETED"
            entry["result"] = result_summary

    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        target_conn = get_connection()
        should_close = True

    try:
        ensure_confirmation_tokens_table(target_conn)
        target_conn.execute(
            """
            UPDATE confirmation_tokens
            SET status = 'COMPLETED',
                created_title_id = ?,
                result_json = ?
            WHERE token = ?;
            """,
            (
                result_summary.get("title_id"),
                json.dumps(result_summary, ensure_ascii=False),
                clean_token,
            )
        )
        target_conn.commit()
    except Exception:
        pass
    finally:
        if should_close:
            target_conn.close()


def fail_confirmation_token(token: str, conn: Optional[sqlite3.Connection] = None) -> None:
    """Menandai token konfirmasi sebagai FAILED jika transaksi database gagal."""
    clean_token = str(token).strip()
    with _TOKEN_LOCK:
        entry = _CONFIRMATION_TOKENS.get(clean_token)
        if entry:
            entry["status"] = "FAILED"

    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        target_conn = get_connection()
        should_close = True

    try:
        ensure_confirmation_tokens_table(target_conn)
        target_conn.execute(
            "UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ?;",
            (clean_token,)
        )
        target_conn.commit()
    except Exception:
        pass
    finally:
        if should_close:
            target_conn.close()


def clear_confirmation_tokens(conn: Optional[sqlite3.Connection] = None) -> None:
    """Membersihkan seluruh token konfirmasi di memori dan database (khusus pengujian)."""
    with _TOKEN_LOCK:
        _ACTIVE_PROCESSING_TOKENS.clear()
        _CONFIRMATION_TOKENS.clear()

    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        try:
            target_conn = get_connection()
            should_close = True
        except Exception:
            return

    try:
        ensure_confirmation_tokens_table(target_conn)
        target_conn.execute("DELETE FROM confirmation_tokens;")
        target_conn.commit()
    except Exception:
        pass
    finally:
        if should_close:
            try:
                target_conn.close()
            except Exception:
                pass


def confirm_and_create_title_with_copies(
    conn: sqlite3.Connection,
    token: str,
    admin_username: str,
    submitted_payload: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], bool]:
    """
    Mengeksekusi konfirmasi pembuatan judul beserta eksemplar secara atomik dan idempoten
    menggunakan database persisten (SQLite v2).
    Mengembalikan tuple: (result_data, is_replay)
    - Jika is_replay == True: transaksi sudah sukses sebelumnya, hasil sebelumnya dikembalikan tanpa penulisan baru.
    - Jika is_replay == False: judul dan seluruh eksemplar dibuat dalam SATU transaksi atomik.
    """
    if not token or not str(token).strip():
        raise ConfirmationTokenError("Token konfirmasi wajib disertakan.")

    clean_token = str(token).strip()
    ensure_confirmation_tokens_table(conn)

    # Fast-path memory lock untuk thread dalam satu proses
    with _TOKEN_LOCK:
        if clean_token in _ACTIVE_PROCESSING_TOKENS:
            raise ConcurrencyConflictError(
                "Permintaan konfirmasi sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
            )
        _ACTIVE_PROCESSING_TOKENS.add(clean_token)

    try:
        # Seluruh koordinasi eksekusi berada di dalam transaksi atomik (BEGIN IMMEDIATE)
        with transaction_scope(conn):
            # 1. Baca token dari database di dalam transaksi write lock
            row = conn.execute(
                "SELECT * FROM confirmation_tokens WHERE token = ?;", (clean_token,)
            ).fetchone()

            if not row:
                raise ConfirmationTokenError("Token konfirmasi tidak valid atau tidak ditemukan.")

            token_data = dict(row)
            now_epoch = time.time()

            # 2. Cek apakah token sudah selesai diproses sebelumnya (idempotensi mutlak)
            if token_data["status"] == "COMPLETED":
                result_json = token_data.get("result_json")
                if result_json:
                    try:
                        cached_result = json.loads(result_json)
                        return cached_result, True
                    except Exception:
                        pass
                return {}, True

            # 3. Cek apakah token sedang diproses worker/proses lain
            if token_data["status"] == "PROCESSING":
                raise ConcurrencyConflictError(
                    "Permintaan konfirmasi sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
                )

            # 4. Cek kedaluwarsa token
            if now_epoch > float(token_data.get("expires_at", 0)):
                raise ConfirmationTokenError(
                    "Token konfirmasi telah kedaluwarsa (batas waktu 15 menit). Silakan lakukan pratinjau ulang."
                )

            # 5. Cek keterikatan sesi admin
            if token_data.get("admin_username") != admin_username:
                raise ConfirmationTokenError("Token konfirmasi tidak sah untuk sesi admin yang aktif.")

            # 6. Cek integritas payload (anti-tampering)
            if submitted_payload is not None:
                submitted_hash = compute_payload_hash(submitted_payload)
                if submitted_hash != token_data.get("payload_hash"):
                    raise ConfirmationTokenError(
                        "Data buku telah dimodifikasi sejak pratinjau. Harap lakukan validasi ulang."
                    )

            # 7. Cek status gagal sebelumnya
            if token_data["status"] == "FAILED":
                raise ConfirmationTokenError(
                    "Proses konfirmasi sebelumnya gagal. Silakan lakukan pratinjau ulang formulir."
                )

            # 8. Tandai PROCESSING di dalam transaksi aktif
            conn.execute(
                "UPDATE confirmation_tokens SET status = 'PROCESSING' WHERE token = ?;",
                (clean_token,)
            )

            # 9. Ekstraksi payload kanonikal yang tersimpan aman di database
            payload = json.loads(token_data["payload_json"])
            judul = payload["judul"]
            sub_judul = payload.get("sub_judul")
            penulis = payload["penulis"]
            penerbit = payload.get("penerbit")
            tahun = payload.get("tahun")
            isbn = payload.get("isbn")
            kategori = payload["kategori"]
            sinopsis = payload.get("sinopsis")
            jumlah = int(payload["jumlah"])

            title_data = {
                "judul": judul,
                "subjudul": sub_judul,
                "sub_judul": sub_judul,
                "penulis": penulis,
                "penerbit": penerbit,
                "tahun": tahun,
                "isbn": isbn,
                "kategori": kategori,
                "sinopsis": sinopsis,
            }

            # 10. Buat judul dan eksemplar dalam transaksi yang sama
            created_title = create_title_with_copies(
                conn,
                title_data=title_data,
                initial_copies=jumlah,
                actor=admin_username,
            )

            result_summary = {
                "title_id": created_title["id"],
                "judul": created_title["judul"],
                "penulis": created_title.get("penulis"),
                "kategori": created_title.get("kategori"),
                "isbn": created_title.get("isbn"),
                "initial_copies_count": jumlah,
                "copy_ids": created_title.get("copy_ids", []),
                "created_at": created_title.get("created_at"),
            }

            # 11. Tandai COMPLETED dan simpan ringkasan hasil di dalam transaksi atomik yang sama
            conn.execute(
                """
                UPDATE confirmation_tokens
                SET status = 'COMPLETED',
                    created_title_id = ?,
                    result_json = ?
                WHERE token = ?;
                """,
                (
                    created_title["id"],
                    json.dumps(result_summary, ensure_ascii=False),
                    clean_token,
                )
            )

            # Sinkronisasi cache memori
            with _TOKEN_LOCK:
                _CONFIRMATION_TOKENS[clean_token] = {
                    "token": clean_token,
                    "admin_username": admin_username,
                    "status": "COMPLETED",
                    "result": result_summary,
                }

            return result_summary, False

    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "locked" in err_msg or "busy" in err_msg:
            raise ConcurrencyConflictError(
                "Permintaan konfirmasi sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
            )
        try:
            with conn:
                conn.execute(
                    "UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ?;",
                    (clean_token,)
                )
        except Exception:
            pass
        raise

    except Exception:
        try:
            with conn:
                conn.execute(
                    "UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ?;",
                    (clean_token,)
                )
        except Exception:
            pass
        raise

    finally:
        with _TOKEN_LOCK:
            _ACTIVE_PROCESSING_TOKENS.discard(clean_token)




# ==============================================================================
# TEMPLATE IMPOR KATALOG (TASK 3-05)
# ==============================================================================

CATALOG_IMPORT_HEADERS: List[str] = ["judul", "penulis", "isbn", "kategori", "jumlah"]
CATALOG_IMPORT_FILENAME: str = "template_impor_katalog.csv"

CATALOG_IMPORT_SAMPLE_DATA: List[Dict[str, Any]] = [
    {
        "judul": "Laskar Pelangi (Contoh)",
        "penulis": "Andrea Hirata",
        "isbn": "978-979-3062-79-2",
        "kategori": "Fiksi",
        "jumlah": 3,
    },
    {
        "judul": "Matematika untuk SMA/MA Kelas X (Contoh)",
        "penulis": "B. K. Noormandiri",
        "isbn": "978-602-298-967-7",
        "kategori": "Buku Pelajaran",
        "jumlah": 10,
    },
    {
        "judul": "Ensiklopedia Sains, Teknologi, dan Lingkungan (Contoh)",
        "penulis": "Tim Pusat Perbukuan",
        "isbn": "",
        "kategori": "Referensi",
        "jumlah": 2,
    },
    {
        "judul": "Bumi Manusia (Contoh)",
        "penulis": "Pramoedya Ananta Toer",
        "isbn": "978-979-97312-3-4",
        "kategori": "Sastra",
        "jumlah": 5,
    },
]


def get_catalog_import_sample_data() -> List[Dict[str, Any]]:
    """
    Mengembalikan salinan data contoh realistis untuk template impor katalog.
    Data contoh berlabel '(Contoh)' dan menyertakan satu baris ISBN kosong yang sah.
    """
    return [dict(item) for item in CATALOG_IMPORT_SAMPLE_DATA]


def generate_catalog_import_template_csv() -> str:
    """
    Menghasilkan string CSV untuk template impor katalog dengan header tepat:
    judul, penulis, isbn, kategori, jumlah
    menggunakan library csv bawaan Python dengan penanganan quoting standar.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CATALOG_IMPORT_HEADERS)
    for row in CATALOG_IMPORT_SAMPLE_DATA:
        writer.writerow([
            row["judul"],
            row["penulis"],
            row.get("isbn") or "",
            row["kategori"],
            row["jumlah"],
        ])
    return output.getvalue()


def get_catalog_import_template_download_payload() -> Tuple[bytes, str, str]:
    """
    Menghasilkan payload siap unduh untuk response Flask:
    (csv_bytes, filename, mimetype)
    Teks di-encode sebagai UTF-8 murni.
    """
    csv_text = generate_catalog_import_template_csv()
    csv_bytes = csv_text.encode("utf-8")
    return csv_bytes, CATALOG_IMPORT_FILENAME, "text/csv; charset=utf-8"


# ==============================================================================
# PARSING & VALIDASI PREVIEW IMPOR KATALOG (TASK 3-06)
# ZERO-WRITES: Tidak ada mutasi/insert/update ke database sama sekali
# ==============================================================================

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def is_potential_formula(value: Any) -> bool:
    """
    Memeriksa apakah string diawali karakter pemicu formula spreadsheet
    seperti '=', '+', '-', '@', atau karakter kontrol.
    Mencegah kerentanan CSV Formula Injection.
    """
    if value is None:
        return False
    val_str = str(value).strip()
    if not val_str:
        return False
    return any(val_str.startswith(p) for p in FORMULA_PREFIXES)


def parse_and_validate_catalog_import_csv(
    conn: Optional[sqlite3.Connection],
    csv_content: Union[bytes, str],
    max_file_size_bytes: int = MAX_CATALOG_IMPORT_FILE_SIZE_BYTES,
    max_rows: int = MAX_CATALOG_IMPORT_ROWS,
) -> Dict[str, Any]:
    """
    Melakukan parsing aman dan validasi bertahap terhadap isi CSV impor katalog.
    Memenuhi Task 3-06:
    - Tidak menulis atau mengubah data di database (Zero-Write strictly guaranteed).
    - Membatasi ukuran file dan batas jumlah baris data.
    - Menolak formula spreadsheet pada sel teks.
    - Menghasilkan ringkasan dan daftar baris terperinci dengan status OK, PERINGATAN, atau ERROR.
    """
    # 1. Dekode dan validasi ukuran
    if isinstance(csv_content, bytes):
        if len(csv_content) > max_file_size_bytes:
            raise ValidationError(
                f"Ukuran file ({len(csv_content):,} byte) melebihi batas maksimum "
                f"yang diizinkan ({max_file_size_bytes // (1024 * 1024)} MiB)."
            )
        try:
            csv_text = csv_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                csv_text = csv_content.decode("utf-8")
            except UnicodeDecodeError:
                raise ValidationError("Format encoding file tidak valid. Harap gunakan format file CSV dengan encoding UTF-8.")
    else:
        csv_text = str(csv_content)

    if not csv_text or not csv_text.strip():
        raise ValidationError("File CSV kosong atau tidak memuat data.")

    # 2. Parsing CSV dengan modul standar csv
    try:
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
    except StopIteration:
        raise ValidationError("File CSV kosong atau tidak memuat baris header.")
    except Exception as e:
        raise ValidationError(f"File CSV tidak dapat diparse: {str(e)}.")

    # 3. Validasi Kontrak Baris Header
    cleaned_header = [h.strip() for h in header]
    if cleaned_header != CATALOG_IMPORT_HEADERS:
        header_str = ", ".join(header) if header else "(kosong)"
        expected_str = ", ".join(CATALOG_IMPORT_HEADERS)
        raise ValidationError(
            f"Header CSV tidak sesuai kontrak. Baris pertama wajib memuat tepat 5 kolom: {expected_str}. "
            f"Header yang terbaca di file Anda: {header_str}."
        )

    # 4. Baca Seluruh Baris Data
    rows_data: List[List[str]] = []
    for row in reader:
        # Lewati baris kosong di akhir file (trailing empty lines)
        if not row or (len(row) == 1 and row[0].strip() == ""):
            continue
        rows_data.append(row)

    if not rows_data:
        raise ValidationError("File CSV hanya memuat header dan tidak memiliki baris data untuk diimpor.")

    if len(rows_data) > max_rows:
        raise ValidationError(
            f"Jumlah baris data dalam file ({len(rows_data):,} baris) melebihi batas maksimum "
            f"yang diizinkan ({max_rows:,} baris)."
        )

    # 5. Validasi Per Baris
    processed_rows: List[Dict[str, Any]] = []
    seen_isbns: Dict[str, int] = {}
    seen_titles_authors: List[Tuple[str, str, int]] = []

    valid_count = 0
    warning_count = 0
    error_count = 0

    for idx, row in enumerate(rows_data):
        row_num = idx + 2  # Baris 1 adalah header di spreadsheet
        errors: List[str] = []
        warnings: List[str] = []

        # Cek jumlah kolom baris
        if len(row) != 5:
            errors.append(f"Jumlah kolom tidak sesuai: terdapat {len(row)} kolom (wajib tepat 5 kolom).")
            padded_row = list(row) + [""] * max(0, 5 - len(row))
            judul_raw, penulis_raw, isbn_raw, kategori_raw, jumlah_raw = padded_row[:5]
        else:
            judul_raw, penulis_raw, isbn_raw, kategori_raw, jumlah_raw = row

        raw_dict = {
            "judul": judul_raw,
            "penulis": penulis_raw,
            "isbn": isbn_raw,
            "kategori": kategori_raw,
            "jumlah": jumlah_raw,
        }

        # Periksa Formula Injection pada tiap cell
        for field_name, cell_val in raw_dict.items():
            if is_potential_formula(cell_val):
                errors.append(
                    f"Kolom '{field_name}' diawali karakter formula spreadsheet ('=', '+', '-', '@') yang tidak diizinkan."
                )

        clean_judul = str(judul_raw).strip()
        clean_penulis = str(penulis_raw).strip()
        clean_isbn = str(isbn_raw).strip() if isbn_raw is not None else ""
        clean_kategori = str(kategori_raw).strip()
        clean_jumlah_str = str(jumlah_raw).strip()
        clean_jumlah: Optional[int] = None

        # A. Validasi Judul
        if not clean_judul:
            errors.append("Judul buku wajib diisi dan tidak boleh kosong.")
        elif len(clean_judul) > 255:
            errors.append("Judul buku terlalu panjang (maksimal 255 karakter).")

        # B. Validasi Penulis
        if not clean_penulis:
            errors.append("Nama penulis wajib diisi dan tidak boleh kosong.")
        elif len(clean_penulis) > 255:
            errors.append("Nama penulis terlalu panjang (maksimal 255 karakter).")

        # C. Validasi Kategori
        if not clean_kategori:
            errors.append("Kategori buku wajib diisi dan tidak boleh kosong.")
        elif len(clean_kategori) > 100:
            errors.append("Kategori buku terlalu panjang (maksimal 100 karakter).")

        # D. Validasi ISBN (Opsional)
        if clean_isbn:
            if len(clean_isbn) > 30:
                errors.append("Format ISBN terlalu panjang (maksimal 30 karakter).")
            else:
                digits_only = clean_isbn.replace("-", "").replace(" ", "").strip()
                if len(digits_only) not in (10, 13):
                    errors.append("Format ISBN tidak valid. ISBN harus memiliki 10 atau 13 digit angka.")
                elif len(digits_only) == 10:
                    if not digits_only[:9].isdigit() or digits_only[9].upper() not in "0123456789X":
                        errors.append("Format ISBN-10 tidak valid (9 digit angka diikuti angka atau 'X').")
                elif len(digits_only) == 13:
                    if not digits_only.isdigit():
                        errors.append("Format ISBN-13 tidak valid (harus 13 digit angka).")

        # E. Validasi Jumlah Eksemplar
        if not clean_jumlah_str:
            errors.append("Jumlah eksemplar wajib diisi.")
        else:
            try:
                if "." in clean_jumlah_str or "," in clean_jumlah_str:
                    errors.append("Jumlah eksemplar harus berupa bilangan bulat positif (tidak boleh desimal/pecahan).")
                else:
                    parsed_qty = int(clean_jumlah_str)
                    if parsed_qty < 1:
                        errors.append("Jumlah eksemplar harus berupa bilangan bulat positif (minimal 1).")
                    elif parsed_qty > MAX_COPIES_PER_ADD:
                        errors.append(f"Jumlah eksemplar terlalu banyak (maksimal {MAX_COPIES_PER_ADD} eksemplar per judul).")
                    else:
                        clean_jumlah = parsed_qty
            except ValueError:
                errors.append("Jumlah eksemplar harus berupa angka bilangan bulat positif.")

        # F. Deteksi Duplikat Intra-File (Antar Baris dalam File yang Sama)
        if clean_isbn and not any("ISBN" in e for e in errors):
            norm_isbn = normalize_isbn(clean_isbn)
            if norm_isbn:
                if norm_isbn in seen_isbns:
                    prev_row = seen_isbns[norm_isbn]
                    warnings.append(f"ISBN identik dengan baris {prev_row} dalam file ini.")
                else:
                    seen_isbns[norm_isbn] = row_num

        if clean_judul and clean_penulis and not any("Judul" in e or "penulis" in e for e in errors):
            for prev_j, prev_p, prev_r in seen_titles_authors:
                is_match, reason = are_titles_and_authors_matching(clean_judul, clean_penulis, prev_j, prev_p)
                if is_match:
                    warnings.append(f"Judul dan penulis serupa dengan baris {prev_r} dalam file ini ({reason}).")
                    break
            seen_titles_authors.append((clean_judul, clean_penulis, row_num))

        # G. Deteksi Duplikat terhadap Katalog Database (Read-Only)
        if conn and clean_judul and clean_penulis:
            try:
                db_candidates = find_similar_catalog_titles(
                    conn,
                    judul=clean_judul,
                    penulis=clean_penulis,
                    isbn=clean_isbn if clean_isbn else None,
                )
                for cand in db_candidates:
                    reasons_str = ", ".join(cand.get("reasons", ["Mirip"]))
                    warnings.append(
                        f"Potensi duplikat katalog: {reasons_str} dengan judul '{cand['judul']}' oleh '{cand['penulis']}' [ID: {cand['id']}]."
                    )
            except Exception:
                pass

        # H. Penentuan Status Baris
        if errors:
            status = "ERROR"
            error_count += 1
        elif warnings:
            status = "PERINGATAN"
            warning_count += 1
        else:
            status = "OK"
            valid_count += 1

        processed_rows.append({
            "row_num": row_num,
            "raw_data": raw_dict,
            "clean_data": {
                "judul": clean_judul,
                "penulis": clean_penulis,
                "isbn": clean_isbn if clean_isbn else None,
                "kategori": clean_kategori,
                "jumlah": clean_jumlah,
            },
            "status": status,
            "errors": errors,
            "warnings": warnings,
        })

    return {
        "total_rows": len(processed_rows),
        "valid_rows_count": valid_count,
        "warning_rows_count": warning_count,
        "error_rows_count": error_count,
        "rows": processed_rows,
    }


# ==============================================================================
# COMMIT IMPOR KATALOG ATOMIK & IDEMPOTENSI (TASK 3-07)
# ==============================================================================

def canonicalize_import_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Menghasilkan representasi kanonikal dari payload impor katalog untuk hashing anti-tampering.
    Normalisasi isi berkas CSV, whitespace, serta preferensi perlakuan baris peringatan.
    """
    csv_val = payload.get("csv_content", "")
    if isinstance(csv_val, bytes):
        try:
            csv_str = csv_val.decode("utf-8-sig")
        except Exception:
            csv_str = csv_val.decode("latin-1", errors="replace")
    else:
        csv_str = str(csv_val or "")

    normalized_csv = "\n".join([line.strip() for line in csv_str.strip().splitlines() if line.strip()])

    return {
        "action": "catalog_import",
        "csv_content": normalized_csv,
        "skip_warnings": bool(payload.get("skip_warnings", False)),
    }


def compute_import_payload_hash(payload: Dict[str, Any]) -> str:
    """Menghitung hash SHA-256 kanonikal dari payload impor katalog."""
    clean = canonicalize_import_payload(payload)
    serialized = json.dumps(clean, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_catalog_import_confirmation_token(
    *args,
    **kwargs
) -> str:
    """
    Menerbitkan token konfirmasi persisten sekali pakai untuk alur komit impor katalog CSV (Task 3-07).
    Token terikat pada sesi admin, hash isi berkas CSV, dan preferensi penanganan peringatan.
    Mendukung pemanggilan:
    - create_catalog_import_confirmation_token(conn, csv_content, admin_username, skip_warnings, ttl_seconds)
    - create_catalog_import_confirmation_token(csv_content, admin_username=admin_username, ...)
    """
    conn = None
    csv_content = None
    admin_username = None
    skip_warnings = False
    ttl_seconds = kwargs.get("ttl_seconds", CONFIRMATION_TOKEN_TTL_SECONDS)

    if len(args) >= 1 and isinstance(args[0], sqlite3.Connection):
        conn = args[0]
        if len(args) >= 2:
            csv_content = args[1]
        if len(args) >= 3:
            admin_username = args[2]
        if len(args) >= 4 and isinstance(args[3], bool):
            skip_warnings = args[3]
        if len(args) >= 5 and isinstance(args[4], (int, float)):
            ttl_seconds = int(args[4])
    else:
        if len(args) >= 1:
            csv_content = args[0]
        if len(args) >= 2 and isinstance(args[1], str):
            admin_username = args[1]
        if len(args) >= 3 and isinstance(args[2], bool):
            skip_warnings = args[2]
        if len(args) >= 4 and isinstance(args[3], (int, float)):
            ttl_seconds = int(args[3])

    if conn is None:
        conn = kwargs.get("conn")
    if csv_content is None:
        csv_content = kwargs.get("csv_content")
    if admin_username is None:
        admin_username = kwargs.get("admin_username")
    if "skip_warnings" in kwargs:
        skip_warnings = bool(kwargs["skip_warnings"])

    if not admin_username or not str(admin_username).strip():
        raise ValidationError("Sesi admin tidak teridentifikasi untuk penerbitan token impor.")
    if not csv_content:
        raise ValidationError("Konten berkas CSV impor wajib disertakan untuk penerbitan token.")

    token = secrets.token_hex(24)
    now_epoch = time.time()
    now_iso = timeutil.format_iso_utc(timeutil.now_utc())
    expires_at = now_epoch + ttl_seconds

    csv_text = csv_content if isinstance(csv_content, str) else csv_content.decode("utf-8-sig", errors="replace")

    payload_dict = {
        "action": "catalog_import",
        "csv_content": csv_text,
        "skip_warnings": bool(skip_warnings),
    }
    payload_hash = compute_import_payload_hash(payload_dict)
    clean_payload = canonicalize_import_payload(payload_dict)
    payload_json = json.dumps(clean_payload, ensure_ascii=False)

    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        target_conn = get_connection()
        should_close = True

    try:
        ensure_confirmation_tokens_table(target_conn)
        target_conn.execute("DELETE FROM confirmation_tokens WHERE expires_at < ?;", (now_epoch - 3600,))
        target_conn.execute(
            """
            INSERT INTO confirmation_tokens (
                token, admin_username, payload_hash, payload_json, status, created_at, expires_at
            ) VALUES (?, ?, ?, ?, 'PENDING', ?, ?);
            """,
            (token, admin_username, payload_hash, payload_json, now_iso, expires_at)
        )
        target_conn.commit()
    finally:
        if should_close:
            target_conn.close()

    with _TOKEN_LOCK:
        _CONFIRMATION_TOKENS[token] = {
            "token": token,
            "admin_username": admin_username,
            "payload": clean_payload,
            "payload_hash": payload_hash,
            "created_at": now_epoch,
            "expires_at": expires_at,
            "status": "PENDING",
            "result": None,
        }

    return token


def commit_catalog_import_with_token(
    conn: sqlite3.Connection,
    token: str,
    admin_username: str,
    submitted_csv_content: Optional[Union[str, bytes]] = None,
    skip_warnings: Optional[bool] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Mengeksekusi komit impor katalog massal secara atomik dan idempoten (Task 3-07).
    Mengembalikan tuple: (result_summary, is_replay)
    - Jika is_replay == True: transaksi sudah selesai sebelumnya, mengembalikan ringkasan sebelumnya tanpa duplikasi.
    - Jika is_replay == False: seluruh judul dan eksemplar dibuat dalam SATU transaksi atomik BEGIN IMMEDIATE.
    Jika terjadi kegagalan pada baris mana pun atau saat audit logging, seluruh perubahan dibatalkan (rollback)
    tanpa ada judul atau eksemplar parsial yang tersimpan.
    Status token 'FAILED' dicatat secara persisten pasca rollback pada transaksi terpisah.
    """
    if not token or not str(token).strip():
        raise ConfirmationTokenError("Token konfirmasi impor wajib disertakan.")

    clean_token = str(token).strip()
    ensure_confirmation_tokens_table(conn)

    # In-memory thread lock
    with _TOKEN_LOCK:
        if clean_token in _ACTIVE_PROCESSING_TOKENS:
            raise ConcurrencyConflictError(
                "Permintaan konfirmasi impor sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
            )
        _ACTIVE_PROCESSING_TOKENS.add(clean_token)

    try:
        with transaction_scope(conn):
            # 1. Baca token dari DB dengan write lock
            row = conn.execute(
                "SELECT * FROM confirmation_tokens WHERE token = ?;", (clean_token,)
            ).fetchone()

            if not row:
                raise ConfirmationTokenError("Token konfirmasi tidak valid atau tidak ditemukan.")

            token_data = dict(row)
            now_epoch = time.time()

            # 2. Cek apakah sudah COMPLETED (Replay Idempotency)
            if token_data["status"] == "COMPLETED":
                result_json = token_data.get("result_json")
                if result_json:
                    try:
                        cached_result = json.loads(result_json)
                        return cached_result, True
                    except Exception:
                        pass
                return {}, True

            # 3. Cek apakah sedang PROCESSING
            if token_data["status"] == "PROCESSING":
                raise ConcurrencyConflictError(
                    "Permintaan konfirmasi impor sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
                )

            # 4. Cek masa berlaku token
            if now_epoch > float(token_data.get("expires_at", 0)):
                raise ConfirmationTokenError(
                    "Token konfirmasi telah kedaluwarsa (batas waktu 15 menit). Silakan lakukan pratinjau ulang berkas."
                )

            # 5. Cek kepemilikan sesi admin
            if token_data.get("admin_username") != admin_username:
                raise ConfirmationTokenError("Token konfirmasi tidak sah untuk sesi admin yang aktif.")

            # 6. Cek status gagal sebelumnya
            if token_data["status"] == "FAILED":
                raise ConfirmationTokenError(
                    "Proses impor sebelumnya gagal. Silakan lakukan pratinjau ulang berkas."
                )

            # Ekstraksi payload dari token persisten
            payload = json.loads(token_data["payload_json"])
            token_csv = payload.get("csv_content", "")
            effective_skip_warnings = payload.get("skip_warnings", False) if skip_warnings is None else bool(skip_warnings)

            # 7. Cek integritas payload jika client mengirimkan submitted_csv_content
            if submitted_csv_content is not None:
                submitted_hash = compute_import_payload_hash({
                    "csv_content": submitted_csv_content,
                    "skip_warnings": effective_skip_warnings
                })
                if submitted_hash != token_data.get("payload_hash"):
                    # Cek juga kemungkinan hash dihitung dengan default skip_warnings dari payload
                    alt_hash = compute_import_payload_hash({
                        "csv_content": submitted_csv_content,
                        "skip_warnings": payload.get("skip_warnings", False)
                    })
                    if alt_hash != token_data.get("payload_hash"):
                        raise ConfirmationTokenError(
                            "Data berkas CSV impor telah dimodifikasi sejak pratinjau. Harap lakukan validasi ulang."
                        )

            # 8. Tandai PROCESSING di dalam transaksi aktif
            conn.execute(
                "UPDATE confirmation_tokens SET status = 'PROCESSING' WHERE token = ?;",
                (clean_token,)
            )

            # 9. Validasi ulang berkas CSV secara server-side terhadap status koneksi database terkini
            preview_res = parse_and_validate_catalog_import_csv(
                conn=conn,
                csv_content=token_csv,
                max_file_size_bytes=MAX_CATALOG_IMPORT_FILE_SIZE_BYTES,
                max_rows=MAX_CATALOG_IMPORT_ROWS,
            )

            rows = preview_res.get("rows", [])
            if not rows:
                raise ValidationError("Berkas CSV tidak memiliki baris data yang valid untuk diimpor.")

            titles_created = []
            total_copies_created = 0
            skipped_rows = []
            problematic_rows = []

            for row_item in rows:
                r_num = row_item["row_num"]
                r_status = row_item["status"]
                c_data = row_item["clean_data"]
                r_data = row_item["raw_data"]

                if r_status == "ERROR":
                    problematic_rows.append({
                        "row_num": r_num,
                        "judul": r_data.get("judul") or "<kosong>",
                        "penulis": r_data.get("penulis") or "<kosong>",
                        "errors": row_item.get("errors", []),
                        "raw_data": r_data,
                    })
                elif r_status == "PERINGATAN" and effective_skip_warnings:
                    skipped_rows.append({
                        "row_num": r_num,
                        "judul": c_data.get("judul") or r_data.get("judul"),
                        "penulis": c_data.get("penulis") or r_data.get("penulis"),
                        "warnings": row_item.get("warnings", []),
                        "reason": "Dilewati karena memiliki peringatan duplikat dan opsi lewati diaktifkan.",
                    })
                else:
                    # Status OK atau PERINGATAN (jika skip_warnings=False, dikonfirmasi sebagai rekaman terpisah DEC-013)
                    title_data = {
                        "judul": c_data["judul"],
                        "penulis": c_data["penulis"],
                        "isbn": c_data.get("isbn"),
                        "kategori": c_data["kategori"],
                    }
                    qty = c_data["jumlah"]

                    created_title = create_title_with_copies(
                        conn,
                        title_data=title_data,
                        initial_copies=qty,
                        actor=admin_username,
                    )

                    titles_created.append({
                        "title_id": created_title["id"],
                        "judul": created_title["judul"],
                        "penulis": created_title.get("penulis"),
                        "isbn": created_title.get("isbn"),
                        "kategori": created_title.get("kategori"),
                        "copies_count": qty,
                        "copy_ids": created_title.get("copy_ids", []),
                        "row_num": r_num,
                        "status_asal": r_status,
                    })
                    total_copies_created += qty

            # 10. Catat Batch Audit Log
            all_created_ids = [t["title_id"] for t in titles_created]
            audit_repo.record_audit(
                conn,
                actor=admin_username,
                action="CATALOG_IMPORT",
                object_type="catalog_import",
                object_id=clean_token,
                detail_json={
                    "token": clean_token,
                    "titles_created_count": len(titles_created),
                    "copies_created_count": total_copies_created,
                    "skipped_rows_count": len(skipped_rows),
                    "problematic_rows_count": len(problematic_rows),
                    "title_ids": all_created_ids,
                },
            )

            result_summary = {
                "token": clean_token,
                "status": "COMPLETED",
                "total_rows": len(rows),
                "titles_created_count": len(titles_created),
                "copies_created_count": total_copies_created,
                "skipped_rows_count": len(skipped_rows),
                "problematic_rows_count": len(problematic_rows),
                "created_titles": titles_created,
                "skipped_details": skipped_rows,
                "problematic_details": problematic_rows,
                "completed_at": timeutil.format_iso_utc(timeutil.now_utc()),
            }

            first_title_id = all_created_ids[0] if all_created_ids else None

            # 11. Tandai COMPLETED dan simpan result_json di dalam transaksi atomik
            conn.execute(
                """
                UPDATE confirmation_tokens
                SET status = 'COMPLETED',
                    created_title_id = ?,
                    result_json = ?
                WHERE token = ?;
                """,
                (first_title_id, json.dumps(result_summary, ensure_ascii=False), clean_token)
            )

            # Sinkronisasi cache memori
            with _TOKEN_LOCK:
                _CONFIRMATION_TOKENS[clean_token] = {
                    "token": clean_token,
                    "admin_username": admin_username,
                    "status": "COMPLETED",
                    "result": result_summary,
                }

            return result_summary, False

    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "locked" in err_msg or "busy" in err_msg:
            raise ConcurrencyConflictError(
                "Permintaan konfirmasi impor sedang diproses oleh sistem. Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
            )
        try:
            with conn:
                conn.execute(
                    "UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ?;",
                    (clean_token,)
                )
        except Exception:
            pass
        raise

    except Exception:
        try:
            with conn:
                conn.execute(
                    "UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ?;",
                    (clean_token,)
                )
        except Exception:
            pass
        raise

    finally:
        with _TOKEN_LOCK:
            _ACTIVE_PROCESSING_TOKENS.discard(clean_token)


def format_short_title(title: Optional[str], max_length: int = 28) -> str:
    """
    Memformat judul buku menjadi versi singkat agar pas di label fisik cetak (Task 3-08).
    Mengutamakan kejelasan agar petugas tidak salah menempelkan label ke buku fisik.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        return "Tanpa Judul"
    if len(clean_title) <= max_length:
        return clean_title
    return clean_title[: max_length - 3].rstrip() + "..."


def get_label_items(
    conn: sqlite3.Connection,
    title_id: Optional[str] = None,
    copy_ids: Optional[Sequence[str]] = None,
    search: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Mengambil daftar item label siap cetak (Task 3-08).
    Setiap item memuat:
    - copy_id: ID eksemplar unik (C-XXXXXX)
    - full_title: Judul lengkap buku
    - short_title: Judul versi singkat
    - penulis: Penulis buku
    - isbn: ISBN buku
    - call_number: Nomor panggil jika ada
    - lokasi_rak: Lokasi rak jika ada
    - qr_svg: Representasi SVG dari QR Code yang HANYA memuat copy_id
    MURNI BACA (READ-ONLY) - Tidak menulis ke database sama sekali.
    """
    from .qr_service import generate_copy_qr_svg

    copies = copy_repo.get_copies_for_labels(
        conn,
        title_id=title_id,
        copy_ids=copy_ids,
        search=search,
        limit=limit
    )

    items = []
    for c in copies:
        cid = str(c.get("copy_id") or "").strip()
        if not cid:
            continue
        full_title = str(c.get("judul") or "").strip()
        short_title = format_short_title(full_title, max_length=28)
        qr_svg = generate_copy_qr_svg(cid)
        items.append({
            "copy_id": cid,
            "title_id": c.get("title_id"),
            "full_title": full_title,
            "short_title": short_title,
            "penulis": str(c.get("penulis") or "").strip(),
            "isbn": c.get("isbn") or "",
            "call_number": c.get("call_number") or "",
            "lokasi_rak": c.get("lokasi_rak") or "",
            "kategori": c.get("kategori") or "",
            "qr_svg": qr_svg,
        })
    return items


def parse_copy_ids(input_data: Union[str, Sequence[str], None]) -> List[str]:
    """
    Mem-parsing input ID eksemplar dari berbagai format (string koma/baris baru/spasi atau list/tuple),
    membersihkan whitespace, membuang token kosong, dan menghapus duplikasi tanpa mengubah urutan asli.
    Mencegah duplikasi label yang tidak disengaja ketika memproses daftar ID (Task 3-09).
    """
    if not input_data:
        return []

    tokens: List[str] = []
    if isinstance(input_data, str):
        import re
        raw_tokens = re.split(r'[\r\n,;\s]+', input_data)
        tokens = [t.strip() for t in raw_tokens if t.strip()]
    elif isinstance(input_data, (list, tuple, set)):
        tokens = [str(t).strip() for t in input_data if str(t).strip()]
    else:
        s = str(input_data).strip()
        tokens = [s] if s else []

    # Deduplikasi dengan mempertahankan urutan kemunculan pertama
    seen: Set[str] = set()
    unique_ids: List[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.add(tok)
            unique_ids.append(tok)

    return unique_ids


def get_reprint_label_items(
    conn: sqlite3.Connection,
    copy_ids: Union[str, Sequence[str]],
) -> List[Dict[str, Any]]:
    """
    Mengambil data label siap cetak ulang untuk daftar ID eksemplar tertentu (Task 3-09).
    - Mempertahankan ID eksemplar asli tanpa membuat ID baru.
    - Menghasilkan payload QR yang identik secara deterministik.
    - Menangani ID tidak dikenal secara aman tanpa membuat label palsu.
    - Mencegah duplikasi label yang tidak disengaja.
    MURNI BACA (READ-ONLY) - Tidak menulis ke database.
    """
    clean_ids = parse_copy_ids(copy_ids)
    if not clean_ids:
        return []

    # Ambil label menggunakan get_label_items
    labels = get_label_items(conn, copy_ids=clean_ids, limit=len(clean_ids))

    # Tandai setiap item dengan flag is_reprint=True untuk rendering UI
    for lbl in labels:
        lbl["is_reprint"] = True

    return labels


def get_unlabeled_candidates(
    conn: sqlite3.Connection,
    search: Optional[str] = None,
    lokasi_rak: Optional[str] = None,
    legacy_only: bool = False,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Mengambil daftar eksemplar kandidat tanpa label / buku lama di rak untuk verifikasi fisik petugas (Task 3-09).
    - Mematuhi definisi operasional: menyajikan buku lama (legacy) dan eksemplar aktif di rak.
    - Menampilkan informasi minimum: ID eksemplar, judul singkat, penulis, call number, lokasi rak.
    - Tidak membuat label palsu untuk rekaman tanpa identitas yang valid.
    MURNI BACA (READ-ONLY) - Tidak menulis ke database.
    """
    candidates = copy_repo.get_unlabeled_candidate_copies(
        conn,
        search=search,
        lokasi_rak=lokasi_rak,
        legacy_only=legacy_only,
        limit=limit,
    )

    enriched = []
    for c in candidates:
        cid = str(c.get("copy_id") or "").strip()
        if not cid:
            # Tidak membuat label atau entri palsu tanpa ID yang valid
            continue
        full_title = str(c.get("judul") or "").strip()
        short_title = format_short_title(full_title, max_length=28)
        enriched.append({
            "copy_id": cid,
            "title_id": c.get("title_id"),
            "full_title": full_title,
            "short_title": short_title,
            "penulis": str(c.get("penulis") or "").strip(),
            "isbn": c.get("isbn") or "",
            "kategori": c.get("kategori") or "",
            "call_number": c.get("call_number") or "",
            "lokasi_rak": c.get("lokasi_rak") or "",
            "tanggal_masuk": c.get("tanggal_masuk") or "",
            "copy_status": c.get("copy_status") or "aktif",
            "legacy_ref": c.get("legacy_ref") or "",
            "legacy_buku_id": c.get("legacy_buku_id"),
        })

    return enriched


def clean_catalog_search_query(raw_query: Any) -> str:
    """
    Membersihkan dan memvalidasi string input pencarian katalog publik (Task 3-12):
    - Konversi ke string aman jika None atau bukan tipe string.
    - Strip spasi di awal dan akhir (whitespace stripping).
    - Membatasi panjang string maksimal sesuai MAX_CATALOG_SEARCH_QUERY_LENGTH di policy.py.
    - Menghasilkan string kosong ("") jika input hanya whitespace, None, atau kosong.
    - Mempertahankan karakter Unicode asli dan aksen.
    """
    if raw_query is None:
        return ""
    if isinstance(raw_query, (list, tuple)):
        # Jika query berulang (?query=a&query=b), ambil nilai pertama
        raw_query = raw_query[0] if raw_query else ""
    s = str(raw_query).strip()
    if len(s) > MAX_CATALOG_SEARCH_QUERY_LENGTH:
        s = s[:MAX_CATALOG_SEARCH_QUERY_LENGTH]
    return s


def escape_like_query(term: str, escape_char: str = "\\") -> str:
    r"""
    Meng-escape karakter wildcard SQL LIKE (% dan _) serta karakter escape (\)
    sehingga pencarian LIKE menjadi pencarian substring literal (Task 3-12).
    """
    return catalog_repo.escape_like_pattern(term, escape_char=escape_char)


def search_catalog_public(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    kategori: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    include_metrics: bool = True
) -> Dict[str, Any]:
    """
    Menjalankan pencarian katalog publik menggunakan data ketersediaan aktual dari VIEW `v_title_availability` (Task 3-12).
    - MURNI BACA (READ-ONLY) - Tidak memodifikasi database (Zero-write).
    - Menjamin query berparameter aman dari SQL Injection dan manipulasi karakter khusus (tanda kutip, komentar, titik koma).
    - Menolak eksemplar nonaktif, rusak, hilang, dan dalam penanganan dari hitungan tersedia (diatur langsung oleh v_title_availability).
    - Menangani input kosong atau hanya spasi dengan aman (menampilkan katalog penuh tanpa filter pencarian).
    - Menangani input sangat panjang dengan pemotongan aman (truncation).
    - Mengembalikan struktur data lengkap siap pakai untuk rendering antarmuka pengguna `koleksi.html`.
    """
    clean_query = clean_catalog_search_query(query)
    clean_kategori = clean_catalog_search_query(kategori)

    # Validasi limit & offset
    safe_limit = None
    if limit is not None:
        try:
            safe_limit = max(1, min(int(limit), MAX_CATALOG_PAGE_SIZE))
        except (ValueError, TypeError):
            safe_limit = DEFAULT_CATALOG_PAGE_SIZE

    safe_offset = max(0, int(offset or 0))

    # Ambil judul dan stok ketersediaan dari repositori via v_title_availability
    items = catalog_repo.search_catalog_titles_with_availability(
        conn,
        query=clean_query,
        kategori=clean_kategori,
        limit=safe_limit,
        offset=safe_offset
    )

    total_count = catalog_repo.count_search_catalog_titles(
        conn,
        query=clean_query,
        kategori=clean_kategori
    )

    metrics: Dict[str, Any] = {}
    if include_metrics:
        metrics = catalog_repo.get_catalog_metrics_v2(conn)

    return {
        "items": items,
        "total_count": total_count,
        "query": clean_query,
        "kategori": clean_kategori,
        "limit": safe_limit,
        "offset": safe_offset,
        "metrics": metrics,
    }
