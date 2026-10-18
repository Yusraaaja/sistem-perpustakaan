# -*- coding: utf-8 -*-
"""
Modul Manajemen Transaksi Terpusat (Unit of Work) untuk Service Layer.
Memenuhi Kriteria Batas Transaksi Wajib Sub-Fase 2B:
1. Service memegang batas transaksi secara penuh.
2. Menggunakan BEGIN IMMEDIATE secara eksplisit untuk mencegah race condition/deadlock.
3. Menghindari nested transaction error pada SQLite.
4. Menjamin atomisitas multi-tabel (katalog, eksemplar, peminjaman, dan audit log).
5. Menjamin rollback penuh jika terjadi kesalahan pada langkah mana pun.
"""
import sqlite3
from contextlib import contextmanager
from typing import Generator


@contextmanager
def transaction_scope(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager untuk transaksi database atomik pada Service Layer.
    - Menjalankan `BEGIN IMMEDIATE` secara eksplisit jika koneksi belum dalam transaksi.
    - Jika koneksi sudah berada dalam transaksi aktif (misal dipanggil oleh transaksi luar),
      tidak mengeksekusi `BEGIN` baru untuk menghindari 'cannot start a transaction within a transaction'.
    - Commit jika seluruh blok selesai tanpa error.
    - Rollback jika terjadi exception apa pun sebelum me-raise kembali exception tersebut.
    """
    is_outer_owner = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
        is_outer_owner = True

    try:
        yield conn
        if is_outer_owner and conn.in_transaction:
            conn.commit()
    except Exception:
        if is_outer_owner and conn.in_transaction:
            conn.rollback()
        raise
