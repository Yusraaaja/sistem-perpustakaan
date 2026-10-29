# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-02: Form Tambah Buku dan Preview Jumlah Eksemplar.
Memverifikasi:
1. Akses form bagi admin terautentikasi dan penolakan bagi pengguna tanpa login.
2. Validasi server-side lengkap: field wajib, ISBN, angka bulat, batas 1..1000.
3. Preview real-time: jumlah 1 menghasilkan "Anda akan membuat 1 eksemplar."
4. Perlindungan jumlah > 100: wajib konfirmasi pengetikan ulang persis sama; jumlah <= 100 tidak perlu.
5. Zero Writes to Database: preview & validasi tidak pernah memutasi atau menambah record DB.
6. Proteksi CSRF tetap ditegakkan pada rute mutasi.
7. Nilai form tetap tersedia (repopulation) setelah validasi gagal.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
from policy import CONFIRMATION_THRESHOLD_COPIES, MAX_COPIES_PER_ADD
from services.catalog_service import validate_add_book_input
from services.exceptions import ValidationError


class BaseAddBookTestCase(unittest.TestCase):
    """Setup terisolasi dengan temporary database dan client Flask."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_add_book.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2 & baseline legacy pada DB uji
        library_app.init_db(self.test_db)
        self._init_v2_schema_if_needed()

    def tearDown(self):
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _init_v2_schema_if_needed(self):
        """Memastikan tabel skema v2 ada pada test database untuk verifikasi zero-write."""
        conn = library_app.get_db_connection()
        try:
            sql_path = os.path.join(ROOT, 'migrations', '0001_initial_v2_schema.sql')
            if os.path.exists(sql_path):
                with open(sql_path, 'r', encoding='utf-8') as f:
                    conn.executescript(f.read())
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _login_admin(self):
        """Helper login admin dengan session dan CSRF token terdaftar."""
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = library_app.ADMIN_USERNAME
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-302'
        return 'test-valid-csrf-token-302'

    def _get_db_counts(self):
        """Menghitung total baris pada tabel katalog dan buku untuk pembuktian zero-write."""
        conn = library_app.get_db_connection()
        counts = {}
        try:
            counts['buku'] = conn.execute("SELECT COUNT(*) FROM buku").fetchone()[0]
        except Exception:
            counts['buku'] = 0

        try:
            counts['catalog_titles'] = conn.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        except Exception:
            counts['catalog_titles'] = 0

        try:
            counts['copies'] = conn.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        except Exception:
            counts['copies'] = 0

        conn.close()
        return counts


class AddBookUnitValidationTests(unittest.TestCase):
    """Pengujian unit langsung untuk fungsi validate_add_book_input."""

    def test_01_valid_input_standard(self):
        data = {
            'judul': 'Laskar Pelangi',
            'penulis': 'Andrea Hirata',
            'kategori': 'Fiksi',
            'isbn': '978-602-291-000-1',
            'jumlah': 25,
        }
        res = validate_add_book_input(data)
        self.assertTrue(res['valid'])
        self.assertEqual(res['judul'], 'Laskar Pelangi')
        self.assertEqual(res['penulis'], 'Andrea Hirata')
        self.assertEqual(res['kategori'], 'Fiksi')
        self.assertEqual(res['jumlah'], 25)
        self.assertFalse(res['requires_confirmation'])
        self.assertEqual(res['preview_message'], 'Anda akan membuat 25 eksemplar.')

    def test_02_quantity_1_preview(self):
        data = {
            'judul': 'Bumi Manusia',
            'penulis': 'Pramoedya Ananta Toer',
            'kategori': 'Sastra',
            'jumlah': 1,
        }
        res = validate_add_book_input(data)
        self.assertEqual(res['jumlah'], 1)
        self.assertEqual(res['preview_message'], 'Anda akan membuat 1 eksemplar.')

    def test_03_quantity_100_no_confirmation_required(self):
        data = {
            'judul': 'Matematika Dasar',
            'penulis': 'Tim Dosen',
            'kategori': 'Pendidikan',
            'jumlah': 100,
        }
        res = validate_add_book_input(data)
        self.assertEqual(res['jumlah'], 100)
        self.assertFalse(res['requires_confirmation'])
        self.assertEqual(res['preview_message'], 'Anda akan membuat 100 eksemplar.')

    def test_04_quantity_101_requires_confirmation_success(self):
        data = {
            'judul': 'Kamus Lengkap Bahasa Indonesia',
            'penulis': 'Badan Bahasa',
            'kategori': 'Referensi',
            'jumlah': 101,
            'jumlah_konfirmasi': 101,
        }
        res = validate_add_book_input(data)
        self.assertEqual(res['jumlah'], 101)
        self.assertTrue(res['requires_confirmation'])
        self.assertEqual(res['jumlah_konfirmasi'], 101)
        self.assertEqual(res['preview_message'], 'Anda akan membuat 101 eksemplar.')

    def test_05_quantity_101_missing_confirmation_raises(self):
        data = {
            'judul': 'Kamus Lengkap',
            'penulis': 'Badan Bahasa',
            'kategori': 'Referensi',
            'jumlah': 101,
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input(data)
        self.assertIn('konfirmasi', str(ctx.exception).lower())

    def test_06_quantity_101_mismatched_confirmation_raises(self):
        data = {
            'judul': 'Kamus Lengkap',
            'penulis': 'Badan Bahasa',
            'kategori': 'Referensi',
            'jumlah': 101,
            'jumlah_konfirmasi': 100,
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input(data)
        self.assertIn('tidak cocok', str(ctx.exception).lower())

    def test_07_empty_required_fields_raise(self):
        # Judul kosong
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({'judul': '', 'penulis': 'Penulis', 'kategori': 'Fiksi', 'jumlah': 5})
        self.assertIn('Judul', str(ctx.exception))

        # Penulis kosong
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({'judul': 'Judul', 'penulis': '   ', 'kategori': 'Fiksi', 'jumlah': 5})
        self.assertIn('penulis', str(ctx.exception).lower())

        # Kategori kosong
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({'judul': 'Judul', 'penulis': 'Penulis', 'kategori': '', 'jumlah': 5})
        self.assertIn('kategori', str(ctx.exception).lower())

        # Jumlah kosong
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({'judul': 'Judul', 'penulis': 'Penulis', 'kategori': 'Fiksi', 'jumlah': ''})
        self.assertIn('jumlah eksemplar', str(ctx.exception).lower())

    def test_08_invalid_quantity_values_raise(self):
        base = {'judul': 'Judul', 'penulis': 'Penulis', 'kategori': 'Fiksi'}

        # Jumlah 0
        with self.assertRaises(ValidationError):
            validate_add_book_input({**base, 'jumlah': 0})

        # Jumlah negatif
        with self.assertRaises(ValidationError):
            validate_add_book_input({**base, 'jumlah': -10})

        # Jumlah non-numerik
        with self.assertRaises(ValidationError):
            validate_add_book_input({**base, 'jumlah': 'sepuluh'})

        # Jumlah float / desimal
        with self.assertRaises(ValidationError):
            validate_add_book_input({**base, 'jumlah': '5.5'})

    def test_09_extreme_values_and_length_limits(self):
        base = {'penulis': 'Penulis', 'kategori': 'Fiksi', 'jumlah': 5}

        # Judul sangat panjang (> 255 karakter)
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({'judul': 'X' * 256, **base})
        self.assertIn('panjang', str(ctx.exception).lower())

        # Jumlah melebihi MAX_COPIES_PER_ADD (1000)
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({'judul': 'Judul', 'penulis': 'Penulis', 'kategori': 'Fiksi', 'jumlah': 1001, 'jumlah_konfirmasi': 1001})
        self.assertIn('maksimal', str(ctx.exception).lower())

    def test_10_isbn_validation_rules(self):
        base = {'judul': 'Judul', 'penulis': 'Penulis', 'kategori': 'Fiksi', 'jumlah': 5}

        # ISBN kosong / None adalah sah (opsional)
        res1 = validate_add_book_input({**base, 'isbn': ''})
        self.assertIsNone(res1['isbn'])

        # ISBN-13 valid dengan tanda hubung
        res2 = validate_add_book_input({**base, 'isbn': '978-602-000-000-0'})
        self.assertEqual(res2['isbn'], '978-602-000-000-0')

        # ISBN-10 valid dengan 'X'
        res3 = validate_add_book_input({**base, 'isbn': '0-123456-47-X'})
        self.assertEqual(res3['isbn'], '0-123456-47-X')

        # ISBN invalid panjang (misal 5 digit)
        with self.assertRaises(ValidationError) as ctx:
            validate_add_book_input({**base, 'isbn': '12345'})
        self.assertIn('ISBN', str(ctx.exception))


class AddBookRouteIntegrationTests(BaseAddBookTestCase):
    """
    Pengujian integrasi rute HTTP untuk Form Tambah Buku dan Preview.
    Memenuhi seluruh 15 acceptance criteria Task 3-02.
    """

    def test_01_form_accessible_by_authenticated_admin(self):
        """Kriteria 1: Form dapat diakses oleh admin terautentikasi."""
        self._login_admin()
        res = self.client.get('/buku/tambah')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Tambah Buku Baru', html)
        self.assertIn('name="judul"', html)
        self.assertIn('name="penulis"', html)
        self.assertIn('name="kategori"', html)
        self.assertIn('name="isbn"', html)
        self.assertIn('name="jumlah"', html)
        self.assertIn('name="jumlah_konfirmasi"', html)
        self.assertIn('id="previewText"', html)

    def test_02_unauthenticated_user_cannot_access_form(self):
        """Kriteria 2: Pengguna tanpa login ditolak dan dialihkan ke /login."""
        # GET /buku/tambah
        res1 = self.client.get('/buku/tambah', follow_redirects=False)
        self.assertEqual(res1.status_code, 302)
        self.assertIn('/login', res1.headers.get('Location', ''))

        # GET /tambah_buku (alias)
        res2 = self.client.get('/tambah_buku', follow_redirects=False)
        self.assertEqual(res2.status_code, 302)
        self.assertIn('/login', res2.headers.get('Location', ''))

        # GET /add
        res3 = self.client.get('/add', follow_redirects=False)
        self.assertEqual(res3.status_code, 302)
        self.assertIn('/login', res3.headers.get('Location', ''))

        # POST /buku/tambah tanpa sesi
        res4 = self.client.post('/buku/tambah', data={'judul': 'Buku Tanpa Izin'}, follow_redirects=False)
        # Menghasilkan 400 (karena CSRF) atau 302 (karena unauth)
        self.assertIn(res4.status_code, (302, 400))

    def test_03_empty_required_fields_rejected_by_server(self):
        """Kriteria 3: Field wajib yang kosong ditolak server dengan HTTP 400."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': '',
            'penulis': 'Andrea Hirata',
            'kategori': 'Fiksi',
            'jumlah': '10',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 400)
        html = res.data.decode('utf-8')
        self.assertIn('Judul buku wajib diisi', html)

    def test_04_quantity_1_produces_preview_1_eksemplar(self):
        """Kriteria 4: Jumlah 1 menghasilkan preview 1 eksemplar."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Laskar Pelangi',
            'penulis': 'Andrea Hirata',
            'kategori': 'Fiksi',
            'jumlah': '1',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Anda akan membuat 1 eksemplar.', html)
        self.assertIn('Tahap Pratinjau Eksemplar', html)

    def test_05_quantity_100_does_not_require_confirmation(self):
        """Kriteria 5: Jumlah 100 tidak memerlukan konfirmasi pengetikan ulang."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Kumpulan Cerpen Sekolah',
            'penulis': 'Tim Guru',
            'kategori': 'Sastra',
            'jumlah': '100',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Anda akan membuat 100 eksemplar.', html)

    def test_06_quantity_101_requires_confirmation_when_missing(self):
        """Kriteria 6: Jumlah 101 mewajibkan konfirmasi ulang; ditolak jika tidak ada."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Buku Panduan Ujian Nasional',
            'penulis': 'Kementerian Pendidikan',
            'kategori': 'Pendidikan',
            'jumlah': '101',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 400)
        html = res.data.decode('utf-8')
        self.assertIn('konfirmasi', html.lower())

    def test_07_quantity_101_with_matching_confirmation_passes(self):
        """Kriteria 7: Jumlah 101 dengan konfirmasi 101 lolos validasi form."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Buku Panduan Ujian Nasional',
            'penulis': 'Kementerian Pendidikan',
            'kategori': 'Pendidikan',
            'jumlah': '101',
            'jumlah_konfirmasi': '101',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Anda akan membuat 101 eksemplar.', html)

    def test_08_quantity_101_with_mismatched_confirmation_rejected(self):
        """Kriteria 8: Jumlah 101 dengan konfirmasi salah ditolak server."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Buku Panduan Siswa',
            'penulis': 'Tim Kurikulum',
            'kategori': 'Pendidikan',
            'jumlah': '101',
            'jumlah_konfirmasi': '100',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 400)
        html = res.data.decode('utf-8')
        self.assertIn('tidak cocok', html.lower())

    def test_09_quantity_101_with_empty_confirmation_rejected(self):
        """Kriteria 9: Jumlah 101 dengan konfirmasi string kosong ditolak server."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Buku Panduan Siswa',
            'penulis': 'Tim Kurikulum',
            'kategori': 'Pendidikan',
            'jumlah': '101',
            'jumlah_konfirmasi': '   ',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 400)
        html = res.data.decode('utf-8')
        self.assertIn('konfirmasi', html.lower())

    def test_10_zero_negative_nonnumeric_quantities_rejected(self):
        """Kriteria 10: Jumlah nol, negatif, desimal, dan nonnumerik ditolak server."""
        token = self._login_admin()
        base = {'csrf_token': token, 'judul': 'Buku Uji', 'penulis': 'Pengarang', 'kategori': 'Umum'}

        # Nol
        res0 = self.client.post('/buku/tambah', data={**base, 'jumlah': '0'})
        self.assertEqual(res0.status_code, 400)

        # Negatif
        res_neg = self.client.post('/buku/tambah', data={**base, 'jumlah': '-5'})
        self.assertEqual(res_neg.status_code, 400)

        # Nonnumerik
        res_str = self.client.post('/buku/tambah', data={**base, 'jumlah': 'sepuluh'})
        self.assertEqual(res_str.status_code, 400)

        # Desimal
        res_dec = self.client.post('/buku/tambah', data={**base, 'jumlah': '5.5'})
        self.assertEqual(res_dec.status_code, 400)

    def test_11_extreme_values_and_long_inputs_handled_safely(self):
        """Kriteria 11: Nilai ekstrem (>1000) dan string ekstra panjang ditolak secara aman."""
        token = self._login_admin()
        base = {'csrf_token': token, 'penulis': 'Pengarang', 'kategori': 'Umum'}

        # Jumlah melebihi MAX_COPIES_PER_ADD (1000)
        res_big = self.client.post('/buku/tambah', data={**base, 'judul': 'Buku Massal', 'jumlah': '1001', 'jumlah_konfirmasi': '1001'})
        self.assertEqual(res_big.status_code, 400)
        self.assertIn('maksimal', res_big.data.decode('utf-8').lower())

        # Judul 500 karakter
        res_long = self.client.post('/buku/tambah', data={**base, 'judul': 'A' * 500, 'jumlah': '5'})
        self.assertEqual(res_long.status_code, 400)
        self.assertIn('terlalu panjang', res_long.data.decode('utf-8').lower())

    def test_12_direct_server_bypass_rejected(self):
        """Kriteria 12: Request langsung (misal via JSON API) tanpa validasi browser tetap ditegakkan server."""
        token = self._login_admin()
        # Direct JSON POST dengan jumlah 150 tanpa konfirmasi
        res = self.client.post(
            '/buku/tambah',
            data=json.dumps({
                'csrf_token': token,
                'judul': 'Buku Bypass Test',
                'penulis': 'Hacker',
                'kategori': 'Keamanan',
                'jumlah': 150,
            }),
            content_type='application/json',
            headers={'X-CSRFToken': token}
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['ok'])
        self.assertIn('konfirmasi', data['message'].lower())

    def test_13_preview_and_validation_do_not_mutate_database(self):
        """
        Kriteria 13: Zero-write strictly verified.
        Preview/validasi tidak membuat atau mengubah data buku maupun eksemplar di database.
        """
        token = self._login_admin()
        counts_before = self._get_db_counts()

        # Jalankan beberapa POST valid dan invalid
        self.client.post('/buku/tambah', data={
            'csrf_token': token,
            'judul': 'Buku Pratinjau 1',
            'penulis': 'Penulis A',
            'kategori': 'Fiksi',
            'jumlah': '10',
        })

        self.client.post('/buku/tambah', data={
            'csrf_token': token,
            'judul': 'Buku Pratinjau 2',
            'penulis': 'Penulis B',
            'kategori': 'Sains',
            'jumlah': '150',
            'jumlah_konfirmasi': '150',
        })

        self.client.post('/buku/tambah', data={
            'csrf_token': token,
            'judul': 'Buku Gagal',
            'penulis': '',
            'kategori': '',
            'jumlah': '-1',
        })

        counts_after = self._get_db_counts()
        self.assertEqual(counts_before['buku'], counts_after['buku'], "Tabel buku termutasi!")
        self.assertEqual(counts_before['catalog_titles'], counts_after['catalog_titles'], "Tabel catalog_titles termutasi!")
        self.assertEqual(counts_before['copies'], counts_after['copies'], "Tabel copies termutasi!")

    def test_14_csrf_protection_enforced(self):
        """Kriteria 14: Proteksi CSRF tetap berfungsi menolak request tanpa token atau dengan token palsu."""
        self._login_admin()

        # POST tanpa token CSRF
        res1 = self.client.post('/buku/tambah', data={'judul': 'Buku Tanpa CSRF', 'jumlah': 5})
        self.assertEqual(res1.status_code, 400)

        # POST dengan token CSRF palsu
        res2 = self.client.post('/buku/tambah', data={'csrf_token': 'forged-token-xyz', 'judul': 'Buku CSRF Palsu', 'jumlah': 5})
        self.assertEqual(res2.status_code, 400)

    def test_15_form_repopulation_on_validation_failure(self):
        """Kriteria 15: Nilai formulir tetap tersedia setelah validasi gagal agar tidak perlu diketik ulang."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Judul Buku Yang Dipertahankan',
            'sub_judul': 'Edisi Khusus Siswa',
            'penulis': 'Nama Penulis Hebat',
            'kategori': '',  # Sengaja dikosongkan agar gagal
            'isbn': '978-602-000-000-0',
            'jumlah': '50',
        }
        res = self.client.post('/buku/tambah', data=payload)
        self.assertEqual(res.status_code, 400)
        html = res.data.decode('utf-8')
        # Nilai yang sudah diketik tetap terisi di HTML
        self.assertIn('Judul Buku Yang Dipertahankan', html)
        self.assertIn('Edisi Khusus Siswa', html)
        self.assertIn('Nama Penulis Hebat', html)
        self.assertIn('978-602-000-000-0', html)


if __name__ == '__main__':
    unittest.main()

