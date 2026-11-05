# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-04: Peringatan Judul Mirip & Deteksi Potensi Duplikat.
Memverifikasi:
1. ISBN sama dengan format tanda hubung/spasi berbeda memicu peringatan.
2. ISBN berbeda tidak memicu peringatan berdasarkan ISBN.
3. ISBN kosong pada kedua rekaman tidak dianggap cocok hanya karena sama-sama kosong.
4. Judul dan penulis yang sama setelah normalisasi memicu peringatan.
5. Perbedaan kapitalisasi dan spasi berlebih ditangani konsisten.
6. Judul sama tetapi penulis berbeda tidak otomatis dianggap duplikat.
7. Judul mirip tetapi jelas berbeda tidak menghasilkan peringatan palsu yang tidak wajar.
8. Beberapa kandidat cocok ditampilkan secara aman dan konsisten.
9. Tidak ada kandidat yang cocok menghasilkan preview normal.
10. Preview dengan peringatan tidak menulis ke database (zero-write terbukti).
11. Admin dapat melanjutkan sesuai alur resmi dan membuat rekaman baru yang terpisah; data lama tidak pernah digabung atau ditimpa (DEC-013).
12. Payload atau peringatan yang dimanipulasi klien tidak dapat melewati pemeriksaan server.
13. Pengiriman ulang token tetap idempoten.
14. Unit testing mendalam untuk fungsi normalisasi teks dan ISBN.
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
from services.catalog_service import (
    normalize_text,
    normalize_isbn,
    are_isbns_matching,
    are_titles_and_authors_matching,
    find_similar_catalog_titles,
    create_title_with_copies,
    clear_confirmation_tokens,
)
from services.exceptions import ConfirmationTokenError


