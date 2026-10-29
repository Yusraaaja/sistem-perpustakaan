# -*- coding: utf-8 -*-
"""
Test Suite untuk Pengujian Waktu, Batas Jatuh Tempo 168 Jam,
Pergantian Hari, Konversi UTC <-> WIB, dan Kompatibilitas Data Lama.
Memenuhi LIB-RETURN-002, 5.5, 4.6, dan Rule 7.
"""
import unittest
import os
import sqlite3
import tempfile
import shutil
from datetime import datetime, timezone, timedelta, date
import zoneinfo

import app as library_app
import config
import policy
from timeutil import (
    now_utc,
    to_school_tz,
    format_school,
    format_school_date,
    parse_db_time,
    calculate_due_datetime,
    check_overdue,
    calculate_overdue_days_from_dates,
    WIB_TZ
)


class TimeAndDueDateUnitTests(unittest.TestCase):
    """Pengujian Unit untuk timeutil, policy, dan batas kalkulasi waktu."""

    def test_01_exact_168_hours_boundary_not_overdue(self):
        """Memastikan pengembalian tepat pada batas 168 jam (7 hari) TIDAK dianggap terlambat (DEC-005, 4.6)."""
        t_borrow = datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc)
        t_due = calculate_due_datetime(t_borrow, hours=policy.LOAN_HOURS)
        
        # Batas due date tepat 168 jam kemudian
        self.assertEqual(t_due - t_borrow, timedelta(hours=168))
        self.assertEqual(t_due, datetime(2026, 10, 17, 8, 0, 0, tzinfo=timezone.utc))

        # Cek pengembalian tepat di titik jatuh tempo (t_return == t_due)
        is_overdue, overdue_days, overdue_sec = check_overdue(current_dt=t_due, due_dt=t_due)
        self.assertFalse(is_overdue, "Tepat pada 168 jam tidak boleh berstatus terlambat")
        self.assertEqual(overdue_days, 0)
        self.assertEqual(overdue_sec, 0.0)

    def test_02_168_hours_plus_one_second_is_overdue(self):
        """Memastikan melewati 1 detik saja (+1 detik) setelah 168 jam langsung dianggap terlambat (LIB-RETURN-002)."""
        t_borrow = datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc)
        t_due = calculate_due_datetime(t_borrow, hours=policy.LOAN_HOURS)
        
        # Pengembalian tepat 1 detik setelah jatuh tempo
        t_late = t_due + timedelta(seconds=1)
        is_overdue, overdue_days, overdue_sec = check_overdue(current_dt=t_late, due_dt=t_due)
        
        self.assertTrue(is_overdue, "Melewati batas 168 jam + 1 detik wajib dianggap terlambat")
        self.assertGreaterEqual(overdue_days, 1, "Keterlambatan minimal 1 hari")
        self.assertEqual(overdue_sec, 1.0)

    def test_03_168_hours_minus_one_second_not_overdue(self):
        """Memastikan pengembalian 1 detik sebelum batas 168 jam adalah sah dan tepat waktu."""
        t_borrow = datetime(2026, 10, 10, 8, 0, 0, tzinfo=timezone.utc)
        t_due = calculate_due_datetime(t_borrow, hours=policy.LOAN_HOURS)
        
        t_before = t_due - timedelta(seconds=1)
        is_overdue, overdue_days, overdue_sec = check_overdue(current_dt=t_before, due_dt=t_due)
        
        self.assertFalse(is_overdue)
        self.assertEqual(overdue_days, 0)
        self.assertEqual(overdue_sec, 0.0)

    def test_04_day_rollover_utc_wib(self):
        """
        Pengujian pergantian hari (midnight rollover):
        Jam 18:00:00 UTC pada hari T adalah jam 01:00:00 WIB pada hari T+1.
        Sistem sekolah harus melihat hari T+1, bukan hari T pada jam server container UTC.
        """
        dt_utc = datetime(2026, 10, 17, 18, 0, 0, tzinfo=timezone.utc)
        dt_wib = to_school_tz(dt_utc)

        # Di UTC masih tanggal 17
        self.assertEqual(dt_utc.day, 17)
        self.assertEqual(dt_utc.strftime('%Y-%m-%d'), '2026-10-17')

        # Di WIB (UTC+7) sudah berganti hari ke tanggal 18 jam 01:00 pagi
        self.assertEqual(dt_wib.day, 18)
        self.assertEqual(dt_wib.hour, 1)
        self.assertEqual(format_school_date(dt_utc), '2026-10-18')

    def test_05_day_rollover_exact_midnight_transition(self):
        """Memastikan transisi pergantian tanggal tepat terjadi pada 00:00:00 WIB (17:00:00 UTC)."""
        just_before_midnight_utc = datetime(2026, 10, 17, 16, 59, 59, tzinfo=timezone.utc)
        exact_midnight_utc = datetime(2026, 10, 17, 17, 0, 0, tzinfo=timezone.utc)

        # 16:59:59 UTC = 23:59:59 WIB (masih tanggal 17)
        self.assertEqual(format_school_date(just_before_midnight_utc), '2026-10-17')
        self.assertEqual(format_school(just_before_midnight_utc, '%H:%M:%S'), '23:59:59')

        # 17:00:00 UTC = 00:00:00 WIB (berganti ke tanggal 18)
        self.assertEqual(format_school_date(exact_midnight_utc), '2026-10-18')
        self.assertEqual(format_school(exact_midnight_utc, '%H:%M:%S'), '00:00:00')

    def test_06_bidirectional_utc_wib_conversion(self):
        """Memastikan konversi bolak-balik antara UTC dan WIB presisi tanpa kehilangan informasi waktu."""
        original_utc = datetime(2026, 10, 17, 4, 30, 45, tzinfo=timezone.utc)
        wib = to_school_tz(original_utc)

        # Offset WIB harus tepat +07:00
        self.assertEqual(wib.utcoffset(), timedelta(hours=7))
        self.assertEqual(wib.hour, 11)
        self.assertEqual(wib.minute, 30)
        self.assertEqual(wib.second, 45)

        # Konversi kembali ke UTC
        converted_back_utc = wib.astimezone(timezone.utc)
        self.assertEqual(original_utc, converted_back_utc)

    def test_07_legacy_naive_date_string_treated_as_wib(self):
        """
        Kompatibilitas data lama:
        String tanggal '2026-09-18' dari database lama tanpa zona waktu (naive)
        diperlakukan sebagai WIB dan ditampilkan konsisten tanpa pergeseran hari.
        """
        legacy_str = '2026-09-18'
        parsed = parse_db_time(legacy_str)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, WIB_TZ)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 9)
        self.assertEqual(parsed.day, 18)

        # Tampilan di zona waktu sekolah tetap '2026-09-18'
        self.assertEqual(format_school_date(parsed), '2026-09-18')

    def test_08_legacy_naive_datetime_string_treated_as_wib(self):
        """
        String datetime '2026-09-18 14:00:00' dari pencatatan lama
        dianggap sebagai waktu WIB (14:00 WIB = 07:00 UTC).
        """
        legacy_dt_str = '2026-09-18 14:00:00'
        parsed = parse_db_time(legacy_dt_str)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, WIB_TZ)
        self.assertEqual(format_school(parsed, '%Y-%m-%d %H:%M:%S'), '2026-09-18 14:00:00')

        # Nilai UTC-nya harus jam 07:00:00 UTC
        utc_equiv = parsed.astimezone(timezone.utc)
        self.assertEqual(utc_equiv.hour, 7)

    def test_09_policy_values_match_decisions(self):
        """Memastikan nilai-nilai kebijakan operasional di policy.py konsisten dengan DEC-005 dan OPEN items."""
        self.assertEqual(policy.LOAN_HOURS, 168)
        self.assertEqual(policy.EXTEND_DAYS, 7)
        self.assertEqual(policy.MAX_EXTENSIONS, 1)
        self.assertEqual(policy.SERIOUS_OVERDUE_DAYS, 7)
        self.assertFalse(policy.ALLOW_RENEW_AFTER_DUE)
        self.assertEqual(policy.GROUP_WINDOW_HOURS, 24)
        self.assertEqual(policy.NOTIF_NAME_MODE, 'full')
        self.assertEqual(policy.BLOCK_MODE, 'serious_only')


