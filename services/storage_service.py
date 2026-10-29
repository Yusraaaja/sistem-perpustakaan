# -*- coding: utf-8 -*-
"""
Modul Layanan Penyimpanan & Validasi Cover Buku (Task 3-11).
Sistem Perpustakaan Digital Sekolah.

Prinsip & Pemisahan Tanggung Jawab:
1. Validasi File:
   - Validasi ukuran maksimum berdasarkan kebijakan resmi (policy.MAX_COVER_IMAGE_SIZE_BYTES).
   - Validasi isi biner berdasarkan signature magic bytes (JPEG, PNG, WEBP, GIF), bukan hanya ekstensi / MIME.
   - Deteksi gambar rusak, file kosong, file terpotong, atau isi non-gambar (skrip, HTML, teks).
   - Verifikasi kecocokan antara ekstensi yang diklaim dengan signature format biner.
2. Nama & Lokasi Penyimpanan:
   - Nama file UUID acak yang dibuat oleh server (bukan nama asli dari client) untuk mencegah tabrakan & eksploitasi.
   - Proteksi ketat terhadap path traversal (tidak dapat menulis ke luar direktori target).
   - Tidak pernah menimpa file cover lama sebelum file baru divalidasi dan berhasil disimpan.
   - Penanganan kegagalan atomik: rollback file baru jika pembaruan metadata basis data gagal (mencegah orphan file).
3. Storage Interface (Penyedia Penyimpanan):
   - Kelas abstrak `Storage` mendefinisikan kontrak penyimpanan (save, delete, exists, get_url, read).
   - Implementasi `LocalStorage` menggunakan sistem berkas lokal (default `static/covers`).
   - Implementasi `FakeStorage` untuk unit testing terisolasi tanpa menyentuh disk fisik.
   - Siap digantikan oleh `SupabaseStorage` pada Fase 10 tanpa merombak logika katalog.
"""
from abc import ABC, abstractmethod
import os
import re
import struct
import uuid
import sqlite3
from typing import Optional, Dict, Any, Tuple, Union, List

import policy
from services.exceptions import (
    ValidationError,
    StorageError,
    CopyNotFoundError,
)
from services.transaction import transaction_scope
from repositories import catalog_repo, audit_repo


# ==============================================================================
# VALIDASI GAMBAR & MAGIC BYTES
# ==============================================================================

def detect_image_format_and_validate(file_bytes: bytes) -> Tuple[bool, str, Optional[str]]:
    """
    Mendeteksi format gambar berdasarkan magic bytes biner asli dan memvalidasi keutuhan dasarnya.
    Mendukung format: PNG, JPEG, GIF, WEBP.
    Mengembalikan: (is_valid, error_message, detected_format_code)
    """
    if not file_bytes:
        return False, "File cover kosong (0 bytes).", None

    size = len(file_bytes)
    if size < 16:
        return False, "File gambar rusak atau ukuran terlalu kecil (< 16 bytes).", None

    # 1. Format PNG: Signature 8 bytes (\x89PNG\r\n\x1a\n)
    if file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        # Validasi struktur PNG: Chunk pertama setelah signature 8-byte wajib IHDR (offset 12..16)
        if size >= 24 and file_bytes[12:16] == b'IHDR':
            return True, "", "png"
        return False, "Struktur header file PNG rusak (chunk IHDR tidak valid atau tidak ditemukan).", None

    # 2. Format JPEG: Signature 3 bytes (\xff\xd8\xff)
    if file_bytes.startswith(b'\xff\xd8\xff'):
        # JPEG yang valid minimal memiliki SOI (\xff\xd8) dan penanda awal wajar
        if size >= 32:
            return True, "", "jpeg"
        return False, "File JPEG rusak atau terpotong prematur (< 32 bytes).", None

    # 3. Format GIF: Signature 6 bytes (GIF87a atau GIF89a)
    if file_bytes.startswith(b'GIF87a') or file_bytes.startswith(b'GIF89a'):
        # GIF minimal 14 bytes (header 6 bytes + logical screen descriptor 7 bytes + 1 byte data/trailer)
        if size >= 14:
            return True, "", "gif"
        return False, "File GIF rusak atau terpotong prematur (< 14 bytes).", None

    # 4. Format WEBP: Container RIFF + format WEBP (offset 8..12)
    if file_bytes.startswith(b'RIFF') and size >= 16 and file_bytes[8:12] == b'WEBP':
        # Validasi chunk awal WEBP (VP8 , VP8L, atau VP8X)
        chunk_fourcc = file_bytes[12:16]
        if chunk_fourcc in (b'VP8 ', b'VP8L', b'VP8X'):
            return True, "", "webp"
        return False, "File WEBP rusak (chunk payload VP8 tidak dikenali).", None

    # Deteksi isi berbahaya atau non-gambar umum
    lower_sample = file_bytes[:512].lower()
    if b'<?php' in lower_sample or b'<script' in lower_sample or b'<html' in lower_sample:
        return False, "Konten file terindikasi sebagai skrip/kode dan ditolak demi keamanan.", None
    if file_bytes.startswith(b'MZ') or file_bytes.startswith(b'\x7fELF'):
        return False, "Konten file terindikasi sebagai berkas biner tereksekusi (executable).", None

    return False, "Konten biner file bukan format gambar yang didukung (verifikasi magic bytes gagal).", None


