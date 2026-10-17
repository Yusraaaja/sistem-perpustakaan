# -*- coding: utf-8 -*-
"""
Modul Utilitas Waktu Terpusat Sistem Perpustakaan Digital Sekolah.
Memenuhi Rule 7, DEC-005, LIB-RETURN-002, Bagian 4.6, dan Bagian 5.5.

Aturan Utama:
1. Penyimpanan waktu internal berbasis UTC (aware datetime).
2. Tampilan antarmuka selalu dalam zona waktu sekolah (SCHOOL_TZ, default Asia/Jakarta / WIB).
3. Kompatibilitas data lama: timestamp lama (naive lokal) pada database lama diasumsikan
   sebagai waktu lokal sekolah (WIB / Asia/Jakarta) saat dibaca, dan tidak mengubah data lama
   di database asli.
"""
from datetime import datetime, timezone, timedelta, date
import zoneinfo
import math
from typing import Union, Optional, Tuple

from config import SCHOOL_TZ, get_school_timezone
from policy import LOAN_HOURS

WIB_TZ = zoneinfo.ZoneInfo('Asia/Jakarta')


def now_utc() -> datetime:
    """Mengembalikan waktu saat ini dalam format timezone-aware UTC."""
    return datetime.now(timezone.utc)


def get_school_tz() -> zoneinfo.ZoneInfo:
    """Mengembalikan objek ZoneInfo zona waktu sekolah yang aktif."""
    return get_school_timezone()


def parse_db_time(val: Union[str, datetime, date, None]) -> Optional[datetime]:
    """
    Mengurai nilai waktu dari database secara aman menjadi timezone-aware datetime.
    
    Penanganan Kompatibilitas Data Lama:
    - String tanggal murni '%Y-%m-%d' (contoh: '2026-09-18'):
      Dianggap dicatat di zona waktu sekolah (WIB / Asia/Jakarta) pada jam 00:00:00.
    - String datetime naive '%Y-%m-%d %H:%M:%S':
      Dianggap waktu lokal sekolah (WIB), lalu dikonversi ke aware datetime.
    - String ISO-8601 (contoh: '2026-10-17T08:00:00Z' atau '+00:00'):
      Diurai langsung sesuai offset/UTC yang tertera.
    """
    if val is None or val == '':
        return None

    if isinstance(val, datetime):
        if val.tzinfo is None:
            # Naive datetime: anggap waktu lokal sekolah (WIB)
            return val.replace(tzinfo=WIB_TZ)
        return val

    if isinstance(val, date):
        # Date object murni: jadikan datetime jam 00:00:00 WIB
        return datetime(val.year, val.month, val.day, 0, 0, 0, tzinfo=WIB_TZ)

    s = str(val).strip()
    if not s:
        return None

    # Cek format ISO-8601 (misal ada Z atau T)
    if 'T' in s or s.endswith('Z') or '+' in s[10:] or '-' in s[10:]:
        try:
            iso_str = s.replace('Z', '+00:00')
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=WIB_TZ)
            return dt
        except ValueError:
            pass

    # Cek format standar 'YYYY-MM-DD HH:MM:SS'
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=WIB_TZ)
        except ValueError:
            pass

    # Cek format tanggal 'YYYY-MM-DD'
    try:
        d = datetime.strptime(s, '%Y-%m-%d').date()
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=WIB_TZ)
    except ValueError:
        pass

    return None


def to_school_tz(dt_or_val: Union[datetime, date, str, None]) -> Optional[datetime]:
    """
    Mengonversi datetime (atau string/date) ke timezone sekolah (SCHOOL_TZ).
    Jika data lama naive, dianggap WIB lalu dikonversi ke SCHOOL_TZ.
    """
    if dt_or_val is None:
        return None

    parsed = parse_db_time(dt_or_val)
    if parsed is None:
        return None

    return parsed.astimezone(get_school_tz())


def format_school(dt_or_val: Union[datetime, date, str, None], fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Memformat waktu ke string dalam zona waktu sekolah.
    Jika input kosong/None, mengembalikan string kosong.
    """
    localized = to_school_tz(dt_or_val)
    if localized is None:
        return ""
    return localized.strftime(fmt)


def format_school_date(dt_or_val: Union[datetime, date, str, None]) -> str:
    """Shorthand untuk format tanggal '%Y-%m-%d' di zona waktu sekolah."""
    return format_school(dt_or_val, '%Y-%m-%d')


def calculate_due_datetime(borrow_dt: Union[datetime, str], hours: int = LOAN_HOURS) -> datetime:
    """
    Menghitung batas jatuh tempo eksak: waktu pinjam + durasi jam (default 168 jam = 7 hari).
    Mengembalikan timezone-aware datetime UTC.
    """
    parsed = parse_db_time(borrow_dt)
    if parsed is None:
        parsed = now_utc()
    return parsed.astimezone(timezone.utc) + timedelta(hours=hours)


def check_overdue(current_dt: Union[datetime, str], due_dt: Union[datetime, str]) -> Tuple[bool, int, float]:
    """
    Memeriksa keterlambatan berdasarkan batas eksak (LIB-RETURN-002, 4.6).
    
    Mengembalikan tuple: (is_overdue, overdue_days, overdue_seconds)
    - Tepat pada batas jatuh tempo (current_dt == due_dt): is_overdue = False, denda = 0.
    - Melewati 1 detik (current_dt > due_dt): is_overdue = True, overdue_days >= 1.
    """
    curr = parse_db_time(current_dt)
    due = parse_db_time(due_dt)
    if curr is None or due is None:
        return False, 0, 0.0

    curr_utc = curr.astimezone(timezone.utc)
    due_utc = due.astimezone(timezone.utc)

    diff_seconds = (curr_utc - due_utc).total_seconds()
    if diff_seconds <= 0:
        return False, 0, 0.0

    # Terlambat: minimal 1 hari, dibulatkan ke atas per hari berikutnya
    overdue_days = max(1, math.ceil(diff_seconds / 86400.0))
    return True, overdue_days, diff_seconds


def calculate_overdue_days_from_dates(check_date: date, due_date: date) -> int:
    """
    Perhitungan selisih hari antar-tanggal kalender di zona waktu sekolah.
    Digunakan untuk kompatibilitas perhitungan denda kalender harian (Rp 1.000 / hari).
    """
    selisih = (check_date - due_date).days
    return max(0, selisih)
