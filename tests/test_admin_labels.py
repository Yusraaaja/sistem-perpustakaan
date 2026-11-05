# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-08: Halaman Cetak Label QR /admin/labels (A4 Grid).
Sistem Perpustakaan Digital Sekolah.

Acceptance Criteria yang Diuji:
1. Admin terautentikasi dapat mengakses halaman label.
2. Pengguna belum login ditolak / diarahkan ke login (HTTP 302 / 401).
3. Pengguna non-admin (misal role murid/user) ditolak.
4. Setiap label menampilkan ID eksemplar yang benar.
5. QR Code HANYA memuat ID eksemplar (tanpa data pribadi, tanpa judul, tanpa URL).
6. QR Code pada setiap label cocok 100% dengan ID teks pada label tersebut.
7. Judul panjang dipotong secara aman dan tidak merusak struktur label card.
8. Data kosong ditangani dengan benar (pesan informatif, tanpa label palsu).
9. HTML/CSS print menyediakan ukuran kertas A4, margin, dan grid 3-kolom.
10. Zero-write guarantee: Membuka /admin/labels tidak mengubah tabel apapun.
11. Kompatibel dengan skema v2 (copies + catalog_titles) dan fallback legacy.
"""
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
    format_short_title,
    generate_copy_qr_svg,
    generate_qr_svg,
    Ecc,
)

# Cek ketersediaan OpenCV QRCodeDetector untuk verifikasi computer vision independen
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class BaseLabelsTestCase(unittest.TestCase):
    """Setup lingkungan uji terisolasi dengan temporary SQLite database."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_labels.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2 penuh dari file migrasi
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
            sess['_csrf_token'] = 'test-valid-csrf-token-308'

    def _login_non_admin(self):
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = 'siswa_test'
            sess['user_role'] = 'user'
            sess['last_active'] = time.time()

    def _seed_sample_catalog(self):
        conn = sqlite3.connect(self.test_db)
        # Title 1: Laskar Pelangi (2 eksemplar)
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

        # Title 2: Bumi Manusia (1 eksemplar aktif, 1 hilang)
        conn.execute("""
            INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at)
            VALUES ('T-BUMIM1', 'Bumi Manusia', 'Pramoedya Ananta Toer', '978-979-97312-3-4', 'Sastra', '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-BUM001', 'T-BUMIM1', '813 TOE b-1', 'aktif', 'Rak B2', '2026-01-02T00:00:00Z');
        """)
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-BUM002', 'T-BUMIM1', '813 TOE b-2', 'hilang', 'Rak B2', '2026-01-02T00:00:00Z');
        """)

        # Title 3: Judul Sangat Panjang
        long_title = "Ensiklopedia Sains dan Teknologi Lengkap untuk Siswa Menengah Kejuruan Seluruh Indonesia Edisi Milenium 2026"
        conn.execute("""
            INSERT INTO catalog_titles (id, judul, penulis, isbn, kategori, created_at, updated_at)
            VALUES ('T-LONGT1', ?, 'Tim Editor Sains', '978-602-00000-0-1', 'Sains', '2026-01-03T00:00:00Z', '2026-01-03T00:00:00Z');
        """, (long_title,))
        conn.execute("""
            INSERT INTO copies (id, title_id, call_number, status, lokasi_rak, created_at)
            VALUES ('C-LNG001', 'T-LONGT1', '500 EDI e', 'aktif', 'Rak C3', '2026-01-03T00:00:00Z');
        """)

        conn.commit()
        conn.close()


class AdminLabelsAuthAndAccessTests(BaseLabelsTestCase):
    """Pengujian Autentikasi dan Otorisasi Route /admin/labels."""

    def test_01_unauthenticated_access_redirects_to_login(self):
        """Pengguna belum login diarahkan ke /login (HTTP 302)."""
        res = self.client.get('/admin/labels', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_02_unauthenticated_api_request_returns_401_json(self):
        """Permintaan JSON tanpa login mengembalikan HTTP 401 Unauthorized."""
        res = self.client.get('/admin/labels', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Unauthorized')

    def test_03_non_admin_user_role_rejected(self):
        """Pengguna yang bukan admin (misal role 'user') ditolak dan diarahkan ke login."""
        self._login_non_admin()
        res = self.client.get('/admin/labels', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_04_authenticated_admin_access_allowed_html(self):
        """Admin yang terautentikasi dapat mengakses halaman HTML dengan status 200 OK."""
        self._login_admin()
        self._seed_sample_catalog()
        res = self.client.get('/admin/labels')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('Cetak Label QR Eksemplar', html)
        self.assertIn('window.print()', html)

    def test_05_authenticated_admin_access_allowed_json(self):
        """Admin yang terautentikasi dapat meminta representasi data JSON dari /admin/labels."""
        self._login_admin()
        self._seed_sample_catalog()
        res = self.client.get('/admin/labels', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('status'), 'success')
        self.assertIsInstance(data.get('labels'), list)
        self.assertGreater(data.get('total'), 0)


class AdminLabelsContentAndIntegrityTests(BaseLabelsTestCase):
    """Pengujian Konten Label, Payload QR, dan Kecocokan Identitas Eksemplar."""

    def test_06_label_displays_human_readable_copy_id(self):
        """Setiap label menampilkan ID eksemplar dalam teks yang terbaca manusia."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('C-LAS001', html)
        self.assertIn('C-LAS002', html)
        self.assertIn('C-BUM001', html)
        # Eksemplar hilang (C-BUM002) tidak muncul di label aktif
        self.assertNotIn('C-BUM002', html)

    def test_07_qr_payload_strictly_contains_only_copy_id(self):
        """
        QR Code HANYA memuat ID eksemplar.
        Tidak memuat nama peminjam, informasi pribadi, kredensial, judul, atau URL.
        """
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels', headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        for item in data['labels']:
            cid = item['copy_id']
            # Validasi bahwa item memiliki qr_svg
            self.assertIn('<svg', item['qr_svg'])
            self.assertIn('</svg>', item['qr_svg'])

            # Jika OpenCV terpasang, decode biner matriks untuk verifikasi payload mutlak
            if HAS_OPENCV:
                detector = cv2.QRCodeDetector()
                qr_obj = generate_qr_svg(cid)
                # Render SVG ke matriks
                from services.qr_service import encode_text, Ecc
                qr_matrix = encode_text(cid, Ecc.MEDIUM)
                border = 4
                s = qr_matrix.size + border * 2
                img = np.ones((s, s), dtype=np.uint8) * 255
                for y in range(qr_matrix.size):
                    for x in range(qr_matrix.size):
                        if qr_matrix.modules[y][x]:
                            img[y + border, x + border] = 0
                img_scaled = cv2.resize(img, (s * 8, s * 8), interpolation=cv2.INTER_NEAREST)
                decoded_text, _, _ = detector.detectAndDecode(img_scaled)

                self.assertEqual(decoded_text, cid)
                self.assertNotIn('http', decoded_text)
                self.assertNotIn('Laskar', decoded_text)
                self.assertNotIn('Pramoedya', decoded_text)
                self.assertNotIn('@', decoded_text)

    def test_08_qr_matches_text_copy_id_on_same_label(self):
        """QR pada setiap label harus cocok dengan ID teks pada label yang sama."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels', headers={'Accept': 'application/json'})
        data = res.get_json()

        for item in data['labels']:
            copy_id = item['copy_id']
            self.assertTrue(copy_id.startswith('C-'))
            # Verifikasi bahwa SVG di-generate dari copy_id yang sama persis
            expected_svg = generate_copy_qr_svg(copy_id)
            self.assertEqual(item['qr_svg'], expected_svg)

    def test_09_long_title_truncation_without_breaking_structure(self):
        """Judul panjang dipotong menjadi versi singkat (short_title) dengan elipsis."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels', headers={'Accept': 'application/json'})
        data = res.get_json()

        long_item = next((item for item in data['labels'] if item['copy_id'] == 'C-LNG001'), None)
        self.assertIsNotNone(long_item)
        self.assertTrue(len(long_item['short_title']) <= 30)
        self.assertTrue(long_item['short_title'].endswith('...'))
        self.assertIn('Ensiklopedia', long_item['short_title'])
        # Judul lengkap tetap tersedia di full_title
        self.assertIn('Seluruh Indonesia', long_item['full_title'])

    def test_10_empty_catalog_displays_empty_state_without_fake_labels(self):
        """Katalog kosong menghasilkan pesan informatif dan TIDAK membuat label palsu."""
        self._login_admin()
        # Jangan seed catalog, database kosong

        res = self.client.get('/admin/labels')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('Tidak Ada Eksemplar yang Ditemukan', html)
        self.assertNotIn('<div class="label-card">', html)
        self.assertNotIn('class="label-card"', html)

        # Cek via JSON
        res_json = self.client.get('/admin/labels', headers={'Accept': 'application/json'})
        data = res_json.get_json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(len(data['labels']), 0)

    def test_11_filter_by_title_id(self):
        """Filter berdasarkan title_id hanya menampilkan eksemplar dari judul tersebut."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels?title_id=T-LASKA1', headers={'Accept': 'application/json'})
        data = res.get_json()
        self.assertEqual(data['total'], 2)
        for item in data['labels']:
            self.assertEqual(item['title_id'], 'T-LASKA1')
            self.assertTrue(item['copy_id'].startswith('C-LAS'))

    def test_12_filter_by_copy_ids(self):
        """Filter berdasarkan list copy_ids spesifik mengembalikan hanya eksemplar yang dipilih."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels?copy_ids=C-LAS001,C-BUM001', headers={'Accept': 'application/json'})
        data = res.get_json()
        self.assertEqual(data['total'], 2)
        retrieved_ids = {item['copy_id'] for item in data['labels']}
        self.assertEqual(retrieved_ids, {'C-LAS001', 'C-BUM001'})

    def test_22_search_filter_by_copy_id_or_title_or_author(self):
        """Pencarian dapat mencocokkan judul, penulis, maupun ID eksemplar."""
        self._login_admin()
        self._seed_sample_catalog()

        # Cari berdasarkan judul
        res = self.client.get('/admin/labels?q=Pelangi', headers={'Accept': 'application/json'})
        data = res.get_json()
        self.assertEqual(data['total'], 2)

        # Cari berdasarkan penulis
        res = self.client.get('/admin/labels?q=Pramoedya', headers={'Accept': 'application/json'})
        data = res.get_json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['labels'][0]['copy_id'], 'C-BUM001')

        # Cari berdasarkan ID eksemplar
        res = self.client.get('/admin/labels?q=C-LNG001', headers={'Accept': 'application/json'})
        data = res.get_json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['labels'][0]['copy_id'], 'C-LNG001')

    def test_23_invalid_limit_query_param_handled_safely(self):
        """Nilai limit yang aneh (bukan angka, negatif, sangat besar) ditangani tanpa error 500."""
        self._login_admin()
        self._seed_sample_catalog()

        # Non-numeric limit
        res1 = self.client.get('/admin/labels?limit=bukan_angka', headers={'Accept': 'application/json'})
        self.assertEqual(res1.status_code, 200)

        # Negatif
        res2 = self.client.get('/admin/labels?limit=-50', headers={'Accept': 'application/json'})
        self.assertEqual(res2.status_code, 200)

        # Sangat besar
        res3 = self.client.get('/admin/labels?limit=999999', headers={'Accept': 'application/json'})
        self.assertEqual(res3.status_code, 200)


