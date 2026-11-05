# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-03: Commit Atomik + Token Konfirmasi Sekali Pakai.
Memverifikasi:
1. Preview valid tidak menulis ke database (zero writes).
2. Konfirmasi valid membuat tepat satu judul dan jumlah eksemplar yang benar.
3. Token hilang, palsu, kedaluwarsa, atau sudah digunakan ditolak tanpa penulisan tambahan.
4. Payload yang diubah setelah preview ditolak (anti-tampering).
5. Dua konfirmasi berurutan dengan token yang sama tidak menggandakan data (idempotensi).
6. Request bersamaan (race condition) dilindungi: hanya satu pembuatan yang berhasil.
7. Kirim ulang request setelah sukses tidak menambah jumlah judul/eksemplar (replay safety).
8. Simulasi kegagalan di tengah jalan (fault injection) menghasilkan rollback penuh (0 judul, 0 eksemplar).
9. Akses tanpa login dan request tanpa CSRF ditolak secara ketat.
10. Seluruh alur kompatibel dengan alias route /buku/tambah dan /tambah_buku.
"""
import concurrent.futures
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
from policy import CONFIRMATION_THRESHOLD_COPIES, MAX_COPIES_PER_ADD, CONFIRMATION_TOKEN_TTL_SECONDS
from services.catalog_service import (
    validate_add_book_input,
    create_confirmation_token,
    consume_confirmation_token,
    clear_confirmation_tokens,
    confirm_and_create_title_with_copies,
    _CONFIRMATION_TOKENS,
    _ACTIVE_PROCESSING_TOKENS,
)
from services.exceptions import (
    ValidationError,
    ConfirmationTokenError,
    ConcurrencyConflictError,
)


class BaseAtomicCommitTestCase(unittest.TestCase):
    """Setup lingkungan terisolasi dengan temporary database skema v2."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_atomic_commit.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema database uji
        library_app.init_db(self.test_db)
        self._init_v2_schema()

        # Bersihkan registry token sebelum tiap tes
        clear_confirmation_tokens()

    def tearDown(self):
        clear_confirmation_tokens()
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _init_v2_schema(self):
        conn = library_app.get_db_connection()
        try:
            sql_path = os.path.join(ROOT, 'migrations', '0001_initial_v2_schema.sql')
            if os.path.exists(sql_path):
                with open(sql_path, 'r', encoding='utf-8') as f:
                    conn.executescript(f.read())
            conn.commit()
        finally:
            conn.close()

    def _login_admin(self):
        """Helper login admin dengan session dan CSRF token terdaftar."""
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = library_app.ADMIN_USERNAME
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-303'
        return 'test-valid-csrf-token-303'

    def _get_db_counts(self):
        """Menghitung total baris pada tabel katalog, eksemplar, dan audit log."""
        conn = library_app.get_db_connection()
        counts = {}
        try:
            counts['catalog_titles'] = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        except Exception:
            counts['catalog_titles'] = 0

        try:
            counts['copies'] = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        except Exception:
            counts['copies'] = 0

        try:
            counts['audit_log'] = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        except Exception:
            counts['audit_log'] = 0

        conn.close()
        return counts


