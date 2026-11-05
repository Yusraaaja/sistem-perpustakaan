# -*- coding: utf-8 -*-
"""
Repositori Catatan Audit Log (audit_log).
Memenuhi Sub-Fase 2A, R2, R12.
"""
import sqlite3
import json
from typing import Optional, List, Dict, Any, Set, Union

import id_generator
import timeutil


def exists_by_id(conn: sqlite3.Connection, audit_id: str) -> bool:
    """Memeriksa keberadaan catatan audit log berdasarkan ID."""
    if not audit_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM audit_log WHERE id = ? LIMIT 1;", (audit_id,)
    ).fetchone()
    return row is not None


def record(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    reason: Optional[str] = None,
    detail_json: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    seen_ids: Optional[Set[str]] = None
) -> str:
    """
    Mencatat entri baru ke tabel `audit_log`.
    Menggunakan ID Generator Crockford Base32 dengan prefix 'AUD-' dan verifikasi tabrakan dua lapis.
    Timestamp otomatis dihasilkan dalam format UTC ISO8601 seragam.
    """
    if not actor or not str(actor).strip():
        raise ValueError("Field 'actor' wajib diisi.")
    if not action or not str(action).strip():
        raise ValueError("Field 'action' wajib diisi.")
    if not object_type or not str(object_type).strip():
        raise ValueError("Field 'object_type' wajib diisi.")
    if not object_id or not str(object_id).strip():
        raise ValueError("Field 'object_id' wajib diisi.")

    def is_taken(candidate: str) -> bool:
        return (seen_ids is not None and candidate in seen_ids) or exists_by_id(conn, candidate)

    audit_id = id_generator.generate_audit_id(is_taken=is_taken)
    if seen_ids is not None:
        seen_ids.add(audit_id)

    now_iso = timeutil.format_iso_utc(timeutil.now_utc())

    detail_str = detail_json
    if isinstance(detail_json, (dict, list)):
        detail_str = json.dumps(detail_json, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO audit_log (
            id, at, actor, action, object_type, object_id, reason, detail_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            audit_id,
            now_iso,
            str(actor).strip(),
            str(action).strip(),
            str(object_type).strip(),
            str(object_id).strip(),
            reason,
            detail_str,
        ),
    )
    return audit_id


def get_by_id(conn: sqlite3.Connection, audit_id: str) -> Optional[Dict[str, Any]]:
    """Mengambil satu entri audit log berdasarkan ID."""
    row = conn.execute(
        "SELECT * FROM audit_log WHERE id = ?;", (audit_id,)
    ).fetchone()
    return dict(row) if row else None


def list_by_object(
    conn: sqlite3.Connection,
    object_type: str,
    object_id: str
) -> List[Dict[str, Any]]:
    """Mendaftar jejak audit log untuk objek tertentu."""
    rows = conn.execute(
        """
        SELECT * FROM audit_log 
        WHERE object_type = ? AND object_id = ? 
        ORDER BY at DESC;
        """,
        (object_type, object_id),
    ).fetchall()
    return [dict(r) for r in rows]


def list_recent(
    conn: sqlite3.Connection,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Mendaftar riwayat audit log terbaru sistem."""
    rows = conn.execute(
        """
        SELECT * FROM audit_log 
        ORDER BY at DESC 
        LIMIT ? OFFSET ?;
        """,
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


# Alias fungsi untuk kemudahan konsumsi di lapisan service
record_audit = record
list_recent_audits = list_recent

