# -*- coding: utf-8 -*-
"""
Test Suite untuk Task 3-10: Nonaktifkan/Tandai Eksemplar Buku per Eksemplar dengan Alasan & Audit Log.
Sistem Perpustakaan Digital Sekolah.

Acceptance Criteria yang Diuji (18+ Kriteria Mutlak):
1. Admin terautentikasi dapat mengakses halaman konfirmasi penonaktifan eksemplar (GET 200).
2. Pengguna tanpa login ditolak dan diarahkan ke login (HTTP 302 / 401).
3. Pengguna non-admin (role 'user') ditolak (HTTP 302 / 401).
4. POST tanpa CSRF token ditolak (HTTP 400).
5. ID eksemplar tidak ditemukan ditangani dengan aman (HTTP 404 Not Found).
6. Alasan kosong atau hanya whitespace ditolak (HTTP 400 ValidationError).
7. Alasan di luar rentang panjang (<5 atau >500 karakter) ditolak (HTTP 400 ValidationError).
8. Status target di luar pilihan yang diizinkan ditolak (HTTP 400 ValidationError).
9. Penonaktifan berhasil mengubah status eksemplar dalam tabel copies (nonaktif, rusak, hilang, dalam_penanganan).
10. Data fisik eksemplar tetap tersimpan utuh di basis data (ROW COUNT SAMA, TANPA HARD DELETE).
11. Trigger database `trg_prevent_delete_copies` terbukti memblokir DELETE fisik.
12. Entri audit_log tercatat lengkap: actor, action, object_type='copies', object_id, reason, detail_json, timestamp UTC.
13. Transaksi atomik: kegagalan penulisan audit_log membatalkan perubahan status eksemplar (rollback penuh).
14. Idempotensi & proteksi replay: penonaktifan berulang ditolak (HTTP 400 InvalidOperationError) tanpa duplikasi audit log.
15. Eksemplar yang sudah berstatus tidak aktif ditolak saat dicoba dinonaktifkan kembali.
16. Konsistensi sirkulasi: eksemplar yang sedang berada dalam peminjaman aktif ditolak (HTTP 400 InvalidOperationError).
17. Eksemplar yang telah dinonaktifkan tidak dapat dipinjam oleh loan_service (CopyNotAvailableError).
18. Zero-write guarantee: Permintaan GET murni baca dan tidak memutasi basis data sama sekali (hash DB identik).
19. Dukungan skema legacy P1 (tabel buku + id_buku_fisik + stok).
20. Alias route /admin/eksemplar/<copy_id>/nonaktifkan berfungsi identik.
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
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as library_app
from repositories import copy_repo, catalog_repo, member_repo, loan_repo, audit_repo
from services import (
    create_title_with_copies,
    deactivate_copy,
    borrow_copies,
    register_member,
    ValidationError,
    InvalidOperationError,
    CopyNotFoundError,
    CopyNotAvailableError,
)


class BaseCopyDeactivateTestCase(unittest.TestCase):
    """Setup lingkungan uji terisolasi dengan temporary SQLite database."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.test_dir, 'test_deactivate.db')
        os.environ['DATABASE_NAME'] = self.test_db
        os.environ['SQLITE_TIMEOUT'] = '15.0'

        library_app.app.config['TESTING'] = True
        self.client = library_app.app.test_client()

        # Inisialisasi skema v2
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
        categories = [
            ("MC-MURID", "murid", "Siswa / Murid"),
            ("MC-GURU-JUR", "guru_jurusan", "Guru kejuruan"),
            ("MC-GURU-UMUM", "guru_umum", "Guru mata pelajaran umum"),
            ("MC-STAF", "staf", "Tenaga kependidikan"),
            ("MC-TEKNISI", "teknisi", "Laboran / teknisi"),
        ]
        for cat_id, jenis, keterangan in categories:
            conn.execute(
                "INSERT OR IGNORE INTO member_categories (id, jenis, keterangan) VALUES (?, ?, ?);",
                (cat_id, jenis, keterangan)
            )
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
            sess['_csrf_token'] = 'test-valid-csrf-token-310'

    def _login_non_admin(self):
        with self.client.session_transaction() as sess:
            sess.permanent = True
            sess['logged_in'] = True
            sess['username'] = 'siswa_biasa'
            sess['user_role'] = 'user'
            sess['last_active'] = time.time()
            sess['_csrf_token'] = 'test-valid-csrf-token-310'

    def _create_sample_copy(self, judul="Laskar Pelangi", penulis="Andrea Hirata") -> str:
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
        copies = copy_repo.list_copies_by_title(conn, title["id"])
        copy_id = copies[0]["id"]
        conn.close()
        return copy_id


