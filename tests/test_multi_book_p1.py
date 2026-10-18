# -*- coding: utf-8 -*-
"""Comprehensive regression tests for P1 Multi-Book Transaction & Circulation."""
import os
import sys
import io
import json
import sqlite3
import shutil
import unittest
import pandas as pd
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
from migrate_p1_multibook import run_migration

TEST_DB_NAME = 'backups/test_p1_regression.db'
BACKUP_SRC = 'backups/perpustakaan_backup_20261010_151029.db'


class MultiBookTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs('backups', exist_ok=True)
        shutil.copy2(BACKUP_SRC, TEST_DB_NAME)
        run_migration(TEST_DB_NAME, dry_run=False)

    @classmethod
    def tearDownClass(cls):
        if 'DATABASE_NAME' in os.environ:
            del os.environ['DATABASE_NAME']
        if os.path.exists(TEST_DB_NAME):
            try:
                os.remove(TEST_DB_NAME)
            except Exception:
                pass

    def setUp(self):
        shutil.copy2(BACKUP_SRC, TEST_DB_NAME)
        run_migration(TEST_DB_NAME, dry_run=False)
        os.environ['DATABASE_NAME'] = TEST_DB_NAME

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['_csrf_token'] = 'csrf-test-token'
        return 'csrf-test-token'

    def _get_db(self):
        conn = sqlite3.connect(TEST_DB_NAME)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def test_01_borrow_single_book(self):
        """Peminjaman 1 buku: stok berkurang 1, header 'Dipinjam', detail 'Dipinjam'."""
        token = self._login_admin()
        conn = self._get_db()
        buku3 = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 3").fetchone()
        self.assertEqual(buku3['stok'], 1)
        self.assertIn("00000301", buku3['id_buku_fisik'])
        conn.close()

        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000301',
            'id_anggota': 'Budi Santoso',
            'tipe_user': 'Siswa',
            'kelas': 'X',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        buku3_after = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 3").fetchone()
        self.assertTrue(buku3_after['id_buku_fisik'] is None or "00000301" not in buku3_after['id_buku_fisik'])

        # Cek header
        header = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Budi Santoso'").fetchone()
        self.assertIsNotNone(header)
        self.assertEqual(header['status'], 'Dipinjam')
        self.assertTrue(header['kode_transaksi'].startswith('TRX-'))

        # Cek detail
        details = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ?", (header['id'],)).fetchall()
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]['id_buku'], 3)
        self.assertEqual(details[0]['no_registrasi'], '00000301')
        self.assertEqual(details[0]['status'], 'Dipinjam')
        conn.close()

    def test_02_borrow_three_books_in_one_transaction(self):
        """Peminjaman 3 buku dalam satu transaksi multi-book."""
        token = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000401, 00000402, 00000601',
            'id_anggota': 'Siti Rahma',
            'tipe_user': 'Siswa',
            'kelas': 'XI',
            'jurusan': 'TKJ',
            'durasi_pinjam': '7'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        header = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Siti Rahma'").fetchone()
        self.assertIsNotNone(header)
        self.assertEqual(header['status'], 'Dipinjam')

        details = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ? ORDER BY id ASC", (header['id'],)).fetchall()
        self.assertEqual(len(details), 3)
        regs = [d['no_registrasi'] for d in details]
        self.assertEqual(regs, ['00000401', '00000402', '00000601'])

        # Cek stok buku 4 berkurang 2 (dari 2 menjadi 0)
        b4 = conn.execute("SELECT stok FROM buku WHERE id = 4").fetchone()
        self.assertEqual(b4['stok'], 0)
        # Cek stok buku 6 berkurang 1 (dari 2 menjadi 1)
        b6 = conn.execute("SELECT stok FROM buku WHERE id = 6").fetchone()
        self.assertEqual(b6['stok'], 1)
        conn.close()

    def test_03_borrow_ten_books_in_one_transaction(self):
        """Peminjaman 10 buku dalam satu transaksi multi-book."""
        token = self._login_admin()
        ten_regs = [
            '00000102', '00000202', '00000203', '00000401', '00000402',
            '00000501', '00000502', '00000503', '00000601', '00000602'
        ]
        reg_input = ", ".join(ten_regs)

        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': reg_input,
            'id_anggota': 'Pak Guru Ahmad',
            'tipe_user': 'Guru',
            'kelas': '-',
            'jurusan': 'Kurikulum',
            'durasi_pinjam': '14'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        header = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Pak Guru Ahmad'").fetchone()
        self.assertIsNotNone(header)
        self.assertEqual(header['status'], 'Dipinjam')

        details = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ?", (header['id'],)).fetchall()
        self.assertEqual(len(details), 10)
        conn.close()

    def test_04_partial_return_then_complete_remaining(self):
        """Peminjaman 10 buku, pengembalian 7 buku (status Sebagian), lalu pengembalian 3 sisa (status Selesai)."""
        token = self._login_admin()
        ten_regs = [
            '00000102', '00000202', '00000203', '00000401', '00000402',
            '00000501', '00000502', '00000503', '00000601', '00000602'
        ]
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': ", ".join(ten_regs),
            'id_anggota': 'Siswa Teladan',
            'tipe_user': 'Siswa',
            'kelas': 'XII',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        header = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Siswa Teladan'").fetchone()
        details = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ? ORDER BY id ASC", (header['id'],)).fetchall()
        conn.close()

        # Kembalikan 7 buku pertama
        first_7 = details[:7]
        remaining_3 = details[7:]

        for item in first_7:
            resp = self.client.post(f'/kembalikan_item/{item["id"]}', data={
                'csrf_token': token,
                'status_kembali': 'Kembali'
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

        # Verifikasi status header adalah 'Sebagian'
        conn = self._get_db()
        h_part = conn.execute("SELECT status FROM peminjaman WHERE id = ?", (header['id'],)).fetchone()
        self.assertEqual(h_part['status'], 'Sebagian')

        # Cek 7 item sudah 'Kembali', 3 item masih 'Dipinjam'
        d_part = conn.execute("SELECT status FROM peminjaman_detail WHERE id_peminjaman = ?", (header['id'],)).fetchall()
        kembali_count = sum(1 for d in d_part if d['status'] == 'Kembali')
        dipinjam_count = sum(1 for d in d_part if d['status'] == 'Dipinjam')
        self.assertEqual(kembali_count, 7)
        self.assertEqual(dipinjam_count, 3)
        conn.close()

        # Kembalikan 3 buku sisanya
        for item in remaining_3:
            resp = self.client.post(f'/kembalikan_item/{item["id"]}', data={
                'csrf_token': token,
                'status_kembali': 'Kembali'
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

        # Verifikasi status header sekarang 'Selesai'
        conn = self._get_db()
        h_done = conn.execute("SELECT status FROM peminjaman WHERE id = ?", (header['id'],)).fetchone()
        self.assertEqual(h_done['status'], 'Selesai')

        d_done = conn.execute("SELECT status FROM peminjaman_detail WHERE id_peminjaman = ?", (header['id'],)).fetchall()
        self.assertTrue(all(d['status'] == 'Kembali' for d in d_done))
        conn.close()

    def test_05_return_same_item_twice_idempotency(self):
        """Pengembalian item yang sama dua kali dicegah (idempotensi, tidak menggandakan stok)."""
        token = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000301',
            'id_anggota': 'Idem User',
            'tipe_user': 'Siswa',
            'kelas': 'X',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        detail = conn.execute("SELECT id FROM peminjaman_detail WHERE no_registrasi = '00000301' AND status = 'Dipinjam'").fetchone()
        self.assertIsNotNone(detail)
        conn.close()

        # Pengembalian pertama (sukses)
        resp1 = self.client.post(f'/kembalikan_item/{detail["id"]}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)
        self.assertEqual(resp1.status_code, 200)

        conn = self._get_db()
        b3_after_1 = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 3").fetchone()
        self.assertEqual(b3_after_1['stok'], 1)
        regs_1 = json.loads(b3_after_1['id_buku_fisik'])
        self.assertEqual(regs_1.count('00000301'), 1)
        conn.close()

        # Pengembalian kedua (harus ditolak/diberi peringatan tanpa menambah stok lagi)
        resp2 = self.client.post(f'/kembalikan_item/{detail["id"]}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)
        self.assertEqual(resp2.status_code, 200)

        conn = self._get_db()
        b3_after_2 = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 3").fetchone()
        self.assertEqual(b3_after_2['stok'], 1)  # Tetap 1, TIDAK menjadi 2!
        regs_2 = json.loads(b3_after_2['id_buku_fisik'])
        self.assertEqual(regs_2.count('00000301'), 1)
        conn.close()

    def test_06_two_items_different_status_in_same_transaction(self):
        """Satu transaksi: 1 Kembali normal, 1 Rusak, 1 Hilang (ganti rugi per item)."""
        token = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000501, 00000502, 00000503',
            'id_anggota': 'Beda Status',
            'tipe_user': 'Siswa',
            'kelas': 'XI',
            'jurusan': 'DKV',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        header = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Beda Status'").fetchone()
        self.assertIsNotNone(header)
        items = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ? ORDER BY id ASC", (header['id'],)).fetchall()
        b5 = conn.execute("SELECT harga_buku FROM buku WHERE id = 5").fetchone()
        harga_buku_5 = b5['harga_buku']
        conn.close()

        # Item 1: Kembali normal
        self.client.post(f'/kembalikan_item/{items[0]["id"]}', data={'csrf_token': token, 'status_kembali': 'Kembali'}, follow_redirects=True)
        # Item 2: Rusak
        self.client.post(f'/kembalikan_item/{items[1]["id"]}', data={'csrf_token': token, 'status_kembali': 'Rusak'}, follow_redirects=True)
        # Item 3: Hilang
        self.client.post(f'/kembalikan_item/{items[2]["id"]}', data={'csrf_token': token, 'status_kembali': 'Hilang'}, follow_redirects=True)

        conn = self._get_db()
        h_res = conn.execute("SELECT * FROM peminjaman WHERE id = ?", (header['id'],)).fetchone()
        self.assertEqual(h_res['status'], 'Menunggu Penggantian')
        self.assertEqual(h_res['total_denda'], harga_buku_5 * 2)

        d1 = conn.execute("SELECT * FROM peminjaman_detail WHERE id = ?", (items[0]['id'],)).fetchone()
        d2 = conn.execute("SELECT * FROM peminjaman_detail WHERE id = ?", (items[1]['id'],)).fetchone()
        d3 = conn.execute("SELECT * FROM peminjaman_detail WHERE id = ?", (items[2]['id'],)).fetchone()

        self.assertEqual(d1['status'], 'Kembali')
        self.assertEqual(d1['denda_kondisi'], 0)

        self.assertEqual(d2['status'], 'Rusak')
        self.assertEqual(d2['denda_kondisi'], harga_buku_5)

        self.assertEqual(d3['status'], 'Hilang')
        self.assertEqual(d3['denda_kondisi'], harga_buku_5)
        self.assertEqual(d3['status_penggantian'], 'Menunggu Penggantian')

        # Hanya item 1 yang kembali ke stok rak (00000501)
        b5_final = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 5").fetchone()
        regs_final = json.loads(b5_final['id_buku_fisik'])
        self.assertIn('00000501', regs_final)
        self.assertNotIn('00000502', regs_final)
        self.assertNotIn('00000503', regs_final)
        conn.close()

    def test_07_invalid_registration_number_rejected(self):
        """Nomor registrasi palsu / tidak valid ditolak tanpa membuat transaksi."""
        token = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': 'NONEXISTENT_REG',
            'id_anggota': 'Fake User',
            'tipe_user': 'Siswa',
            'kelas': 'X',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        h = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Fake User'").fetchone()
        self.assertIsNone(h)
        conn.close()

    def test_08_unavailable_book_atomic_rollback(self):
        """Jika 1 dari 3 buku tidak tersedia (misal reg 00001501 milik Yusra yang sedang dipinjam), seluruh peminjaman batal."""
        token = self._login_admin()
        conn = self._get_db()
        b1_stok_before = conn.execute("SELECT stok FROM buku WHERE id = 1").fetchone()['stok']
        b2_stok_before = conn.execute("SELECT stok FROM buku WHERE id = 2").fetchone()['stok']
        conn.close()

        # 00000102 (tersedia), 00000202 (tersedia), 00001501 (SEDANG DIPINJAM YUSRA)
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000102, 00000202, 00001501',
            'id_anggota': 'Atomic Candidate',
            'tipe_user': 'Siswa',
            'kelas': 'XI',
            'jurusan': 'TKJ',
            'durasi_pinjam': '7'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        h = conn.execute("SELECT * FROM peminjaman WHERE id_anggota = 'Atomic Candidate'").fetchone()
        self.assertIsNone(h)

        b1_stok_after = conn.execute("SELECT stok FROM buku WHERE id = 1").fetchone()['stok']
        b2_stok_after = conn.execute("SELECT stok FROM buku WHERE id = 2").fetchone()['stok']
        self.assertEqual(b1_stok_before, b1_stok_after)
        self.assertEqual(b2_stok_before, b2_stok_after)
        conn.close()

    def test_09_fine_calculation_per_item(self):
        """Perhitungan denda keterlambatan per item jika melewati jatuh tempo."""
        token = self._login_admin()
        conn = self._get_db()
        tgl_pinjam = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        tgl_tenggat = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

        c = conn.cursor()
        c.execute("""
            INSERT INTO peminjaman (kode_transaksi, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, tgl_kembali_seharusnya, status, total_denda)
            VALUES ('TRX-TEST-LATE', 'Siswa Terlambat', 'Siswa', 'X', 'RPL', ?, ?, 'Dipinjam', 0)
        """, (tgl_pinjam, tgl_tenggat))
        p_id = c.lastrowid
        c.execute("""
            INSERT INTO peminjaman_detail (id_peminjaman, id_buku, no_registrasi, status, denda_keterlambatan, denda_kondisi)
            VALUES (?, 1, '00000102', 'Dipinjam', 0, 0)
        """, (p_id,))
        d_id = c.lastrowid

        b1 = conn.execute("SELECT id_buku_fisik FROM buku WHERE id = 1").fetchone()
        regs = json.loads(b1['id_buku_fisik'])
        if '00000102' in regs:
            regs.remove('00000102')
        c.execute("UPDATE buku SET stok = ?, id_buku_fisik = ? WHERE id = 1", (len(regs), json.dumps(regs)))
        conn.commit()
        conn.close()

        resp = self.client.post(f'/kembalikan_item/{d_id}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        detail = conn.execute("SELECT * FROM peminjaman_detail WHERE id = ?", (d_id,)).fetchone()
        header = conn.execute("SELECT * FROM peminjaman WHERE id = ?", (p_id,)).fetchone()

        self.assertEqual(detail['status'], 'Kembali')
        # Terlambat 3 hari * 1000 = 3000
        self.assertEqual(detail['denda_keterlambatan'], 3000)
        self.assertEqual(header['total_denda'], 3000)
        conn.close()

    def test_10_book_history_api_and_excel_export(self):
        """API riwayat buku dan ekspor Excel berfungsi normal dengan relasi header-detail."""
        self._login_admin()
        api_resp = self.client.get('/api/riwayat_buku/15')
        self.assertEqual(api_resp.status_code, 200)
        data = json.loads(api_resp.data)
        self.assertGreaterEqual(len(data), 1)
        self.assertEqual(data[0]['id_anggota'], 'Yusra')
        self.assertEqual(data[0]['status'], 'Dipinjam')

        excel_resp = self.client.get('/export_peminjaman')
        self.assertEqual(excel_resp.status_code, 200)
        self.assertIn('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', excel_resp.content_type)
        self.assertGreater(len(excel_resp.data), 1000)

    def test_11_completed_loan_deletion_rejected_preserves_history(self):
        """Penghapusan transaksi selesai (Selesai) DITOLAK: riwayat tetap terlindungi permanen demi audit."""
        token = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000701',
            'id_anggota': 'Hapus Candidate Selesai',
            'tipe_user': 'Siswa',
            'kelas': 'X',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        header = conn.execute("SELECT id FROM peminjaman WHERE id_anggota = 'Hapus Candidate Selesai'").fetchone()
        self.assertIsNotNone(header)
        h_id = header['id']
        detail = conn.execute("SELECT id FROM peminjaman_detail WHERE id_peminjaman = ?", (h_id,)).fetchone()
        conn.close()

        # Kembalikan buku terlebih dahulu hingga status menjadi 'Selesai'
        self.client.post(f'/kembalikan_item/{detail["id"]}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)

        conn = self._get_db()
        h_ready = conn.execute("SELECT status FROM peminjaman WHERE id = ?", (h_id,)).fetchone()
        self.assertEqual(h_ready['status'], 'Selesai')
        conn.close()

        # Hapus transaksi selesai -> DITOLAK demi integritas riwayat arsip
        del_resp = self.client.post(f'/hapus_peminjaman/{h_id}', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        conn = self._get_db()
        h_after = conn.execute("SELECT id, status FROM peminjaman WHERE id = ?", (h_id,)).fetchone()
        self.assertIsNotNone(h_after)
        self.assertEqual(h_after['status'], 'Selesai')

        d_after = conn.execute("SELECT id FROM peminjaman_detail WHERE id_peminjaman = ?", (h_id,)).fetchall()
        self.assertEqual(len(d_after), 1)

        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(len(violations), 0)
        conn.close()

    def test_12_active_loan_deletion_rejected_preserves_state(self):
        """Penghapusan transaksi aktif (Dipinjam) DITOLAK: stok, rincian, status, dan riwayat tidak berubah."""
        token = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000701',
            'id_anggota': 'Active User Protected',
            'tipe_user': 'Siswa',
            'kelas': 'X',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        header = conn.execute("SELECT id, status, total_denda FROM peminjaman WHERE id_anggota = 'Active User Protected'").fetchone()
        self.assertIsNotNone(header)
        h_id = header['id']
        self.assertEqual(header['status'], 'Dipinjam')

        b7_before = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 7").fetchone()
        details_before = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ?", (h_id,)).fetchall()
        self.assertEqual(len(details_before), 1)
        conn.close()

        # Coba hapus transaksi yang masih aktif -> HARUS DITOLAK
        del_resp = self.client.post(f'/hapus_peminjaman/{h_id}', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        conn = self._get_db()
        # Header transaksi MASIH ADA dan status tetap 'Dipinjam'
        h_after = conn.execute("SELECT id, status, total_denda FROM peminjaman WHERE id = ?", (h_id,)).fetchone()
        self.assertIsNotNone(h_after)
        self.assertEqual(h_after['status'], 'Dipinjam')
        self.assertEqual(h_after['total_denda'], header['total_denda'])

        # Rincian detail item MASIH ADA
        details_after = conn.execute("SELECT * FROM peminjaman_detail WHERE id_peminjaman = ?", (h_id,)).fetchall()
        self.assertEqual(len(details_after), 1)
        self.assertEqual(details_after[0]['status'], 'Dipinjam')

        # Stok dan nomor registrasi buku TIDAK BERUBAH
        b7_after = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 7").fetchone()
        self.assertEqual(b7_before['stok'], b7_after['stok'])
        self.assertEqual(b7_before['id_buku_fisik'], b7_after['id_buku_fisik'])
        conn.close()

    def test_13_partial_loan_deletion_rejected_preserves_state(self):
        """Penghapusan transaksi sebagian (Sebagian) DITOLAK: stok dan rincian tetap terlindungi."""
        token = self._login_admin()
        # Pinjam 2 buku (Buku 4: 00000401 dan 00000402)
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00000401, 00000402',
            'id_anggota': 'Partial User Protected',
            'tipe_user': 'Siswa',
            'kelas': 'XI',
            'jurusan': 'TKJ',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        header = conn.execute("SELECT id FROM peminjaman WHERE id_anggota = 'Partial User Protected'").fetchone()
        h_id = header['id']
        items = conn.execute("SELECT id FROM peminjaman_detail WHERE id_peminjaman = ? ORDER BY id ASC", (h_id,)).fetchall()
        conn.close()

        # Kembalikan 1 buku -> status transaksi menjadi 'Sebagian'
        self.client.post(f'/kembalikan_item/{items[0]["id"]}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)

        conn = self._get_db()
        h_part = conn.execute("SELECT status FROM peminjaman WHERE id = ?", (h_id,)).fetchone()
        self.assertEqual(h_part['status'], 'Sebagian')

        b4_before = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 4").fetchone()
        conn.close()

        # Coba hapus transaksi Sebagian -> HARUS DITOLAK
        del_resp = self.client.post(f'/hapus_peminjaman/{h_id}', data={'csrf_token': token}, follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        conn = self._get_db()
        h_after = conn.execute("SELECT status FROM peminjaman WHERE id = ?", (h_id,)).fetchone()
        self.assertIsNotNone(h_after)
        self.assertEqual(h_after['status'], 'Sebagian')

        details_after = conn.execute("SELECT status FROM peminjaman_detail WHERE id_peminjaman = ?", (h_id,)).fetchall()
        self.assertEqual(len(details_after), 2)
        statuses = [d['status'] for d in details_after]
        self.assertIn('Kembali', statuses)
        self.assertIn('Dipinjam', statuses)

        b4_after = conn.execute("SELECT stok, id_buku_fisik FROM buku WHERE id = 4").fetchone()
        self.assertEqual(b4_before['stok'], b4_after['stok'])
        conn.close()

    def test_14_excel_import_multiple_books_without_reg_no_conflict(self):
        """Impor Excel dengan beberapa buku tanpa nomor registrasi tidak bentrok dengan UNIQUE constraint."""
        token = self._login_admin()

        # Buat file excel in-memory dengan 2 buku tanpa reg dan 1 buku dengan reg
        excel_data = [
            {
                'judul': 'Buku Uji Tanpa Reg 1',
                'penulis': 'Penulis A',
                'penerbit': 'Penerbit A',
                'tahun_terbit': '2025',
                'isbn': '978-001',
                'kategori': 'Teknologi',
                'sinopsis': 'Sinopsis 1',
                'lokasi_rak': 'R1',
                'sumber_perolehan': 'Pembelian',
                'tanggal_masuk': '2026-01-01',
                'kondisi_buku': 'Baik',
                'harga_buku': '50000',
                'no_registrasi_list': ''
            },
            {
                'judul': 'Buku Uji Tanpa Reg 2',
                'penulis': 'Penulis B',
                'penerbit': 'Penerbit B',
                'tahun_terbit': '2025',
                'isbn': '978-002',
                'kategori': 'Teknologi',
                'sinopsis': 'Sinopsis 2',
                'lokasi_rak': 'R1',
                'sumber_perolehan': 'Pembelian',
                'tanggal_masuk': '2026-01-01',
                'kondisi_buku': 'Baik',
                'harga_buku': '60000',
                'no_registrasi_list': ''
            },
            {
                'judul': 'Buku Uji Dengan Reg',
                'penulis': 'Penulis C',
                'penerbit': 'Penerbit C',
                'tahun_terbit': '2025',
                'isbn': '978-003',
                'kategori': 'Sains',
                'sinopsis': 'Sinopsis 3',
                'lokasi_rak': 'R2',
                'sumber_perolehan': 'Hadiah',
                'tanggal_masuk': '2026-01-01',
                'kondisi_buku': 'Baik',
                'harga_buku': '75000',
                'no_registrasi_list': '88880101, 88880102'
            }
        ]

        df = pd.DataFrame(excel_data)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)

        resp = self.client.post('/import_excel', data={
            'csrf_token': token,
            'excel_file': (buf, 'test_books.xlsx')
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        conn = self._get_db()
        # Verifikasi buku tanpa reg tersimpan dengan id_buku_fisik NULL
        b1 = conn.execute("SELECT * FROM buku WHERE judul = 'Buku Uji Tanpa Reg 1'").fetchone()
        b2 = conn.execute("SELECT * FROM buku WHERE judul = 'Buku Uji Tanpa Reg 2'").fetchone()
        self.assertIsNotNone(b1)
        self.assertIsNotNone(b2)
        self.assertIsNone(b1['id_buku_fisik'])
        self.assertIsNone(b2['id_buku_fisik'])
        self.assertEqual(b1['stok'], 1)
        self.assertEqual(b2['stok'], 1)

        # Verifikasi buku dengan reg tersimpan dengan JSON reg list
        b3 = conn.execute("SELECT * FROM buku WHERE judul = 'Buku Uji Dengan Reg'").fetchone()
        self.assertIsNotNone(b3)
        self.assertIsNotNone(b3['id_buku_fisik'])
        regs = json.loads(b3['id_buku_fisik'])
        self.assertEqual(regs, ['88880101', '88880102'])
        self.assertEqual(b3['stok'], 2)
        conn.close()

    def test_15_lost_book_sets_header_status_menunggu_penggantian(self):
        """Ketika buku dikembalikan dengan status 'Hilang', header berstatus 'Menunggu Penggantian' (bukan Selesai)."""
        token = self._login_admin()
        # Pinjam 2 buku (Buku 11: 00001101 dan 00001102)
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': token,
            'no_registrasi': '00001101, 00001102',
            'id_anggota': 'Siswa Buku Hilang',
            'tipe_user': 'Siswa',
            'kelas': 'X',
            'jurusan': 'RPL',
            'durasi_pinjam': '7'
        }, follow_redirects=True)

        conn = self._get_db()
        header = conn.execute("SELECT id FROM peminjaman WHERE id_anggota = 'Siswa Buku Hilang'").fetchone()
        self.assertIsNotNone(header)
        h_id = header['id']
        items = conn.execute("SELECT id FROM peminjaman_detail WHERE id_peminjaman = ? ORDER BY id ASC", (h_id,)).fetchall()
        self.assertEqual(len(items), 2)
        conn.close()

        # Item 1 dikembalikan normal
        self.client.post(f'/kembalikan_item/{items[0]["id"]}', data={
            'csrf_token': token,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)

        # Item 2 dilaporkan Hilang
        self.client.post(f'/kembalikan_item/{items[1]["id"]}', data={
            'csrf_token': token,
            'status_kembali': 'Hilang'
        }, follow_redirects=True)

        conn = self._get_db()
        h_res = conn.execute("SELECT status, total_denda FROM peminjaman WHERE id = ?", (h_id,)).fetchone()
        # Status header HARUS 'Menunggu Penggantian', TIDAK BOLEH 'Selesai' karena penggantian belum tuntas
        self.assertEqual(h_res['status'], 'Menunggu Penggantian')
        self.assertGreater(h_res['total_denda'], 0)

        d1 = conn.execute("SELECT status, status_penggantian FROM peminjaman_detail WHERE id = ?", (items[0]['id'],)).fetchone()
        d2 = conn.execute("SELECT status, status_penggantian FROM peminjaman_detail WHERE id = ?", (items[1]['id'],)).fetchone()
        self.assertEqual(d1['status'], 'Kembali')
        self.assertEqual(d2['status'], 'Hilang')
        self.assertEqual(d2['status_penggantian'], 'Menunggu Penggantian')
        conn.close()


if __name__ == '__main__':
    unittest.main()
