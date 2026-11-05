# -*- coding: utf-8 -*-
"""
Konfigurasi Inti Sistem Perpustakaan Digital Sekolah.
Mengelola parameter lingkungan, zona waktu sekolah (SCHOOL_TZ), dan keamanan.
"""
import os
import zoneinfo

# ==============================================================================
# ZONA WAKTU SEKOLAH (Rule 7)
# ==============================================================================
# Database menyimpan waktu dalam format UTC (ISO-8601).
# Tampilan pengguna wajib dikonversi ke zona waktu sekolah ini.
SCHOOL_TZ = os.environ.get('SCHOOL_TZ', 'Asia/Jakarta').strip()

def get_school_timezone():
    """Mengembalikan objek zoneinfo.ZoneInfo untuk zona waktu sekolah."""
    try:
        return zoneinfo.ZoneInfo(SCHOOL_TZ)
    except Exception:
        # Fallback ke Asia/Jakarta jika nama zona waktu tidak valid
        return zoneinfo.ZoneInfo('Asia/Jakarta')

