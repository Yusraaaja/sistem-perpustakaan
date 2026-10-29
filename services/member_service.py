# -*- coding: utf-8 -*-
"""
Business Service untuk Pengelolaan Anggota Perpustakaan.
Memenuhi Sub-Fase 2B, DEC-020 (penonaktifan anggota, bukan penghapusan),
DEC-023 (data anggota minimal tanpa kelas/telepon), dan Task 4-01 (Token QR Anggota HMAC-SHA256).
"""
import csv
import hashlib
import hmac
import io
import json
import math
import os
import secrets
import sqlite3
import threading
import time
from typing import Dict, Any, Optional, Union, List, Tuple, Set

import id_generator
import timeutil
from policy import (
    MEMBER_TOKEN_DELIMITER,
    MEMBER_TOKEN_SIG_LENGTH,
    MAX_MEMBER_TOKEN_LENGTH,
    MAX_MEMBER_SEARCH_QUERY_LENGTH,
    DEFAULT_MEMBER_PAGE_SIZE,
    MAX_MEMBER_PAGE_SIZE,
    OFFICIAL_MEMBER_CATEGORIES,
    MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
    MAX_MEMBER_IMPORT_ROWS,
    MEMBER_IMPORT_FILENAME,
    MEMBER_IMPORT_HEADERS,
    MEMBER_REQUIRED_HEADERS,
    MEMBER_IGNORED_COLUMN_NAMES,
    MEMBER_MATCH_STATUSES,
    MEMBER_ACTION_CHOICES,
    CONFIRMATION_TOKEN_TTL_SECONDS,
    MIN_MEMBER_STATUS_REASON_LENGTH,
    MAX_MEMBER_STATUS_REASON_LENGTH,
    OFFICIAL_MEMBER_STATUSES,
    MIN_MEMBER_QR_REISSUE_REASON_LENGTH,
    MAX_MEMBER_QR_REISSUE_REASON_LENGTH,
)
from . import qr_service
from repositories import (
    member_repo,
    audit_repo,
)
from .exceptions import (
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
    SecretKeyError,
    InvalidMemberTokenError,
    MemberTokenRevokedError,
    ConfirmationTokenError,
    ConcurrencyConflictError,
    InvalidOperationError,
)
from .transaction import transaction_scope


# ==============================================================================
# MANAJEMEN KUNCI RAHASIA & TOKEN QR ANGGOTA (TASK 4-01, DEC-010, LIB-QR-001)
# ==============================================================================

