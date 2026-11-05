# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-01: Verifikasi Autentikasi Admin, Rate Limit Login,
Cookie Flags, CSRF per POST, Session Lifetime, Idle Timeout, dan Logout.
Sistem Perpustakaan Digital Sekolah.
"""
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
from policy import ADMIN_SESSION_LIFETIME_HOURS, ADMIN_IDLE_TIMEOUT_MINUTES


class BaseAdminAuthTestCase(unittest.TestCase):
    """Base setup dengan database terisolasi dan client Flask yang bersih."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_auth.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema database uji
        library_app.init_db(self.test_db)
        self._seed_sample_book()

        # Bersihkan rate limiter
        with library_app._LOGIN_RATE_LIMIT_LOCK:
            library_app._LOGIN_ATTEMPTS.clear()

    def tearDown(self):
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        with library_app._LOGIN_RATE_LIMIT_LOCK:
            library_app._LOGIN_ATTEMPTS.clear()

    def _seed_sample_book(self):
        conn = library_app.get_db_connection()
        try:
            # Pastikan tabel peminjaman memiliki id_buku untuk kompatibilitas route detail_buku legacy
            try:
                conn.execute("ALTER TABLE peminjaman ADD COLUMN id_buku INTEGER")
            except Exception:
                pass

            conn.execute('''
                INSERT INTO buku (id, judul, penulis, stok, id_buku_fisik)
                VALUES (1, 'Laskar Pelangi', 'Andrea Hirata', 3, '["00000101", "00000102", "00000103"]')
            ''')
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _login_admin(self):
        """Helper untuk menyimulasikan sesi admin terautentikasi penuh dengan CSRF token."""
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = library_app.ADMIN_USERNAME
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-301'
        return 'test-valid-csrf-token-301'

    def _get_csrf_token(self):
        """Helper untuk mendapatkan token CSRF dari session tanpa login admin."""
        with self.client.session_transaction() as sess:
            if '_csrf_token' not in sess:
                sess['_csrf_token'] = 'test-anon-csrf-token'
            return sess['_csrf_token']


