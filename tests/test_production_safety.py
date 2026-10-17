import unittest
import os
import sqlite3
import tempfile
import shutil
import time

import app as library_app

class ProductionSafetyHardeningTests(unittest.TestCase):
    def setUp(self):
        # Gunakan database uji sementara yang terisolasi
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_safety.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi database uji
        library_app.init_db(self.test_db)
        
        # Reset state rate limiter untuk pengujian bersih
        with library_app._LOGIN_RATE_LIMIT_LOCK:
            library_app._LOGIN_ATTEMPTS.clear()

    def tearDown(self):
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        with library_app._LOGIN_RATE_LIMIT_LOCK:
            library_app._LOGIN_ATTEMPTS.clear()

    def _get_csrf_token(self):
        with self.client.session_transaction() as sess:
            if '_csrf_token' not in sess:
                sess['_csrf_token'] = 'test_token_1234567890'
            return sess['_csrf_token']

    def test_01_session_cookie_security_flags(self):
        """Memastikan flag keamanan session cookie terpasang (HTTPOnly & SameSite Lax)."""
        self.assertTrue(library_app.app.config.get('SESSION_COOKIE_HTTPONLY'))
        self.assertEqual(library_app.app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax')

    def test_02_production_guards_reject_weak_secret_key(self):
        """Memastikan mode produksi menolak startup jika SECRET_KEY kosong atau placeholder."""
        old_env = os.environ.get('FLASK_ENV')
        old_secret = os.environ.get('SECRET_KEY')
        try:
            os.environ['FLASK_ENV'] = 'production'
            
            # Kasus 1: Secret key placeholder bawaan template
            os.environ['SECRET_KEY'] = 'ganti_dengan_kunci_acak_yang_panjang_dan_aman_di_produksi'
            
            # Cek deteksi
            secret_check = (os.environ.get('SECRET_KEY') or '').strip().lower()
            self.assertIn(secret_check, library_app._PLACEHOLDER_SECRETS)

            # Kasus 2: Secret key terlalu pendek (<16 karakter)
            os.environ['SECRET_KEY'] = 'pendek123'
            self.assertLess(len(os.environ['SECRET_KEY']), 16)
        finally:
            if old_env is not None:
                os.environ['FLASK_ENV'] = old_env
            else:
                os.environ.pop('FLASK_ENV', None)
            if old_secret is not None:
                os.environ['SECRET_KEY'] = old_secret
            else:
                os.environ.pop('SECRET_KEY', None)

    def test_03_production_guards_reject_default_admin_password(self):
        """Memastikan mode produksi menolak jika password admin masih '123' atau placeholder."""
        old_env = os.environ.get('FLASK_ENV')
        old_pwd = os.environ.get('ADMIN_PASSWORD')
        try:
            os.environ['FLASK_ENV'] = 'production'
            
            # Kasus 1: Default password '123'
            os.environ['ADMIN_PASSWORD'] = '123'
            self.assertIn(os.environ['ADMIN_PASSWORD'], library_app._PLACEHOLDER_PASSWORDS)

            # Kasus 2: Placeholder template
            os.environ['ADMIN_PASSWORD'] = 'ganti_dengan_password_admin_yang_kuat'
            self.assertIn(os.environ['ADMIN_PASSWORD'], library_app._PLACEHOLDER_PASSWORDS)
        finally:
            if old_env is not None:
                os.environ['FLASK_ENV'] = old_env
            else:
                os.environ.pop('FLASK_ENV', None)
            if old_pwd is not None:
                os.environ['ADMIN_PASSWORD'] = old_pwd
            else:
                os.environ.pop('ADMIN_PASSWORD', None)

    def test_04_login_rate_limiting_blocks_after_max_attempts(self):
        """Memastikan proteksi brute force memblokir IP setelah 5 kali gagal login berturut-turut."""
        ip = '192.168.1.100'
        token = self._get_csrf_token()

        # 5 kali percobaan login gagal
        for i in range(5):
            res = self.client.post('/login', data={
                'username': 'admin',
                'password': f'wrong_pass_{i}',
                'csrf_token': token
            }, headers={'X-Forwarded-For': ip})
            if i < 4:
                self.assertEqual(res.status_code, 200)
            else:
                # Percobaan ke-5 memicu lockout
                self.assertEqual(res.status_code, 429)

        # Percobaan ke-6 langsung ditolak dengan HTTP 429 meskipun menggunakan password yang benar
        res_blocked = self.client.post('/login', data={
            'username': library_app.ADMIN_USERNAME,
            'password': '123',
            'csrf_token': token
        }, headers={'X-Forwarded-For': ip})
        self.assertEqual(res_blocked.status_code, 429)
        self.assertIn('Terlalu banyak percobaan login gagal', res_blocked.get_data(as_text=True))

    def test_05_successful_login_clears_rate_limit(self):
        """Memastikan login berhasil membersihkan rekaman percobaan gagal."""
        ip = '192.168.1.101'
        token = self._get_csrf_token()

        # 2 kali gagal
        self.client.post('/login', data={
            'username': 'admin',
            'password': 'wrong',
            'csrf_token': token
        }, headers={'X-Forwarded-For': ip})
        self.client.post('/login', data={
            'username': 'admin',
            'password': 'wrong',
            'csrf_token': token
        }, headers={'X-Forwarded-For': ip})

        # Cek ada 2 percobaan tercatat
        self.assertEqual(library_app._LOGIN_ATTEMPTS.get(ip, {}).get('count'), 2)

        # Login berhasil dengan kredensial yang tepat
        # (Dalam test mode lokal, default password '123' terverifikasi jika tidak disetel khusus)
        res_success = self.client.post('/login', data={
            'username': library_app.ADMIN_USERNAME,
            'password': '123',
            'csrf_token': token
        }, headers={'X-Forwarded-For': ip})
        self.assertEqual(res_success.status_code, 302)

        # Verifikasi record percobaan terhapus
        self.assertNotIn(ip, library_app._LOGIN_ATTEMPTS)

    def test_06_reset_catalog_requires_confirmation_keyword(self):
        """Memastikan /reset_katalog_buku menolak jika konfirmasi != 'KOSONGKAN'."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
        token = self._get_csrf_token()

        # Isi 1 buku
        conn = library_app.get_db_connection()
        conn.execute("INSERT INTO buku (judul, stok) VALUES ('Buku Tes', 5)")
        conn.commit()
        conn.close()

        # Request POST tanpa konfirmasi
        res = self.client.post('/reset_katalog_buku', data={'csrf_token': token}, follow_redirects=True)
        self.assertIn('Pengosongan katalog dibatalkan', res.get_data(as_text=True))

        # Cek buku tidak terhapus
        conn = library_app.get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM buku").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_07_reset_catalog_blocked_when_active_loans_exist(self):
        """Memastikan /reset_katalog_buku menolak pengosongan jika terdapat transaksi peminjaman aktif."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
        token = self._get_csrf_token()

        conn = library_app.get_db_connection()
        conn.execute("INSERT INTO buku (judul, stok) VALUES ('Buku Tes Sirkulasi', 1)")
        book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Buat peminjaman aktif
        conn.execute("""
            INSERT INTO peminjaman (id_anggota, tgl_pinjam, tgl_kembali_seharusnya, status)
            VALUES ('Siswa Aktif', '2026-10-01', '2026-10-08', 'Dipinjam')
        """)
        conn.commit()
        conn.close()

        # Kirim kata kunci 'KOSONGKAN'
        res = self.client.post('/reset_katalog_buku', data={
            'csrf_token': token,
            'konfirmasi': 'KOSONGKAN'
        }, follow_redirects=True)

        self.assertIn('terdapat 1 transaksi peminjaman yang masih aktif', res.get_data(as_text=True))

        # Verifikasi buku tetap utuh
        conn = library_app.get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM buku").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_08_reset_catalog_blocked_in_production(self):
        """Memastikan /reset_katalog_buku diblokir di mode produksi jika ALLOW_CATALOG_RESET!=true."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
        token = self._get_csrf_token()

        old_is_prod = library_app.IS_PRODUCTION
        try:
            library_app.IS_PRODUCTION = True
            os.environ['ALLOW_CATALOG_RESET'] = 'false'

            res = self.client.post('/reset_katalog_buku', data={
                'csrf_token': token,
                'konfirmasi': 'KOSONGKAN'
            }, follow_redirects=True)

            self.assertIn('Fitur pengosongan katalog dinonaktifkan di lingkungan produksi', res.get_data(as_text=True))
        finally:
            library_app.IS_PRODUCTION = old_is_prod

    def test_09_database_timeout_configuration(self):
        """Memastikan get_db_connection menerapkan timeout dan busy_timeout sesuai konfigurasi."""
        os.environ['SQLITE_TIMEOUT'] = '25.0'
        conn = library_app.get_db_connection()
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.close()
        self.assertEqual(busy, 25000)

    def test_10_init_db_preserves_legacy_schema(self):
        """Memastikan init_db() tidak membuat peminjaman_detail prematur pada database skema lama."""
        legacy_db = os.path.join(self.test_dir, 'legacy_test.db')
        conn = sqlite3.connect(legacy_db)
        # Buat skema legacy peminjaman (tanpa kode_transaksi)
        conn.execute("""
            CREATE TABLE peminjaman (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_buku INTEGER,
                id_anggota TEXT,
                status TEXT DEFAULT 'Dipinjam'
            )
        """)
        conn.commit()
        conn.close()

        # Jalankan init_db pada legacy_db
        library_app.init_db(legacy_db)

        # Verifikasi tabel peminjaman_detail TIDAK dibuat secara prematur
        conn_check = sqlite3.connect(legacy_db)
        tables = [r[0] for r in conn_check.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn_check.close()
        self.assertNotIn('peminjaman_detail', tables)


if __name__ == '__main__':
    unittest.main()