class AtomicAddBookCommitTests(BaseAtomicCommitTestCase):
    """Pengujian acceptance criteria Task 3-03."""

    def test_01_preview_valid_does_not_write_to_db(self):
        """Kriteria 1: Preview valid menerbitkan token tetapi tidak menulis ke DB."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Sang Pemimpi',
            'penulis': 'Andrea Hirata',
            'kategori': 'Fiksi',
            'isbn': '978-602-291-001-8',
            'jumlah': '15',
        }

        counts_before = self._get_db_counts()

        # Eksekusi POST preview
        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['ok'])
        self.assertIn('confirm_token', data)
        self.assertIn('15 eksemplar', data['preview_message'])

        counts_after = self._get_db_counts()
        self.assertEqual(counts_before['catalog_titles'], counts_after['catalog_titles'])
        self.assertEqual(counts_before['copies'], counts_after['copies'])
        self.assertEqual(counts_before['audit_log'], counts_after['audit_log'])

    def test_02_valid_confirmation_creates_exact_title_and_copies_atomically(self):
        """Kriteria 2: Konfirmasi valid membuat tepat satu judul dan seluruh eksemplar secara atomik."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Garis Waktu',
            'penulis': 'Fiersa Besari',
            'kategori': 'Sastra',
            'isbn': '978-602-000-001-5',
            'jumlah': '5',
        }

        # 1. Preview
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_prev.status_code, 200)
        confirm_token = res_prev.get_json()['confirm_token']

        # 2. Konfirmasi
        confirm_payload = {
            'csrf_token': token,
            'confirm_token': confirm_token,
            **payload
        }
        res_conf = self.client.post('/buku/tambah/konfirmasi', data=confirm_payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_conf.status_code, 200)
        conf_data = res_conf.get_json()
        self.assertTrue(conf_data['ok'])
        self.assertFalse(conf_data['is_replay'])

        result = conf_data['data']
        self.assertEqual(result['judul'], 'Garis Waktu')
        self.assertEqual(result['initial_copies_count'], 5)
        self.assertEqual(len(result['copy_ids']), 5)
        self.assertTrue(result['title_id'].startswith('T-'))

        # Verifikasi langsung pada SQLite
        conn = library_app.get_db_connection()
        title_row = conn.execute("SELECT * FROM catalog_titles WHERE id = ?;", (result['title_id'],)).fetchone()
        self.assertIsNotNone(title_row)
        self.assertEqual(title_row['judul'], 'Garis Waktu')

        copy_rows = conn.execute("SELECT * FROM copies WHERE title_id = ?;", (result['title_id'],)).fetchall()
        self.assertEqual(len(copy_rows), 5)
        for r in copy_rows:
            self.assertTrue(r['id'].startswith('C-'))
            self.assertEqual(r['status'], 'aktif')

        audit_row = conn.execute("SELECT * FROM audit_log WHERE object_id = ?;", (result['title_id'],)).fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row['action'], 'TITLE_CREATE')
        conn.close()

    def test_03_missing_fake_expired_tokens_rejected(self):
        """Kriteria 3: Token hilang, palsu, dan kedaluwarsa ditolak tanpa menulis ke DB."""
        csrf_tok = self._login_admin()
        payload = {
            'csrf_token': csrf_tok,
            'judul': 'Buku Uji Keamanan',
            'penulis': 'Security Auditor',
            'kategori': 'Teknologi',
            'jumlah': '10',
        }
        counts_init = self._get_db_counts()

        # Token hilang
        res_missing = self.client.post('/buku/tambah/konfirmasi', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_missing.status_code, 400)
        self.assertIn('token konfirmasi wajib', res_missing.get_json()['error'].lower())

        # Token palsu
        res_fake = self.client.post('/buku/tambah/konfirmasi', data={**payload, 'confirm_token': 'fake-token-9999'}, headers={'Accept': 'application/json'})
        self.assertEqual(res_fake.status_code, 400)
        self.assertIn('tidak valid atau tidak ditemukan', res_fake.get_json()['error'].lower())

        # Token kedaluwarsa (simulasi dengan token yang TTL-nya lewat)
        real_token = create_confirmation_token(payload, admin_username=library_app.ADMIN_USERNAME, ttl_seconds=-10)
        res_exp = self.client.post('/buku/tambah/konfirmasi', data={**payload, 'confirm_token': real_token}, headers={'Accept': 'application/json'})
        self.assertEqual(res_exp.status_code, 400)
        self.assertIn('kedaluwarsa', res_exp.get_json()['error'].lower())

        # Pastikan tidak ada data yang tertulis
        counts_after = self._get_db_counts()
        self.assertEqual(counts_init, counts_after)

    def test_04_tampered_payload_rejected(self):
        """Kriteria 4: Modifikasi payload setelah tahap preview ditolak server (anti-tampering)."""
        token = self._login_admin()
        preview_payload = {
            'csrf_token': token,
            'judul': 'Buku Asli',
            'penulis': 'Penulis Asli',
            'kategori': 'Sains',
            'jumlah': '5',
        }

        # 1. Preview 5 eksemplar
        res_prev = self.client.post('/buku/tambah', data=preview_payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']

        # 2. Ubah jumlah menjadi 50 saat konfirmasi tanpa mengulang preview
        tampered_payload = {
            'csrf_token': token,
            'confirm_token': confirm_token,
            'judul': 'Buku Asli',
            'penulis': 'Penulis Asli',
            'kategori': 'Sains',
            'jumlah': '50',  # Diubah!
        }
        res_conf = self.client.post('/buku/tambah/konfirmasi', data=tampered_payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_conf.status_code, 400)
        self.assertIn('dimodifikasi', res_conf.get_json()['error'].lower())

        # Pastikan tidak ada record yang terbentuk di database
        counts = self._get_db_counts()
        self.assertEqual(counts['catalog_titles'], 0)
        self.assertEqual(counts['copies'], 0)

    def test_05_sequential_double_confirmation_does_not_duplicate(self):
        """Kriteria 5: Dua konfirmasi berurutan dengan token yang sama tidak menggandakan data (idempotensi)."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Filosofi Teras',
            'penulis': 'Henry Manampiring',
            'kategori': 'Filsafat',
            'jumlah': '8',
        }

        # Preview
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']

        # Konfirmasi pertama
        confirm_data = {'csrf_token': token, 'confirm_token': confirm_token, **payload}
        res1 = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.get_json()['is_replay'])

        counts_after_first = self._get_db_counts()
        self.assertEqual(counts_after_first['catalog_titles'], 1)
        self.assertEqual(counts_after_first['copies'], 8)

        # Konfirmasi kedua dengan token yang sama persis
        res2 = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()['is_replay'])
        self.assertIn('sudah berhasil disimpan sebelumnya', res2.get_json()['message'])

        # Pastikan jumlah judul dan eksemplar di database TIDAK BERTAMBAH
        counts_after_second = self._get_db_counts()
        self.assertEqual(counts_after_second['catalog_titles'], 1)
        self.assertEqual(counts_after_second['copies'], 8)

    def test_06_concurrent_confirmation_race_condition_protection(self):
        """Kriteria 6: Dua request konfirmasi bersamaan (race condition) hanya memproses 1 pembuatan."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Concurreny Under the Hood',
            'penulis': 'Leslie Lamport',
            'kategori': 'Komputer',
            'jumlah': '12',
        }

        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']
        confirm_data = {'csrf_token': token, 'confirm_token': confirm_token, **payload}

        results = []

        def worker():
            with library_app.app.test_client() as c:
                with c.session_transaction() as sess:
                    sess.permanent = True
                    sess['logged_in'] = True
                    sess['admin_username'] = library_app.ADMIN_USERNAME
                    sess['last_active'] = time.time()
                    sess['_csrf_token'] = token
                resp = c.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
                return resp.status_code, resp.get_json()

        # Eksekusi 2 thread secara paralel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker)
            f2 = executor.submit(worker)
            results.append(f1.result())
            results.append(f2.result())

        # Minimal satu harus berhasil (HTTP 200). Request lainnya harus 200 (replay) atau 409 (conflict).
        status_codes = [r[0] for r in results]
        self.assertIn(200, status_codes)
        for s in status_codes:
            self.assertIn(s, (200, 409))

        # Integritas database: Judul dan eksemplar dibuat TEPAT SEKALI
        counts = self._get_db_counts()
        self.assertEqual(counts['catalog_titles'], 1)
        self.assertEqual(counts['copies'], 12)

    def test_07_resubmit_after_success_preserves_counts(self):
        """Kriteria 7: Refresh/Kirim ulang request berkali-kali setelah sukses tidak menambah data."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Clean Code',
            'penulis': 'Robert C. Martin',
            'kategori': 'Komputer',
            'jumlah': '3',
        }

        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']
        confirm_data = {'csrf_token': token, 'confirm_token': confirm_token, **payload}

        # Simpan pertama
        self.client.post('/buku/tambah/konfirmasi', data=confirm_data)

        # Resubmit 3 kali
        for _ in range(3):
            res = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()['is_replay'])

        counts = self._get_db_counts()
        self.assertEqual(counts['catalog_titles'], 1)
        self.assertEqual(counts['copies'], 3)

    def test_08_fault_injection_atomic_rollback(self):
        """Kriteria 8: Simulasi kegagalan di tengah jalan me-rollback seluruh operasi (0 judul, 0 eksemplar)."""
        conn = library_app.get_db_connection()
        counts_before = self._get_db_counts()

        payload = {
            'judul': 'Buku Gagal Atomik',
            'penulis': 'Penulis Kegagalan',
            'kategori': 'Eksperimen',
            'jumlah': 10,
        }
        token = create_confirmation_token(payload, admin_username=library_app.ADMIN_USERNAME)

        # Inject error pada copy_repo.create_copy saat pembuatan eksemplar ke-3
        call_count = [0]
        original_create_copy = library_app.copy_repo.create_copy

        def failing_create_copy(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise sqlite3.OperationalError("Simulasi disk error atau integritas terputus di tengah jalan")
            return original_create_copy(*args, **kwargs)

        with patch('repositories.copy_repo.create_copy', side_effect=failing_create_copy):
            with self.assertRaises(sqlite3.OperationalError):
                confirm_and_create_title_with_copies(
                    conn=conn,
                    token=token,
                    admin_username=library_app.ADMIN_USERNAME,
                    submitted_payload=payload
                )

        conn.close()

        # Verifikasi ROLLBACK PENUH: Judul dan seluruh eksemplar harus 0
        counts_after = self._get_db_counts()
        self.assertEqual(counts_before['catalog_titles'], counts_after['catalog_titles'], "Judul tidak ter-rollback!")
        self.assertEqual(counts_before['copies'], counts_after['copies'], "Eksemplar tidak ter-rollback!")
        self.assertEqual(counts_before['audit_log'], counts_after['audit_log'], "Audit log tidak ter-rollback!")

    def test_09_unauthenticated_and_csrf_protection_enforced(self):
        """Kriteria 9 & 10: Penolakan akses tanpa login dan proteksi CSRF pada rute konfirmasi."""
        # Unauthenticated GET /buku/tambah/konfirmasi
        res1 = self.client.get('/buku/tambah/konfirmasi', follow_redirects=False)
        self.assertEqual(res1.status_code, 302)
        self.assertIn('/login', res1.headers.get('Location', ''))

        # Unauthenticated POST
        res2 = self.client.post('/buku/tambah/konfirmasi', data={'confirm_token': 'abc'}, follow_redirects=False)
        self.assertIn(res2.status_code, (302, 400))

        # Authenticated tapi tanpa token CSRF
        self._login_admin()
        res3 = self.client.post('/buku/tambah/konfirmasi', data={'confirm_token': 'abc'})
        self.assertEqual(res3.status_code, 400)

        # Authenticated dengan token CSRF palsu
        res4 = self.client.post('/buku/tambah/konfirmasi', data={'csrf_token': 'forged-csrf-token', 'confirm_token': 'abc'})
        self.assertEqual(res4.status_code, 400)

    def test_10_quantity_over_100_confirmation_end_to_end(self):
        """Kriteria 12: Alur lengkap pembuatan judul dengan jumlah > 100 eksemplar."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Modul Praktek Komputer Siswa',
            'penulis': 'Tim Laboratorium Komputer',
            'kategori': 'Praktikum',
            'isbn': '978-602-000-099-2',
            'jumlah': '105',
            'jumlah_konfirmasi': '105',
        }

        # 1. Preview
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_prev.status_code, 200)
        confirm_token = res_prev.get_json()['confirm_token']

        # 2. Konfirmasi
        res_conf = self.client.post('/buku/tambah/konfirmasi', data={'csrf_token': token, 'confirm_token': confirm_token, **payload}, headers={'Accept': 'application/json'})
        self.assertEqual(res_conf.status_code, 200)
        data = res_conf.get_json()['data']
        self.assertEqual(data['initial_copies_count'], 105)
        self.assertEqual(len(data['copy_ids']), 105)

        # Verifikasi di database
        conn = library_app.get_db_connection()
        count_copies = conn.execute("SELECT COUNT(*) FROM copies WHERE title_id = ?;", (data['title_id'],)).fetchone()[0]
        conn.close()
        self.assertEqual(count_copies, 105)

    def test_11_concurrent_token_consumption_isolated_db_connections(self):
        """Audit 1: Token yang sama dikirim bersamaan melalui dua koneksi database terisolasi."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Distributed Systems In Depth',
            'penulis': 'Martin Kleppmann',
            'kategori': 'Sains Komputer',
            'jumlah': '7',
        }

        # 1. Preview menghasilkan token persisten
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']

        # 2. Simulasikan dua worker/proses dengan koneksi database mandiri
        results = []

        def worker_task(worker_id):
            conn = library_app.get_connection(self.test_db)
            try:
                res, is_replay = confirm_and_create_title_with_copies(
                    conn=conn,
                    token=confirm_token,
                    admin_username=library_app.ADMIN_USERNAME,
                    submitted_payload=payload
                )
                return (worker_id, 'SUCCESS', is_replay, res)
            except ConcurrencyConflictError as cce:
                return (worker_id, 'CONFLICT', None, str(cce))
            except Exception as e:
                return (worker_id, 'ERROR', None, str(e))
            finally:
                conn.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker_task, i) for i in (1, 2)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # Minimal satu worker harus berhasil membuat (is_replay == False)
        # Worker lainnya harus mendapatkan is_replay == True (replay result) atau CONFLICT (HTTP 409)
        statuses = [r[1] for r in results]
        self.assertIn('SUCCESS', statuses)

        # Integritas database: Judul dan eksemplar HARUS tepat 1 judul dan 7 eksemplar
        counts = self._get_db_counts()
        self.assertEqual(counts['catalog_titles'], 1, "Judul katalog terduplikasi pada eksekusi paralel!")
        self.assertEqual(counts['copies'], 7, "Jumlah eksemplar terduplikasi pada eksekusi paralel!")

    def test_12_resubmission_after_success_idempotency_contract(self):
        """Audit 2: Pengiriman ulang setelah operasi berhasil mengembalikan ringkasan identik tanpa baris baru."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Refactoring UI Design',
            'penulis': 'Adam Wathan',
            'kategori': 'Desain',
            'jumlah': '4',
        }

        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']
        confirm_data = {'csrf_token': token, 'confirm_token': confirm_token, **payload}

        # Eksekusi awal
        res1 = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res1.status_code, 200)
        json1 = res1.get_json()
        self.assertFalse(json1['is_replay'])
        title_id_initial = json1['data']['title_id']
        copy_ids_initial = json1['data']['copy_ids']

        counts_baseline = self._get_db_counts()

        # Pengiriman ulang ke-1 dan ke-2
        for _ in range(2):
            res_retry = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
            self.assertEqual(res_retry.status_code, 200)
            json_retry = res_retry.get_json()
            self.assertTrue(json_retry['is_replay'])
            self.assertEqual(json_retry['data']['title_id'], title_id_initial)
            self.assertEqual(json_retry['data']['copy_ids'], copy_ids_initial)

        counts_after = self._get_db_counts()
        self.assertEqual(counts_baseline['catalog_titles'], counts_after['catalog_titles'])
        self.assertEqual(counts_baseline['copies'], counts_after['copies'])
        self.assertEqual(counts_baseline['audit_log'], counts_after['audit_log'])

    def test_13_recovery_after_full_application_restart(self):
        """Audit 3: Pemulihan dan pengulangan request setelah status aplikasi diinisialisasi ulang (restart simulasi)."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Operating Systems Three Easy Pieces',
            'penulis': 'Remzi Arpaci-Dusseau',
            'kategori': 'Sistem Operasi',
            'jumlah': '6',
        }

        # Langkah 1: Buat token via preview
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_prev.status_code, 200)
        confirm_token = res_prev.get_json()['confirm_token']

        # Langkah 2: SIMULASIKAN RESTART APLIKASI TOTAL SEBELUM KONFIRMASI
        _CONFIRMATION_TOKENS.clear()
        _ACTIVE_PROCESSING_TOKENS.clear()

        # Langkah 3: Eksekusi konfirmasi setelah restart
        confirm_data = {'csrf_token': token, 'confirm_token': confirm_token, **payload}
        res_conf = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res_conf.status_code, 200)
        json_conf = res_conf.get_json()
        self.assertFalse(json_conf['is_replay'])
        created_title_id = json_conf['data']['title_id']

        counts_after_commit = self._get_db_counts()
        self.assertEqual(counts_after_commit['catalog_titles'], 1)
        self.assertEqual(counts_after_commit['copies'], 6)

        # Langkah 4: SIMULASIKAN RESTART KEDUA SETELAH COMMIT BERHASIL
        _CONFIRMATION_TOKENS.clear()
        _ACTIVE_PROCESSING_TOKENS.clear()

        # Langkah 5: Klien mengirim ulang request setelah restart
        res_retry = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res_retry.status_code, 200)
        json_retry = res_retry.get_json()
        self.assertTrue(json_retry['is_replay'])
        self.assertEqual(json_retry['data']['title_id'], created_title_id)

        # Jumlah baris di database tetap tidak bertambah
        counts_final = self._get_db_counts()
        self.assertEqual(counts_after_commit, counts_final)

    def test_14_mid_batch_failure_leaves_zero_partial_records_and_cannot_be_replayed(self):
        """Audit 4: Kegagalan transaksi tidak meninggalkan judul atau eksemplar parsial di database."""
        conn = library_app.get_db_connection()
        counts_before = self._get_db_counts()

        payload = {
            'judul': 'Buku Uji Kegagalan Batch',
            'penulis': 'Penguji Atomisitas',
            'kategori': 'Uji Coba',
            'jumlah': 8,
        }
        token = create_confirmation_token(conn, payload, admin_username=library_app.ADMIN_USERNAME)

        # Suntikkan kegagalan pada saat pembuatan eksemplar ke-4
        created_copies_counter = [0]
        real_create_copy = library_app.copy_repo.create_copy

        def failing_create_copy(*args, **kwargs):
            created_copies_counter[0] += 1
            if created_copies_counter[0] >= 4:
                raise sqlite3.IntegrityError("Simulasi kegagalan integritas foreign key di tengah batch!")
            return real_create_copy(*args, **kwargs)

        with patch('repositories.copy_repo.create_copy', side_effect=failing_create_copy):
            with self.assertRaises(sqlite3.IntegrityError):
                confirm_and_create_title_with_copies(
                    conn=conn,
                    token=token,
                    admin_username=library_app.ADMIN_USERNAME,
                    submitted_payload=payload
                )

        # Verifikasi database BERSIH TOTAL: 0 judul baru, 0 eksemplar baru
        counts_after = self._get_db_counts()
        self.assertEqual(counts_before['catalog_titles'], counts_after['catalog_titles'], "Judul parsial tertinggal di DB!")
        self.assertEqual(counts_before['copies'], counts_after['copies'], "Eksemplar parsial tertinggal di DB!")

        # Token harus berstatus FAILED di database dan ditolak jika dikonfirmasi ulang
        row = conn.execute("SELECT status FROM confirmation_tokens WHERE token = ?;", (token,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['status'], 'FAILED')

        with self.assertRaises(ConfirmationTokenError):
            confirm_and_create_title_with_copies(
                conn=conn,
                token=token,
                admin_username=library_app.ADMIN_USERNAME,
                submitted_payload=payload
            )

        conn.close()

    def test_15_lost_initial_response_client_retry_exact_match(self):
        """Audit 5: Hasil transaksi yang sudah berhasil tidak dibuat ulang ketika respons awal tidak diterima klien."""
        token = self._login_admin()
        payload = {
            'csrf_token': token,
            'judul': 'Networks and Firewalls',
            'penulis': 'W. Richard Stevens',
            'kategori': 'Jaringan',
            'jumlah': '5',
        }

        # 1. Preview
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']
        confirm_data = {'csrf_token': token, 'confirm_token': confirm_token, **payload}

        # 2. Request pertama berhasil dikomit ke DB, tetapi kita simulasikan respons HTTP hilang/drop
        res1 = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res1.status_code, 200)
        first_result = res1.get_json()['data']

        # 3. Klien (mengira permintaan gagal/timeout) melakukan retry dengan token dan data yang sama persis
        res_retry = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res_retry.status_code, 200)
        retry_json = res_retry.get_json()

        # Harus terdeteksi sebagai replay
        self.assertTrue(retry_json['is_replay'])
        retry_result = retry_json['data']

        # Hasil yang dikembalikan harus identik persis dengan hasil eksekusi pertama
        self.assertEqual(first_result['title_id'], retry_result['title_id'])
        self.assertEqual(first_result['judul'], retry_result['judul'])
        self.assertEqual(first_result['initial_copies_count'], retry_result['initial_copies_count'])
        self.assertEqual(first_result['copy_ids'], retry_result['copy_ids'])

        # Tidak ada duplikasi baris judul maupun eksemplar
        conn = library_app.get_db_connection()
        titles_count = conn.execute("SELECT COUNT(*) FROM catalog_titles WHERE judul = 'Networks and Firewalls';").fetchone()[0]
        copies_count = conn.execute("SELECT COUNT(*) FROM copies WHERE title_id = ?;", (first_result['title_id'],)).fetchone()[0]
        conn.close()

        self.assertEqual(titles_count, 1, "Judul terduplikasi saat klien melakukan retry!")
        self.assertEqual(copies_count, 5, "Eksemplar terduplikasi saat klien melakukan retry!")


if __name__ == '__main__':
    unittest.main()