class AdminRouteRejectionTests(BaseAdminAuthTestCase):
    """
    Memverifikasi bahwa setiap route admin MENOLAK akses tanpa login (Task 3-01 AC 1).
    Memastikan tidak ada perubahan database saat request ditolak.
    """

    def test_01_unauth_add_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/add', data={'judul': 'Buku Ilegal', 'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))
        # Verifikasi database tidak berubah
        conn = library_app.get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM buku WHERE judul = 'Buku Ilegal'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_02_unauth_edit_get_rejected(self):
        res = self.client.get('/edit/1', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_03_unauth_edit_post_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/edit/1', data={'judul': 'Judul Diubah Tanpa Izin', 'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))
        # Verifikasi judul tidak berubah di DB
        conn = library_app.get_db_connection()
        judul = conn.execute("SELECT judul FROM buku WHERE id = 1").fetchone()[0]
        conn.close()
        self.assertEqual(judul, 'Laskar Pelangi')

    def test_04_unauth_delete_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/delete/1', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))
        # Verifikasi buku tetap ada di DB
        conn = library_app.get_db_connection()
        buku = conn.execute("SELECT id FROM buku WHERE id = 1").fetchone()
        conn.close()
        self.assertIsNotNone(buku)

    def test_05_unauth_reset_katalog_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/reset_katalog_buku', data={'konfirmasi': 'KOSONGKAN', 'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))
        # Verifikasi katalog tidak dikosongkan
        conn = library_app.get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM buku").fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    def test_06_unauth_upload_cover_rejected(self):
        token = self._get_csrf_token()
        data = {
            'csrf_token': token,
            'cover_file': (io.BytesIO(b'\x89PNG\r\n\x1a\nfake'), 'test.png')
        }
        res = self.client.post('/buku/1/upload_cover', data=data, content_type='multipart/form-data', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_07_unauth_peminjaman_dashboard_rejected(self):
        res = self.client.get('/peminjaman', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_08_unauth_proses_pinjam_admin_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/proses_pinjam_admin', data={'id_anggota': 'M-TEST', 'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_09_unauth_kembalikan_item_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/kembalikan_item/1', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_10_unauth_kembalikan_batch_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/kembalikan/1', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_11_unauth_perpanjang_item_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/perpanjang_item/1', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_12_unauth_lunasi_denda_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/lunasi_denda/1', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_13_unauth_hapus_peminjaman_rejected(self):
        token = self._get_csrf_token()
        res = self.client.post('/hapus_peminjaman/1', data={'csrf_token': token}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_14_unauth_api_riwayat_buku_returns_401_json(self):
        res = self.client.get('/api/riwayat_buku/1', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get('error'), 'Unauthorized')

    def test_15_unauth_export_peminjaman_rejected(self):
        res = self.client.get('/export_peminjaman', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_16_unauth_import_excel_rejected(self):
        token = self._get_csrf_token()
        data = {
            'csrf_token': token,
            'excel_file': (io.BytesIO(b'fake excel content'), 'test.xlsx')
        }
        res = self.client.post('/import_excel', data=data, content_type='multipart/form-data', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_public_routes_remain_accessible_without_login(self):
        """Memastikan route publik tetap dapat diakses bebas tanpa login."""
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/koleksi').status_code, 200)
        self.assertEqual(self.client.get('/buku/1').status_code, 200)
        self.assertEqual(self.client.get('/search?query=laskar').status_code, 302)
        self.assertEqual(self.client.get('/api/search_suggestions?q=laskar').status_code, 200)
        self.assertEqual(self.client.get('/login').status_code, 200)


class AdminCSRFProtectionTests(BaseAdminAuthTestCase):
    """
    Memverifikasi penolakan CSRF (missing token dan invalid token) pada seluruh
    route POST yang memutasi state sebelum operasi dijalankan (Task 3-01 AC 4).
    """

    def test_csrf_missing_rejected_on_all_post_routes(self):
        """Setiap route POST mutasi harus menolak HTTP 400 jika token CSRF hilang."""
        self._login_admin()

        post_routes = [
            ('/add', {'judul': 'Buku Baru'}),
            ('/edit/1', {'judul': 'Edit Buku'}),
            ('/delete/1', {}),
            ('/reset_katalog_buku', {'konfirmasi': 'KOSONGKAN'}),
            ('/proses_pinjam_admin', {'id_anggota': 'M-01'}),
            ('/kembalikan_item/1', {'status_kembali': 'Kembali'}),
            ('/kembalikan/1', {'status_kembali': 'Kembali'}),
            ('/perpanjang_item/1', {}),
            ('/lunasi_denda/1', {}),
            ('/hapus_peminjaman/1', {}),
        ]

        for route, payload in post_routes:
            with self.subTest(route=route):
                res = self.client.post(route, data=payload)
                self.assertEqual(res.status_code, 400, f"Route {route} tidak menolak missing CSRF!")

    def test_csrf_invalid_rejected_on_all_post_routes(self):
        """Setiap route POST mutasi harus menolak HTTP 400 jika token CSRF palsu/salah."""
        self._login_admin()

        post_routes = [
            ('/add', {'judul': 'Buku Baru', 'csrf_token': 'fake-forged-token'}),
            ('/edit/1', {'judul': 'Edit Buku', 'csrf_token': 'fake-forged-token'}),
            ('/delete/1', {'csrf_token': 'fake-forged-token'}),
            ('/reset_katalog_buku', {'konfirmasi': 'KOSONGKAN', 'csrf_token': 'fake-forged-token'}),
            ('/proses_pinjam_admin', {'id_anggota': 'M-01', 'csrf_token': 'fake-forged-token'}),
            ('/kembalikan_item/1', {'status_kembali': 'Kembali', 'csrf_token': 'fake-forged-token'}),
            ('/kembalikan/1', {'status_kembali': 'Kembali', 'csrf_token': 'fake-forged-token'}),
            ('/perpanjang_item/1', {'csrf_token': 'fake-forged-token'}),
            ('/lunasi_denda/1', {'csrf_token': 'fake-forged-token'}),
            ('/hapus_peminjaman/1', {'csrf_token': 'fake-forged-token'}),
        ]

        for route, payload in post_routes:
            with self.subTest(route=route):
                res = self.client.post(route, data=payload)
                self.assertEqual(res.status_code, 400, f"Route {route} tidak menolak invalid CSRF!")

    def test_csrf_missing_and_invalid_on_multipart_uploads(self):
        """Memverifikasi penolakan CSRF pada route multipart/form-data upload."""
        self._login_admin()

        # 1. upload_cover tanpa CSRF
        res1 = self.client.post(
            '/buku/1/upload_cover',
            data={'cover_file': (io.BytesIO(b'fake'), 'test.png')},
            content_type='multipart/form-data'
        )
        self.assertEqual(res1.status_code, 400)

        # 2. upload_cover dengan CSRF palsu
        res2 = self.client.post(
            '/buku/1/upload_cover',
            data={'cover_file': (io.BytesIO(b'fake'), 'test.png'), 'csrf_token': 'fake'},
            content_type='multipart/form-data'
        )
        self.assertEqual(res2.status_code, 400)

        # 3. import_excel tanpa CSRF
        res3 = self.client.post(
            '/import_excel',
            data={'excel_file': (io.BytesIO(b'fake'), 'test.xlsx')},
            content_type='multipart/form-data'
        )
        self.assertEqual(res3.status_code, 400)

    def test_csrf_missing_and_invalid_on_login_post(self):
        """Memverifikasi bahwa POST /login juga terlindungi dari serangan CSRF."""
        # Missing CSRF pada login
        res1 = self.client.post('/login', data={'username': 'admin', 'password': '123'})
        self.assertEqual(res1.status_code, 400)

        # Invalid CSRF pada login
        res2 = self.client.post('/login', data={'username': 'admin', 'password': '123', 'csrf_token': 'palsu'})
        self.assertEqual(res2.status_code, 400)


class AdminSessionLifecycleTests(BaseAdminAuthTestCase):
    """
    Memverifikasi Session Lifetime absolut 8 jam, Idle Timeout 120 menit,
    dan sanitasi pembersihan sesi pada logout (Task 3-01 AC 5).
    """

    def test_01_session_lifetime_and_cookie_configuration(self):
        """Memastikan PERMANENT_SESSION_LIFETIME terpasang 8 jam dan cookie path = '/'."""
        self.assertEqual(library_app.app.config.get('PERMANENT_SESSION_LIFETIME'), timedelta(hours=8))
        self.assertEqual(library_app.app.config.get('SESSION_COOKIE_PATH'), '/')
        self.assertTrue(library_app.app.config.get('SESSION_COOKIE_HTTPONLY'))
        self.assertEqual(library_app.app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax')

    def test_02_successful_login_initializes_permanent_and_last_active(self):
        """Login sukses menandai sesi permanent dan menginisialisasi last_active."""
        token = self._get_csrf_token()
        res = self.client.post('/login', data={
            'username': library_app.ADMIN_USERNAME,
            'password': '123',
            'csrf_token': token
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        with self.client.session_transaction() as sess:
            self.assertTrue(sess.permanent)
            self.assertTrue(sess.get('logged_in'))
            self.assertIsNotNone(sess.get('last_active'))
            self.assertAlmostEqual(sess.get('last_active'), time.time(), delta=5.0)

    def test_03_idle_timeout_allows_active_session_and_updates_timestamp(self):
        """Sesi admin yang aktif dalam rentang < 120 menit tetap diizinkan dan memperbarui last_active."""
        self._login_admin()
        # Setel last_active 10 menit yang lalu
        past_time = time.time() - 600
        with self.client.session_transaction() as sess:
            sess['last_active'] = past_time

        res = self.client.get('/peminjaman', follow_redirects=False)
        self.assertEqual(res.status_code, 200)

        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get('logged_in'))
            # Memastikan timestamp diperbarui ke waktu sekarang
            self.assertGreater(sess.get('last_active'), past_time)

    def test_04_idle_timeout_exceeded_clears_session_and_redirects(self):
        """Sesi admin yang tidak aktif > 120 menit dibersihkan dan dialihkan ke login."""
        self._login_admin()
        # Setel last_active 121 menit yang lalu (melebihi batas 120 menit)
        expired_time = time.time() - (121 * 60)
        with self.client.session_transaction() as sess:
            sess['last_active'] = expired_time

        res = self.client.get('/peminjaman', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

        # Verifikasi data otentikasi telah dibersihkan
        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get('logged_in', False))
            self.assertNotIn('last_active', sess)

        # Verifikasi akses berikutnya ditolak
        res_next = self.client.get('/peminjaman', follow_redirects=False)
        self.assertEqual(res_next.status_code, 302)
        self.assertIn('/login', res_next.headers.get('Location', ''))

    def test_05_logout_clears_entire_session(self):
        """Memverifikasi bahwa logout membersihkan data autentikasi dan atribut custom (session.clear)."""
        self._login_admin()
        with self.client.session_transaction() as sess:
            sess['custom_attr'] = 'some_data'

        res = self.client.get('/logout', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/', res.headers.get('Location', ''))

        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get('logged_in', False))
            self.assertNotIn('admin_username', sess)
            self.assertNotIn('custom_attr', sess)
            self.assertNotIn('last_active', sess)

        # Akses setelah logout harus ditolak
        res_after = self.client.get('/peminjaman', follow_redirects=False)
        self.assertEqual(res_after.status_code, 302)
        self.assertIn('/login', res_after.headers.get('Location', ''))

    def test_06_fail_closed_in_production_mode_when_last_active_missing(self):
        """Memastikan di mode produksi (bukan TESTING), sesi tanpa last_active ditolak fail-closed."""
        old_testing = library_app.app.config.get('TESTING')
        try:
            library_app.app.config['TESTING'] = False
            with self.client.session_transaction() as sess:
                sess['logged_in'] = True
                sess.pop('last_active', None)

            res = self.client.get('/peminjaman', follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertIn('/login', res.headers.get('Location', ''))
        finally:
            library_app.app.config['TESTING'] = old_testing


if __name__ == '__main__':
    unittest.main()