def get_member_token_secret(custom_secret: Optional[Union[str, bytes]] = None) -> bytes:
    """
    Mengambil kunci rahasia untuk penandatanganan dan verifikasi HMAC-SHA256 token QR anggota.
    - Jika custom_secret diberikan (misal pada unit test terisolasi), gunakan langsung.
    - Jika tidak diberikan, ambil dari environment variable 'SECRET_KEY' atau 'FLASK_SECRET_KEY'.
    - Jika berada dalam konteks aplikasi Flask yang aktif, periksa current_app.secret_key.
    - Menolak jika kunci tidak dikonfigurasi atau kosong (SecretKeyError).
    - Tidak pernah menampilkan nilai kunci rahasia di pesan error atau log (Production Safety).
    """
    if custom_secret is not None:
        if isinstance(custom_secret, bytes):
            if not custom_secret:
                raise SecretKeyError("Kunci rahasia tidak boleh kosong.")
            return custom_secret
        if isinstance(custom_secret, str):
            clean = custom_secret.strip()
            if not clean:
                raise SecretKeyError("Kunci rahasia tidak boleh kosong.")
            return clean.encode("utf-8")
        raise SecretKeyError("Tipe kunci rahasia tidak valid. Diharapkan string atau bytes.")

    # 1. Coba dari environment variable
    secret = (os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY") or "").strip()

    # 2. Coba dari Flask current_app jika tersedia dalam konteks request
    if not secret:
        try:
            from flask import current_app
            if current_app and current_app.secret_key:
                app_sec = current_app.secret_key
                if isinstance(app_sec, bytes) and app_sec:
                    return app_sec
                elif isinstance(app_sec, str) and app_sec.strip():
                    return app_sec.strip().encode("utf-8")
        except Exception:
            pass

    if not secret:
        raise SecretKeyError(
            "Kunci rahasia (SECRET_KEY) aplikasi belum dikonfigurasi. "
            "Operasi token QR anggota tidak dapat dilakukan."
        )

    return secret.encode("utf-8")


def build_member_token_payload(member_id: str, qr_version: int = 1) -> str:
    """
    Membangun payload token QR anggota secara kanonikal dan deterministik.
    Format kanonikal resmi: "{member_id}:{qr_version}" (contoh: "M-3K9X7W:1").
    Memenuhi DEC-010 & LIB-QR-001: Tanpa data pribadi anggota (nama, kelas, telepon).
    """
    if not member_id or not isinstance(member_id, str) or not member_id.strip():
        raise ValidationError("ID anggota tidak boleh kosong.")

    clean_id = member_id.strip().upper()
    if not clean_id.startswith("M-"):
        raise ValidationError(f"Format ID anggota '{clean_id}' tidak valid. Harus diawali dengan prefix 'M-'.")

    if not isinstance(qr_version, int) or qr_version < 1:
        raise ValidationError(f"Versi QR anggota '{qr_version}' tidak valid. Harus berupa integer >= 1.")

    return f"{clean_id}{MEMBER_TOKEN_DELIMITER}{qr_version}"


def sign_member_token_payload(payload: str, secret_key: Optional[Union[str, bytes]] = None) -> str:
    """
    Menandatangani payload string menggunakan algoritma HMAC-SHA256 standar.
    Mengembalikan tanda autentikasi berupa 64 karakter heksadesimal lowercase.
    """
    if not payload or not isinstance(payload, str) or not payload.strip():
        raise ValidationError("Payload yang akan ditandatangani tidak boleh kosong.")

    secret_bytes = get_member_token_secret(secret_key)
    payload_bytes = payload.strip().encode("utf-8")
    return hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()


def generate_member_qr_token(
    member_id: str,
    qr_version: int = 1,
    secret_key: Optional[Union[str, bytes]] = None
) -> str:
    """
    Menghasilkan token QR anggota lengkap: "{member_id}:{qr_version}:{signature_hex}".
    Memenuhi Task 4-01, DEC-010, dan LIB-QR-001.
    """
    payload = build_member_token_payload(member_id=member_id, qr_version=qr_version)
    sig = sign_member_token_payload(payload, secret_key=secret_key)
    return f"{payload}{MEMBER_TOKEN_DELIMITER}{sig}"


def parse_member_qr_token(token: str) -> Dict[str, Any]:
    """
    Mem-parsing dan memvalidasi struktur sintaksis string token QR anggota.
    Menolak token kosong, terpotong, atau dengan format yang rusak.
    Mengembalikan dictionary: {
        "member_id": str,
        "qr_version": int,
        "signature": str,
        "payload": str
    }
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise InvalidMemberTokenError("Token QR anggota tidak boleh kosong.")

    clean_token = token.strip()
    if len(clean_token) > MAX_MEMBER_TOKEN_LENGTH:
        raise InvalidMemberTokenError("Token QR anggota melebihi batas panjang maksimum yang diizinkan.")

    parts = clean_token.split(MEMBER_TOKEN_DELIMITER)
    if len(parts) != 3:
        raise InvalidMemberTokenError(
            f"Format token QR anggota tidak valid. Diharapkan 3 komponen (member_id:qr_version:signature), "
            f"diterima {len(parts)} komponen."
        )

    raw_member_id, raw_qr_version, raw_sig = parts

    clean_member_id = raw_member_id.strip().upper()
    if not clean_member_id or not clean_member_id.startswith("M-"):
        raise InvalidMemberTokenError(
            f"Format ID anggota dalam token tidak valid: '{raw_member_id}'. Harus diawali dengan 'M-'."
        )

    try:
        qr_version = int(raw_qr_version.strip())
        if qr_version < 1:
            raise ValueError()
    except (ValueError, TypeError):
        raise InvalidMemberTokenError(
            f"Versi QR dalam token tidak valid: '{raw_qr_version}'. Harus berupa integer >= 1."
        )

    clean_sig = raw_sig.strip().lower()
    if len(clean_sig) != MEMBER_TOKEN_SIG_LENGTH or not all(c in "0123456789abcdef" for c in clean_sig):
        raise InvalidMemberTokenError(
            "Tanda tangan token QR tidak valid. Harus berupa 64 karakter heksadesimal."
        )

    canonical_payload = f"{clean_member_id}{MEMBER_TOKEN_DELIMITER}{qr_version}"
    return {
        "member_id": clean_member_id,
        "qr_version": qr_version,
        "signature": clean_sig,
        "payload": canonical_payload,
    }


def verify_member_token_signature(
    token: str,
    secret_key: Optional[Union[str, bytes]] = None
) -> Dict[str, Any]:
    """
    Memverifikasi integritas kriptografis token QR anggota menggunakan HMAC-SHA256
    dan perbandingan aman terhadap timing attack (hmac.compare_digest).
    Menolak jika token rusak, dipotong, dimodifikasi, atau ditandatangani dengan kunci yang berbeda.
    Mengembalikan payload token terverifikasi: {"member_id": str, "qr_version": int, "payload": str}.
    """
    parsed = parse_member_qr_token(token)
    expected_sig = sign_member_token_payload(parsed["payload"], secret_key=secret_key)

    if not hmac.compare_digest(expected_sig, parsed["signature"]):
        raise InvalidMemberTokenError("Tanda tangan token QR anggota tidak cocok atau token telah dimodifikasi.")

    return {
        "member_id": parsed["member_id"],
        "qr_version": parsed["qr_version"],
        "payload": parsed["payload"],
    }


def verify_member_qr_token(
    conn: Optional[sqlite3.Connection],
    token: str,
    secret_key: Optional[Union[str, bytes]] = None,
    check_active: bool = False
) -> Dict[str, Any]:
    """
    Memverifikasi token QR anggota secara menyeluruh:
    1. Verifikasi integritas kriptografis HMAC-SHA256 (timing-safe).
    2. Jika koneksi database diberikan:
       - Memeriksa keberadaan anggota di database (MemberNotFoundError).
       - Memeriksa kesesuaian qr_version dengan versi aktif di database (MemberTokenRevokedError).
       - Jika check_active=True, memastikan anggota berstatus 'aktif' (MemberInactiveError).
    Mengembalikan data anggota lengkap beserta statusnya.
    """
    verified = verify_member_token_signature(token, secret_key=secret_key)
    member_id = verified["member_id"]
    token_version = verified["qr_version"]

    if conn is None:
        return {
            "id": member_id,
            "member_id": member_id,
            "qr_version": token_version,
            "status": None,
        }

    member = member_repo.get_member_by_id(conn, member_id)
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{member_id}' tidak ditemukan di sistem perpustakaan.")

    db_version = int(member.get("qr_version") or 1)
    if db_version != token_version:
        raise MemberTokenRevokedError(
            f"Token QR anggota sudah tidak berlaku (versi kartu: {token_version}, versi aktif: {db_version}). "
            "Kartu mungkin telah dicabut atau diterbitkan ulang."
        )

    if check_active and member.get("status") != "aktif":
        raise MemberInactiveError(
            f"Anggota '{member['nama']}' berstatus nonaktif. "
            "Silakan hubungi petugas untuk mengaktifkan kembali akun anggota."
        )

    return member


def validate_member_token(
    token: str,
    conn: Optional[sqlite3.Connection] = None,
    secret_key: Optional[Union[str, bytes]] = None,
    check_active: bool = False
) -> Dict[str, Any]:
    """
    Fungsi wrapper yang aman dari unhandled exception (cocok untuk API / controller / kiosk).
    Mengembalikan dictionary respons terstruktur tanpa membocorkan trace internal:
    - Sukses: {"valid": True, "code": "OK", "member_id": "...", "qr_version": ..., "member": {...}}
    - Gagal : {"valid": False, "code": "<KODE_ERROR>", "message": "<Pesan bahasa Indonesia ramah>"}
    """
    try:
        member = verify_member_qr_token(
            conn=conn,
            token=token,
            secret_key=secret_key,
            check_active=check_active
        )
        return {
            "valid": True,
            "code": "OK",
            "member_id": member.get("id") or member.get("member_id"),
            "qr_version": member.get("qr_version"),
            "member": member if conn is not None else None,
        }
    except InvalidMemberTokenError as e:
        return {"valid": False, "code": "INVALID_TOKEN", "message": str(e)}
    except MemberNotFoundError as e:
        return {"valid": False, "code": "MEMBER_NOT_FOUND", "message": str(e)}
    except MemberTokenRevokedError as e:
        return {"valid": False, "code": "TOKEN_REVOKED", "message": str(e)}
    except MemberInactiveError as e:
        return {"valid": False, "code": "MEMBER_INACTIVE", "message": str(e)}
    except SecretKeyError as e:
        return {"valid": False, "code": "SECRET_KEY_ERROR", "message": str(e)}
    except Exception:
        return {
            "valid": False,
            "code": "VERIFICATION_ERROR",
            "message": "Terjadi kesalahan saat memverifikasi token anggota.",
        }


# ==============================================================================
# OPERASI BISNIS ANGGOTA (FASE 2B / SUB-FASE 2B)
# ==============================================================================



def validate_member_for_borrowing(conn: sqlite3.Connection, member_id: str) -> Dict[str, Any]:
    """
    Memeriksa kelayakan anggota untuk meminjam buku.
    - Anggota harus terdaftar di database.
    - Status anggota harus 'aktif' (DEC-020).
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")

    member = member_repo.get_member_by_id(conn, member_id.strip())
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{member_id}' tidak ditemukan.")

    if member["status"] != "aktif":
        raise MemberInactiveError(
            f"Anggota '{member['nama']}' berstatus nonaktif. "
            "Peminjaman baru hanya dapat dilakukan oleh anggota aktif. "
            "Silakan hubungi petugas untuk mengaktifkan kembali akun."
        )

    return member


def register_member(
    conn: sqlite3.Connection,
    nama: str,
    category_id: str,
    status: str = "aktif",
    actor: str = "admin"
) -> Dict[str, Any]:
    """
    Mendaftarkan anggota baru ke sistem dan mencatat audit log.
    Seluruh operasi berjalan dalam satu transaksi atomik.
    """
    if not nama or not str(nama).strip():
        raise ValidationError("Nama anggota wajib diisi.")
    if not category_id or not str(category_id).strip():
        raise ValidationError("Kategori anggota wajib dipilih.")

    if not member_repo.category_exists(conn, category_id.strip()):
        raise ValidationError(f"Kategori anggota dengan ID '{category_id}' tidak valid.")

    if status not in {"aktif", "nonaktif"}:
        raise ValidationError(f"Status '{status}' tidak valid. Pilihan: 'aktif' atau 'nonaktif'.")

    with transaction_scope(conn):
        member_id = member_repo.create_member(
            conn,
            {
                "nama": str(nama).strip(),
                "category_id": str(category_id).strip(),
                "status": status,
            },
        )
        audit_repo.record_audit(
            conn,
            actor=actor,
            action="MEMBER_REGISTER",
            object_type="members",
            object_id=member_id,
            detail_json={"nama": str(nama).strip(), "category_id": str(category_id).strip()},
        )
        member = member_repo.get_member_by_id(conn, member_id)

    return member


def set_member_status(
    conn: sqlite3.Connection,
    member_id: str,
    target_status: str,
    reason: str,
    actor: str = "admin",
) -> Dict[str, Any]:
    """
    Mengubah status operasional anggota (aktif <-> nonaktif) dengan alasan wajib dan audit log (Task 4-06, DEC-020).
    - Memenuhi DEC-020: Anggota tidak aktif dinonaktifkan tanpa penghapusan fisik atau otomatis (no hard delete).
    - Validasi ketat: ID anggota wajib valid, status target sah ('aktif' / 'nonaktif'), alasan wajib diisi (5-500 karakter).
    - Konsistensi & Idempotensi: Menolak perubahan redundan jika anggota sudah berada pada status target.
    - Atomik: Mutasi status anggota dan entri audit_log dieksekusi dalam satu transaksi database (transaction_scope).
    - Isolasi: Tidak memutasi data anggota lain, transaksi peminjaman eksisting, atau riwayat sirkulasi.
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")
    clean_member_id = str(member_id).strip().upper()

    clean_target = str(target_status).strip().lower() if target_status else ""
    if clean_target not in OFFICIAL_MEMBER_STATUSES:
        raise ValidationError(
            f"Status target '{target_status}' tidak valid. Pilihan yang diizinkan: {OFFICIAL_MEMBER_STATUSES}"
        )

    if not reason or not str(reason).strip():
        raise ValidationError("Alasan perubahan status anggota wajib diisi.")
    clean_reason = str(reason).strip()
    if len(clean_reason) < MIN_MEMBER_STATUS_REASON_LENGTH:
        raise ValidationError(
            f"Alasan perubahan status minimal {MIN_MEMBER_STATUS_REASON_LENGTH} karakter."
        )
    if len(clean_reason) > MAX_MEMBER_STATUS_REASON_LENGTH:
        raise ValidationError(
            f"Alasan perubahan status maksimal {MAX_MEMBER_STATUS_REASON_LENGTH} karakter."
        )

    clean_actor = str(actor).strip() if actor and str(actor).strip() else "admin"

    member = member_repo.get_member_by_id(conn, clean_member_id)
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{clean_member_id}' tidak ditemukan di sistem perpustakaan.")

    current_status = member.get("status", "aktif")
    if current_status == clean_target:
        raise InvalidOperationError(
            f"Anggota '{clean_member_id}' ({member['nama']}) sudah berstatus '{clean_target}'. Tidak ada perubahan yang dilakukan."
        )

    action_name = "MEMBER_DEACTIVATE" if clean_target == "nonaktif" else "MEMBER_REACTIVATE"
    detail = {
        "previous_status": current_status,
        "new_status": clean_target,
        "nama": member.get("nama"),
        "category_id": member.get("category_id"),
    }

    with transaction_scope(conn):
        ok = member_repo.update_member_status(conn, clean_member_id, clean_target)
        if not ok:
            raise InvalidOperationError(f"Gagal memperbarui status anggota '{clean_member_id}'.")
        audit_id = audit_repo.record_audit(
            conn,
            actor=clean_actor,
            action=action_name,
            object_type="members",
            object_id=clean_member_id,
            reason=clean_reason,
            detail_json=detail,
        )

    return {
        "ok": True,
        "member_id": clean_member_id,
        "nama": member.get("nama"),
        "previous_status": current_status,
        "new_status": clean_target,
        "reason": clean_reason,
        "actor": clean_actor,
        "audit_id": audit_id,
    }


def deactivate_member(
    conn: sqlite3.Connection,
    member_id: str,
    reason: str,
    actor: str = "admin",
) -> Dict[str, Any]:
    """
    Menonaktifkan anggota aktif tanpa menghapus riwayat transaksi (DEC-020, Task 4-06).
    """
    return set_member_status(
        conn=conn,
        member_id=member_id,
        target_status="nonaktif",
        reason=reason,
        actor=actor,
    )


def reactivate_member(
    conn: sqlite3.Connection,
    member_id: str,
    reason: str,
    actor: str = "admin",
) -> Dict[str, Any]:
    """
    Mengaktifkan kembali anggota nonaktif tanpa mengubah riwayat transaksi (DEC-020, Task 4-06).
    """
    return set_member_status(
        conn=conn,
        member_id=member_id,
        target_status="aktif",
        reason=reason,
        actor=actor,
    )


def get_member_audit_history(
    conn: sqlite3.Connection,
    member_id: str,
) -> List[Dict[str, Any]]:
    """
    Mengambil seluruh riwayat catatan audit yang terkait dengan satu anggota (Task 4-06).
    Mendukung pencarian pada object_type 'members' maupun 'member'.
    """
    if not member_id or not str(member_id).strip():
        return []
    clean_id = str(member_id).strip().upper()
    audits = audit_repo.list_by_object(conn, "members", clean_id)
    if not audits:
        audits = audit_repo.list_by_object(conn, "member", clean_id)
    return audits


def get_member_qr(
    conn: sqlite3.Connection,
    member_id: str,
    secret_key: Optional[Union[str, bytes]] = None,
) -> Dict[str, Any]:
    """
    Mengambil data QR terkini untuk anggota tanpa melakukan mutasi basis data (Read-Only).
    Menghasilkan token HMAC-SHA256 berdasarkan qr_version terkini dari database dan kode QR SVG.
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")
    clean_member_id = str(member_id).strip().upper()

    member = member_repo.get_member_by_id(conn, clean_member_id)
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{clean_member_id}' tidak ditemukan di sistem perpustakaan.")

    qr_version = int(member.get("qr_version") or 1)
    token = generate_member_qr_token(
        member_id=clean_member_id,
        qr_version=qr_version,
        secret_key=secret_key,
    )
    qr_svg = qr_service.generate_member_qr_svg(token)

    return {
        "ok": True,
        "member_id": clean_member_id,
        "nama": member.get("nama"),
        "status": member.get("status"),
        "category_id": member.get("category_id"),
        "category_jenis": member.get("category_jenis"),
        "category_keterangan": member.get("category_keterangan"),
        "qr_version": qr_version,
        "token": token,
        "qr_svg": qr_svg,
        "member": member,
    }


def reissue_member_qr(
    conn: sqlite3.Connection,
    member_id: str,
    reason: str,
    actor: str = "admin",
    secret_key: Optional[Union[str, bytes]] = None,
) -> Dict[str, Any]:
    """
    Mencabut token QR lama dan menerbitkan token QR baru dengan menaikkan qr_version tepat +1 (Task 4-07, LIB-QR-001).
    - Memenuhi DEC-010 & DEC-023: Tanpa pembocoran data pribadi (nama/kelas/telepon) dan tanpa pembocoran secret key.
    - Token lama otomatis tidak valid lagi karena qr_version di database telah bertambah.
    - Mempertahankan member_id, identitas, status akun, dan seluruh riwayat transaksi peminjaman.
    - Status anggota ('aktif' atau 'nonaktif') TIDAK diubah secara otomatis.
    - Validasi alasan wajib (5 - 500 karakter).
    - Eksekusi atomik dalam transaction_scope: jika penulisan audit_log gagal, kenaikan qr_version di-rollback 100%.
    - Token baru hanya digenerate dan dikembalikan setelah transaksi berhasil dikonfirmasi (commit).
    """
    if not member_id or not str(member_id).strip():
        raise ValidationError("ID Anggota tidak boleh kosong.")
    clean_member_id = str(member_id).strip().upper()

    if not reason or not str(reason).strip():
        raise ValidationError("Alasan pencabutan dan penerbitan ulang QR wajib diisi.")
    clean_reason = str(reason).strip()
    if len(clean_reason) < MIN_MEMBER_QR_REISSUE_REASON_LENGTH:
        raise ValidationError(
            f"Alasan penerbitan ulang QR minimal {MIN_MEMBER_QR_REISSUE_REASON_LENGTH} karakter."
        )
    if len(clean_reason) > MAX_MEMBER_QR_REISSUE_REASON_LENGTH:
        raise ValidationError(
            f"Alasan penerbitan ulang QR maksimal {MAX_MEMBER_QR_REISSUE_REASON_LENGTH} karakter."
        )

    clean_actor = str(actor).strip() if actor and str(actor).strip() else "admin"

    member = member_repo.get_member_by_id(conn, clean_member_id)
    if not member:
        raise MemberNotFoundError(f"Anggota dengan ID '{clean_member_id}' tidak ditemukan di sistem perpustakaan.")

    old_qr_version = int(member.get("qr_version") or 1)

    # Eksekusi atomik: pembaruan versi dan pencatatan audit log
    with transaction_scope(conn):
        new_version = member_repo.increment_qr_version(conn, clean_member_id)
        if new_version != old_qr_version + 1:
            raise InvalidOperationError(
                f"Inkonsistensi versi QR: versi lama {old_qr_version}, versi baru {new_version}."
            )

        audit_detail = {
            "member_id": clean_member_id,
            "nama": member.get("nama"),
            "old_qr_version": old_qr_version,
            "new_qr_version": new_version,
            "category_id": member.get("category_id"),
            "status": member.get("status"),
        }
        audit_id = audit_repo.record_audit(
            conn,
            actor=clean_actor,
            action="MEMBER_QR_REISSUE",
            object_type="members",
            object_id=clean_member_id,
            reason=clean_reason,
            detail_json=audit_detail,
        )

    # Post-commit: generate token dan QR SVG baru hanya setelah transaksi berhasil
    new_token = generate_member_qr_token(
        member_id=clean_member_id,
        qr_version=new_version,
        secret_key=secret_key,
    )
    new_qr_svg = qr_service.generate_member_qr_svg(new_token)

    return {
        "ok": True,
        "member_id": clean_member_id,
        "nama": member.get("nama"),
        "status": member.get("status"),
        "category_id": member.get("category_id"),
        "old_qr_version": old_qr_version,
        "new_qr_version": new_version,
        "token": new_token,
        "qr_svg": new_qr_svg,
        "reason": clean_reason,
        "actor": clean_actor,
        "audit_id": audit_id,
    }


revoke_and_reissue_member_qr = reissue_member_qr



def _row_to_dict(cursor: Optional[sqlite3.Cursor], row: Any) -> Dict[str, Any]:
    """Helper konversi baris database menjadi dict murni, tahan variasi row_factory."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if isinstance(row, sqlite3.Row) or hasattr(row, "keys"):
        return dict(row)
    if cursor and cursor.description:
        col_names = [d[0] for d in cursor.description]
        return dict(zip(col_names, row))
    return {}


# ==============================================================================
# SEEDING KATEGORI & PENCARIAN ANGGOTA ADMIN (TASK 4-02)
# ==============================================================================

def seed_member_categories(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Melakukan seeding data 5 kategori anggota resmi perpustakaan sekolah:
    1. MC-MURID: murid (Siswa / Murid berdasarkan jurusan)
    2. MC-GURU-JUR: guru_jurusan (Guru kejuruan berdasarkan program keahlian)
    3. MC-GURU-UMUM: guru_umum (Guru mata pelajaran umum)
    4. MC-STAF: staf (Tenaga kependidikan / staf tata usaha)
    5. MC-TEKNISI: teknisi (Laboran / teknisi bengkel/lab)
    
    Bersifat idempoten (menjalankannya kembali tidak menyebabkan duplikasi atau error).
    Mengembalikan seluruh kategori anggota yang tersimpan di basis data.
    """
    with transaction_scope(conn):
        member_repo.seed_default_categories(conn)
    return member_repo.list_categories(conn)


def get_all_categories(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Mengambil seluruh daftar kategori anggota yang tersedia di sistem."""
    return member_repo.list_categories(conn)


def clean_member_search_query(raw_query: Any) -> str:
    """
    Membersihkan dan memvalidasi kueri pencarian anggota:
    - Menghapus whitespace di awal dan akhir.
    - Mengonversi None menjadi string kosong.
    - Memotong kueri jika melebihi MAX_MEMBER_SEARCH_QUERY_LENGTH tanpa error.
    """
    if raw_query is None:
        return ""
    if not isinstance(raw_query, str):
        raw_query = str(raw_query)
    cleaned = raw_query.strip()
    if len(cleaned) > MAX_MEMBER_SEARCH_QUERY_LENGTH:
        cleaned = cleaned[:MAX_MEMBER_SEARCH_QUERY_LENGTH]
    return cleaned


def search_members_admin(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    page: int = 1,
    per_page: int = DEFAULT_MEMBER_PAGE_SIZE
) -> Dict[str, Any]:
    """
    Layanan pencarian dan penyajian daftar anggota untuk antarmuka admin (Task 4-02).
    - Mendukung pencarian teks pada nama anggota dan ID anggota ('M-XXXXXX').
    - Mendukung filter status ('aktif', 'nonaktif').
    - Mendukung filter kategori anggota berdasarkan category_id.
    - Paginasi aman dengan batas per_page terkalibrasi.
    - Seluruh kueri menggunakan parameterized binding dengan perlindungan SQL Injection.
    - Menjaga privasi: tidak mengekspos PII yang melanggar DEC-023.
    """
    clean_q = clean_member_search_query(query)
    clean_status = str(status).strip().lower() if status and str(status).strip() else None
    if clean_status and clean_status not in {"aktif", "nonaktif"}:
        clean_status = None

    clean_category_id = str(category_id).strip() if category_id and str(category_id).strip() else None

    # Normalisasi paginasi
    try:
        page_num = int(page)
        if page_num < 1:
            page_num = 1
    except (ValueError, TypeError):
        page_num = 1

    try:
        limit_num = int(per_page)
        if limit_num < 1:
            limit_num = DEFAULT_MEMBER_PAGE_SIZE
        elif limit_num > MAX_MEMBER_PAGE_SIZE:
            limit_num = MAX_MEMBER_PAGE_SIZE
    except (ValueError, TypeError):
        limit_num = DEFAULT_MEMBER_PAGE_SIZE

    offset = (page_num - 1) * limit_num

    total = member_repo.count_members(
        conn,
        status=clean_status,
        category_id=clean_category_id,
        search=clean_q if clean_q else None
    )

    members = member_repo.list_members(
        conn,
        status=clean_status,
        category_id=clean_category_id,
        search=clean_q if clean_q else None,
        limit=limit_num,
        offset=offset
    )

    total_pages = max(1, math.ceil(total / limit_num)) if total > 0 else 1

    return {
        "members": members,
        "total": total,
        "page": page_num,
        "per_page": limit_num,
        "total_pages": total_pages,
        "has_prev": page_num > 1,
        "has_next": page_num < total_pages,
        "query": clean_q,
        "status": clean_status or "",
        "category_id": clean_category_id or "",
    }


def get_member_management_metrics(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Mengambil metrik ringkasan untuk dashboard pengelolaan anggota admin."""
    return member_repo.get_member_summary_metrics(conn)


# ==============================================================================
# TEMPLATE & VALIDASI AWAL IMPOR ANGGOTA (TASK 4-03, DEC-023)
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


MEMBER_IMPORT_SAMPLE_DATA: List[Dict[str, Any]] = [
    {
        "nama": "Ahmad Fauzi (Contoh)",
        "jenis": "murid",
        "keterangan": "Teknik Komputer dan Jaringan",
        "status": "aktif",
        "id_anggota": "",
    },
    {
        "nama": "Budi Santoso, S.T. (Contoh)",
        "jenis": "guru_jurusan",
        "keterangan": "Teknik Komputer dan Jaringan",
        "status": "aktif",
        "id_anggota": "",
    },
    {
        "nama": "Siti Nurhaliza, S.Pd. (Contoh)",
        "jenis": "guru_umum",
        "keterangan": "Matematika",
        "status": "aktif",
        "id_anggota": "",
    },
    {
        "nama": "Hendra Wijaya (Contoh)",
        "jenis": "staf",
        "keterangan": "Tata Usaha Keuangan",
        "status": "aktif",
        "id_anggota": "",
    },
    {
        "nama": "Rudi Hartono (Contoh)",
        "jenis": "teknisi",
        "keterangan": "Laboran Bengkel Listrik",
        "status": "aktif",
        "id_anggota": "",
    },
    {
        "nama": "Citra Kirana (Contoh)",
        "jenis": "murid",
        "keterangan": "Akuntansi",
        "status": "nonaktif",
        "id_anggota": "M-58QVMS",
    },
]

MEMBER_JENIS_SYNONYMS: Dict[str, Tuple[str, str]] = {
    # Murid
    "murid": ("murid", "MC-MURID"),
    "siswa": ("murid", "MC-MURID"),
    "peserta didik": ("murid", "MC-MURID"),
    "mc-murid": ("murid", "MC-MURID"),

    # Guru Jurusan
    "guru_jurusan": ("guru_jurusan", "MC-GURU-JUR"),
    "guru jurusan": ("guru_jurusan", "MC-GURU-JUR"),
    "guru kejuruan": ("guru_jurusan", "MC-GURU-JUR"),
    "guru produktif": ("guru_jurusan", "MC-GURU-JUR"),
    "mc-guru-jur": ("guru_jurusan", "MC-GURU-JUR"),

    # Guru Umum
    "guru_umum": ("guru_umum", "MC-GURU-UMUM"),
    "guru umum": ("guru_umum", "MC-GURU-UMUM"),
    "guru mapel": ("guru_umum", "MC-GURU-UMUM"),
    "guru mata pelajaran": ("guru_umum", "MC-GURU-UMUM"),
    "mc-guru-umum": ("guru_umum", "MC-GURU-UMUM"),

    # Staf
    "staf": ("staf", "MC-STAF"),
    "staff": ("staf", "MC-STAF"),
    "tenaga kependidikan": ("staf", "MC-STAF"),
    "tu": ("staf", "MC-STAF"),
    "tata usaha": ("staf", "MC-STAF"),
    "mc-staf": ("staf", "MC-STAF"),

    # Teknisi
    "teknisi": ("teknisi", "MC-TEKNISI"),
    "laboran": ("teknisi", "MC-TEKNISI"),
    "toolman": ("teknisi", "MC-TEKNISI"),
    "teknisi bengkel": ("teknisi", "MC-TEKNISI"),
    "mc-teknisi": ("teknisi", "MC-TEKNISI"),
}


def get_member_import_sample_data() -> List[Dict[str, Any]]:
    """
    Mengembalikan salinan data contoh realistis untuk template impor anggota.
    Semua data berlabel '(Contoh)' dan bersifat sintetis tanpa data pribadi asli.
    """
    return [dict(item) for item in MEMBER_IMPORT_SAMPLE_DATA]


def generate_member_import_template_csv() -> str:
    """
    Menghasilkan string CSV untuk template impor anggota dengan header resmi:
    nama, jenis, keterangan, status, id_anggota
    menggunakan library csv bawaan Python dengan penanganan quoting standar.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(list(MEMBER_IMPORT_HEADERS))
    for row in MEMBER_IMPORT_SAMPLE_DATA:
        writer.writerow([
            row["nama"],
            row["jenis"],
            row.get("keterangan") or "",
            row.get("status") or "aktif",
            row.get("id_anggota") or "",
        ])
    return output.getvalue()


def get_member_import_template_download_payload() -> Tuple[bytes, str, str]:
    """
    Menghasilkan payload siap unduh untuk response Flask:
    (csv_bytes, filename, mimetype)
    Teks di-encode sebagai UTF-8 murni.
    """
    csv_text = generate_member_import_template_csv()
    csv_bytes = csv_text.encode("utf-8")
    return csv_bytes, MEMBER_IMPORT_FILENAME, "text/csv; charset=utf-8"


def normalize_member_jenis(
    jenis_raw: Any,
    conn: Optional[sqlite3.Connection] = None
) -> Optional[Tuple[str, str]]:
    """
    Menormalkan input teks jenis anggota ke tuple (canonical_jenis, category_id).
    Mendukung sinonim umum serta pencocokan langsung terhadap tabel member_categories jika koneksi tersedia.
    Jika tidak dikenali, mengembalikan None.
    """
    if not jenis_raw:
        return None
    key = str(jenis_raw).strip().lower()
    if key in MEMBER_JENIS_SYNONYMS:
        return MEMBER_JENIS_SYNONYMS[key]

    # Cek terhadap database jika koneksi diberikan
    if conn:
        try:
            row = conn.execute(
                "SELECT id, jenis FROM member_categories WHERE LOWER(id) = ? OR LOWER(jenis) = ? LIMIT 1;",
                (key, key)
            ).fetchone()
            if row:
                return (row["jenis"], row["id"])
        except Exception:
            pass

    return None


def validate_member_id_format(member_id: Any) -> bool:
    """
    Memvalidasi apakah string ID anggota sesuai format resmi Crockford Base32 (M-XXXXXX).
    Contoh valid: 'M-2K9X7W', 'M-3F8N5D'.
    """
    if not member_id or not isinstance(member_id, str):
        return False
    clean_id = member_id.strip()
    parts = clean_id.split("-")
    if len(parts) != 2 or parts[0] != "M":
        return False
    suffix = parts[1].upper()
    if len(suffix) != id_generator.DEFAULT_SUFFIX_LENGTH:
        return False
    return all(c in id_generator.CROCKFORD_BASE32_ALPHABET for c in suffix)


def validate_member_import_header(raw_headers: List[str]) -> Tuple[Dict[str, int], List[str]]:
    """
    Memeriksa dan memetakan header CSV impor anggota (Task 4-03).
    Mengembalikan:
      - header_map: dict pemetaan nama kolom standar ("nama", "jenis", dll.) ke indeks kolom CSV
      - warnings: list peringatan untuk kolom yang diabaikan (misal 'kelas', 'telepon') per DEC-023
    Melempar ValidationError jika:
      - Header kosong
      - Kolom duplikat
      - Kolom wajib ('nama', 'jenis') tidak ditemukan
    """
    if not raw_headers:
        raise ValidationError("File CSV tidak memuat baris header.")

    cleaned_headers = [str(h).strip().lower() for h in raw_headers]
    if not any(cleaned_headers):
        raise ValidationError("Baris header CSV kosong.")

    # Cek duplikasi
    seen_headers: Set[str] = set()
    for h in cleaned_headers:
        if not h:
            continue
        if h in seen_headers:
            raise ValidationError(f"Header CSV mengandung kolom duplikat: '{h}'.")
        seen_headers.add(h)

    header_map: Dict[str, int] = {}
    warnings: List[str] = []

    for idx, h in enumerate(cleaned_headers):
        if not h:
            continue

        raw_name = raw_headers[idx].strip()

        # Deteksi kolom yang diabaikan (DEC-023: kelas & telepon)
        if h in MEMBER_IGNORED_COLUMN_NAMES:
            if h in {"kelas", "rombel", "tingkat", "class"}:
                warnings.append(
                    f"Kolom '{raw_name}' diabaikan sesuai kebijakan privasi DEC-023 (data kelas siswa tidak disimpan)."
                )
            elif h in {"telepon", "no_telepon", "no_hp", "hp", "telp", "wa", "kontak", "phone", "nomor_telepon", "nomor_hp"}:
                warnings.append(
                    f"Kolom '{raw_name}' diabaikan sesuai kebijakan privasi DEC-023 (nomor kontak pribadi tidak disimpan)."
                )
            else:
                warnings.append(
                    f"Kolom '{raw_name}' diabaikan sesuai kebijakan privasi DEC-023."
                )
            continue

        # Kolom resmi yang diakui
        if h in {"nama", "nama_anggota", "nama_lengkap"}:
            header_map["nama"] = idx
        elif h in {"jenis", "jenis_anggota", "kategori", "tipe"}:
            header_map["jenis"] = idx
        elif h in {"keterangan", "ket", "jurusan", "program_keahlian", "mapel", "bagian"}:
            header_map["keterangan"] = idx
        elif h in {"status", "status_anggota"}:
            header_map["status"] = idx
        elif h in {"id_anggota", "id", "member_id", "id_member"}:
            header_map["id_anggota"] = idx
        else:
            # Kolom tak dikenal diabaikan dengan peringatan ramah
            warnings.append(
                f"Kolom '{raw_name}' tidak dikenali dan akan diabaikan."
            )

    # Validasi keberadaan kolom wajib
    missing_required = [col for col in MEMBER_REQUIRED_HEADERS if col not in header_map]
    if missing_required:
        missing_str = ", ".join(missing_required)
        raise ValidationError(
            f"Kolom wajib tidak lengkap pada file CSV. Kolom berikut wajib ada: {missing_str}."
        )

    return header_map, warnings


def parse_and_validate_member_import_csv(
    conn: Optional[sqlite3.Connection],
    csv_content: Union[bytes, str],
    max_file_size_bytes: int = MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
    max_rows: int = MAX_MEMBER_IMPORT_ROWS,
) -> Dict[str, Any]:
    """
    Melakukan parsing aman dan validasi terhadap berkas CSV impor anggota.
    Memenuhi Task 4-03:
    - Tidak menulis atau mengubah data di database (Zero-Write strictly guaranteed).
    - Membatasi ukuran file (default 2 MiB) dan baris data (default 2.000 baris).
    - Menolak formula spreadsheet pada sel teks untuk mencegah CSV Injection.
    - Mengabaikan kolom 'kelas' dan 'telepon' dengan peringatan jelas tanpa mengungkap PII ke log.
    - Menghasilkan ringkasan dan rincian baris dengan status OK, PERINGATAN, atau ERROR.
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

    # 3. Validasi Kontrak Baris Header & Peringatan Kolom Diabaikan
    header_map, file_warnings = validate_member_import_header(header)

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
    valid_count = 0
    warning_count = 0
    error_count = 0

    max_idx = max(header_map.values())

    for idx, row in enumerate(rows_data):
        row_num = idx + 2  # Baris 1 adalah header di spreadsheet
        errors: List[str] = []
        warnings: List[str] = []

        # Pastikan panjang baris mencukupi indeks kolom yang dipetakan
        if len(row) <= max_idx:
            padded_row = list(row) + [""] * (max_idx + 1 - len(row))
        else:
            padded_row = list(row)

        nama_raw = padded_row[header_map["nama"]]
        jenis_raw = padded_row[header_map["jenis"]]
        keterangan_raw = padded_row[header_map["keterangan"]] if "keterangan" in header_map else ""
        status_raw = padded_row[header_map["status"]] if "status" in header_map else ""
        id_raw = padded_row[header_map["id_anggota"]] if "id_anggota" in header_map else ""

        # Periksa Formula Injection pada tiap cell nilai resmi
        raw_cells = {
            "nama": nama_raw,
            "jenis": jenis_raw,
            "keterangan": keterangan_raw,
            "status": status_raw,
            "id_anggota": id_raw,
        }
        for field_name, cell_val in raw_cells.items():
            if is_potential_formula(cell_val):
                errors.append(
                    f"Kolom '{field_name}' diawali karakter formula spreadsheet ('=', '+', '-', '@') yang tidak diizinkan."
                )

        # Validasi Nama Anggota (Wajib)
        clean_nama = nama_raw.strip()
        if not clean_nama:
            errors.append("Nama anggota wajib diisi.")
        elif len(clean_nama) > 150:
            errors.append("Nama anggota melebihi batas panjang maksimum (150 karakter).")

        # Validasi Jenis Anggota (Wajib)
        normalized_jenis = normalize_member_jenis(jenis_raw, conn=conn)
        if not normalized_jenis:
            if not jenis_raw.strip():
                errors.append("Jenis anggota wajib diisi.")
            else:
                errors.append(
                    f"Jenis anggota '{jenis_raw.strip()}' tidak valid. Pilihan yang didukung: "
                    f"murid, guru_jurusan, guru_umum, staf, teknisi."
                )
            canonical_jenis = jenis_raw.strip()
            category_id = ""
        else:
            canonical_jenis, category_id = normalized_jenis

        # Validasi Keterangan (Opsional)
        clean_keterangan = keterangan_raw.strip()
        if len(clean_keterangan) > 255:
            errors.append("Keterangan anggota melebihi batas panjang maksimum (255 karakter).")

        # Validasi Status (Opsional, Default 'aktif')
        clean_status = status_raw.strip().lower() if status_raw.strip() else "aktif"
        if clean_status not in {"aktif", "nonaktif"}:
            errors.append(
                f"Status '{status_raw.strip()}' tidak valid. Nilai yang diperbolehkan adalah 'aktif' atau 'nonaktif'."
            )

        # Validasi ID Anggota (Opsional)
        clean_id = id_raw.strip().upper() if id_raw.strip() else ""
        if clean_id:
            if not validate_member_id_format(clean_id):
                errors.append(
                    f"Format ID anggota '{clean_id}' tidak valid. Format harus Crockford Base32 (contoh: M-2K9X7W)."
                )
            elif conn:
                # Cek keberadaan ID di database untuk indikasi preview pembaruan (Task 4-04)
                if member_repo.exists_by_id(conn, clean_id):
                    warnings.append(f"ID cocok dengan anggota terdaftar '{clean_id}' (pembaruan data).")
                else:
                    warnings.append(f"ID '{clean_id}' belum terdaftar (akan didaftarkan sebagai ID baru).")

        # Evaluasi Status Baris
        if errors:
            status_code = "ERROR"
            error_count += 1
        elif warnings:
            status_code = "PERINGATAN"
            warning_count += 1
        else:
            status_code = "OK"
            valid_count += 1

        processed_rows.append({
            "row_number": row_num,
            "nama": clean_nama,
            "jenis": canonical_jenis,
            "category_id": category_id,
            "keterangan": clean_keterangan,
            "status": clean_status if clean_status in {"aktif", "nonaktif"} else status_raw.strip(),
            "id_anggota": clean_id,
            "status_code": status_code,
            "errors": errors,
            "warnings": warnings,
        })

    return {
        "total_rows": len(rows_data),
        "valid_rows_count": valid_count,
        "warning_rows_count": warning_count,
        "error_rows_count": error_count,
        "can_proceed": error_count == 0,
        "file_warnings": file_warnings,
        "rows": processed_rows,
    }


# ==============================================================================
# PRATINJAU PENCOCOKAN IMPOR ANGGOTA (TASK 4-04, OPEN-011)
# ZERO-WRITES: Murni read-only tanpa perubahan ke database sama sekali
# ==============================================================================

def preview_member_import_matching(
    conn: sqlite3.Connection,
    csv_content: Union[bytes, str],
    max_file_size_bytes: int = MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
    max_rows: int = MAX_MEMBER_IMPORT_ROWS,
) -> Dict[str, Any]:
    """
    Melakukan pratinjau pencocokan anggota (Task 4-04 & OPEN-011).
    - Murni read-only: Tidak menulis ke database sama sekali.
    - Mengabaikan kolom kelas dan telepon sesuai privasi DEC-023.
    - Mencocokkan ID anggota jika ada:
      * ID cocok -> PEMBARUAN (Kandidat Pembaruan Data).
      * ID tidak dikenal -> TIDAK_DITEMUKAN (Error / Ditolak membuat ID sembarangan).
    - Jika tanpa ID anggota:
      * 0 cocok -> BARU (Kandidat Anggota Baru).
      * 1 cocok -> KEMUNGKINAN_SAMA (Pilihan: Perbarui, Buat Baru, Lewati).
      * >1 cocok -> AMBIGU (Pilihan: Pilih Kandidat Tertentu, Buat Baru, Lewati).
    - Memeriksa duplikasi internal berkas (ID sama berulang di file).
    - Menyediakan opsi tindakan yang sah per baris.
    """
    # 1. Parsing & Validasi format dasar (Task 4-03)
    parsed_res = parse_and_validate_member_import_csv(
        conn=conn,
        csv_content=csv_content,
        max_file_size_bytes=max_file_size_bytes,
        max_rows=max_rows,
    )

    rows: List[Dict[str, Any]] = parsed_res["rows"]
    file_warnings: List[str] = parsed_res["file_warnings"]

    # 2. Deteksi duplikasi di dalam file impor (In-file Duplicates)
    id_occurrences: Dict[str, List[int]] = {}
    name_occurrences: Dict[str, List[int]] = {}

    for r in rows:
        r_id = r.get("id_anggota", "").strip().upper()
        if r_id:
            id_occurrences.setdefault(r_id, []).append(r["row_number"])

        clean_name = r.get("nama", "").strip().lower()
        if clean_name:
            name_occurrences.setdefault(clean_name, []).append(r["row_number"])

    # Tandai konflik ID duplikat di dalam berkas impor
    for r_id, r_nums in id_occurrences.items():
        if len(r_nums) > 1:
            r_nums_str = ", ".join(map(str, r_nums))
            for r in rows:
                if r.get("id_anggota", "").strip().upper() == r_id:
                    err_msg = f"Konflik berkas: ID anggota '{r_id}' muncul {len(r_nums)} kali pada baris {r_nums_str}."
                    if err_msg not in r["errors"]:
                        r["errors"].append(err_msg)
                    r["status_code"] = "ERROR"

    # Tandai peringatan nama berulang di dalam berkas impor jika tanpa ID
    for clean_name, r_nums in name_occurrences.items():
        if len(r_nums) > 1:
            r_nums_str = ", ".join(map(str, r_nums))
            for r in rows:
                if not r.get("id_anggota") and r.get("nama", "").strip().lower() == clean_name:
                    warn_msg = f"Nama anggota '{r['nama']}' muncul berulang di dalam berkas pada baris {r_nums_str}."
                    if warn_msg not in r["warnings"]:
                        r["warnings"].append(warn_msg)

    # 3. Klasifikasi Pencocokan Database (OPEN-011)
    has_members_table = False
    try:
        check_tbl = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='members'").fetchone()
        has_members_table = check_tbl is not None
    except Exception:
        has_members_table = False

    matched_rows: List[Dict[str, Any]] = []

    for r in rows:
        row_dict = dict(r)
        row_num = r.get("row_number", 0)
        row_dict["row_num"] = row_num
        row_dict["row_number"] = row_num
        errors = list(r.get("errors", []))
        warnings = list(r.get("warnings", []))
        status_code = r.get("status_code", "OK")

        r_id = r.get("id_anggota", "").strip().upper()
        r_nama = r.get("nama", "").strip()

        candidates: List[Dict[str, Any]] = []
        matched_member: Optional[Dict[str, Any]] = None
        target_member_id: Optional[str] = None
        diff: Dict[str, Any] = {}
        available_actions: List[str] = []
        selected_action: str = "LEWATI"
        match_status: str = "ERROR"
        match_reason: str = ""

        # Raw data & Clean data untuk konsistensi akses template dan test
        row_dict["raw_data"] = {
            "nama": r.get("nama", ""),
            "jenis": r.get("jenis", ""),
            "keterangan": r.get("keterangan", ""),
            "status": r.get("status", ""),
            "id_anggota": r.get("id_anggota", ""),
        }
        row_dict["clean_data"] = {
            "nama": r.get("nama", ""),
            "jenis": r.get("jenis", ""),
            "keterangan": r.get("keterangan", ""),
            "status": r.get("status", ""),
            "id_anggota": r.get("id_anggota", ""),
            "category_id": r.get("category_id", ""),
        }

        # Kasus 1: Baris sudah memiliki error validasi awal atau duplikat file
        if errors:
            match_status = "ERROR"
            status_code = "ERROR"
            match_reason = "Baris tidak valid: " + "; ".join(errors)
            available_actions = ["LEWATI"]
            selected_action = "LEWATI"

        # Kasus 2: Berkas menyertakan ID anggota (r_id tidak kosong)
        elif r_id:
            db_row = None
            cand_cur = None
            if has_members_table:
                cand_cur = conn.execute(
                    """
                    SELECT m.id, m.nama, m.category_id, mc.jenis as category_jenis, mc.keterangan as category_keterangan,
                           m.status, m.qr_version, m.created_at
                    FROM members m
                    LEFT JOIN member_categories mc ON m.category_id = mc.id
                    WHERE m.id = ?;
                    """,
                    (r_id,)
                )
                db_row = cand_cur.fetchone()

            if db_row:
                cand = _row_to_dict(cand_cur, db_row)
                candidates = [cand]
                matched_member = cand
                target_member_id = cand["id"]
                match_status = "PEMBARUAN"
                match_reason = f"ID cocok dengan anggota terdaftar '{cand['id']}' ({cand['nama']})."
                available_actions = ["PERBARUI", "LEWATI"]
                selected_action = "PERBARUI"

                # Hitung perbedaan nilai (Diff)
                if cand["nama"].strip() != r["nama"].strip():
                    diff["nama"] = {
                        "old": cand["nama"],
                        "new": r["nama"],
                        "db_val": cand["nama"],
                        "csv_val": r["nama"],
                    }
                if cand["category_id"] != r.get("category_id"):
                    diff["category_id"] = {
                        "old": cand.get("category_jenis") or cand["category_id"],
                        "new": r.get("jenis") or r.get("category_id"),
                        "db_val": cand.get("category_jenis") or cand["category_id"],
                        "csv_val": r.get("jenis") or r.get("category_id"),
                    }
                if cand["status"] != r["status"]:
                    diff["status"] = {
                        "old": cand["status"],
                        "new": r["status"],
                        "db_val": cand["status"],
                        "csv_val": r["status"],
                    }

                if diff:
                    diff_keys = list(diff.keys())
                    warnings.append(f"Terdapat perbedaan data dengan data terdaftar: {', '.join(diff_keys)}.")
                    status_code = "PERINGATAN"
                else:
                    status_code = "OK"
            else:
                match_status = "TIDAK_DITEMUKAN"
                status_code = "ERROR"
                err_msg = f"ID anggota '{r_id}' tidak ditemukan di database. Jangan menetapkan ID buatan sendiri untuk anggota baru."
                errors.append(err_msg)
                match_reason = err_msg
                available_actions = ["LEWATI"]
                selected_action = "LEWATI"

        # Kasus 3: Berkas tanpa ID anggota (r_id kosong) -> Cari berdasarkan nama
        else:
            db_rows = []
            cands_cur = None
            if has_members_table:
                cands_cur = conn.execute(
                    """
                    SELECT m.id, m.nama, m.category_id, mc.jenis as category_jenis, mc.keterangan as category_keterangan,
                           m.status, m.qr_version, m.created_at
                    FROM members m
                    LEFT JOIN member_categories mc ON m.category_id = mc.id
                    WHERE LOWER(TRIM(m.nama)) = LOWER(TRIM(?))
                    ORDER BY m.created_at ASC, m.id ASC;
                    """,
                    (r_nama,)
                )
                db_rows = cands_cur.fetchall()
            found_cands = [_row_to_dict(cands_cur, c) for c in db_rows]

            if not found_cands:
                # 0 cocok: Kandidat anggota baru
                match_status = "BARU"
                status_code = "OK" if not warnings else "PERINGATAN"
                match_reason = "Tidak ditemukan anggota terdaftar dengan nama ini. Anggota akan didaftarkan sebagai anggota baru."
                available_actions = ["BUAT_BARU", "LEWATI"]
                selected_action = "BUAT_BARU"
            elif len(found_cands) == 1:
                # 1 cocok: Kemungkinan sama
                cand = found_cands[0]
                candidates = found_cands
                target_member_id = cand["id"]
                match_status = "KEMUNGKINAN_SAMA"
                status_code = "PERINGATAN"
                match_reason = (
                    f"Ditemukan 1 anggota terdaftar dengan nama sama: '{cand['id']}' "
                    f"({cand['nama']}, {cand.get('category_jenis', cand['category_id'])}, {cand['status']}). "
                    f"Petugas dapat memilih memperbarui anggota ini atau mendaftar sebagai anggota baru."
                )
                available_actions = ["PERBARUI", "BUAT_BARU", "LEWATI"]
                selected_action = "PERBARUI"

                # Hitung perbedaan
                if cand["category_id"] != r.get("category_id"):
                    diff["category_id"] = {
                        "old": cand.get("category_jenis") or cand["category_id"],
                        "new": r.get("jenis") or r.get("category_id"),
                        "db_val": cand.get("category_jenis") or cand["category_id"],
                        "csv_val": r.get("jenis") or r.get("category_id"),
                    }
                if cand["status"] != r["status"]:
                    diff["status"] = {
                        "old": cand["status"],
                        "new": r["status"],
                        "db_val": cand["status"],
                        "csv_val": r["status"],
                    }
                if diff:
                    warnings.append(f"Perbedaan dengan kandidat terdaftar: {', '.join(diff.keys())}.")
            else:
                # >1 cocok: Ambigu
                candidates = found_cands
                match_status = "AMBIGU"
                status_code = "PERINGATAN"
                match_reason = (
                    f"Ditemukan {len(found_cands)} anggota terdaftar dengan nama yang sama. "
                    f"Petugas harus memilih kandidat yang ingin diperbarui atau mendaftar sebagai anggota baru."
                )
                available_actions = ["PILIH_KANDIDAT", "BUAT_BARU", "LEWATI"]
                selected_action = "PILIH_KANDIDAT"

        row_dict["match_status"] = match_status
        row_dict["status_code"] = status_code
        row_dict["match_reason"] = match_reason
        row_dict["candidates"] = candidates
        row_dict["matched_member"] = matched_member
        row_dict["target_member_id"] = target_member_id
        row_dict["diff"] = diff
        row_dict["available_actions"] = available_actions
        row_dict["selected_action"] = selected_action
        row_dict["errors"] = errors
        row_dict["warnings"] = warnings

        matched_rows.append(row_dict)

    # 4. Agregasi Statistik Ringkasan Pratinjau
    total_rows = len(matched_rows)
    baru_count = sum(1 for r in matched_rows if r["match_status"] == "BARU")
    pembaruan_count = sum(1 for r in matched_rows if r["match_status"] == "PEMBARUAN")
    kemungkinan_sama_count = sum(1 for r in matched_rows if r["match_status"] == "KEMUNGKINAN_SAMA")
    ambigu_count = sum(1 for r in matched_rows if r["match_status"] == "AMBIGU")
    tidak_ditemukan_count = sum(1 for r in matched_rows if r["match_status"] == "TIDAK_DITEMUKAN")
    error_count = sum(1 for r in matched_rows if r["status_code"] == "ERROR")
    warning_count = sum(1 for r in matched_rows if r["status_code"] == "PERINGATAN")
    valid_count = sum(1 for r in matched_rows if r["status_code"] == "OK")

    return {
        "total_rows": total_rows,
        "baru_count": baru_count,
        "pembaruan_count": pembaruan_count,
        "kemungkinan_sama_count": kemungkinan_sama_count,
        "ambigu_count": ambigu_count,
        "tidak_ditemukan_count": tidak_ditemukan_count,
        "error_count": error_count,
        "error_rows_count": error_count,
        "warning_count": warning_count,
        "warning_rows_count": warning_count,
        "valid_count": valid_count,
        "valid_rows_count": valid_count,
        "can_proceed": (error_count == 0),
        "file_warnings": file_warnings,
        "rows": matched_rows,
    }


def validate_member_import_decisions(
    preview_result: Dict[str, Any],
    decisions: Dict[Any, Dict[str, Any]]
) -> Tuple[bool, List[str], Dict[int, Dict[str, Any]]]:
    """
    Memvalidasi keputusan tindakan yang dipilih petugas per baris data impor (Task 4-04).
    Parameter decisions berupa dict mapping row_number -> {'action': ..., 'target_member_id': ...}.
    Aturan validasi:
    - Tindakan wajib ada di available_actions baris tersebut.
    - Jika tindakan 'PERBARUI' atau 'PILIH_KANDIDAT', target_member_id wajib ada di daftar candidates baris itu.
    - Anti-collision: Dua baris berbeda tidak boleh sama-sama memperbarui target_member_id yang sama.
    - Baris berstatus ERROR hanya dapat memilih LEWATI.
    Mengembalikan (is_valid, list_of_errors, validated_decisions).
    """
    errors: List[str] = []
    seen_targets: Dict[str, int] = {}  # target_id -> row_number
    validated_decisions: Dict[int, Dict[str, Any]] = {}

    rows = preview_result.get("rows", [])
    row_map = {r["row_number"]: r for r in rows}

    for row_num, row in row_map.items():
        decision = decisions.get(row_num) or decisions.get(str(row_num)) or {}
        action = decision.get("action") or row.get("selected_action")
        target_id = decision.get("target_member_id") or row.get("target_member_id")

        if action not in row.get("available_actions", []):
            errors.append(
                f"Baris {row_num}: Tindakan '{action}' tidak tersedia untuk baris {row_num} dengan status '{row.get('match_status')}'. "
                f"Pilihan yang sah: {', '.join(row.get('available_actions', []))}."
            )
            continue

        if action in ("PERBARUI", "PILIH_KANDIDAT"):
            if not target_id:
                errors.append(f"Baris {row_num}: Tindakan '{action}' mewajibkan penentuan target anggota yang diperbarui.")
                continue

            cand_ids = {c["id"] for c in row.get("candidates", [])}
            if target_id not in cand_ids:
                errors.append(f"Baris {row_num}: Target anggota '{target_id}' bukan kandidat sah untuk baris ini.")
                continue

            if target_id in seen_targets:
                errors.append(
                    f"Konflik target pembaruan ganda: Baris {row_num} dan baris {seen_targets[target_id]} "
                    f"sama-sama memilih memperbarui anggota '{target_id}'."
                )
            else:
                seen_targets[target_id] = row_num

        validated_decisions[row_num] = {
            "action": action,
            "target_member_id": target_id,
        }

    return len(errors) == 0, errors, validated_decisions


# ==============================================================================
# TOKEN KONFIRMASI & COMMIT ATOMIK IMPOR ANGGOTA (TASK 4-05, DEC-023)
# ==============================================================================

_MEMBER_TOKEN_LOCK = threading.RLock()
_ACTIVE_PROCESSING_MEMBER_TOKENS: Set[str] = set()
_MEMBER_CONFIRMATION_TOKENS: Dict[str, Dict[str, Any]] = {}


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
            created_title_id TEXT,
            result_json TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_confirmation_tokens_expires ON confirmation_tokens(expires_at);")


def canonicalize_member_import_payload(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Menghasilkan representasi kanonikal dari payload impor anggota untuk hashing SHA-256.
    Memastikan struktur konsisten dan tahan variasi tipe data integer/string pada nomor baris.
    """
    csv_raw = payload_dict.get("csv_content") or ""
    if isinstance(csv_raw, bytes):
        csv_text = csv_raw.decode("utf-8-sig", errors="replace")
    else:
        csv_text = str(csv_raw)

    decisions_raw = payload_dict.get("decisions") or {}
    clean_decisions: Dict[str, Dict[str, Any]] = {}
    if isinstance(decisions_raw, dict):
        for k, v in decisions_raw.items():
            try:
                row_key = str(int(k))
            except (ValueError, TypeError):
                row_key = str(k).strip()
            if isinstance(v, dict):
                clean_decisions[row_key] = {
                    "action": str(v.get("action", "")).strip().upper(),
                    "target_member_id": str(v.get("target_member_id") or "").strip().upper() or None,
                }
            elif isinstance(v, str):
                clean_decisions[row_key] = {
                    "action": str(v).strip().upper(),
                    "target_member_id": None,
                }

    return {
        "action": "member_import",
        "csv_content": csv_text.strip(),
        "decisions": clean_decisions,
    }


def compute_member_import_payload_hash(payload_dict: Dict[str, Any]) -> str:
    """Menghitung hash SHA-256 kanonikal dari payload impor anggota untuk deteksi modifikasi/tampering."""
    clean = canonicalize_member_import_payload(payload_dict)
    serialized = json.dumps(clean, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_member_import_confirmation_token(
    *args,
    **kwargs
) -> str:
    """
    Menerbitkan token konfirmasi persisten sekali pakai untuk alur komit impor anggota massal (Task 4-05).
    Token terikat pada sesi admin, hash isi berkas CSV, dan keputusan pencocokan yang telah divalidasi.
    Mendukung pemanggilan:
    - create_member_import_confirmation_token(conn, csv_content, decisions, admin_username, ttl_seconds)
    - create_member_import_confirmation_token(csv_content, decisions, admin_username=admin_username, ...)
    """
    conn = None
    csv_content = None
    decisions = None
    admin_username = None
    ttl_seconds = kwargs.get("ttl_seconds", CONFIRMATION_TOKEN_TTL_SECONDS)

    if len(args) >= 1 and isinstance(args[0], sqlite3.Connection):
        conn = args[0]
        if len(args) >= 2:
            csv_content = args[1]
        if len(args) >= 3:
            decisions = args[2]
        if len(args) >= 4 and isinstance(args[3], str):
            admin_username = args[3]
        if len(args) >= 5 and isinstance(args[4], (int, float)):
            ttl_seconds = int(args[4])
    else:
        if len(args) >= 1:
            csv_content = args[0]
        if len(args) >= 2:
            decisions = args[1]
        if len(args) >= 3 and isinstance(args[2], str):
            admin_username = args[2]
        if len(args) >= 4 and isinstance(args[3], (int, float)):
            ttl_seconds = int(args[3])

    if conn is None:
        conn = kwargs.get("conn")
    if csv_content is None:
        csv_content = kwargs.get("csv_content")
    if decisions is None:
        decisions = kwargs.get("decisions")
    if admin_username is None:
        admin_username = kwargs.get("admin_username")

    if not admin_username or not str(admin_username).strip():
        raise ValidationError("Sesi admin tidak teridentifikasi untuk penerbitan token impor anggota.")
    if not csv_content:
        raise ValidationError("Konten berkas CSV impor wajib disertakan untuk penerbitan token.")

    should_close = False
    target_conn = conn
    if target_conn is None:
        from db import get_connection
        target_conn = get_connection()
        should_close = True

    try:
        # Validasi pratinjau dan keputusan server-side sebelum menerbitkan token
        preview_res = preview_member_import_matching(
            conn=target_conn,
            csv_content=csv_content,
            max_file_size_bytes=MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
            max_rows=MAX_MEMBER_IMPORT_ROWS,
        )

        is_valid, decision_errors, validated_decisions = validate_member_import_decisions(
            preview_result=preview_res,
            decisions=decisions or {},
        )
        if not is_valid:
            raise ValidationError(f"Keputusan impor anggota tidak valid: {'; '.join(decision_errors)}")

        token = secrets.token_hex(24)
        now_epoch = time.time()
        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        expires_at = now_epoch + ttl_seconds

        csv_text = csv_content if isinstance(csv_content, str) else csv_content.decode("utf-8-sig", errors="replace")

        payload_dict = {
            "action": "member_import",
            "csv_content": csv_text,
            "decisions": validated_decisions,
            "summary_preview": {
                "total_rows": preview_res["total_rows"],
                "baru_count": preview_res["baru_count"],
                "pembaruan_count": preview_res["pembaruan_count"],
                "kemungkinan_sama_count": preview_res["kemungkinan_sama_count"],
                "ambigu_count": preview_res["ambigu_count"],
                "tidak_ditemukan_count": preview_res["tidak_ditemukan_count"],
                "error_count": preview_res["error_count"],
            }
        }
        payload_hash = compute_member_import_payload_hash(payload_dict)
        clean_payload = canonicalize_member_import_payload(payload_dict)
        payload_json = json.dumps(clean_payload, ensure_ascii=False)

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

        with _MEMBER_TOKEN_LOCK:
            _MEMBER_CONFIRMATION_TOKENS[token] = {
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
    finally:
        if should_close:
            target_conn.close()


def commit_member_import_with_token(
    conn: sqlite3.Connection,
    token: str,
    admin_username: str,
    submitted_csv_content: Optional[Union[str, bytes]] = None,
    submitted_decisions: Optional[Dict[Any, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Mengeksekusi komit impor anggota massal secara atomik dan idempoten (Task 4-05).
    Mengembalikan tuple: (result_summary, is_replay)
    - Jika is_replay == True: transaksi sudah selesai sebelumnya, mengembalikan ringkasan sebelumnya tanpa mutasi data.
    - Jika is_replay == False: seluruh pembuatan (BUAT_BARU) dan pembaruan (PERBARUI) dieksekusi dalam SATU transaksi atomik BEGIN IMMEDIATE.
    - Anggota di luar berkas impor 100% tidak dimutasi (zero write to unrelated records).
    - Memenuhi DEC-023: Tanpa kolom kelas dan tanpa nomor telepon.
    """
    clean_token = str(token).strip() if token else ""
    if not clean_token:
        raise ConfirmationTokenError("Token konfirmasi tidak valid atau tidak disertakan.")

    ensure_confirmation_tokens_table(conn)

    # 1. Baca token dari database
    token_cur = conn.execute(
        "SELECT * FROM confirmation_tokens WHERE token = ?;", (clean_token,)
    )
    row = token_cur.fetchone()

    if not row:
        raise ConfirmationTokenError("Token konfirmasi tidak valid atau tidak ditemukan.")

    token_data = _row_to_dict(token_cur, row)
    now_epoch = time.time()

    # 2. Replay Idempotency: Jika sudah COMPLETED, kembalikan hasil sebelumnya tanpa mutasi DB
    if token_data["status"] == "COMPLETED":
        cached_result = None
        if token_data.get("result_json"):
            try:
                cached_result = json.loads(token_data["result_json"])
            except Exception:
                pass
        if cached_result:
            return cached_result, True
        return {
            "token": clean_token,
            "status": "COMPLETED",
            "message": "Transaksi impor anggota telah selesai diproses sebelumnya.",
        }, True

    # 3. Cegah balapan konkurensi (Race Condition)
    with _MEMBER_TOKEN_LOCK:
        if clean_token in _ACTIVE_PROCESSING_MEMBER_TOKENS or token_data["status"] == "PROCESSING":
            raise ConcurrencyConflictError(
                "Permintaan konfirmasi impor anggota sedang diproses oleh sistem. "
                "Mohon tunggu beberapa saat dan jangan menekan tombol berulang kali."
            )

    # 4. Validasi waktu kedaluwarsa (15 menit)
    if now_epoch > float(token_data.get("expires_at", 0)):
        raise ConfirmationTokenError(
            "Token konfirmasi telah kedaluwarsa (batas waktu 15 menit). Silakan lakukan pratinjau ulang berkas."
        )

    # 5. Cek kepemilikan sesi admin
    if token_data.get("admin_username") != admin_username:
        raise ConfirmationTokenError("Token konfirmasi tidak sah untuk sesi admin yang aktif.")

    # 6. Cek status gagal sebelumnya
    if token_data.get("status") == "FAILED":
        raise ConfirmationTokenError(
            "Proses impor sebelumnya gagal. Silakan lakukan pratinjau ulang berkas."
        )

    # 7. Ekstraksi payload dari token persisten
    payload = json.loads(token_data["payload_json"])
    token_csv = payload.get("csv_content", "")
    token_decisions = payload.get("decisions", {})

    effective_csv = token_csv if submitted_csv_content is None else (
        submitted_csv_content if isinstance(submitted_csv_content, str) else submitted_csv_content.decode("utf-8-sig", errors="replace")
    )
    effective_decisions = token_decisions if submitted_decisions is None else submitted_decisions

    # 8. Cek integritas anti-tampering jika client mengirimkan data ulang
    if submitted_csv_content is not None or submitted_decisions is not None:
        submitted_hash = compute_member_import_payload_hash({
            "csv_content": effective_csv,
            "decisions": effective_decisions,
        })
        if submitted_hash != token_data.get("payload_hash"):
            raise ConfirmationTokenError(
                "Data berkas CSV impor atau keputusan petugas telah dimodifikasi sejak pratinjau. Harap lakukan validasi ulang."
            )

    # 9. Kunci token dalam proses memori
    with _MEMBER_TOKEN_LOCK:
        _ACTIVE_PROCESSING_MEMBER_TOKENS.add(clean_token)

    try:
        # 10. Eksekusi transaksi atomik BEGIN IMMEDIATE
        with transaction_scope(conn):
            conn.execute(
                "UPDATE confirmation_tokens SET status = 'PROCESSING' WHERE token = ?;",
                (clean_token,)
            )

            # Validasi ulang server-side pada koneksi database aktif
            preview_res = preview_member_import_matching(
                conn=conn,
                csv_content=token_csv,
                max_file_size_bytes=MAX_MEMBER_IMPORT_FILE_SIZE_BYTES,
                max_rows=MAX_MEMBER_IMPORT_ROWS,
            )

            is_valid, decision_errors, validated_decisions = validate_member_import_decisions(
                preview_result=preview_res,
                decisions=token_decisions,
            )
            if not is_valid:
                raise ValidationError(f"Validasi keputusan impor anggota gagal: {'; '.join(decision_errors)}")

            rows = preview_res.get("rows", [])
            if not rows:
                raise ValidationError("Berkas CSV tidak memiliki baris data untuk diimpor.")

            created_members: List[Dict[str, Any]] = []
            updated_members: List[Dict[str, Any]] = []
            skipped_members: List[Dict[str, Any]] = []
            failed_members: List[Dict[str, Any]] = []

            seen_ids: Set[str] = set()

            for row_item in rows:
                r_num = row_item["row_num"]
                c_data = row_item["clean_data"]
                r_data = row_item["raw_data"]
                status_code = row_item["status_code"]
                match_status = row_item["match_status"]

                decision = validated_decisions.get(r_num) or {}
                action = decision.get("action")
                target_id = decision.get("target_member_id")

                if action == "LEWATI":
                    skipped_members.append({
                        "row_num": r_num,
                        "nama": c_data.get("nama") or r_data.get("nama") or "<kosong>",
                        "reason": "Dilewati sesuai keputusan petugas." if status_code != "ERROR" else "Dilewati karena baris data tidak valid.",
                        "status_asal": match_status,
                    })
                elif action == "BUAT_BARU":
                    member_data = {
                        "nama": c_data["nama"],
                        "category_id": c_data["category_id"],
                        "status": c_data["status"],
                    }
                    new_id = member_repo.create_member(conn, member_data, seen_ids=seen_ids)
                    created_members.append({
                        "row_num": r_num,
                        "id": new_id,
                        "nama": c_data["nama"],
                        "jenis": c_data["jenis"],
                        "category_id": c_data["category_id"],
                        "status": c_data["status"],
                        "keterangan": c_data.get("keterangan", ""),
                    })
                elif action == "PERBARUI":
                    if not target_id:
                        raise ValidationError(f"Baris {r_num}: Target anggota untuk pembaruan wajib ditentukan.")
                    existing = member_repo.get_member_by_id(conn, target_id)
                    if not existing:
                        raise MemberNotFoundError(f"Baris {r_num}: Anggota target '{target_id}' tidak ditemukan di database.")

                    update_data = {
                        "nama": c_data["nama"],
                        "category_id": c_data["category_id"],
                        "status": c_data["status"],
                    }
                    updated_ok = member_repo.update_member(conn, target_id, update_data)
                    if not updated_ok:
                        raise ValidationError(f"Baris {r_num}: Gagal memperbarui data anggota '{target_id}'.")

                    updated_members.append({
                        "row_num": r_num,
                        "id": target_id,
                        "nama": c_data["nama"],
                        "jenis": c_data["jenis"],
                        "category_id": c_data["category_id"],
                        "status": c_data["status"],
                        "keterangan": c_data.get("keterangan", ""),
                    })
                else:
                    raise ValidationError(f"Baris {r_num}: Tindakan '{action}' tidak dikenal.")

            total_processed = len(rows)
            created_count = len(created_members)
            updated_count = len(updated_members)
            skipped_count = len(skipped_members)
            failed_count = len(failed_members)

            result_summary = {
                "token": clean_token,
                "status": "COMPLETED",
                "total_processed": total_processed,
                "total_rows": total_processed,
                "created_count": created_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "created_members": created_members,
                "updated_members": updated_members,
                "skipped_members": skipped_members,
                "failed_members": failed_members,
                "completed_at": timeutil.format_iso_utc(timeutil.now_utc()),
            }

            # 11. Catat Audit Log resmi
            audit_repo.record_audit(
                conn,
                actor=admin_username,
                action="MEMBER_IMPORT",
                object_type="member_import",
                object_id=clean_token,
                detail_json={
                    "token": clean_token,
                    "total_processed": total_processed,
                    "created_count": created_count,
                    "updated_count": updated_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed_count,
                    "created_ids": [m["id"] for m in created_members],
                    "updated_ids": [m["id"] for m in updated_members],
                }
            )

            # 12. Tandai COMPLETED dan simpan result_json
            conn.execute(
                """
                UPDATE confirmation_tokens
                SET status = 'COMPLETED',
                    result_json = ?
                WHERE token = ?;
                """,
                (json.dumps(result_summary, ensure_ascii=False), clean_token)
            )

        # 13. Perbarui cache memori
        with _MEMBER_TOKEN_LOCK:
            _MEMBER_CONFIRMATION_TOKENS[clean_token] = {
                "token": clean_token,
                "status": "COMPLETED",
                "result": result_summary,
            }

        return result_summary, False

    except Exception as exc:
        # Tandai FAILED pada token jika terjadi kegagalan transaksi
        try:
            conn.execute(
                "UPDATE confirmation_tokens SET status = 'FAILED' WHERE token = ? AND status != 'COMPLETED';",
                (clean_token,)
            )
            conn.commit()
        except Exception:
            pass
        raise exc
    finally:
        with _MEMBER_TOKEN_LOCK:
            _ACTIVE_PROCESSING_MEMBER_TOKENS.discard(clean_token)


def commit_member_import(
    conn: sqlite3.Connection,
    csv_content: Union[str, bytes],
    decisions: Dict[Any, Dict[str, Any]],
    admin_username: str,
) -> Dict[str, Any]:
    """
    Helper untuk mengeksekusi komit impor anggota secara langsung.
    Menerbitkan token konfirmasi internal dan mengeksekusi komit atomik.
    """
    token = create_member_import_confirmation_token(
        conn=conn,
        csv_content=csv_content,
        decisions=decisions,
        admin_username=admin_username,
    )
    result, _ = commit_member_import_with_token(
        conn=conn,
        token=token,
        admin_username=admin_username,
    )
    return result


def clear_member_confirmation_tokens(conn: Optional[sqlite3.Connection] = None) -> None:
    """Membersihkan seluruh token konfirmasi impor anggota di memori dan basis data (khusus pengujian)."""
    with _MEMBER_TOKEN_LOCK:
        _ACTIVE_PROCESSING_MEMBER_TOKENS.clear()
        _MEMBER_CONFIRMATION_TOKENS.clear()

    should_close = False
    target_conn = conn
    if target_conn is None:
        try:
            from db import get_connection
            target_conn = get_connection()
            should_close = True
        except Exception:
            return

    try:
        ensure_confirmation_tokens_table(target_conn)
        target_conn.execute("DELETE FROM confirmation_tokens WHERE payload_json LIKE '%member_import%';")
        target_conn.commit()
    except Exception:
        pass
    finally:
        if should_close:
            try:
                target_conn.close()
            except Exception:
                pass





