# -*- coding: utf-8 -*-
"""
Modul Koneksi dan Manajemen Database Terpusat Skema v2.
Memenuhi Requirement R1, R2, R3 (PRAGMA foreign_keys = ON di setiap koneksi).
"""
import sqlite3
import os
from typing import Optional


def get_connection(
    db_path: Optional[str] = None,
    timeout: Optional[float] = None
) -> sqlite3.Connection:
    """
    Membuka koneksi ke SQLite dengan penegakan integritas Foreign Keys (Task 1B-03 / R3).
    - Menjadi jalur koneksi terpusat untuk aplikasi runtime, repository, service, dan migrator.
    - Resolusi db_path default: os.environ.get('DATABASE_NAME') or 'perpustakaan.db'.
    - Menjamin PRAGMA foreign_keys = ON di setiap koneksi.
    - Menetapkan PRAGMA busy_timeout sesuai konfigurasi timeout untuk mencegah database locked.
    - Mendukung konfigurasi SQLITE_TIMEOUT dan SQLITE_JOURNAL_MODE dari environment.
    - Mengaktifkan row_factory = sqlite3.Row untuk akses data berbasis nama kolom.
    """
    if not db_path:
        db_file = os.environ.get('DATABASE_NAME') or 'perpustakaan.db'
        if db_file == ':memory:' or os.path.isabs(db_file):
            db_path = db_file
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, db_file)

    if timeout is None:
        timeout = float(os.environ.get('SQLITE_TIMEOUT', 30.0))

    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)};")
    conn.execute("PRAGMA foreign_keys = ON;")

    _env_journal = os.environ.get('SQLITE_JOURNAL_MODE')
    if _env_journal:
        try:
            conn.execute(f"PRAGMA journal_mode = {_env_journal.strip().upper()};")
        except sqlite3.Error:
            pass

    conn.row_factory = sqlite3.Row
    return conn


def detect_schema_version(conn: sqlite3.Connection) -> str:
    """
    Mendeteksi versi skema database (R1):
    - 'v1': Skema lama awal (tanpa tabel peminjaman_detail)
    - 'P1': Skema multi-book P1 (memiliki peminjaman_detail, belum skema v2)
    - 'v2': Skema v2 terisolasi (memiliki catalog_titles dan schema_version >= 2)
    """
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    # Cek apakah skema v2 sudah terpasang
    if "catalog_titles" in tables and "copies" in tables and "loan_items" in tables:
        if "schema_version" in tables:
            row = cursor.execute("SELECT MAX(version) FROM schema_version").fetchone()
            if row and row[0] is not None and row[0] >= 2:
                return "v2"
        return "v2"

    if "peminjaman_detail" not in tables:
        return "v1"

    return "P1"