def validate_cover_image(
    file_bytes: bytes,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Validasi komprehensif file unggahan cover buku:
    1. Batas ukuran file (maksimal 2 MiB per policy).
    2. Validasi ekstensi yang diklaim (jika filename diberikan).
    3. Validasi signature biner asli (magic bytes).
    4. Verifikasi kecocokan antara format biner dengan ekstensi yang diklaim.
    
    Mengembalikan: (is_valid, error_message, canonical_extension)
    """
    if not file_bytes or len(file_bytes) == 0:
        return False, "File cover kosong (0 bytes).", ""

    # 1. Batas Ukuran Maksimum
    max_size = policy.MAX_COVER_IMAGE_SIZE_BYTES
    if len(file_bytes) > max_size:
        max_mb = max_size // (1024 * 1024)
        return False, f"Ukuran file cover ({len(file_bytes)} bytes) melebihi batas maksimum {max_mb} MB.", ""

    # 2. Validasi Ekstensi yang Diklaim (jika filename ada)
    claimed_ext = ""
    if filename:
        clean_name = os.path.basename(str(filename).replace('\\', '/').strip())
        if not clean_name or '.' not in clean_name:
            return False, "Nama file cover tidak memiliki ekstensi yang valid.", ""
        
        claimed_ext = clean_name.rsplit('.', 1)[1].lower()
        if claimed_ext not in policy.ALLOWED_COVER_EXTENSIONS:
            allowed_str = ", ".join(policy.ALLOWED_COVER_EXTENSIONS).upper()
            return False, f"Format/ekstensi file '.{claimed_ext}' tidak didukung. Format yang diizinkan: {allowed_str}.", ""

    # 3. Validasi Magic Bytes & Keutuhan Header
    is_valid_format, format_err, detected_format = detect_image_format_and_validate(file_bytes)
    if not is_valid_format or not detected_format:
        return False, format_err, ""

    # 4. Verifikasi Kecocokan Ekstensi dengan Magic Bytes
    if claimed_ext:
        if claimed_ext in ('jpg', 'jpeg') and detected_format != 'jpeg':
            return False, f"Signature format biner file ({detected_format.upper()}) tidak cocok dengan ekstensi yang diklaim (.{claimed_ext}).", ""
        if claimed_ext == 'png' and detected_format != 'png':
            return False, f"Signature format biner file ({detected_format.upper()}) tidak cocok dengan ekstensi yang diklaim (.{claimed_ext}).", ""
        if claimed_ext == 'gif' and detected_format != 'gif':
            return False, f"Signature format biner file ({detected_format.upper()}) tidak cocok dengan ekstensi yang diklaim (.{claimed_ext}).", ""
        if claimed_ext == 'webp' and detected_format != 'webp':
            return False, f"Signature format biner file ({detected_format.upper()}) tidak cocok dengan ekstensi yang diklaim (.{claimed_ext}).", ""

    # Normalisasi ekstensi kanonik (jpeg -> jpg)
    canonical_ext = "jpg" if detected_format == "jpeg" else detected_format
    return True, "", canonical_ext


def generate_cover_filename(extension: str) -> str:
    """
    Menghasilkan nama file UUID acak dari server dengan ekstensi kanonik.
    Mencegah tabrakan nama dan melindungi dari serangan path traversal / arbitrary overwrite.
    """
    clean_ext = str(extension).lstrip('.').lower().strip()
    return f"{uuid.uuid4().hex}.{clean_ext}"


# ==============================================================================
# STORAGE INTERFACE (Penyedia Penyimpanan Aset)
# ==============================================================================

class Storage(ABC):
    """
    Kontrak interface penyimpanan aset (Task 3-11).
    Memisahkan abstraksi penyimpanan dari sistem berkas lokal.
    """

    @abstractmethod
    def save(self, file_bytes: bytes, filename: str, content_type: Optional[str] = None) -> str:
        """
        Menyimpan data biner ke media penyimpanan.
        Mengembalikan identifier / nama file relatif yang disimpan.
        """
        pass

    @abstractmethod
    def delete(self, identifier: str) -> bool:
        """
        Menghapus file dari media penyimpanan berdasarkan identifier/nama file.
        Mengembalikan True jika berhasil dihapus atau file memang tidak ada.
        """
        pass

    @abstractmethod
    def exists(self, identifier: str) -> bool:
        """Memeriksa keberadaan file di media penyimpanan."""
        pass

    @abstractmethod
    def get_url(self, identifier: str) -> str:
        """Mengembalikan URL atau path relatif yang dapat diakses klien peramban."""
        pass

    @abstractmethod
    def read(self, identifier: str) -> bytes:
        """Membaca isi biner file dari media penyimpanan."""
        pass


class LocalStorage(Storage):
    """
    Implementasi penyimpanan berkas pada disk lokal (default static/covers).
    Dilengkapi perlindungan anti-path traversal dan pembuatan direktori otomatis.
    """

    def __init__(self, base_dir: Optional[str] = None, url_prefix: str = "/static/covers"):
        if base_dir is None:
            # Menggunakan direktori static/covers di root workspace
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base_dir = os.path.join(root_dir, "static", "covers")
        self.base_dir = os.path.abspath(base_dir)
        self.url_prefix = url_prefix.rstrip('/')
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve_safe_path(self, identifier: str) -> str:
        """
        Memastikan path target berada secara ketat di dalam base_dir (anti-path traversal).
        """
        clean_name = os.path.basename(str(identifier).replace('\\', '/').strip())
        if not clean_name or clean_name in ('.', '..'):
            raise ValidationError("Nama file tidak valid atau berpotensi membahayakan sistem.")

        target = os.path.abspath(os.path.join(self.base_dir, clean_name))
        try:
            common = os.path.commonpath([target, self.base_dir])
            if common != self.base_dir:
                raise ValidationError("Path traversal terdeteksi. Akses ke luar direktori penyimpanan ditolak.")
        except ValueError:
            raise ValidationError("Path traversal terdeteksi.")
        return target

    def save(self, file_bytes: bytes, filename: str, content_type: Optional[str] = None) -> str:
        target_path = self._resolve_safe_path(filename)
        safe_name = os.path.basename(target_path)

        try:
            with open(target_path, "wb") as f:
                f.write(file_bytes)
        except OSError as e:
            raise StorageError(f"Gagal menulis file cover ke disk lokal: {str(e)}")

        return safe_name

    def delete(self, identifier: str) -> bool:
        if not identifier or not str(identifier).strip():
            return True
        try:
            target_path = self._resolve_safe_path(identifier)
            if os.path.isfile(target_path):
                os.remove(target_path)
            return True
        except (ValidationError, OSError):
            return False

    def exists(self, identifier: str) -> bool:
        if not identifier or not str(identifier).strip():
            return False
        try:
            target_path = self._resolve_safe_path(identifier)
            return os.path.isfile(target_path)
        except ValidationError:
            return False

    def get_url(self, identifier: str) -> str:
        if not identifier or not str(identifier).strip():
            return ""
        s = str(identifier).strip()
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/"):
            return s
        safe_name = os.path.basename(s.replace('\\', '/'))
        return f"{self.url_prefix}/{safe_name}"

    def read(self, identifier: str) -> bytes:
        target_path = self._resolve_safe_path(identifier)
        if not os.path.isfile(target_path):
            raise StorageError(f"File '{identifier}' tidak ditemukan di penyimpanan lokal.")
        try:
            with open(target_path, "rb") as f:
                return f.read()
        except OSError as e:
            raise StorageError(f"Gagal membaca file dari disk: {str(e)}")


class FakeStorage(Storage):
    """
    Penyimpanan tiruan dalam memori untuk pengujian terisolasi (Fake / In-Memory Storage).
    Mendukung pengujian simulasi kegagalan penyimpanan atau penghapusan tanpa mutasi disk fisik.
    """

    def __init__(self, url_prefix: str = "/static/covers"):
        self._files: Dict[str, bytes] = {}
        self.url_prefix = url_prefix.rstrip('/')
        self.simulate_save_error = False
        self.simulate_delete_error = False

    def save(self, file_bytes: bytes, filename: str, content_type: Optional[str] = None) -> str:
        if self.simulate_save_error:
            raise StorageError("Simulasi kegagalan I/O pada penyimpanan FakeStorage.")
        safe_name = os.path.basename(str(filename).replace('\\', '/').strip())
        self._files[safe_name] = bytes(file_bytes)
        return safe_name

    def delete(self, identifier: str) -> bool:
        if self.simulate_delete_error:
            raise StorageError("Simulasi kegagalan I/O saat menghapus di FakeStorage.")
        if not identifier:
            return True
        safe_name = os.path.basename(str(identifier).replace('\\', '/').strip())
        self._files.pop(safe_name, None)
        return True

    def exists(self, identifier: str) -> bool:
        if not identifier:
            return False
        safe_name = os.path.basename(str(identifier).replace('\\', '/').strip())
        return safe_name in self._files

    def get_url(self, identifier: str) -> str:
        if not identifier:
            return ""
        s = str(identifier).strip()
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/"):
            return s
        safe_name = os.path.basename(s.replace('\\', '/'))
        return f"{self.url_prefix}/{safe_name}"

    def read(self, identifier: str) -> bytes:
        safe_name = os.path.basename(str(identifier).replace('\\', '/').strip())
        if safe_name not in self._files:
            raise StorageError(f"File '{safe_name}' tidak ditemukan di FakeStorage.")
        return self._files[safe_name]


# Registry Storage Aktif (Singleton / Default Provider)
_GLOBAL_STORAGE: Optional[Storage] = None


def get_storage() -> Storage:
    """Mengambil penyedia penyimpanan aktif (default LocalStorage)."""
    global _GLOBAL_STORAGE
    if _GLOBAL_STORAGE is None:
        _GLOBAL_STORAGE = LocalStorage()
    return _GLOBAL_STORAGE


def set_storage(storage: Optional[Storage]) -> None:
    """Mengatur penyedia penyimpanan aktif (berguna untuk pengujian unit)."""
    global _GLOBAL_STORAGE
    _GLOBAL_STORAGE = storage


def reset_storage() -> None:
    """Mereset penyedia penyimpanan ke default LocalStorage."""
    global _GLOBAL_STORAGE
    _GLOBAL_STORAGE = None


# ==============================================================================
# BUSINESS SERVICE: UPLOAD COVER BUKU
# ==============================================================================

def update_book_cover(
    conn: sqlite3.Connection,
    book_id: Union[str, int],
    file_bytes: bytes,
    original_filename: str,
    content_type: Optional[str] = None,
    storage: Optional[Storage] = None,
    actor: str = "admin",
) -> Dict[str, Any]:
    """
    Mengunggah cover buku baru untuk judul katalog tertentu dengan alur aman:
    1. Validasi keberadaan buku/judul katalog.
    2. Validasi biner gambar (magic bytes, ukuran, ekstensi).
    3. Pembuatan nama file UUID acak dari server.
    4. Penyimpanan file baru ke storage provider.
    5. Pembaruan metadata katalog & audit log secara atomik.
    6. Pembersihan file cover lama dari storage jika sukses.
    7. Rollback file baru dari storage jika transaksi basis data gagal.
    """
    if not book_id or not str(book_id).strip():
        raise ValidationError("ID Buku/Judul katalog wajib diisi.")
    clean_id = str(book_id).strip()

    # 1. Validasi File Gambar
    is_valid, err_msg, canonical_ext = validate_cover_image(
        file_bytes=file_bytes,
        filename=original_filename,
        content_type=content_type,
    )
    if not is_valid:
        raise ValidationError(err_msg)

    # 2. Cek Keberadaan Buku & Skema Database
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    is_v2 = "catalog_titles" in tables
    is_legacy = "buku" in tables

    actual_title_id: Optional[str] = None
    old_cover: Optional[str] = None
    book_title = ""

    if is_v2:
        title_obj = catalog_repo.get_title_by_id(conn, clean_id)
        if not title_obj and clean_id.isdigit():
            title_obj = catalog_repo.get_title_by_legacy_id(conn, int(clean_id))
        if not title_obj:
            raise CopyNotFoundError(f"Judul katalog dengan ID '{clean_id}' tidak ditemukan.")
        actual_title_id = title_obj["id"]
        old_cover = title_obj.get("cover_path")
        book_title = title_obj.get("judul", "")
    elif is_legacy:
        row = conn.execute("SELECT * FROM buku WHERE id = ?;", (clean_id,)).fetchone()
        if not row:
            raise CopyNotFoundError(f"Buku dengan ID '{clean_id}' tidak ditemukan.")
        buku_dict = dict(row)
        actual_title_id = str(buku_dict["id"])
        old_cover = buku_dict.get("cover_img")
        book_title = buku_dict.get("judul", "")
    else:
        raise CopyNotFoundError("Tabel katalog tidak ditemukan di basis data.")

    # 3. Buat Nama UUID & Simpan ke Storage Provider
    storage_provider = storage or get_storage()
    new_filename = generate_cover_filename(canonical_ext)

    try:
        saved_identifier = storage_provider.save(file_bytes, new_filename, content_type)
    except Exception as save_err:
        raise StorageError(f"Gagal menyimpan cover buku ke storage: {str(save_err)}")

    # 4. Transaksi Basis Data Atomik
    try:
        with transaction_scope(conn):
            if is_v2:
                catalog_repo.update_title(conn, actual_title_id, {"cover_path": new_filename})
                if "audit_log" in tables:
                    audit_repo.record_audit(
                        conn,
                        actor=actor,
                        action="COVER_UPLOAD",
                        object_type="catalog_titles",
                        object_id=actual_title_id,
                        reason=f"Upload cover buku: {original_filename}",
                        detail_json={
                            "previous_cover": old_cover,
                            "new_cover": new_filename,
                            "judul": book_title,
                        }
                    )
            else:
                conn.execute(
                    "UPDATE buku SET cover_img = ? WHERE id = ?;",
                    (new_filename, actual_title_id)
                )
                if "audit_log" in tables:
                    audit_repo.record_audit(
                        conn,
                        actor=actor,
                        action="COVER_UPLOAD",
                        object_type="buku",
                        object_id=str(actual_title_id),
                        reason=f"Upload cover buku: {original_filename}",
                        detail_json={
                            "previous_cover": old_cover,
                            "new_cover": new_filename,
                            "judul": book_title,
                        }
                    )
    except Exception as db_err:
        # ATOMIC CLEANUP: Batalkan penyimpanan file baru agar tidak menjadi orphan file
        try:
            storage_provider.delete(new_filename)
        except Exception:
            pass
        raise db_err

    # 5. Penghapusan Cover Lama (Setelah transaksi database sukses)
    if old_cover and str(old_cover).strip() and old_cover != new_filename:
        try:
            storage_provider.delete(old_cover)
        except Exception:
            # Kegagalan penghapusan file lama tidak membatalkan transaksi utama
            pass

    return {
        "ok": True,
        "book_id": actual_title_id,
        "cover_path": new_filename,
        "cover_url": storage_provider.get_url(new_filename),
        "previous_cover": old_cover,
        "filename": new_filename,
        "judul": book_title,
    }