class BaseDuplicateWarningTestCase(unittest.TestCase):
    """Setup lingkungan terisolasi dengan database sementara skema v2."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_dup_warning.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2
        library_app.init_db(self.test_db)
        self._init_v2_schema()
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
            sess['_csrf_token'] = 'test-valid-csrf-token-304'
        return 'test-valid-csrf-token-304'

    def _seed_book(self, judul, penulis, isbn=None, kategori='Umum', copies_count=3):
        """Helper membuat satu buku katalog awal di database."""
        conn = library_app.get_db_connection()
        try:
            title = create_title_with_copies(
                conn=conn,
                title_data={
                    'judul': judul,
                    'penulis': penulis,
                    'isbn': isbn,
                    'kategori': kategori,
                },
                initial_copies=copies_count,
                actor='admin_seeder'
            )
            return title
        finally:
            conn.close()

    def _get_db_counts(self):
        """Menghitung jumlah baris aktual pada catalog_titles dan copies."""
        conn = library_app.get_db_connection()
        try:
            titles = conn.execute("SELECT COUNT(*) FROM catalog_titles;").fetchone()[0]
            copies = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
            return {'catalog_titles': titles, 'copies': copies}
        finally:
            conn.close()


class DuplicateTitleUnitNormalizationTests(unittest.TestCase):
    """Pengujian unit mendalam untuk fungsi normalisasi dan pencocokan teks/ISBN."""

    def test_normalize_isbn_rules(self):
        # Format tanda hubung dan spasi
        self.assertEqual(normalize_isbn("978-602-000-099-2"), "9786020000992")
        self.assertEqual(normalize_isbn("978 602 000 099 2"), "9786020000992")
        self.assertEqual(normalize_isbn("9786020000992"), "9786020000992")
        self.assertEqual(normalize_isbn("  0-321-12521-5  "), "0321125215")
        # ISBN-10 check digit X
        self.assertEqual(normalize_isbn("0-321-12521-x"), "032112521X")
        self.assertEqual(normalize_isbn("032112521X"), "032112521X")
        # Kosong dan None
        self.assertIsNone(normalize_isbn(""))
        self.assertIsNone(normalize_isbn("   "))
        self.assertIsNone(normalize_isbn(None))

    def test_are_isbns_matching_rules(self):
        # ISBN sama dengan variasi tanda hubung/spasi
        self.assertTrue(are_isbns_matching("978-602-000-099-2", "9786020000992"))
        self.assertTrue(are_isbns_matching("978 602 000 099 2", "978-602-000-099-2"))
        self.assertTrue(are_isbns_matching("0-321-12521-x", "032112521X"))
        # ISBN berbeda
        self.assertFalse(are_isbns_matching("978-602-000-099-2", "978-602-000-099-3"))
        # Aturan Kritis 3: Dua ISBN kosong tidak boleh dianggap cocok
        self.assertFalse(are_isbns_matching(None, None))
        self.assertFalse(are_isbns_matching("", ""))
        self.assertFalse(are_isbns_matching(None, "978-602-000-099-2"))
        self.assertFalse(are_isbns_matching("978-602-000-099-2", None))

    def test_normalize_text_rules(self):
        self.assertEqual(normalize_text("Laskar Pelangi"), "laskar pelangi")
        self.assertEqual(normalize_text("  LASKAR   PELANGI.  "), "laskar pelangi")
        self.assertEqual(normalize_text("Harry Potter: Kamar Rahasia!"), "harry potter kamar rahasia")
        self.assertEqual(normalize_text("Anak-Anak Revolusi"), "anak anak revolusi")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")

    def test_are_titles_and_authors_matching_rules(self):
        # 1. Judul dan penulis sama persis
        match, reason = are_titles_and_authors_matching(
            "Laskar Pelangi", "Andrea Hirata",
            "laskar pelangi", "andrea hirata"
        )
        self.assertTrue(match)
        self.assertIn("sama persis", reason)

        # 2. Judul sama tetapi penulis berbeda -> BUKAN duplikat
        match, reason = are_titles_and_authors_matching(
            "Fisika Dasar", "David Halliday",
            "Fisika Dasar", "Sutrisno"
        )
        self.assertFalse(match)
        self.assertIsNone(reason)

        # 3. Judul dengan angka berbeda -> BUKAN duplikat (misal buku kelas/jilid)
        match, reason = are_titles_and_authors_matching(
            "Matematika SMA Kelas 1", "Budi Raharjo",
            "Matematika SMA Kelas 2", "Budi Raharjo"
        )
        self.assertFalse(match)

        # 4. Judul sangat mirip typo minor dengan penulis sama -> Cocok
        match, reason = are_titles_and_authors_matching(
            "Laskar Pelangi", "Andrea Hirata",
            "Laskar Pelangii", "Andrea Hirata"
        )
        self.assertTrue(match)
        self.assertIn("sangat mirip", reason)

        # 5. Judul berbeda dengan penulis sama -> BUKAN duplikat
        match, reason = are_titles_and_authors_matching(
            "Laskar Pelangi", "Andrea Hirata",
            "Sang Pemimpi", "Andrea Hirata"
        )
        self.assertFalse(match)


class DuplicateTitleWarningIntegrationTests(BaseDuplicateWarningTestCase):
    """Pengujian integrasi rute /buku/tambah dan alur konfirmasi Task 3-04."""

    def test_01_same_isbn_with_different_hyphens_or_spaces_triggers_warning(self):
        """Kriteria 1: ISBN sama dengan perbedaan tanda hubung/spasi memicu peringatan duplikat."""
        self._seed_book(
            judul="Ensiklopedia Sains Alam",
            penulis="Dr. Bambang",
            isbn="978-602-000-099-2",
            kategori="Sains"
        )

        csrf_token = self._login_admin()
        # Input dengan ISBN tanpa tanda hubung
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Buku Sains Terbaru',
            'penulis': 'Prof. Joko',
            'kategori': 'Sains',
            'isbn': '9786020000992',  # Format bersih tanpa tanda hubung
            'jumlah': '5',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 1)
        candidate = data['duplicate_candidates'][0]
        self.assertEqual(candidate['judul'], "Ensiklopedia Sains Alam")
        self.assertTrue(any("ISBN" in r for r in candidate['reasons']))

    def test_02_different_isbn_does_not_trigger_isbn_warning(self):
        """Kriteria 2: ISBN berbeda tidak memicu peringatan berdasarkan ISBN."""
        self._seed_book(
            judul="Buku Sejarah Indonesia",
            penulis="Sartono Kartodirdjo",
            isbn="978-602-000-099-2",
            kategori="Sejarah"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Biologi Sel Molekuler',
            'penulis': 'Bruce Alberts',
            'kategori': 'Biologi',
            'isbn': '978-602-000-099-3',  # Digit terakhir berbeda
            'jumlah': '3',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertFalse(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 0)

    def test_03_empty_isbns_on_both_records_not_considered_match(self):
        """Kriteria 3: ISBN kosong pada kedua rekaman tidak dianggap cocok hanya karena sama-sama kosong."""
        self._seed_book(
            judul="Kumpulan Cerpen Klasik",
            penulis="Pramoedya Ananta Toer",
            isbn=None,
            kategori="Sastra"
        )

        csrf_token = self._login_admin()
        # Input tanpa ISBN dengan judul & penulis berbeda
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Kamus Bahasa Daerah',
            'penulis': 'Tim Pusat Bahasa',
            'kategori': 'Bahasa',
            'isbn': '',  # Kosong
            'jumlah': '2',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertFalse(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 0)

    def test_04_same_title_and_author_after_normalization_triggers_warning(self):
        """Kriteria 4: Judul dan penulis sama setelah normalisasi memicu peringatan."""
        self._seed_book(
            judul="Filosofi Teras",
            penulis="Henry Manampiring",
            isbn=None,
            kategori="Filsafat"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'filosofi teras',
            'penulis': 'henry manampiring',
            'kategori': 'Filsafat',
            'isbn': '',
            'jumlah': '4',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 1)
        cand = data['duplicate_candidates'][0]
        self.assertEqual(cand['judul'], "Filosofi Teras")
        self.assertTrue(any("Judul dan penulis" in r for r in cand['reasons']))

    def test_05_capitalization_and_excess_whitespace_handled_consistently(self):
        """Kriteria 5: Perbedaan kapitalisasi, tanda baca, dan spasi berlebih ditangani konsisten."""
        self._seed_book(
            judul="Laskar Pelangi",
            penulis="Andrea Hirata",
            isbn=None,
            kategori="Novel"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': '   LASKAR    PELANGI!   ',
            'penulis': '   andrea   hirata.   ',
            'kategori': 'Novel',
            'jumlah': '5',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 1)

    def test_06_same_title_different_author_not_duplicate(self):
        """Kriteria 6: Judul sama tetapi penulis berbeda tidak otomatis dianggap duplikat."""
        self._seed_book(
            judul="Fisika Dasar",
            penulis="David Halliday",
            kategori="Sains"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Fisika Dasar',
            'penulis': 'Sutrisno',  # Penulis berbeda
            'kategori': 'Sains',
            'jumlah': '10',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertFalse(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 0)

    def test_07_similar_title_clearly_different_no_false_positive(self):
        """Kriteria 7: Judul mirip tetapi jelas berbeda tidak menghasilkan peringatan palsu."""
        # Buku Seri Kelas 1
        self._seed_book(
            judul="Matematika SMA Kelas 1",
            penulis="Tim Penulis Guru",
            kategori="Pelajaran"
        )

        csrf_token = self._login_admin()
        # Input Buku Seri Kelas 2 oleh penulis yang sama
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Matematika SMA Kelas 2',
            'penulis': 'Tim Penulis Guru',
            'kategori': 'Pelajaran',
            'jumlah': '15',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertFalse(data['duplicate_warning'], "Kelas 2 tidak boleh cocok dengan Kelas 1!")
        self.assertEqual(len(data['duplicate_candidates']), 0)

    def test_08_multiple_matching_candidates_displayed_safely(self):
        """Kriteria 8: Beberapa kandidat cocok ditampilkan secara aman dan konsisten."""
        # Buku 1 cocok karena ISBN sama
        self._seed_book(
            judul="Clean Code Architecture",
            penulis="Robert C. Martin",
            isbn="978-013-235-088-4",
            kategori="Komputer"
        )
        # Buku 2 cocok karena Judul dan Penulis sama
        self._seed_book(
            judul="Clean Code",
            penulis="Robert C. Martin",
            isbn="978-013-999-999-9",
            kategori="Komputer"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Clean Code',
            'penulis': 'Robert C. Martin',
            'kategori': 'Komputer',
            'isbn': '9780132350884',  # Cocok ISBN buku 1, dan cocok judul+penulis buku 2
            'jumlah': '3',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 2)

    def test_09_no_matching_candidate_produces_normal_preview(self):
        """Kriteria 9: Tidak ada kandidat yang cocok menghasilkan preview normal."""
        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Buku Unik Pertama di Perpustakaan',
            'penulis': 'Penulis Baru',
            'kategori': 'Umum',
            'isbn': '978-111-222-333-4',
            'jumlah': '5',
        }

        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertFalse(data['duplicate_warning'])
        self.assertEqual(len(data['duplicate_candidates']), 0)
        self.assertIn('Belum ada perubahan yang ditulis', data['message'])

    def test_10_preview_with_warning_does_not_write_to_database_zero_write(self):
        """Kriteria 10: Preview dengan peringatan TIDAK menulis ke database (zero-write terbukti)."""
        self._seed_book(
            judul="Atlas Indonesia dan Dunia",
            penulis="Badan Informasi Geospasial",
            isbn="978-602-123-456-7",
            copies_count=4
        )
        counts_before = self._get_db_counts()
        self.assertEqual(counts_before['catalog_titles'], 1)
        self.assertEqual(counts_before['copies'], 4)

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Atlas Indonesia dan Dunia',
            'penulis': 'Badan Informasi Geospasial',
            'kategori': 'Geografi',
            'isbn': '9786021234567',
            'jumlah': '10',
        }

        # Eksekusi preview
        res = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['duplicate_warning'])

        # Verifikasi strictly zero-write: tidak ada penambahan judul maupun eksemplar
        counts_after = self._get_db_counts()
        self.assertEqual(counts_before['catalog_titles'], counts_after['catalog_titles'])
        self.assertEqual(counts_before['copies'], counts_after['copies'])

    def test_11_admin_can_proceed_creating_separate_new_record_without_merging(self):
        """Kriteria 11: Admin dapat melanjutkan konfirmasi dan membuat rekaman baru terpisah (DEC-013, tidak gabung diam-diam)."""
        seeded = self._seed_book(
            judul="Kamus Besar Bahasa Indonesia",
            penulis="Pusat Bahasa",
            isbn="978-979-407-182-3",
            copies_count=5
        )
        seeded_id = seeded['id']
        counts_before = self._get_db_counts()
        self.assertEqual(counts_before['catalog_titles'], 1)
        self.assertEqual(counts_before['copies'], 5)

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Kamus Besar Bahasa Indonesia',
            'penulis': 'Pusat Bahasa',
            'kategori': 'Kamus',
            'isbn': '978-979-407-182-3',
            'jumlah': '3',
        }

        # 1. Preview memicu peringatan
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        self.assertEqual(res_prev.status_code, 200)
        prev_json = res_prev.get_json()
        self.assertTrue(prev_json['duplicate_warning'])
        confirm_token = prev_json['confirm_token']

        # 2. Admin tetap melanjutkan konfirmasi simpan
        confirm_data = {'csrf_token': csrf_token, 'confirm_token': confirm_token, **payload}
        res_conf = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res_conf.status_code, 200)
        conf_json = res_conf.get_json()
        self.assertFalse(conf_json['is_replay'])

        new_title_id = conf_json['data']['title_id']
        # ID judul baru harus BERBEDA dengan ID buku lama (bukan merge / bukan overwrite)
        self.assertNotEqual(new_title_id, seeded_id)

        # 3. Verifikasi di database: Jumlah judul bertambah menjadi tepat 2, eksemplar menjadi 8 (5 + 3)
        counts_after = self._get_db_counts()
        self.assertEqual(counts_after['catalog_titles'], 2)
        self.assertEqual(counts_after['copies'], 8)

        # Verifikasi buku lama tetap utuh
        conn = library_app.get_db_connection()
        seeded_copies = conn.execute("SELECT COUNT(*) FROM copies WHERE title_id = ?;", (seeded_id,)).fetchone()[0]
        new_copies = conn.execute("SELECT COUNT(*) FROM copies WHERE title_id = ?;", (new_title_id,)).fetchone()[0]
        conn.close()

        self.assertEqual(seeded_copies, 5, "Eksemplar buku lama tidak boleh berubah!")
        self.assertEqual(new_copies, 3, "Eksemplar buku baru harus tepat 3!")

    def test_12_client_tampering_of_warning_or_payload_cannot_bypass_server(self):
        """Kriteria 12: Payload atau peringatan yang dimanipulasi klien tidak dapat melewati pemeriksaan server."""
        self._seed_book(
            judul="Psikologi Pendidikan",
            penulis="Prof. Sugiyono",
            isbn="978-602-865-011-2"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Psikologi Pendidikan',
            'penulis': 'Prof. Sugiyono',
            'kategori': 'Pendidikan',
            'isbn': '978-602-865-011-2',
            'jumlah': '4',
        }

        # Preview
        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']

        # Klien mencoba memanipulasi payload saat konfirmasi (misal: mengubah judul dan jumlah)
        tampered_data = {
            'csrf_token': csrf_token,
            'confirm_token': confirm_token,
            'judul': 'Buku Berubah',
            'penulis': 'Prof. Sugiyono',
            'kategori': 'Pendidikan',
            'isbn': '978-602-865-011-2',
            'jumlah': '10',  # Diubah!
        }

        res_conf = self.client.post('/buku/tambah/konfirmasi', data=tampered_data, headers={'Accept': 'application/json'})
        self.assertEqual(res_conf.status_code, 400)
        self.assertIn('dimodifikasi', res_conf.get_json()['error'].lower())

    def test_13_token_resubmission_remains_idempotent_with_warning(self):
        """Kriteria 13: Pengiriman ulang token tetap idempoten meskipun ada peringatan duplikat."""
        self._seed_book(
            judul="Algoritma & Pemrograman",
            penulis="Rinaldi Munir",
            isbn="978-602-000-111-1"
        )

        csrf_token = self._login_admin()
        payload = {
            'csrf_token': csrf_token,
            'judul': 'Algoritma & Pemrograman',
            'penulis': 'Rinaldi Munir',
            'kategori': 'Komputer',
            'isbn': '978-602-000-111-1',
            'jumlah': '2',
        }

        res_prev = self.client.post('/buku/tambah', data=payload, headers={'Accept': 'application/json'})
        confirm_token = res_prev.get_json()['confirm_token']
        confirm_data = {'csrf_token': csrf_token, 'confirm_token': confirm_token, **payload}

        # Eksekusi simpan awal
        res1 = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.get_json()['is_replay'])

        counts_baseline = self._get_db_counts()

        # Eksekusi kirim ulang
        res2 = self.client.post('/buku/tambah/konfirmasi', data=confirm_data, headers={'Accept': 'application/json'})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()['is_replay'])

        counts_after = self._get_db_counts()
        self.assertEqual(counts_baseline['catalog_titles'], counts_after['catalog_titles'])
        self.assertEqual(counts_baseline['copies'], counts_after['copies'])


if __name__ == '__main__':
    unittest.main()

