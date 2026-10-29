# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-09: Cetak Ulang Label Identik + Halaman Eksemplar Tanpa Label.
Sistem Perpustakaan Digital Sekolah.

Acceptance Criteria yang Diuji:
1. Cetak ulang menggunakan ID eksemplar yang sama (tidak membuat ID baru).
2. Payload QR hasil cetak ulang identik deterministik dengan payload sebelumnya.
3. ID teks dan QR tetap cocok 100%.
4. Beberapa eksemplar dapat dipilih tanpa menghasilkan label duplikat yang tidak disengaja.
5. ID yang tidak dikenal ditangani dengan aman tanpa crash dan tanpa membuat label palsu.
6. Halaman eksemplar tanpa label hanya menampilkan kandidat sesuai definisi yang ditetapkan.
7. Buku legacy ditangani sesuai skema aktual (legacy_copy_map & legacy_buku_id pada v2, id_buku_fisik pada P1).
8. Pengguna tanpa login dan non-admin ditolak (HTTP 302 redirect / 401 JSON).
9. Zero-write guarantee: Halaman dan aksi cetak ulang tidak mengubah data katalog, eksemplar, token, atau audit log.
10. Tata letak cetak A4 dan CSS media print dari Task 3-08 tetap berfungsi penuh.
"""
import hashlib
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
from services import (
    get_label_items,
    get_reprint_label_items,
    get_unlabeled_candidates,
    parse_copy_ids,
    format_short_title,
    generate_copy_qr_svg,
    generate_qr_svg,
    Ecc,
)

# Cek OpenCV untuk verifikasi scanning QR fisik
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class BaseReprintAndUnlabeledTestCase(unittest.TestCase):
    """Setup lingkungan uji terisolasi dengan temporary SQLite database."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_reprint_unlabeled.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2 dari migrations
        self._init_v2_schema()

    def tearDown(self):
        os.environ.pop('DATABASE_NAME', None)
        os.environ.pop('SQLITE_TIMEOUT', None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _init_v2_schema(self):
        conn = sqlite3.connect(self.test_db)
        migration_file = os.path.join(ROOT, 'migrations', '0001_initial_v2_schema.sql')
        if os.path.exists(migration_file):
            with open(migration_file, 'r', encoding='utf-8') as f:
                conn.executescript(f.read())
        conn.commit()
        conn.close()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = library_app.ADMIN_USERNAME
            sess['user_role'] = 'admin'
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-309'

    def _login_non_admin(self):
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = 'siswa_test'
            sess['user_role'] = 'user'
            sess['last_active'] = time.time()

    def _seed_sample_catalog_and_legacy(self):
        """Menyiapkan kombinasi buku baru dan buku legacy (migrasi) dengan mapping."""
        conn = sqlite3.connect(self.test_db)

        # 1. Judul Baru (Bukan legacy): Laskar Pelangi (2 eksemplar)
        conn.execute("""
            INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at)
            VALUES ('T-LASKA1', 'Laskar Pelangi', 'Andrea Hirata', '978-979-3062-79-2', 'Fiksi', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-LAS001', 'T-LASKA1', '813 HIR l-1', 'aktif', 'Rak A1', '2026-01-01T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-LAS002', 'T-LASKA1', '813 HIR l-2', 'aktif', 'Rak A1', '2026-01-01T00:00:00Z');
        """)

        # 2. Judul Legacy: Bumi Manusia (Hasil migrasi dari buku id 15, 2 eksemplar)
        conn.execute("""
            INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, legacy_buku_id, created_at, updated_at)
            VALUES ('T-BUMIM1', 'Bumi Manusia', 'Pramoedya Ananta Toer', '978-979-97312-3-4', 'Sastra', 15, '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-BUM001', 'T-BUMIM1', '813 TOE b-1', 'aktif', 'Rak B2', '2026-01-02T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-BUM002', 'T-BUMIM1', '813 TOE b-2', 'aktif', 'Rak B2', '2026-01-02T00:00:00Z');
        """)
        # Peta nomor registrasi legacy
        conn.execute("""
            INSERT INTO legacy_copy_map (old_ref, copy_id, legacy_buku_id)
            VALUES ('00001501', 'C-BUM001', 15);
        """)
        conn.execute("""
            INSERT INTO legacy_copy_map (old_ref, copy_id, legacy_buku_id)
            VALUES ('00001502', 'C-BUM002', 15);
        """)

        # 3. Judul Legacy 2: Kamus Bahasa Indonesia (1 eksemplar aktif, 1 rusak)
        conn.execute("""
            INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, legacy_buku_id, created_at, updated_at)
            VALUES ('T-KAMUS1', 'Kamus Besar Bahasa Indonesia', 'Tim Balai Bahasa', '978-979-00000-0-1', 'Referensi', 8, '2026-01-03T00:00:00Z', '2026-01-03T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-KAM001', 'T-KAMUS1', '413 TIM k-1', 'aktif', 'Rak R1', '2026-01-03T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-KAM002', 'T-KAMUS1', '413 TIM k-2', 'rusak', 'Rak R1', '2026-01-03T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO legacy_copy_map (old_ref, copy_id, legacy_buku_id)
            VALUES ('00000801', 'C-KAM001', 8);
        """)

        conn.commit()
        conn.close()

    def _get_db_hash(self):
        """Menghitung SHA-256 seluruh isi basis data uji."""
        h = hashlib.sha256()
        with open(self.test_db, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()


class AdminLabelsReprintAndAuthTests(BaseReprintAndUnlabeledTestCase):
    """Pengujian Otorisasi dan Akses Route Cetak Ulang & Eksemplar Tanpa Label."""

    def test_01_unauthenticated_reprint_redirects_to_login(self):
        """Pengguna belum login ke /admin/labels/cetak-ulang diarahkan ke /login (HTTP 302)."""
        res = self.client.get('/admin/labels/cetak-ulang', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_02_unauthenticated_unlabeled_redirects_to_login(self):
        """Pengguna belum login ke /admin/labels/tanpa-label diarahkan ke /login (HTTP 302)."""
        res = self.client.get('/admin/labels/tanpa-label', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_03_unauthenticated_api_reprint_returns_401(self):
        """Permintaan JSON tanpa login ke route cetak ulang mengembalikan HTTP 401."""
        res = self.client.get('/admin/labels/cetak-ulang', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get('error'), 'Unauthorized')

    def test_04_unauthenticated_api_unlabeled_returns_401(self):
        """Permintaan JSON tanpa login ke route tanpa-label mengembalikan HTTP 401."""
        res = self.client.get('/admin/labels/tanpa-label', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get('error'), 'Unauthorized')

    def test_05_non_admin_role_rejected(self):
        """Pengguna non-admin (role 'user') ditolak pada route cetak ulang dan tanpa-label."""
        self._login_non_admin()
        res1 = self.client.get('/admin/labels/cetak-ulang', follow_redirects=False)
        self.assertEqual(res1.status_code, 302)
        res2 = self.client.get('/admin/labels/tanpa-label', follow_redirects=False)
        self.assertEqual(res2.status_code, 302)

    def test_06_authenticated_admin_can_access_reprint_form(self):
        """Admin terautentikasi dapat mengakses form cetak ulang (status 200 OK)."""
        self._login_admin()
        res = self.client.get('/admin/labels/cetak-ulang')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('Cetak Ulang Label QR Eksemplar', html)
        self.assertIn('name="copy_ids"', html)

    def test_07_authenticated_admin_can_access_unlabeled_page(self):
        """Admin terautentikasi dapat mengakses halaman eksemplar tanpa label (status 200 OK)."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()
        res = self.client.get('/admin/labels/tanpa-label')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('Eksemplar Tanpa Label', html)
        self.assertIn('Buku Lama di Rak', html)


class LabelReprintDeterministicTests(BaseReprintAndUnlabeledTestCase):
    """Pengujian Determinisme dan Integritas Cetak Ulang Label Eksemplar."""

    def test_08_reprint_uses_exact_same_existing_copy_id(self):
        """Cetak ulang menggunakan ID eksemplar yang sudah ada, tanpa membuat ID baru."""
        self._seed_sample_catalog_and_legacy()
        conn = sqlite3.connect(self.test_db)
        labels = get_reprint_label_items(conn, ['C-BUM001'])
        conn.close()

        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]['copy_id'], 'C-BUM001')
        self.assertEqual(labels[0]['full_title'], 'Bumi Manusia')
        self.assertTrue(labels[0].get('is_reprint'))

    def test_09_reprint_generates_strictly_identical_qr_payload_and_svg(self):
        """Cetak ulang menghasilkan payload dan pola SVG QR yang 100% identik deterministik."""
        cid = 'C-BUM001'
        svg1 = generate_copy_qr_svg(cid)
        svg2 = generate_copy_qr_svg(cid)
        self.assertEqual(svg1, svg2, "Generator QR wajib 100% deterministik untuk ID yang sama")

        # Pastikan tidak ada data sensitif / URL / judul di dalam QR
        self.assertNotIn('Bumi Manusia', svg1)
        self.assertNotIn('http://', svg1.replace('http://www.w3.org/2000/svg', ''))
        self.assertNotIn('https://', svg1)

    @unittest.skipUnless(HAS_OPENCV, "OpenCV tidak tersedia untuk scan fisik QR")
    def test_10_reprinted_qr_decoded_strictly_matches_copy_id(self):
        """QR hasil cetak ulang dipindai menggunakan OpenCV dan terbukti mengembalikan copy_id."""
        cid = 'C-BUM001'
        svg = generate_copy_qr_svg(cid)

        # Parse modul SVG menjadi matriks 2D biner
        import re
        size_match = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        self.assertIsNotNone(size_match)
        dim = int(size_match.group(1))

        matrix = np.full((dim, dim), 255, dtype=np.uint8)
        rects = re.findall(r'<rect x="(\d+)" y="(\d+)" width="1" height="1"', svg)
        for rx, ry in rects:
            matrix[int(ry), int(rx)] = 0

        scale = 12
        large_img = cv2.resize(matrix, (dim * scale, dim * scale), interpolation=cv2.INTER_NEAREST)

        detector = cv2.QRCodeDetector()
        decoded_text, points, _ = detector.detectAndDecode(large_img)
        self.assertEqual(decoded_text, cid)

    def test_11_multiple_copies_reprinted_without_accidental_duplicates(self):
        """Memproses daftar ID yang memuat duplikasi tidak menghasilkan label ganda yang tidak disengaja."""
        self._seed_sample_catalog_and_legacy()
        conn = sqlite3.connect(self.test_db)
        # Kirim ID ganda: C-BUM001 dua kali, C-LAS001 tiga kali
        raw_ids = ['C-BUM001', 'C-BUM001', 'C-LAS001', 'C-BUM001', 'C-LAS001']
        labels = get_reprint_label_items(conn, raw_ids)
        conn.close()

        # Divalidasi hanya menghasilkan 2 label unik
        returned_ids = [lbl['copy_id'] for lbl in labels]
        self.assertEqual(len(returned_ids), 2)
        self.assertIn('C-BUM001', returned_ids)
        self.assertIn('C-LAS001', returned_ids)

    def test_12_parse_copy_ids_handles_newlines_commas_and_spaces(self):
        """parse_copy_ids mem-parsing berbagai delimiter secara bersih dan membuang duplikasi."""
        raw_input = "C-BUM001, C-LAS001; C-BUM002\nC-BUM001   C-KAM001\r\n\r\n"
        cleaned = parse_copy_ids(raw_input)
        expected = ['C-BUM001', 'C-LAS001', 'C-BUM002', 'C-KAM001']
        self.assertEqual(cleaned, expected)

    def test_13_unknown_copy_ids_handled_safely_without_fake_labels(self):
        """ID tidak dikenal (non-existent) ditangani dengan aman tanpa crash dan tanpa membuat label palsu."""
        self._seed_sample_catalog_and_legacy()
        conn = sqlite3.connect(self.test_db)
        labels = get_reprint_label_items(conn, ['C-NONEXISTENT-999', 'C-BUM001'])
        conn.close()

        # Hanya ID yang benar-benar ada yang dikembalikan
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]['copy_id'], 'C-BUM001')

    def test_14_reprint_via_post_endpoint_renders_a4_layout_and_banner(self):
        """POST /admin/labels/cetak-ulang menampilkan mode cetak ulang dan CSS grid A4 Task 3-08."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.post('/admin/labels/cetak-ulang', data={
            'copy_ids': 'C-BUM001, C-BUM002',
            'csrf_token': 'test-valid-csrf-token-309',
        })
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Verifikasi konten dan banner mode cetak ulang
        self.assertIn('Mode Cetak Ulang', html)
        self.assertIn('C-BUM001', html)
        self.assertIn('C-BUM002', html)
        self.assertIn('size: A4 portrait;', html)
        self.assertIn('grid-template-columns: repeat(3, 1fr)', html)
        self.assertIn('page-break-inside: avoid', html)

    def test_15_reprint_api_json_returns_reprint_mode_metadata(self):
        """Permintaan JSON ke /admin/labels/cetak-ulang mengembalikan metadata mode reprint."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.post(
            '/admin/labels/cetak-ulang',
            json={
                'copy_ids': ['C-BUM001', 'C-BUM002'],
                'csrf_token': 'test-valid-csrf-token-309',
            },
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-309'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('mode'), 'reprint')
        self.assertEqual(data.get('total'), 2)
        self.assertEqual(len(data.get('labels', [])), 2)


class UnlabeledCopiesCandidatesTests(BaseReprintAndUnlabeledTestCase):
    """Pengujian Halaman Eksemplar Tanpa Label / Buku Lama di Rak."""

    def test_16_unlabeled_candidates_shows_legacy_copies_by_default(self):
        """Secara default (scope=legacy), hanya eksemplar buku lama migrasi yang ditampilkan."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.get('/admin/labels/tanpa-label?scope=legacy')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Buku legacy harus ada: Bumi Manusia (C-BUM001, C-BUM002), Kamus (C-KAM001)
        self.assertIn('C-BUM001', html)
        self.assertIn('C-BUM002', html)
        self.assertIn('C-KAM001', html)
        self.assertIn('00001501', html)  # Nomor registrasi lama
        self.assertIn('00001502', html)

        # Buku baru (Laskar Pelangi) BUKAN buku legacy sehingga tidak ada dalam filter legacy
        self.assertNotIn('C-LAS001', html)
        self.assertNotIn('C-LAS002', html)

        # Eksemplar rusak (C-KAM002) tidak ditampilkan karena bukan aktif di rak
        self.assertNotIn('C-KAM002', html)

    def test_17_unlabeled_candidates_shows_all_active_when_scope_is_all(self):
        """Jika scope=all, seluruh eksemplar aktif di rak ditampilkan sebagai panduan verifikasi fisik."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.get('/admin/labels/tanpa-label?scope=all')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('C-BUM001', html)
        self.assertIn('C-LAS001', html)
        self.assertIn('C-KAM001', html)

    def test_18_unlabeled_candidates_filters_by_search_query(self):
        """Pencarian q menyaring berdasarkan ID eksemplar, nomor registrasi lama, judul, atau penulis."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        # Cari berdasarkan nomor registrasi lama
        res = self.client.get('/admin/labels/tanpa-label?q=00001501')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('C-BUM001', html)
        self.assertNotIn('C-KAM001', html)

        # Cari berdasarkan penulis
        res2 = self.client.get('/admin/labels/tanpa-label?q=Pramoedya')
        self.assertEqual(res2.status_code, 200)
        html2 = res2.get_data(as_text=True)
        self.assertIn('C-BUM001', html2)
        self.assertIn('C-BUM002', html2)
        self.assertNotIn('C-KAM001', html2)

    def test_19_unlabeled_candidates_filters_by_lokasi_rak(self):
        """Filter lokasi rak menyaring eksemplar yang berada pada rak tertentu."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.get('/admin/labels/tanpa-label?lokasi_rak=Rak%20R1')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('C-KAM001', html)
        self.assertNotIn('C-BUM001', html)

    def test_20_unlabeled_candidates_empty_state_without_fake_labels(self):
        """Jika tidak ada eksemplar yang cocok, tampilkan pesan kosong informatif tanpa membuat label palsu."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.get('/admin/labels/tanpa-label?q=JudulTidakAdaSamaSekali999')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('Tidak Ada Eksemplar yang Ditemukan', html)
        self.assertNotIn('name="copy_ids"', html)

    def test_21_unlabeled_candidates_api_json_format(self):
        """Permintaan API JSON ke /admin/labels/tanpa-label mengembalikan daftar kandidat terstruktur."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        res = self.client.get('/admin/labels/tanpa-label', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertIn('candidates', data)
        self.assertGreaterEqual(len(data['candidates']), 3)
        first = data['candidates'][0]
        self.assertIn('copy_id', first)
        self.assertIn('full_title', first)
        self.assertIn('short_title', first)
        self.assertIn('lokasi_rak', first)


class ZeroWriteAndIntegrityTests(BaseReprintAndUnlabeledTestCase):
    """Pengujian Zero-Write dan Integritas Basis Data."""

    def test_22_zero_write_guarantee_on_reprint_and_unlabeled(self):
        """Membuka halaman cetak ulang dan tanpa-label tidak mengubah basis data sama sekali."""
        self._login_admin()
        self._seed_sample_catalog_and_legacy()

        hash_before = self._get_db_hash()

        # 1. Buka halaman tanpa-label (HTML & JSON)
        self.client.get('/admin/labels/tanpa-label')
        self.client.get('/admin/labels/tanpa-label', headers={'Accept': 'application/json'})

        # 2. Buka form cetak ulang
        self.client.get('/admin/labels/cetak-ulang')

        # 3. Jalankan aksi cetak ulang (POST HTML & JSON)
        self.client.post('/admin/labels/cetak-ulang', data={
            'copy_ids': 'C-BUM001, C-BUM002',
            'csrf_token': 'test-valid-csrf-token-309',
        })
        self.client.post(
            '/admin/labels/cetak-ulang',
            json={'copy_ids': ['C-BUM001'], 'csrf_token': 'test-valid-csrf-token-309'},
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-309'}
        )

        hash_after = self._get_db_hash()
        self.assertEqual(hash_before, hash_after, "Operasi Task 3-09 wajib 100% Zero-Write")

    def test_23_legacy_p1_schema_fallback_handling(self):
        """Memverifikasi penanganan skema legacy P1 (tabel buku) tanpa membuat label palsu."""
        # Buat database terpisah dengan skema buku legacy saja
        legacy_db = os.path.join(self.test_dir, 'legacy_p1.db')
        conn = sqlite3.connect(legacy_db)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE buku (
                id INTEGER PRIMARY KEY,
                judul TEXT,
                penulis TEXT,
                isbn TEXT,
                kategori TEXT,
                lokasi_rak TEXT,
                tanggal_masuk TEXT,
                id_buku_fisik TEXT
            );
        """)
        # Buku 1: Ada 2 nomor registrasi valid
        conn.execute("""
            INSERT INTO buku (id, judul, penulis, isbn, kategori, lokasi_rak, tanggal_masuk, id_buku_fisik)
            VALUES (1, 'Fisika Dasar', 'Halliday', '1234567890', 'Sains', 'Rak S1', '2026-01-01', '["00000101", "00000102"]');
        """)
        # Buku 2: id_buku_fisik kosong / NULL (tidak boleh dibuat label palsu)
        conn.execute("""
            INSERT INTO buku (id, judul, penulis, isbn, kategori, lokasi_rak, tanggal_masuk, id_buku_fisik)
            VALUES (2, 'Buku Tanpa Fisik', 'Penulis X', '9999999999', 'Umum', 'Rak U1', '2026-01-01', NULL);
        """)
        conn.commit()

        candidates = get_unlabeled_candidates(conn)
        conn.close()

        # Hanya eksemplar dengan nomor registrasi valid yang dikembalikan (2 eksemplar)
        self.assertEqual(len(candidates), 2)
        cids = [c['copy_id'] for c in candidates]
        self.assertIn('00000101', cids)
        self.assertIn('00000102', cids)
        # Pastikan tidak ada label palsu seperti C-2 atau dummy ID
        self.assertNotIn('C-2', cids)


if __name__ == '__main__':
    unittest.main()
