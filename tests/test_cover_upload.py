# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-11: Upload Cover dengan Validasi Keamanan dan Storage Interface.
Sistem Perpustakaan Digital Sekolah.

Acceptance Criteria yang Diuji (17+ Kriteria Mutlak):
1. Upload cover valid berhasil (PNG, JPEG, GIF, WEBP).
2. File yang melebihi batas ukuran (policy.MAX_COVER_IMAGE_SIZE_BYTES / 2 MB) ditolak.
3. File kosong (0 bytes) ditolak.
4. Ekstensi gambar dengan isi non-gambar ditolak.
5. Magic bytes tidak cocok dengan format yang diklaim ditolak.
6. Gambar rusak ditangani dengan aman tanpa crash.
7. Format yang tidak didukung (.exe, .php, .svg, .pdf, .txt) ditolak.
8. Nama file UUID dihasilkan oleh server (bukan nama asli client).
9. Nama file berbahaya tidak dapat menyebabkan path traversal.
10. Upload tanpa autentikasi ditolak (HTTP 302 / 401).
11. Pengguna non-admin ditolak (HTTP 302 / 401).
12. POST tanpa CSRF valid ditolak (HTTP 400).
13. Kegagalan penyimpanan tidak menghasilkan metadata sukses palsu.
14. Kegagalan pembaruan metadata ditangani tanpa meninggalkan file yang tidak konsisten (orphan file cleanup).
15. Penggantian cover mempertahankan file lama jika upload baru gagal.
16. Penggantian cover menghapus file lama jika upload baru sukses.
17. Interface Storage dapat diuji menggunakan implementasi lokal atau FakeStorage.
18. Dukungan skema legacy P1 (tabel buku.cover_img).
19. ID buku tidak ditemukan mengembalikan HTTP 404 Not Found.
20. Zero-write guarantee: Database tidak termutasi saat validasi upload gagal.
"""
import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
import policy
from repositories import catalog_repo, copy_repo
from services import (
    create_title_with_copies,
    Storage,
    LocalStorage,
    FakeStorage,
    get_storage,
    set_storage,
    reset_storage,
    validate_cover_image,
    generate_cover_filename,
    update_book_cover,
    ValidationError,
    StorageError,
    CopyNotFoundError,
)

# Binary fixtures untuk pengujian gambar valid
VALID_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x00' * 20 + b'IEND\xaeB`\x82'
VALID_JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' + b'\x00' * 20 + b'\xff\xd9'
VALID_GIF = b'GIF89a\n\x00\n\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\n\x00\n\x00\x00\x02\x02D\x01\x00;'
VALID_WEBP = b'RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\x90\x01\x00\x9d\x01*\x01\x00\x01\x00'


class BaseCoverUploadTestCase(unittest.TestCase):
    """Setup lingkungan uji terisolasi dengan temporary SQLite DB dan temp storage."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_cover.db')
        self.storage_dir = os.path.join(self.test_dir, 'covers')
        os.makedirs(self.storage_dir, exist_ok=True)

        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        # Konfigurasi Storage Provider lokal terisolasi
        self.local_storage = LocalStorage(base_dir=self.storage_dir, url_prefix="/static/covers")
        set_storage(self.local_storage)
        library_app.app.config['STORAGE_PROVIDER'] = self.local_storage
        library_app.app.config['UPLOAD_FOLDER'] = self.storage_dir
        library_app.app.config['TESTING'] = True

        self.client = library_app.app.test_client()

        # Inisialisasi skema v2
        self._init_v2_schema()

    def tearDown(self):
        reset_storage()
        library_app.app.config.pop('STORAGE_PROVIDER', None)
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

    def _get_db_hash(self) -> str:
        h = hashlib.sha256()
        with open(self.test_db, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _login_admin(self):
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['admin_username'] = library_app.ADMIN_USERNAME
            sess['user_role'] = 'admin'
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-311'

    def _login_non_admin(self):
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['username'] = 'siswa_user'
            sess['user_role'] = 'user'
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-311'

    def _create_sample_title(self, judul="Laskar Pelangi", penulis="Andrea Hirata") -> str:
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        title = create_title_with_copies(
            conn,
            title_data={
                "judul": judul,
                "penulis": penulis,
                "kategori": "Fiksi",
            },
            initial_copies=1,
            copy_base_data={"lokasi_rak": "Rak A-1"},
        )
        conn.close()
        return title["id"]


class TestCoverUploadSuite(BaseCoverUploadTestCase):

    def test_01_upload_valid_cover_png_success(self):
        """Upload cover PNG valid berhasil memperbarui metadata catalog_titles.cover_path."""
        title_id = self._create_sample_title("Bumi Manusia", "Pramoedya Ananta Toer")
        self._login_admin()

        data = {
            'csrf_token': 'test-valid-csrf-token-311',
            'cover_file': (io.BytesIO(VALID_PNG), 'sample_cover.png', 'image/png'),
        }
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)

        # Cek database v2
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        title_db = catalog_repo.get_title_by_id(conn, title_id)
        conn.close()

        self.assertIsNotNone(title_db)
        cover_path = title_db['cover_path']
        self.assertTrue(cover_path)
        self.assertTrue(cover_path.endswith('.png'))

        # Verifikasi file ada di local storage
        self.assertTrue(self.local_storage.exists(cover_path))

    def test_02_upload_valid_formats_jpeg_gif_webp(self):
        """Upload cover mendukung format JPEG, GIF, dan WEBP."""
        self._login_admin()

        test_cases = [
            ("Laskar Pelangi", VALID_JPEG, "cover.jpg", "image/jpeg", ".jpg"),
            ("Negeri 5 Menara", VALID_GIF, "cover.gif", "image/gif", ".gif"),
            ("Ronggeng Dukuh Paruk", VALID_WEBP, "cover.webp", "image/webp", ".webp"),
        ]

        for judul, bdata, fname, mime, ext in test_cases:
            tid = self._create_sample_title(judul, "Penulis Uji")
            res = self.client.post(
                f'/buku/{tid}/upload_cover',
                headers={'X-CSRFToken': 'test-valid-csrf-token-311'},
                data={
                    'csrf_token': 'test-valid-csrf-token-311',
                    'cover_file': (io.BytesIO(bdata), fname, mime),
                },
                content_type='multipart/form-data',
            )
            self.assertEqual(res.status_code, 302)

            conn = sqlite3.connect(self.test_db)
            conn.row_factory = sqlite3.Row
            t = catalog_repo.get_title_by_id(conn, tid)
            conn.close()

            self.assertTrue(t['cover_path'].endswith(ext))
            self.assertTrue(self.local_storage.exists(t['cover_path']))

    def test_03_file_exceeding_max_size_rejected(self):
        """File yang melebihi batas ukuran (2 MB per policy) ditolak dengan HTTP 400."""
        title_id = self._create_sample_title()
        self._login_admin()

        # Buat file PNG valid tapi ukurannya 2.1 MB
        oversized_data = VALID_PNG + b'\x00' * (2 * 1024 * 1024 + 500)

        is_val, msg, _ = validate_cover_image(oversized_data, 'huge.png', 'image/png')
        self.assertFalse(is_val)
        self.assertIn('melebihi batas maksimum', msg.lower())

        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(oversized_data), 'huge.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertIn(res.status_code, (400, 413))

    def test_04_empty_file_rejected(self):
        """File cover kosong (0 bytes) ditolak dengan HTTP 400."""
        title_id = self._create_sample_title()
        self._login_admin()

        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(b''), 'empty.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('error'), 'Validation Error')
        self.assertIn('kosong', data.get('message', '').lower())

    def test_05_image_extension_with_non_image_content_rejected(self):
        """File berekstensi gambar namun berisi teks/skrip ditolak (Magic byte check)."""
        title_id = self._create_sample_title()
        self._login_admin()

        script_payload = b"<?php echo 'malicious code'; ?>\nThis is plain text pretending to be a PNG."
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(script_payload), 'avatar.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('error'), 'Validation Error')

    def test_06_magic_bytes_mismatch_with_claimed_extension_rejected(self):
        """Signature biner file yang tidak cocok dengan ekstensi yang diklaim ditolak."""
        title_id = self._create_sample_title()
        self._login_admin()

        # Konten biner JPEG diunggah dengan nama file .png
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_JPEG), 'disguised_photo.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('tidak cocok', data.get('message', '').lower())

    def test_07_corrupted_image_handled_safely(self):
        """Header gambar rusak ditangani dengan aman tanpa crash server."""
        title_id = self._create_sample_title()
        self._login_admin()

        # Signature PNG palsu yang diikuti sampah biner tanpa chunk IHDR
        broken_png = b'\x89PNG\r\n\x1a\n' + b'\xff' * 30
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(broken_png), 'corrupted.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('rusak', data.get('message', '').lower())

    def test_08_unsupported_format_rejected(self):
        """Format yang tidak didukung (.exe, .pdf, .svg, .txt) ditolak secara eksplisit."""
        title_id = self._create_sample_title()
        self._login_admin()

        svg_content = b"<svg xmlns='http://www.w3.org/2000/svg'><circle r='50'/></svg>"
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(svg_content), 'vector.svg', 'image/svg+xml'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('tidak didukung', data.get('message', '').lower())

    def test_09_server_generates_uuid_filename(self):
        """Server menghasilkan nama file UUID, bukan nama file asli pengguna."""
        title_id = self._create_sample_title()
        self._login_admin()

        original_client_name = "Foto Cover Asli Saya (2026).png"
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), original_client_name, 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        stored_filename = data['result']['cover_path']
        self.assertNotIn("Foto Cover Asli", stored_filename)
        # Verifikasi format UUID hex (32 karakter alfanumerik + .png)
        base_no_ext = stored_filename.replace('.png', '')
        self.assertEqual(len(base_no_ext), 32)
        int(base_no_ext, 16)  # Memastikan valid hexadecimal

    def test_10_malicious_filename_cannot_cause_path_traversal(self):
        """Nama file dengan path traversal (../../etc/passwd) tidak dapat keluar dari direktori penyimpanan."""
        title_id = self._create_sample_title()
        self._login_admin()

        malicious_filename = "../../../../evil_escape.png"
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), malicious_filename, 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        stored_filename = data['result']['cover_path']
        self.assertNotIn("..", stored_filename)
        self.assertTrue(self.local_storage.exists(stored_filename))

    def test_11_unauthenticated_upload_rejected(self):
        """Pengguna belum login ditolak saat mencoba mengunggah cover (HTTP 302 / 401)."""
        title_id = self._create_sample_title()

        # HTML request with valid CSRF in session
        with self.client.session_transaction() as sess:
            sess['_csrf_token'] = 'anon-csrf'
        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            data={'csrf_token': 'anon-csrf'},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

        # JSON request
        res_json = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'anon-csrf'}
        )
        self.assertEqual(res_json.status_code, 401)

    def test_12_non_admin_user_rejected(self):
        """Pengguna non-admin (role 'user') ditolak mengakses upload cover."""
        title_id = self._create_sample_title()
        self._login_non_admin()

        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), 'sample.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 401)

    def test_13_post_without_csrf_rejected_400(self):
        """POST tanpa CSRF token yang valid ditolak dengan HTTP 400."""
        title_id = self._create_sample_title()
        self._login_admin()

        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            data={'cover_file': (io.BytesIO(VALID_PNG), 'sample.png', 'image/png')},
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 400)

    def test_14_storage_failure_does_not_produce_false_success(self):
        """Kegagalan penyimpanan (I/O error) tidak memperbarui metadata basis data (tidak ada sukses palsu)."""
        title_id = self._create_sample_title()
        self._login_admin()

        fake_storage = FakeStorage()
        fake_storage.simulate_save_error = True
        library_app.app.config['STORAGE_PROVIDER'] = fake_storage

        res = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), 'sample.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 500)

        # Verifikasi cover_path di database tetap kosong
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        title_db = catalog_repo.get_title_by_id(conn, title_id)
        conn.close()
        self.assertIsNone(title_db['cover_path'])

    def test_15_database_failure_cleans_up_stored_file(self):
        """Kegagalan pembaruan basis data membersihkan file baru dari storage (mencegah orphan file)."""
        title_id = self._create_sample_title()
        fake_storage = FakeStorage()

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        # Mock catalog_repo.update_title untuk melempar error basis data
        with patch('repositories.catalog_repo.update_title', side_effect=sqlite3.DatabaseError("Disk lock error")):
            with self.assertRaises(sqlite3.DatabaseError):
                update_book_cover(
                    conn=conn,
                    book_id=title_id,
                    file_bytes=VALID_PNG,
                    original_filename="test.png",
                    storage=fake_storage,
                )

        # Verifikasi tidak ada file yatim (orphan file) yang tertinggal di fake_storage
        self.assertEqual(len(fake_storage._files), 0)
        conn.close()

    def test_16_replacing_cover_retains_old_file_if_new_upload_fails(self):
        """Penggantian cover mempertahankan file lama di storage jika unggahan baru gagal."""
        title_id = self._create_sample_title()
        self._login_admin()

        # 1. Upload cover pertama yang valid
        res1 = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), 'first.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res1.status_code, 200)
        first_cover = res1.get_json()['result']['cover_path']
        self.assertTrue(self.local_storage.exists(first_cover))

        # 2. Coba upload file kedua yang rusak
        res2 = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(b'corrupted_bytes_only'), 'second.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res2.status_code, 400)

        # Verifikasi file pertama tetap tersimpan aman di storage
        self.assertTrue(self.local_storage.exists(first_cover))

        # Verifikasi database tetap mengarah ke file pertama
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        title_db = catalog_repo.get_title_by_id(conn, title_id)
        conn.close()
        self.assertEqual(title_db['cover_path'], first_cover)

    def test_17_replacing_cover_deletes_old_file_when_new_upload_succeeds(self):
        """Penggantian cover membersihkan file lama dari storage jika unggahan baru sukses."""
        title_id = self._create_sample_title()
        self._login_admin()

        # 1. Upload cover pertama
        res1 = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), 'old.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res1.status_code, 200)
        old_cover = res1.get_json()['result']['cover_path']
        self.assertTrue(self.local_storage.exists(old_cover))

        # 2. Upload cover kedua yang valid
        res2 = self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_JPEG), 'new.jpg', 'image/jpeg'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res2.status_code, 200)
        new_cover = res2.get_json()['result']['cover_path']

        # Verifikasi file baru ada, file lama sudah dihapus
        self.assertTrue(self.local_storage.exists(new_cover))
        self.assertFalse(self.local_storage.exists(old_cover))

    def test_18_storage_interface_pluggable_with_fake_storage(self):
        """Interface Storage dapat diuji secara pluggable menggunakan FakeStorage."""
        fake = FakeStorage(url_prefix="/custom/cdn")
        set_storage(fake)

        saved = fake.save(VALID_PNG, "test_file.png")
        self.assertEqual(saved, "test_file.png")
        self.assertTrue(fake.exists("test_file.png"))
        self.assertEqual(fake.get_url("test_file.png"), "/custom/cdn/test_file.png")
        self.assertEqual(fake.read("test_file.png"), VALID_PNG)

        fake.delete("test_file.png")
        self.assertFalse(fake.exists("test_file.png"))

    def test_19_legacy_p1_schema_fallback(self):
        """Upload cover pada database skema legacy P1 memperbarui tabel buku.cover_img."""
        legacy_db = os.path.join(self.test_dir, 'test_legacy.db')
        conn = sqlite3.connect(legacy_db)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE buku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                judul TEXT NOT NULL,
                cover_img TEXT
            );
        """)
        conn.execute("INSERT INTO buku (id, judul, cover_img) VALUES (50, 'Buku Fisika P1', NULL);")
        conn.commit()

        fake_storage = FakeStorage()
        res = update_book_cover(
            conn=conn,
            book_id="50",
            file_bytes=VALID_PNG,
            original_filename="fisika.png",
            storage=fake_storage,
        )
        self.assertTrue(res['ok'])
        conn.commit()

        # Periksa tabel buku
        row = conn.execute("SELECT * FROM buku WHERE id = 50;").fetchone()
        self.assertTrue(row['cover_img'].endswith('.png'))
        self.assertTrue(fake_storage.exists(row['cover_img']))
        conn.close()

    def test_20_non_existent_book_id_returns_404(self):
        """Mengunggah cover untuk ID buku yang tidak ada mengembalikan HTTP 404."""
        self._login_admin()

        res = self.client.post(
            '/buku/T-TIDAKADA999/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(VALID_PNG), 'sample.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(res.status_code, 404)

    def test_21_zero_write_when_upload_validation_fails(self):
        """Database tidak termutasi sama sekali (zero-write) saat validasi upload cover gagal."""
        title_id = self._create_sample_title()
        self._login_admin()

        hash_before = self._get_db_hash()

        # Kirim file teks non-gambar
        self.client.post(
            f'/buku/{title_id}/upload_cover',
            headers={'Accept': 'application/json', 'X-CSRFToken': 'test-valid-csrf-token-311'},
            data={
                'csrf_token': 'test-valid-csrf-token-311',
                'cover_file': (io.BytesIO(b'not an image content'), 'test.png', 'image/png'),
            },
            content_type='multipart/form-data',
        )

        hash_after = self._get_db_hash()
        self.assertEqual(hash_before, hash_after, "Basis data harus 100% tidak berubah saat upload gagal!")


if __name__ == '__main__':
    unittest.main()