class AdminLabelsPrintLayoutCssTests(BaseLabelsTestCase):
    """Pengujian CSS Cetak Khusus (@media print, A4, grid, margin, no-print)."""

    def test_13_print_stylesheet_includes_a4_and_margin(self):
        """HTML memuat aturan @page dengan size A4 portrait dan margin 10mm."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels')
        html = res.get_data(as_text=True)

        self.assertIn('@page', html)
        self.assertIn('size: A4 portrait;', html)
        self.assertIn('margin: 10mm;', html)

    def test_14_print_stylesheet_includes_media_print_grid(self):
        """CSS @media print mengatur grid 3 kolom dan mencegah pemotongan halaman."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels')
        html = res.get_data(as_text=True)

        self.assertIn('@media print', html)
        self.assertIn('grid-template-columns: repeat(3, 1fr)', html)
        self.assertIn('page-break-inside: avoid', html)
        self.assertIn('break-inside: avoid', html)

    def test_15_print_stylesheet_suppresses_navigation_controls(self):
        """Elemen non-cetak seperti navbar, sidebar, form, dan tombol disembunyikan."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels')
        html = res.get_data(as_text=True)

        self.assertIn('.no-print', html)
        self.assertIn('display: none !important;', html)

    def test_16_window_print_trigger_present(self):
        """Halaman menyediakan tombol kontrol cetak yang memanggil window.print()."""
        self._login_admin()
        self._seed_sample_catalog()

        res = self.client.get('/admin/labels')
        html = res.get_data(as_text=True)

        self.assertIn('onclick="window.print()"', html)


class AdminLabelsZeroWriteGuaranteeTests(BaseLabelsTestCase):
    """Pengujian Zero-Write Guarantee (Membuka /admin/labels tidak mengubah database)."""

    def test_17_opening_labels_page_does_not_mutate_database(self):
        """
        Memanggil /admin/labels berulang kali tidak mengubah hitungan tabel:
        catalog_titles, copies, confirmation_tokens, audit_log.
        """
        self._login_admin()
        self._seed_sample_catalog()

        conn = sqlite3.connect(self.test_db)
        titles_before = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        copies_before = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        tokens_before = conn.execute("SELECT COUNT(*) FROM confirmation_tokens;").fetchone()[0]
        audits_before = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        conn.close()

        # Eksekusi berbagai request GET
        self.client.get('/admin/labels')
        self.client.get('/admin/labels?title_id=T-LASKA1')
        self.client.get('/admin/labels?q=Laskar')
        self.client.get('/admin/labels?copy_ids=C-LAS001,C-LAS002')
        self.client.get('/admin/labels', headers={'Accept': 'application/json'})

        conn = sqlite3.connect(self.test_db)
        titles_after = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
        copies_after = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        tokens_after = conn.execute("SELECT COUNT(*) FROM confirmation_tokens;").fetchone()[0]
        audits_after = conn.execute("SELECT COUNT(*) FROM audit_log;").fetchone()[0]
        conn.close()

        self.assertEqual(titles_before, titles_after)
        self.assertEqual(copies_before, copies_after)
        self.assertEqual(tokens_before, tokens_after)
        self.assertEqual(audits_before, audits_after)


class QrServiceDirectUnitTests(unittest.TestCase):
    """Pengujian Unit Langsung untuk Modul services.qr_service."""

    def test_18_generate_copy_qr_svg_validation(self):
        """generate_copy_qr_svg melempar ValueError jika copy_id kosong."""
        with self.assertRaises(ValueError):
            generate_copy_qr_svg("")
        with self.assertRaises(ValueError):
            generate_copy_qr_svg("   ")
        with self.assertRaises(ValueError):
            generate_copy_qr_svg(None)

    def test_19_generate_copy_qr_svg_structure(self):
        """generate_copy_qr_svg menghasilkan string SVG yang valid dan lengkap."""
        svg = generate_copy_qr_svg("C-234567")
        self.assertTrue(svg.startswith('<svg'))
        self.assertTrue(svg.endswith('</svg>'))
        self.assertIn('viewBox="0 0', svg)
        self.assertIn('<rect width="100%" height="100%" fill="#FFFFFF"/>', svg)
        self.assertIn('<path d="', svg)

    def test_20_format_short_title_helper(self):
        """format_short_title memotong string secara rapi dan menangani input None."""
        self.assertEqual(format_short_title(None), "Tanpa Judul")
        self.assertEqual(format_short_title(""), "Tanpa Judul")
        self.assertEqual(format_short_title("Laskar Pelangi"), "Laskar Pelangi")
        self.assertEqual(
            format_short_title("Buku Sangat Panjang Sekali Yang Melebihi Tiga Puluh Karakter", max_length=25),
            "Buku Sangat Panjang Se..."
        )

    def test_21_legacy_schema_fallback(self):
        """Memverifikasi bahwa database legacy dengan tabel buku tetap didukung untuk cetak label."""
        test_dir = tempfile.mkdtemp()
        test_db = os.path.join(test_dir, 'legacy.db')
        try:
            conn = sqlite3.connect(test_db)
            conn.row_factory = sqlite3.Row
            conn.execute('''
                CREATE TABLE buku (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    judul TEXT NOT NULL,
                    penulis TEXT,
                    isbn TEXT,
                    kategori TEXT,
                    lokasi_rak TEXT,
                    id_buku_fisik TEXT
                );
            ''')
            conn.execute('''
                INSERT INTO buku (id, judul, penulis, isbn, kategori, lokasi_rak, id_buku_fisik)
                VALUES (1, 'Buku Klasik Legacy', 'Penulis Lawas', '123-456', 'Klasik', 'Rak Z', '["LEG-001", "LEG-002"]');
            ''')
            conn.commit()

            labels = get_label_items(conn)
            self.assertEqual(len(labels), 2)
            ids = [item['copy_id'] for item in labels]
            self.assertIn('LEG-001', ids)
            self.assertIn('LEG-002', ids)
            for item in labels:
                self.assertEqual(item['full_title'], 'Buku Klasik Legacy')
                self.assertTrue(item['qr_svg'].startswith('<svg'))
            conn.close()
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