class TestCopyDeactivateSuite(BaseCopyDeactivateTestCase):

    def test_01_authenticated_admin_can_access_deactivate_page_html(self):
        """Admin terautentikasi dapat mengakses halaman konfirmasi penonaktifan eksemplar (status 200)."""
        copy_id = self._create_sample_copy("Bumi Manusia", "Pramoedya Ananta Toer")
        self._login_admin()

        res = self.client.get(f'/admin/copies/{copy_id}/deactivate')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('Nonaktifkan / Tandai Eksemplar Buku', html)
        self.assertIn(copy_id, html)
        self.assertIn('Bumi Manusia', html)
        self.assertIn('Pramoedya Ananta Toer', html)
        self.assertIn('tanpa hard delete', html.lower())
        self.assertIn('csrf_token', html)

    def test_02_authenticated_admin_can_access_alias_url(self):
        """Admin dapat mengakses route alias /admin/eksemplar/<copy_id>/nonaktifkan."""
        copy_id = self._create_sample_copy("Negeri 5 Menara", "A. Fuadi")
        self._login_admin()

        res = self.client.get(f'/admin/eksemplar/{copy_id}/nonaktifkan')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn(copy_id, html)
        self.assertIn('Negeri 5 Menara', html)

    def test_03_authenticated_admin_get_json_metadata(self):
        """Permintaan GET dengan Accept: application/json mengembalikan metadata eksemplar secara terstruktur."""
        copy_id = self._create_sample_copy("Sangkuriang", "Cerita Rakyat")
        self._login_admin()

        res = self.client.get(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'Accept': 'application/json'}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('copy_id'), copy_id)
        self.assertEqual(data.get('current_status'), 'aktif')
        self.assertTrue(data.get('can_deactivate'))

    def test_04_unauthenticated_user_redirected_to_login(self):
        """Pengguna belum login yang mengakses halaman penonaktifan diarahkan ke /login (HTTP 302)."""
        copy_id = self._create_sample_copy()
        res = self.client.get(f'/admin/copies/{copy_id}/deactivate', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_05_unauthenticated_api_returns_401(self):
        """Permintaan API JSON tanpa login mengembalikan HTTP 401 Unauthorized."""
        copy_id = self._create_sample_copy()
        res = self.client.get(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'Accept': 'application/json'}
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json().get('error'), 'Unauthorized')

    def test_06_non_admin_role_rejected(self):
        """Pengguna non-admin (role 'user') ditolak mengakses fitur penonaktifan."""
        copy_id = self._create_sample_copy()
        self._login_non_admin()

        res1 = self.client.get(f'/admin/copies/{copy_id}/deactivate', follow_redirects=False)
        self.assertEqual(res1.status_code, 302)

        res2 = self.client.get(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'Accept': 'application/json'}
        )
        self.assertEqual(res2.status_code, 401)

    def test_07_post_without_csrf_token_rejected_400(self):
        """Permintaan POST tanpa CSRF token yang valid ditolak oleh sistem (HTTP 400)."""
        copy_id = self._create_sample_copy()
        self._login_admin()

        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            data={'reason': 'Alasan valid untuk pengujian tanpa CSRF'},
        )
        self.assertEqual(res.status_code, 400)

    def test_08_non_existent_copy_id_returns_404(self):
        """ID eksemplar yang tidak ada di database mengembalikan HTTP 404 Not Found."""
        self._login_admin()

        # HTML
        res_html = self.client.get('/admin/copies/C-TIDAKADA999/deactivate')
        self.assertEqual(res_html.status_code, 404)

        # JSON
        res_json = self.client.get(
            '/admin/copies/C-TIDAKADA999/deactivate',
            headers={'Accept': 'application/json'}
        )
        self.assertEqual(res_json.status_code, 404)
        self.assertEqual(res_json.get_json().get('error'), 'Not Found')

    def test_09_empty_or_whitespace_reason_rejected_400(self):
        """Alasan kosong atau hanya whitespace ditolak dengan HTTP 400 (ValidationError)."""
        copy_id = self._create_sample_copy()
        self._login_admin()

        # HTML form dengan string kosong
        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            data={
                'csrf_token': 'test-valid-csrf-token-310',
                'reason': '   ',
            }
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('wajib diisi', res.get_data(as_text=True))

        # JSON request
        res_json = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
            data=json.dumps({'reason': ''})
        )
        self.assertEqual(res_json.status_code, 400)
        self.assertIn('wajib diisi', res_json.get_json().get('message', ''))

    def test_10_reason_length_bounds_rejected_400(self):
        """Alasan yang kurang dari 5 karakter atau lebih dari 500 karakter ditolak (HTTP 400)."""
        copy_id = self._create_sample_copy()
        self._login_admin()

        # Kurang dari 5 karakter
        res_short = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            data={
                'csrf_token': 'test-valid-csrf-token-310',
                'reason': 'rusk',
            }
        )
        self.assertEqual(res_short.status_code, 400)
        self.assertIn('minimal 5 karakter', res_short.get_data(as_text=True))

        # Lebih dari 500 karakter
        long_reason = "Alasan sangat panjang " * 30  # > 600 karakter
        res_long = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            data={
                'csrf_token': 'test-valid-csrf-token-310',
                'reason': long_reason,
            }
        )
        self.assertEqual(res_long.status_code, 400)
        self.assertIn('maksimal 500 karakter', res_long.get_data(as_text=True))

    def test_11_invalid_target_status_rejected_400(self):
        """Status target yang tidak dikenali ditolak dengan HTTP 400 (ValidationError)."""
        copy_id = self._create_sample_copy()
        self._login_admin()

        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            data={
                'csrf_token': 'test-valid-csrf-token-310',
                'reason': 'Alasan valid untuk status invalid',
                'target_status': 'dijual_bebas',
            }
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('tidak valid', res.get_data(as_text=True))

    def test_12_deactivate_success_updates_status_in_db(self):
        """Penonaktifan eksemplar berhasil memperbarui status eksemplar di database."""
        copy_id = self._create_sample_copy("Ronggeng Dukuh Paruk", "Ahmad Tohari")
        self._login_admin()

        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
            data=json.dumps({
                'reason': 'Halaman sobek dan terlepas pada bab tengah.',
                'target_status': 'rusak',
            })
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['result']['new_status'], 'rusak')

        # Cek langsung di database
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        copy_row = copy_repo.get_copy_by_id(conn, copy_id)
        conn.close()

        self.assertIsNotNone(copy_row)
        self.assertEqual(copy_row['status'], 'rusak')

    def test_13_physical_copy_row_count_strictly_preserved_no_hard_delete(self):
        """Data fisik eksemplar tetap tersimpan utuh di basis data (ROW COUNT SAMA, TANPA HARD DELETE)."""
        copy_id = self._create_sample_copy("Cantik Itu Luka", "Eka Kurniawan")
        self._login_admin()

        conn = sqlite3.connect(self.test_db)
        count_before = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        conn.close()

        # Eksekusi penonaktifan via web POST
        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            data={
                'csrf_token': 'test-valid-csrf-token-310',
                'reason': 'Eksemplar ditarik karena cover terkelupas parah.',
                'target_status': 'nonaktif',
            },
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)

        # Cek jumlah baris di tabel copies
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        count_after = conn.execute("SELECT COUNT(*) FROM copies;").fetchone()[0]
        copy_persisted = copy_repo.get_copy_by_id(conn, copy_id)

        # Verifikasi trigger R12: DELETE fisik harus gagal dibatalkan oleh trigger
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            conn.execute("DELETE FROM copies WHERE id = ?;", (copy_id,))
        self.assertIn("dilarang", str(ctx.exception).lower())

        conn.close()

        self.assertEqual(count_before, count_after, "Jumlah baris di tabel copies harus 100% sama!")
        self.assertIsNotNone(copy_persisted, "Baris eksemplar fisik harus tetap ada di tabel!")
        self.assertEqual(copy_persisted['status'], 'nonaktif')

    def test_14_audit_log_created_with_full_details(self):
        """audit_log mencatat lengkap: actor, action, object_id, reason, detail_json, timestamp UTC."""
        copy_id = self._create_sample_copy("Supernova", "Dee Lestari")
        self._login_admin()

        reason_text = "Hilang saat peminjaman eksternal dan diganti kompensasi."
        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
            data=json.dumps({
                'reason': reason_text,
                'target_status': 'hilang',
            })
        )
        self.assertEqual(res.status_code, 200)

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        logs = conn.execute(
            "SELECT * FROM audit_log WHERE object_type = 'copies' AND object_id = ?;",
            (copy_id,)
        ).fetchall()
        conn.close()

        self.assertEqual(len(logs), 1)
        entry = dict(logs[0])
        self.assertEqual(entry['actor'], library_app.ADMIN_USERNAME)
        self.assertEqual(entry['action'], 'COPY_MARK_HILANG')
        self.assertEqual(entry['object_type'], 'copies')
        self.assertEqual(entry['object_id'], copy_id)
        self.assertEqual(entry['reason'], reason_text)
        self.assertTrue(entry['at'])

        detail = json.loads(entry['detail_json'])
        self.assertEqual(detail['previous_status'], 'aktif')
        self.assertEqual(detail['new_status'], 'hilang')
        self.assertEqual(detail['judul'], 'Supernova')

    def test_15_audit_log_failure_rolls_back_status_change(self):
        """Jika penulisan audit_log gagal, status eksemplar wajib di-rollback (transaksi atomik)."""
        copy_id = self._create_sample_copy("Filosofi Kopi", "Dee Lestari")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row

        with patch('repositories.audit_repo.record_audit', side_effect=sqlite3.DatabaseError("Disk I/O Error pada audit")):
            with self.assertRaises(sqlite3.DatabaseError):
                deactivate_copy(
                    conn,
                    copy_id=copy_id,
                    reason="Percobaan penonaktifan yang harus gagal audit.",
                    actor="admin",
                )

        # Verifikasi status di database tetap 'aktif'
        copy_check = copy_repo.get_copy_by_id(conn, copy_id)
        self.assertEqual(copy_check['status'], 'aktif')
        conn.close()

    def test_16_replay_or_resubmission_rejected_idempotent(self):
        """Percobaan penonaktifan berulang pada eksemplar yang sama ditolak (HTTP 400) tanpa duplikasi audit."""
        copy_id = self._create_sample_copy("Pulang", "Leila S. Chudori")
        self._login_admin()

        # Eksekusi pertama: Sukses
        res1 = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
            data=json.dumps({
                'reason': 'Kondisi rusak parah terkena air.',
                'target_status': 'rusak',
            })
        )
        self.assertEqual(res1.status_code, 200)

        # Eksekusi kedua (replay / double click): Ditolak
        res2 = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
            data=json.dumps({
                'reason': 'Kondisi rusak parah terkena air (kirim ulang).',
                'target_status': 'rusak',
            })
        )
        self.assertEqual(res2.status_code, 400)
        self.assertEqual(res2.get_json().get('error'), 'Invalid Operation')

        # Verifikasi audit log hanya ada 1 entri (tidak duplikat)
        conn = sqlite3.connect(self.test_db)
        log_count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE object_id = ?;",
            (copy_id,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(log_count, 1)

    def test_17_deactivating_already_inactive_copy_rejected(self):
        """Eksemplar yang berstatus tidak aktif ditolak saat dicoba dinonaktifkan kembali."""
        copy_id = self._create_sample_copy("Laut Bercerita", "Leila S. Chudori")

        conn = sqlite3.connect(self.test_db)
        copy_repo.update_copy_status(conn, copy_id, "nonaktif")
        conn.commit()

        # Panggil via service
        with self.assertRaises(InvalidOperationError) as ctx:
            deactivate_copy(
                conn,
                copy_id=copy_id,
                reason="Mencoba menonaktifkan eksemplar yang sudah nonaktif.",
            )
        self.assertIn("sudah berstatus", str(ctx.exception))
        conn.close()

    def test_18_active_loan_cannot_be_deactivated(self):
        """LIB-LOAN-002: Eksemplar yang sedang berada dalam peminjaman aktif tidak dapat dinonaktifkan."""
        copy_id = self._create_sample_copy("Ayat-Ayat Cinta", "Habiburrahman El Shirazy")

        # Daftarkan anggota dan lakukan peminjaman
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        member = register_member(conn, nama="Budi Santoso", category_id="MC-MURID")
        borrow_copies(conn, member_id=member["id"], copy_ids=[copy_id])
        conn.commit()
        conn.close()

        self._login_admin()

        # Percobaan via web POST
        res = self.client.post(
            f'/admin/copies/{copy_id}/deactivate',
            headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
            data=json.dumps({
                'reason': 'Ingin menonaktifkan padahal sedang dipinjam.',
                'target_status': 'nonaktif',
            })
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('sedang dipinjam', data.get('message', '').lower())

        # Verifikasi status di DB tetap aktif
        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        copy_obj = copy_repo.get_copy_by_id(conn, copy_id)
        conn.close()
        self.assertEqual(copy_obj['status'], 'aktif')

    def test_19_deactivated_copy_cannot_be_borrowed_by_loan_service(self):
        """Eksemplar yang telah dinonaktifkan tidak dapat dipinjam oleh loan_service (CopyNotAvailableError)."""
        copy_id = self._create_sample_copy("Laskar Pelangi 2", "Andrea Hirata")

        conn = sqlite3.connect(self.test_db)
        conn.row_factory = sqlite3.Row
        deactivate_copy(conn, copy_id=copy_id, reason="Rusak berat terendam banjir")
        conn.commit()

        member = register_member(conn, nama="Siti Aminah", category_id="MC-MURID")
        with self.assertRaises(CopyNotAvailableError) as ctx:
            borrow_copies(conn, member_id=member["id"], copy_ids=[copy_id])
        self.assertIn("tidak dapat dipinjam", str(ctx.exception).lower())
        conn.close()

    def test_20_zero_write_on_get_request(self):
        """Permintaan GET ke route penonaktifan murni baca (100% zero-write ke DB)."""
        copy_id = self._create_sample_copy("Kamus Besar Bahasa Indonesia", "Tim Balai Pustaka")
        self._login_admin()

        hash_before = self._get_db_hash()

        # 1. Buka HTML beberapa kali
        self.client.get(f'/admin/copies/{copy_id}/deactivate')
        self.client.get(f'/admin/eksemplar/{copy_id}/nonaktifkan')

        # 2. Buka JSON API
        self.client.get(f'/admin/copies/{copy_id}/deactivate', headers={'Accept': 'application/json'})

        hash_after = self._get_db_hash()
        self.assertEqual(hash_before, hash_after, "Hash basis data harus identik 100% setelah seluruh request GET!")

    def test_21_legacy_p1_schema_fallback(self):
        """Penonaktifan buku pada database skema legacy P1 (tabel buku + id_buku_fisik + stok)."""
        legacy_db = os.path.join(self.test_dir, 'test_legacy_p1.db')
        conn = sqlite3.connect(legacy_db)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE buku (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                judul TEXT NOT NULL,
                pengarang TEXT,
                kategori TEXT,
                rak TEXT,
                no_panggil TEXT,
                stok INTEGER DEFAULT 1,
                id_buku_fisik TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE audit_log (
                id TEXT PRIMARY KEY,
                at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                reason TEXT,
                detail_json TEXT
            );
        """)
        conn.execute("""
            INSERT INTO buku (id, judul, pengarang, stok, id_buku_fisik)
            VALUES (101, 'Buku Pelajaran Fisika', 'Prof. Joko', 2, '["FIS-001", "FIS-002"]');
        """)
        conn.commit()

        # Panggil deactivate_copy pada eksemplar FIS-001
        res = deactivate_copy(
            conn,
            copy_id="FIS-001",
            reason="Buku lama hilang dari rak perpustakaan",
            actor="admin",
            target_status="hilang"
        )
        self.assertTrue(res.get('ok'))
        conn.commit()

        # Periksa buku di tabel buku
        row = conn.execute("SELECT * FROM buku WHERE id = 101;").fetchone()
        self.assertEqual(row['stok'], 1)
        remaining_fisik = json.loads(row['id_buku_fisik'])
        self.assertNotIn("FIS-001", remaining_fisik)
        self.assertIn("FIS-002", remaining_fisik)

        # Periksa audit log
        audit = conn.execute("SELECT * FROM audit_log WHERE object_id = 'FIS-001';").fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit['action'], 'COPY_DEACTIVATE')
        conn.close()

    def test_22_target_status_options_support(self):
        """Mendukung penandaan eksemplar ke berbagai target status resmi (rusak, hilang, dalam_penanganan)."""
        self._login_admin()

        targets = [
            ("rusak", "COPY_MARK_RUSAK", "Rusak terkena rayap"),
            ("hilang", "COPY_MARK_HILANG", "Hilang tidak ada di rak setelah stock opname"),
            ("dalam_penanganan", "COPY_MARK_DALAM_PENANGANAN", "Sedang diperbaiki jilidnya"),
        ]

        for target_st, expected_action, reason in targets:
            cid = self._create_sample_copy(f"Buku Status {target_st}", "Penulis Uji")
            res = self.client.post(
                f'/admin/copies/{cid}/deactivate',
                headers={'X-CSRFToken': 'test-valid-csrf-token-310', 'Content-Type': 'application/json'},
                data=json.dumps({
                    'reason': reason,
                    'target_status': target_st,
                })
            )
            self.assertEqual(res.status_code, 200)

            conn = sqlite3.connect(self.test_db)
            conn.row_factory = sqlite3.Row
            c = copy_repo.get_copy_by_id(conn, cid)
            self.assertEqual(c['status'], target_st)

            audit = conn.execute(
                "SELECT * FROM audit_log WHERE object_id = ? ORDER BY id DESC LIMIT 1;",
                (cid,)
            ).fetchone()
            self.assertEqual(audit['action'], expected_action)
            conn.close()


if __name__ == '__main__':
    unittest.main()
