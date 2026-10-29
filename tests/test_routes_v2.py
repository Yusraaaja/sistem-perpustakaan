# -*- coding: utf-8 -*-
"""
Integration Tests untuk Sub-Fase 2C: Staging dan Integrasi Route Schema v2.
Menguji integrasi route inti Flask terhadap database staging v2 yang terisolasi.
Memenuhi DEC-005, DEC-006, DEC-007, DEC-020, DEC-024, P2-01, P2-02, R2, R8, R9, R12.
"""
import os
import sys
import sqlite3
import unittest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
import timeutil
from repositories import catalog_repo, copy_repo, member_repo, loan_repo

TEST_STAGING_DB = os.path.join(ROOT, 'backups', 'test_v2_staging.db')
SCHEMA_V2_SQL = os.path.join(ROOT, 'migrations', '0001_initial_v2_schema.sql')


class SchemaV2RouteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(os.path.join(ROOT, 'backups'), exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if 'DATABASE_NAME' in os.environ:
            del os.environ['DATABASE_NAME']

    def setUp(self):
        self.db_path = os.path.join(ROOT, 'backups', f"staging_{self._testMethodName}.db")
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        with open(SCHEMA_V2_SQL, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.close()

        self._seed_staging_data()
        os.environ['DATABASE_NAME'] = self.db_path

        library_app.app.config['TESTING'] = True
        library_app.app.config['WTF_CSRF_ENABLED'] = False
        self.client = library_app.app.test_client()

    def tearDown(self):
        if 'DATABASE_NAME' in os.environ:
            del os.environ['DATABASE_NAME']
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['admin_username'] = 'admin_tester'
            sess['_csrf_token'] = 'csrf-test-token-v2'
        return 'csrf-test-token-v2'

    def _get_staging_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _seed_staging_data(self):
        conn = self._get_staging_db()
        try:
            # 0. Schema version
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, name, applied_at) VALUES (2, '0001_initial_v2_schema', ?);",
                (timeutil.format_iso_utc(timeutil.now_utc()),)
            )

            # 1. Kategori Anggota
            member_repo.create_category(conn, 'MC-SISWA', 'Siswa', 'Kategori Murid')
            member_repo.create_category(conn, 'MC-GURU', 'Guru', 'Kategori Pendidik')

            # 2. Anggota
            member_repo.create_member(conn, {
                'id': 'MB-TEST-01',
                'nama': 'Ahmad Fauzi',
                'category_id': 'MC-SISWA',
                'status': 'aktif'
            })
            member_repo.create_member(conn, {
                'id': 'MB-TEST-INACTIVE',
                'nama': 'Doni Nonaktif',
                'category_id': 'MC-SISWA',
                'status': 'nonaktif'
            })

            # 3. Judul Katalog
            catalog_repo.create_title(conn, {
                'id': 'BK-TEST-01',
                'judul': 'Laskar Pelangi',
                'penulis': 'Andrea Hirata',
                'isbn': '978-979-3062-79-2',
                'kategori': 'Fiksi'
            })
            catalog_repo.create_title(conn, {
                'id': 'BK-TEST-02',
                'judul': 'Bumi Manusia',
                'penulis': 'Pramoedya Ananta Toer',
                'isbn': '978-979-973-123-0',
                'kategori': 'Sastra'
            })

            # 4. Eksemplar Fisik
            copy_repo.create_copy(conn, {
                'id': 'CP-LP-01',
                'title_id': 'BK-TEST-01',
                'call_number': 'LP-001',
                'status': 'aktif',
                'lokasi_rak': 'Rak A1'
            })
            copy_repo.create_copy(conn, {
                'id': 'CP-LP-02',
                'title_id': 'BK-TEST-01',
                'call_number': 'LP-002',
                'status': 'aktif',
                'lokasi_rak': 'Rak A1'
            })
            copy_repo.create_copy(conn, {
                'id': 'CP-BM-01',
                'title_id': 'BK-TEST-02',
                'call_number': 'BM-001',
                'status': 'aktif',
                'lokasi_rak': 'Rak B2'
            })
            copy_repo.create_copy(conn, {
                'id': 'CP-BM-02',
                'title_id': 'BK-TEST-02',
                'call_number': 'BM-002',
                'status': 'nonaktif',
                'lokasi_rak': 'Gudang'
            })

            # 5. Legacy copy map untuk pengujian backward-compatibility registrasi lama
            copy_repo.map_legacy_copy(conn, old_ref='00001001', copy_id='CP-LP-01')

            conn.commit()
        finally:
            conn.close()

    def test_01_get_peminjaman_route_renders_successfully(self):
        """Memastikan route GET /peminjaman dapat diakses dan merender template tanpa error 500."""
        self._login_admin()
        resp = self.client.get('/peminjaman')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Peminjaman', resp.data)

    def test_02_borrow_multi_item_success(self):
        """Peminjaman multi-eksemplar berhasil secara atomik dan memperbarui status ketersediaan."""
        csrf = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['LP-001', 'CP-LP-02'],
            'durasi_pinjam': 7
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'berhasil dibuat untuk 2 buku', resp.data)

        # Verifikasi di database staging
        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            self.assertEqual(len(loans), 1)
            loan_id = loans[0]['id']

            items = loan_repo.get_loan_items(conn, loan_id)
            self.assertEqual(len(items), 2)
            for it in items:
                self.assertIsNone(it['returned_at'])

            # Cek availability di view
            avail_lp1 = copy_repo.get_copy_availability(conn, copy_id='CP-LP-01')[0]
            avail_lp2 = copy_repo.get_copy_availability(conn, copy_id='CP-LP-02')[0]
            self.assertEqual(avail_lp1['availability_status'], 'dipinjam')
            self.assertEqual(avail_lp2['availability_status'], 'dipinjam')

            # Cek audit log
            logs = conn.execute("SELECT * FROM audit_log WHERE object_id = ?;", (loan_id,)).fetchall()
            self.assertTrue(len(logs) >= 1)
            self.assertEqual(logs[0]['action'], 'LOAN_CREATE')
        finally:
            conn.close()

    def test_03_borrow_with_legacy_registration_number(self):
        """Peminjaman menggunakan nomor registrasi legacy melalui legacy_copy_map."""
        csrf = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'Ahmad Fauzi',  # Lookup via nama
            'no_registrasi': ['00001001'], # Mapped ke CP-LP-01
            'durasi_pinjam': 7
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'berhasil dibuat untuk 1 buku', resp.data)

        conn = self._get_staging_db()
        try:
            avail = copy_repo.get_copy_availability(conn, copy_id='CP-LP-01')[0]
            self.assertEqual(avail['availability_status'], 'dipinjam')
        finally:
            conn.close()

    def test_04_borrow_inactive_member_rejected(self):
        """DEC-020: Anggota nonaktif ditolak saat mengajukan peminjaman buku."""
        csrf = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-INACTIVE',
            'no_registrasi': ['BM-001'],
            'durasi_pinjam': 7
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'nonaktif', resp.data)

        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            self.assertEqual(len(loans), 0)
        finally:
            conn.close()

    def test_05_borrow_unavailable_copy_atomic_rollback(self):
        """Jika salah satu eksemplar tidak tersedia/nonaktif, seluruh transaksi dibatalkan (atomik)."""
        csrf = self._login_admin()
        resp = self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['BM-001', 'CP-BM-02'], # CP-BM-02 berstatus nonaktif
            'durasi_pinjam': 7
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'dibatalkan', resp.data)

        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            self.assertEqual(len(loans), 0)
            # BM-001 tetap tersedia
            avail = copy_repo.get_copy_availability(conn, copy_id='CP-BM-01')[0]
            self.assertEqual(avail['availability_status'], 'tersedia')
        finally:
            conn.close()

    def test_06_return_single_item_partial(self):
        """DEC-007: Pengembalian parsial satu item berhasil dan membebaskan eksemplar fisik."""
        csrf = self._login_admin()
        # Pinjam 2 item terlebih dahulu
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['LP-001', 'CP-LP-02'],
            'durasi_pinjam': 7
        })

        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            loan_id = loans[0]['id']
            items = loan_repo.get_loan_items(conn, loan_id)
            item_to_return = items[0]
            item_to_keep = items[1]
        finally:
            conn.close()

        # Kembalikan item pertama
        resp = self.client.post(f'/kembalikan_item/{item_to_return["id"]}', data={
            'csrf_token': csrf,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'berhasil diproses', resp.data)

        conn = self._get_staging_db()
        try:
            # Item 1 kembali, Item 2 masih dipinjam
            ret_item = loan_repo.get_loan_item_by_id(conn, item_to_return['id'])
            keep_item = loan_repo.get_loan_item_by_id(conn, item_to_keep['id'])
            self.assertIsNotNone(ret_item['returned_at'])
            self.assertIsNone(keep_item['returned_at'])

            # Eksemplar 1 kembali tersedia
            avail1 = copy_repo.get_copy_availability(conn, copy_id=item_to_return['copy_id'])[0]
            self.assertEqual(avail1['availability_status'], 'tersedia')

            # Eksemplar 2 tetap dipinjam
            avail2 = copy_repo.get_copy_availability(conn, copy_id=item_to_keep['copy_id'])[0]
            self.assertEqual(avail2['availability_status'], 'dipinjam')
        finally:
            conn.close()

    def test_07_extend_loan_item_once_and_limit_second_attempt(self):
        """DEC-005: Perpanjangan masa pinjam berhasil 1 kali (+7 hari) dan ditolak pada upaya kedua."""
        csrf = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['BM-001'],
            'durasi_pinjam': 7
        })

        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            item_id = loan_repo.get_loan_items(conn, loans[0]['id'])[0]['id']
            old_item = loan_repo.get_loan_item_by_id(conn, item_id)
            old_due = old_item['due_at']
        finally:
            conn.close()

        # Perpanjangan pertama: SUKSES
        resp1 = self.client.post(f'/perpanjang_item/{item_id}', data={
            'csrf_token': csrf
        }, follow_redirects=True)

        self.assertEqual(resp1.status_code, 200)
        self.assertIn(b'berhasil diperpanjang 7 hari', resp1.data)

        conn = self._get_staging_db()
        try:
            ext_item = loan_repo.get_loan_item_by_id(conn, item_id)
            self.assertEqual(ext_item['extension_count'], 1)
            # Jatuh tempo baru lebih lama dari jatuh tempo lama
            self.assertGreater(ext_item['due_at'], old_due)
        finally:
            conn.close()

        # Perpanjangan kedua: DITOLAK (DEC-005 batas 1x)
        resp2 = self.client.post(f'/perpanjang_item/{item_id}', data={
            'csrf_token': csrf
        }, follow_redirects=True)

        self.assertEqual(resp2.status_code, 200)
        self.assertIn(b'Batas perpanjangan maksimal 1 kali', resp2.data)

        conn = self._get_staging_db()
        try:
            final_item = loan_repo.get_loan_item_by_id(conn, item_id)
            self.assertEqual(final_item['extension_count'], 1)
        finally:
            conn.close()

    def test_08_resolve_lost_or_damaged_without_cash_fines(self):
        """DEC-024: Penyelesaian buku hilang/rusak tidak membebankan denda uang melainkan penggantian fisik."""
        csrf = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['BM-001'],
            'durasi_pinjam': 7
        })

        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            item_id = loan_repo.get_loan_items(conn, loans[0]['id'])[0]['id']
        finally:
            conn.close()

        resp = self.client.post(f'/kembalikan_item/{item_id}', data={
            'csrf_token': csrf,
            'status_kembali': 'Hilang',
            'replacement_type': 'Kamus Bahasa Arab',
            'notes': 'Hilang saat kegiatan kemah pramuka'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'kewajiban penggantian fisik', resp.data)

        conn = self._get_staging_db()
        try:
            item = loan_repo.get_loan_item_by_id(conn, item_id)
            self.assertEqual(item['return_condition'], 'hilang')
            self.assertIsNotNone(item['returned_at'])

            # Eksemplar tercatat hilang
            copy_obj = copy_repo.get_copy_by_id(conn, 'CP-BM-01')
            self.assertEqual(copy_obj['status'], 'hilang')

            # Periksa legacy extra: denda = 0, status penggantian selesai
            extra = conn.execute("SELECT * FROM legacy_loan_item_extra WHERE loan_item_id = ?;", (item_id,)).fetchone()
            self.assertIsNotNone(extra)
            self.assertEqual(extra['fine_overdue'], 0)
            self.assertEqual(extra['fine_condition'], 0)
            self.assertEqual(extra['status_penggantian'], 'selesai')
        finally:
            conn.close()

    def test_09_batch_return_all_items(self):
        """Pengembalian seluruh item transaksi sekaligus via route /kembalikan/<pinjam_id>."""
        csrf = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['LP-001', 'CP-LP-02'],
            'durasi_pinjam': 7
        })

        conn = self._get_staging_db()
        try:
            loans = loan_repo.list_loans(conn)
            loan_id = loans[0]['id']
        finally:
            conn.close()

        resp = self.client.post(f'/kembalikan/{loan_id}', data={
            'csrf_token': csrf,
            'status_kembali': 'Kembali'
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Berhasil memproses pengembalian seluruh buku (2 item)', resp.data)

        conn = self._get_staging_db()
        try:
            items = loan_repo.get_loan_items(conn, loan_id)
            for it in items:
                self.assertIsNotNone(it['returned_at'])
            avail1 = copy_repo.get_copy_availability(conn, copy_id='CP-LP-01')[0]
            avail2 = copy_repo.get_copy_availability(conn, copy_id='CP-LP-02')[0]
            self.assertEqual(avail1['availability_status'], 'tersedia')
            self.assertEqual(avail2['availability_status'], 'tersedia')
        finally:
            conn.close()

    def test_10_deactivate_copy_via_delete_route_without_history_deletion(self):
        """P2-02: Route /delete/<id> menonaktifkan status eksemplar tanpa DELETE SQL fisik."""
        csrf = self._login_admin()
        resp = self.client.post('/delete/CP-BM-01', data={'csrf_token': csrf}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'berhasil dinonaktifkan tanpa menghapus riwayat', resp.data)

        conn = self._get_staging_db()
        try:
            # Pastikan row masih ada di database
            copy_obj = copy_repo.get_copy_by_id(conn, 'CP-BM-01')
            self.assertIsNotNone(copy_obj)
            self.assertEqual(copy_obj['status'], 'nonaktif')
        finally:
            conn.close()

    def test_11_deactivate_actively_borrowed_copy_rejected(self):
        """Eksemplar yang sedang dipinjam aktif ditolak saat akan dinonaktifkan."""
        csrf = self._login_admin()
        self.client.post('/proses_pinjam_admin', data={
            'csrf_token': csrf,
            'id_anggota': 'MB-TEST-01',
            'no_registrasi': ['BM-001'],
            'durasi_pinjam': 7
        })

        resp = self.client.post('/delete/CP-BM-01', data={'csrf_token': csrf}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'sedang dipinjam', resp.data)

        conn = self._get_staging_db()
        try:
            copy_obj = copy_repo.get_copy_by_id(conn, 'CP-BM-01')
            self.assertEqual(copy_obj['status'], 'aktif')
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