class TimeIntegrationWithRoutesTests(unittest.TestCase):
    """Pengujian Integrasi alur peminjaman dan pengembalian terhadap penanganan waktu."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_time_integration.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema header-detail
        library_app.init_db(self.test_db)
        self._seed_sample_books()

    def tearDown(self):
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _seed_sample_books(self):
        conn = sqlite3.connect(self.test_db)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO buku (id, judul, penulis, stok, id_buku_fisik, harga_buku)
            VALUES (1, 'Fisika Dasar', 'Halliday', 2, '["00000101", "00000102"]', 75000)
        ''')
        conn.commit()
        conn.close()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user'] = 'admin'
            sess['_csrf_token'] = 'test_time_csrf_token'
            return sess['_csrf_token']

    def test_10_borrowing_calculates_dates_in_school_tz(self):
        """Memastikan proses_pinjam_admin menghasilkan tgl_pinjam dan tgl_kembali_seharusnya sesuai kalender sekolah."""
        token = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000101',
            'id_anggota': 'Siswa Waktu',
            'tipe_user': 'Siswa',
            'kelas': 'XI',
            'jurusan': 'TKJ',
            'durasi_pinjam': '7'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        header = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Siswa Waktu'").fetchone()
        self.assertIsNotNone(header)

        # Cek tanggal peminjaman cocok dengan hari ini di zona waktu sekolah
        expected_today = format_school_date(now_utc())
        self.assertEqual(header['tgl_pinjam'], expected_today)

        # Cek jatuh tempo 7 hari kemudian
        expected_due = format_school_date(now_utc() + timedelta(days=7))
        self.assertEqual(header['tgl_kembali_seharusnya'], expected_due)
        conn.close()

    def test_11_on_time_return_has_zero_fine(self):
        """Pengembalian sebelum/pada jatuh tempo menghasilkan denda 0."""
        token = self._login_admin()
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        
        # Pinjam 3 hari lalu, jatuh tempo 4 hari ke depan (masih aktif)
        t_pinjam = format_school_date(now_utc() - timedelta(days=3))
        t_tenggat = format_school_date(now_utc() + timedelta(days=4))
        
        c.execute("""
            INSERT INTO peminjaman (kode_transaksi, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, tgl_kembali_seharusnya, status, total_denda)
            VALUES ('TRX-TIME-01', 'Budi OnTime', 'Siswa', 'X', 'RPL', ?, ?, 'Dipinjam', 0)
        """, (t_pinjam, t_tenggat))
        p_id = c.lastrowid
        c.execute("""
            INSERT INTO peminjaman_detail (id_peminjaman, id_buku, no_registrasi, status, denda_keterlambatan, denda_kondisi)
            VALUES (?, 1, '00000101', 'Dipinjam', 0, 0)
        """, (p_id,))
        d_id = c.lastrowid
        conn.commit()
        conn.close()

        # Eksekusi pengembalian
        resp = self.client.post(f'/kembalikan_item/{d_id}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        detail = conn.execute("SELECT * FROM peminjaman_detail WHERE id = ?", (d_id,)).fetchone()
        header = conn.execute("SELECT * FROM peminjaman WHERE id = ?", (p_id,)).fetchone()

        self.assertEqual(detail['status'], 'Kembali')
        self.assertEqual(detail['denda_keterlambatan'], 0)
        self.assertEqual(header['total_denda'], 0)
        self.assertEqual(detail['tgl_dikembalikan'], format_school_date(now_utc()))
        conn.close()


if __name__ == '__main__':
    unittest.main()

