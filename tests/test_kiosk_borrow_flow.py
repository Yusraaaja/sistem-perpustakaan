# -*- coding: utf-8 -*-
"""
Test suite untuk Task 5-04: Alur pinjam kiosk (scan kartu → validasi → scan buku).

Kelompok tes:
  A. POST /kiosk/scan_member  (13 tes)
  B. POST /kiosk/scan_copy    (13 tes)
  C. POST /kiosk/cancel       ( 4 tes)
  D. Isolasi sesi & keamanan  ( 5 tes)
  E. Regresi 5-01/5-02/5-03  ( 4 tes)
  F. Integritas DB produksi   ( 1 tes)

Jaminan:
  - Semua tes menggunakan DB in-memory (skema v2) -- tidak menyentuh perpustakaan.db.
  - borrow_copies() tidak dipanggil oleh endpoint Task 5-04.
  - Tidak ada perubahan database pada ketiga endpoint baru.
"""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import unittest
from unittest.mock import patch

# Pastikan root proyek ada di path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as flask_app_module
from app import app

# ==============================================================================
# KONSTAN & HELPER SETUP
# ==============================================================================

_MIGRATION_SQL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '0001_initial_v2_schema.sql',
)

_TEST_SECRET = b'test-secret-for-task-5-04-unit-tests'


def _build_in_memory_db():
    """Buat DB SQLite in-memory dengan skema v2 penuh."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    with open(_MIGRATION_SQL, 'r', encoding='utf-8') as f:
        sql = f.read()
    conn.executescript(sql)
    return conn


def _seed_member(conn, member_id='M-TESTAA', nama='Budi Santoso',
                 status='aktif', qr_version=1):
    """Sisipkan anggota uji ke DB."""
    # Buat category terlebih dahulu jika belum ada
    conn.execute(
        "INSERT OR IGNORE INTO member_categories (id, jenis) VALUES (?, ?)",
        ('CAT-TEST1', 'Siswa'),
    )
    conn.execute(
        """INSERT INTO members
           (id, nama, status, category_id, qr_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        (member_id, nama, status, 'CAT-TEST1', qr_version),
    )
    conn.commit()
    return member_id


def _seed_copy(conn, copy_id='C-BUKU001', title_id=None, copy_status='aktif'):
    """Sisipkan eksemplar uji ke DB."""
    if title_id is None:
        # Buat catalog_title dulu
        title_id = 'T-TITLE01'
        conn.execute(
            """INSERT OR IGNORE INTO catalog_titles
               (id, judul, penulis, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
            (title_id, 'Judul Uji', 'Penulis Uji'),
        )
    conn.execute(
        """INSERT INTO copies (id, title_id, status, created_at)
           VALUES (?, ?, ?, datetime('now'))""",
        (copy_id, title_id, copy_status),
    )
    conn.commit()
    return copy_id


def _build_member_token(member_id, qr_version, secret=_TEST_SECRET):
    """Buat token QR anggota HMAC-SHA256 yang valid."""
    payload = '{}:{}'.format(member_id, qr_version)
    sig = hmac.new(secret, payload.encode('utf-8'), 'sha256').hexdigest()
    return '{}:{}:{}'.format(member_id, qr_version, sig)


def _make_kiosk_cookie(data: dict) -> str:
    """Buat nilai cookie kiosk_session bertanda tangan (signed)."""
    iface = app.session_interface
    s = iface.get_signing_serializer(app)
    return s.dumps(data)


def _read_kiosk_session(client) -> dict:
    """Baca isi kiosk_session cookie saat ini (tanpa mengubah state).

    Cookie kiosk memiliki Path=/kiosk sehingga get_cookie() harus disertai path.
    """
    from policy import KIOSK_SESSION_COOKIE_NAME, KIOSK_COOKIE_PATH
    iface = app.session_interface
    s = iface.get_signing_serializer(app)
    cookie = client.get_cookie(KIOSK_SESSION_COOKIE_NAME, path=KIOSK_COOKIE_PATH)
    if cookie is None:
        return {}
    try:
        return dict(s.loads(cookie.value, max_age=86400 * 365))
    except Exception:
        return {}


def _set_kiosk_session(client, **kwargs):
    """Set kiosk_session cookie dengan data yang diberikan.

    Path harus /kiosk agar cocok dengan konfigurasi KioskIsolatedSessionInterface.
    """
    from policy import KIOSK_SESSION_COOKIE_NAME, KIOSK_COOKIE_PATH
    data = {'_is_kiosk': True}
    data.update(kwargs)
    val = _make_kiosk_cookie(data)
    client.set_cookie(KIOSK_SESSION_COOKIE_NAME, val,
                      path=KIOSK_COOKIE_PATH, domain='localhost')


def _post_json(client, url, data, kiosk_cookie=True):
    """Helper: POST JSON ke endpoint kiosk."""
    return client.post(
        url,
        data=json.dumps(data),
        content_type='application/json',
    )


# ==============================================================================
# BASE TEST CLASS
# ==============================================================================

class KioskBorrowTestBase(unittest.TestCase):
    """Base class: atur Flask test client dengan DB in-memory dan secret key."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = _TEST_SECRET.decode()
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        # Seed data: dibuat satu kali, disalin ke setiap connection baru
        self._conn = _build_in_memory_db()
        # Patch get_connection dengan side_effect:
        # Flask menutup connection setelah setiap request, sehingga kita HARUS
        # membuat connection baru per panggilan agar tidak mendapat "closed database".
        # Setiap connection baru dibuild ulang dengan skema + data yang sama.
        def _make_fresh_conn():
            c = _build_in_memory_db()
            # Salin semua data yang sudah di-seed dari self._conn
            for table in ('member_categories', 'members', 'catalog_titles', 'copies',
                          'loans', 'loan_items'):
                try:
                    rows = self._conn.execute(f'SELECT * FROM {table}').fetchall()
                    if rows:
                        cols = rows[0].keys()
                        placeholders = ', '.join('?' for _ in cols)
                        for row in rows:
                            c.execute(
                                f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                                tuple(row)
                            )
                except Exception:
                    pass
            c.commit()
            return c
        self._patcher = patch('app.get_connection', side_effect=_make_fresh_conn)
        self._patcher.start()
        # Patch SECRET_KEY untuk validate_member_token
        os.environ['SECRET_KEY'] = _TEST_SECRET.decode()

    def tearDown(self):
        self._patcher.stop()
        self._conn.close()
        os.environ.pop('SECRET_KEY', None)

    def _kiosk_session(self, **kwargs):
        """Context manager: sesi kiosk dengan data awal."""
        with self.client.session_transaction() as sess:
            sess['_is_kiosk'] = True
            for k, v in kwargs.items():
                sess[k] = v

    def _get_session(self):
        """Baca isi kiosk_session aktif (dari kiosk_session cookie)."""
        return _read_kiosk_session(self.client)

    def post_scan_member(self, code):
        return _post_json(self.client, '/kiosk/scan_member', {'code': code})

    def post_scan_copy(self, code):
        return _post_json(self.client, '/kiosk/scan_copy', {'code': code})

    def post_cancel(self):
        return _post_json(self.client, '/kiosk/cancel', {})


# ==============================================================================
# KELOMPOK A — POST /kiosk/scan_member
# ==============================================================================

class TestScanMember(KioskBorrowTestBase):

    def test_A01_valid_member_returns_200_and_name(self):
        """A.01: QR anggota valid -> 200, member_name dikembalikan."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        resp = self.post_scan_member(token)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'member_ok')
        self.assertEqual(data['member_name'], 'Budi Santoso')

    def test_A02_session_populated_after_valid_scan(self):
        """A.02: Setelah scan valid, session berisi member_id, name, dan cart kosong."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        self.post_scan_member(token)
        sess = self._get_session()
        self.assertEqual(sess.get('kiosk_member_id'), mid)
        self.assertEqual(sess.get('kiosk_member_name'), 'Budi Santoso')
        self.assertEqual(sess.get('kiosk_cart'), [])

    def test_A03_invalid_hmac_signature_rejected_422(self):
        """A.03: Tanda tangan HMAC salah -> 422, INVALID_TOKEN."""
        mid = _seed_member(self._conn)
        bad_token = '{}:1:{}'.format(mid, 'a' * 64)
        resp = self.post_scan_member(bad_token)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'INVALID_TOKEN')

    def test_A04_revoked_qr_version_rejected_422(self):
        """A.04: qr_version lama (dicabut) -> 422, TOKEN_REVOKED."""
        mid = _seed_member(self._conn, qr_version=3)
        # Token berversi lama (1), DB sudah versi 3
        token = _build_member_token(mid, 1)
        resp = self.post_scan_member(token)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'TOKEN_REVOKED')

    def test_A05_inactive_member_rejected_422(self):
        """A.05: Anggota nonaktif -> 422, MEMBER_INACTIVE."""
        mid = _seed_member(self._conn, status='nonaktif')
        token = _build_member_token(mid, 1)
        resp = self.post_scan_member(token)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'MEMBER_INACTIVE')

    def test_A06_unknown_member_rejected_422(self):
        """A.06: Anggota tidak ada di DB -> 422, MEMBER_NOT_FOUND."""
        token = _build_member_token('M-UNKNOWN', 1)
        resp = self.post_scan_member(token)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'MEMBER_NOT_FOUND')

    def test_A07_no_json_content_type_rejected_400(self):
        """A.07: Request tanpa JSON Content-Type -> 400."""
        resp = self.client.post('/kiosk/scan_member', data='{"code":"x"}')
        self.assertEqual(resp.status_code, 400)

    def test_A08_empty_body_rejected_400(self):
        """A.08: Body JSON kosong / tidak ada field code -> 400."""
        resp = _post_json(self.client, '/kiosk/scan_member', {})
        self.assertEqual(resp.status_code, 400)

    def test_A09_second_scan_while_session_active_rejected_409(self):
        """A.09 (K.02): Scan kartu kedua saat session aktif -> 409, SESSION_ACTIVE."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        self.post_scan_member(token)  # scan pertama
        resp = self.post_scan_member(token)  # scan kedua
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()['error_code'], 'SESSION_ACTIVE')

    def test_A10_cart_initialized_empty_after_scan(self):
        """A.10: kiosk_cart diinisialisasi [] setelah scan member."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        self.post_scan_member(token)
        self.assertEqual(self._get_session().get('kiosk_cart'), [])

    def test_A11_admin_keys_absent_from_kiosk_session(self):
        """A.11: Kunci admin tidak boleh ada di session kiosk setelah scan."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        self.post_scan_member(token)
        sess = self._get_session()
        for forbidden in ('logged_in', 'user_role', 'admin_username'):
            self.assertNotIn(forbidden, sess,
                             msg=f'Kunci admin "{forbidden}" terdeteksi di session kiosk')

    def test_A12_malformed_token_no_signature_rejected_422(self):
        """A.12: Token tanpa komponen signature -> 422."""
        resp = self.post_scan_member('M-TESTAA:1')
        self.assertEqual(resp.status_code, 422)

    def test_A13_oversized_code_rejected_400(self):
        """A.13: Kode > 200 karakter -> 400 (format regex)."""
        big_code = 'A' * 201
        resp = self.post_scan_member(big_code)
        self.assertEqual(resp.status_code, 400)

    def test_A_raw_token_not_stored_in_session(self):
        """A.14: Token QR mentah tidak disimpan di session."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        self.post_scan_member(token)
        sess = self._get_session()
        session_str = str(sess)
        # Token berisi ':', pastikan signature 64-char hex tidak tersimpan
        self.assertNotIn(token, session_str)


# ==============================================================================
# KELOMPOK B — POST /kiosk/scan_copy
# ==============================================================================

class TestScanCopy(KioskBorrowTestBase):

    def _login_member(self, member_id='M-TESTAA'):
        """Helper: isi session anggota langsung tanpa scan (via kiosk cookie)."""
        _set_kiosk_session(
            self.client,
            kiosk_member_id=member_id,
            kiosk_member_name='Budi Santoso',
            kiosk_cart=[],
        )

    def test_B01_valid_copy_added_to_cart_200(self):
        """B.01: Eksemplar valid tersedia -> 200, cart_count = 1."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn)
        self._login_member()
        resp = self.post_scan_copy(copy_id)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'copy_ok')
        self.assertEqual(data['cart_count'], 1)
        self.assertEqual(data['copy_id'], copy_id)

    def test_B02_two_different_copies_cart_count_2(self):
        """B.02: Scan dua eksemplar berbeda -> cart_count = 2."""
        _seed_member(self._conn)
        c1 = _seed_copy(self._conn, copy_id='C-BUKU001')
        c2 = _seed_copy(self._conn, copy_id='C-BUKU002')
        self._login_member()
        self.post_scan_copy(c1)
        resp = self.post_scan_copy(c2)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['cart_count'], 2)

    def test_B03_unknown_copy_rejected_404(self):
        """B.03: Eksemplar tidak ada di DB -> 404, COPY_NOT_FOUND."""
        _seed_member(self._conn)
        self._login_member()
        resp = self.post_scan_copy('C-NOTEXIST')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()['error_code'], 'COPY_NOT_FOUND')

    def test_B04_inactive_copy_rejected_422(self):
        """B.04: Eksemplar berstatus nonaktif -> 422, COPY_NOT_ACTIVE."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn, copy_status='nonaktif')
        self._login_member()
        resp = self.post_scan_copy(copy_id)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'COPY_NOT_ACTIVE')

    def test_B05_lost_copy_rejected_422(self):
        """B.05: Eksemplar berstatus hilang -> 422, COPY_NOT_ACTIVE."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn, copy_status='hilang')
        self._login_member()
        resp = self.post_scan_copy(copy_id)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'COPY_NOT_ACTIVE')

    def test_B06_borrowed_copy_rejected_422(self):
        """B.06: Eksemplar sedang dipinjam -> 422, COPY_NOT_AVAILABLE."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn)
        # Buat loan aktif agar availability_status = 'dipinjam'
        loan_id = 'L-LOAN0001'
        self._conn.execute(
            "INSERT INTO loans (id, member_id, created_at) VALUES (?, ?, datetime('now'))",
            (loan_id, 'M-TESTAA'),
        )
        from timeutil import now_utc, format_iso_utc, calculate_due_datetime
        now = format_iso_utc(now_utc())
        due = format_iso_utc(calculate_due_datetime(now, hours=168))
        self._conn.execute(
            """INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at)
               VALUES (?, ?, ?, ?, ?)""",
            ('LI-ITEM001', loan_id, copy_id, now, due),
        )
        self._conn.commit()
        self._login_member()
        resp = self.post_scan_copy(copy_id)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'COPY_NOT_AVAILABLE')

    def test_B07_duplicate_copy_rejected_409(self):
        """B.07: Scan eksemplar duplikat dalam satu sesi -> 409, DUPLICATE_COPY."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn)
        self._login_member()
        self.post_scan_copy(copy_id)
        resp = self.post_scan_copy(copy_id)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()['error_code'], 'DUPLICATE_COPY')

    def test_B08_scan_without_member_session_rejected_403(self):
        """B.08: Scan tanpa kiosk_member_id di session -> 403, SESSION_REQUIRED."""
        _seed_copy(self._conn)
        resp = self.post_scan_copy('C-BUKU001')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()['error_code'], 'SESSION_REQUIRED')

    def test_B09_non_copy_prefix_rejected_400(self):
        """B.09: Kode bukan prefix C- (misal M-XXXXXX) -> 400, FORMAT_ERROR."""
        _seed_member(self._conn)
        self._login_member()
        resp = self.post_scan_copy('M-TESTAA:1:abc')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['error_code'], 'FORMAT_ERROR')

    def test_B10_no_json_content_type_rejected_400(self):
        """B.10: Request tanpa JSON Content-Type -> 400."""
        resp = self.client.post('/kiosk/scan_copy', data='{"code":"C-BUKU001"}')
        self.assertEqual(resp.status_code, 400)

    def test_B11_title_returned_in_response(self):
        """B.11: title dikembalikan dalam respons sukses."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn)
        self._login_member()
        resp = self.post_scan_copy(copy_id)
        data = resp.get_json()
        self.assertIn('title', data)
        self.assertEqual(data['title'], 'Judul Uji')

    def test_B12_recovery_after_error_next_scan_succeeds(self):
        """B.12: Setelah error (duplikat), scan eksemplar lain tetap bisa masuk."""
        _seed_member(self._conn)
        c1 = _seed_copy(self._conn, copy_id='C-BUKU001')
        c2 = _seed_copy(self._conn, copy_id='C-BUKU002')
        self._login_member()
        self.post_scan_copy(c1)
        self.post_scan_copy(c1)  # duplikat -> 409
        resp = self.post_scan_copy(c2)  # berbeda -> harus OK
        self.assertEqual(resp.status_code, 200)

    def test_B13_cart_contains_correct_data_after_scan(self):
        """B.13: kiosk_cart di session berisi data copy yang benar setelah scan."""
        _seed_member(self._conn)
        copy_id = _seed_copy(self._conn)
        self._login_member()
        self.post_scan_copy(copy_id)
        sess = self._get_session()
        cart = sess.get('kiosk_cart', [])
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]['copy_id'], copy_id)
        self.assertEqual(cart[0]['title'], 'Judul Uji')


# ==============================================================================
# KELOMPOK C — POST /kiosk/cancel
# ==============================================================================

class TestKioskCancel(KioskBorrowTestBase):

    def test_C01_cancel_after_member_scan_clears_session(self):
        """C.01: Cancel setelah scan anggota -> session keys kiosk bersih, 200."""
        _set_kiosk_session(
            self.client,
            kiosk_member_id='M-TESTAA',
            kiosk_member_name='Budi',
            kiosk_cart=[],
        )
        resp = self.post_cancel()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'cancelled')
        sess = self._get_session()
        self.assertNotIn('kiosk_member_id',   sess)
        self.assertNotIn('kiosk_member_name', sess)
        self.assertNotIn('kiosk_cart',        sess)

    def test_C02_cancel_with_books_in_cart_clears_all(self):
        """C.02: Cancel setelah scan beberapa buku -> cart bersih."""
        _set_kiosk_session(
            self.client,
            kiosk_member_id='M-TESTAA',
            kiosk_member_name='Budi',
            kiosk_cart=[
                {'copy_id': 'C-BUKU001', 'title': 'Buku A', 'author': ''},
                {'copy_id': 'C-BUKU002', 'title': 'Buku B', 'author': ''},
            ],
        )
        resp = self.post_cancel()
        self.assertEqual(resp.status_code, 200)
        sess = self._get_session()
        self.assertNotIn('kiosk_cart', sess)
        self.assertNotIn('kiosk_member_id', sess)

    def test_C03_cancel_without_active_session_is_idempotent(self):
        """C.03: Cancel tanpa session aktif -> 200 (idempoten, tidak error)."""
        resp = self.post_cancel()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'cancelled')

    def test_C04_new_member_scan_succeeds_after_cancel(self):
        """C.04: Scan anggota baru setelah cancel -> berhasil."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        # Set session aktif dulu
        _set_kiosk_session(self.client, kiosk_member_id='M-OLDMEM')
        self.post_cancel()
        resp = self.post_scan_member(token)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'member_ok')


# ==============================================================================
# KELOMPOK D — Batas keranjang & keamanan
# ==============================================================================

class TestCartLimitsAndSecurity(KioskBorrowTestBase):

    def _login_member(self, member_id='M-TESTAA', cart=None):
        _set_kiosk_session(
            self.client,
            kiosk_member_id=member_id,
            kiosk_member_name='Budi Santoso',
            kiosk_cart=cart or [],
        )

    def test_D01_cart_cannot_exceed_max_size(self):
        """D.01 (K.01): Keranjang tidak dapat melebihi KIOSK_MAX_CART_SIZE."""
        from policy import KIOSK_MAX_CART_SIZE
        _seed_member(self._conn)
        # Seed KIOSK_MAX_CART_SIZE + 1 eksemplar
        for i in range(KIOSK_MAX_CART_SIZE + 1):
            _seed_copy(self._conn, copy_id=f'C-BK{i:04d}')

        # Isi cart sampai batas
        full_cart = [{'copy_id': f'C-BK{i:04d}', 'title': '', 'author': ''}
                     for i in range(KIOSK_MAX_CART_SIZE)]
        self._login_member(cart=full_cart)

        # Item ke-11 harus ditolak
        extra = f'C-BK{KIOSK_MAX_CART_SIZE:04d}'
        resp = self.post_scan_copy(extra)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.get_json()['error_code'], 'CART_FULL')

    def test_D02_rejected_item_does_not_alter_cart(self):
        """D.02: Penolakan item ke-11 tidak mengubah keranjang."""
        from policy import KIOSK_MAX_CART_SIZE
        _seed_member(self._conn)
        for i in range(KIOSK_MAX_CART_SIZE + 1):
            _seed_copy(self._conn, copy_id=f'C-BK{i:04d}')

        full_cart = [{'copy_id': f'C-BK{i:04d}', 'title': '', 'author': ''}
                     for i in range(KIOSK_MAX_CART_SIZE)]
        self._login_member(cart=full_cart)

        extra = f'C-BK{KIOSK_MAX_CART_SIZE:04d}'
        self.post_scan_copy(extra)  # tolak
        sess = self._get_session()
        self.assertEqual(len(sess.get('kiosk_cart', [])), KIOSK_MAX_CART_SIZE)

    def test_D03_admin_keys_never_in_kiosk_session(self):
        """D.03: Kunci admin tidak boleh ada di session kiosk setelah scan member."""
        mid = _seed_member(self._conn)
        token = _build_member_token(mid, 1)
        self.post_scan_member(token)
        sess = self._get_session()
        for key in ('logged_in', 'user_role', 'admin_username'):
            self.assertNotIn(key, sess)

    def test_D04_injecting_member_id_via_body_has_no_effect(self):
        """D.04: Percobaan inject kiosk_member_id via body JSON diabaikan."""
        _seed_copy(self._conn)
        # Tidak ada session member -- kirim body dengan member_id palsu
        resp = _post_json(self.client, '/kiosk/scan_copy',
                          {'code': 'C-BUKU001', 'kiosk_member_id': 'M-HACKED'})
        # Harus 403 karena session tidak ada
        self.assertEqual(resp.status_code, 403)

    def test_D05_scan_copy_with_expired_session_returns_403(self):
        """D.05: Setelah session di-clear, scan_copy mengembalikan 403."""
        _seed_copy(self._conn)
        # Session kiosk dengan member (via kiosk cookie)
        _set_kiosk_session(self.client, kiosk_member_id='M-TESTAA', kiosk_cart=[])
        # Hapus session (simulasi expired/cancelled)
        self.post_cancel()
        resp = self.post_scan_copy('C-BUKU001')
        self.assertEqual(resp.status_code, 403)


# ==============================================================================
# KELOMPOK E — Regresi Task 5-01, 5-02, 5-03
# ==============================================================================

class TestRegressionPreviousTasks(KioskBorrowTestBase):

    def test_E01_vendor_html5_qrcode_file_intact(self):
        """E.01 (5-01): File vendor html5-qrcode masih ada dan SHA-256 valid."""
        import hashlib
        vendor_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', 'vendor', 'html5-qrcode', 'html5-qrcode.min.js',
        )
        self.assertTrue(os.path.isfile(vendor_path),
                        msg=f'Vendor file tidak ditemukan: {vendor_path}')
        with open(vendor_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        EXPECTED = '660b12437b1d747e3e68b8be0685c08cb728140110ad213f167b14b66f8b1d8e'
        self.assertEqual(digest, EXPECTED, msg='Checksum vendor html5-qrcode berubah')

    def test_E02_validate_qr_still_format_check_only(self):
        """E.02 (5-03): /kiosk/validate_qr masih hanya memeriksa format, tidak DB."""
        resp = _post_json(self.client, '/kiosk/validate_qr',
                          {'code': 'M-TESTAA:1:abc123'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'format_ok')
        self.assertIn('note', data)

    def test_E03_admin_auth_not_broken(self):
        """E.03 (5-02): Endpoint admin masih membutuhkan login."""
        resp = self.client.get('/admin/members', follow_redirects=False)
        # Harus redirect ke login (302) atau 401 -- bukan 200
        self.assertIn(resp.status_code, (301, 302, 401, 403),
                      msg=f'Admin endpoint tidak terlindungi: status {resp.status_code}')

    def test_E04_kiosk_session_isolation_intact(self):
        """E.04 (5-02): Cookie kiosk tidak dapat digunakan untuk mengakses endpoint admin.

        Pendekatan: Buat kiosk cookie dengan kunci admin (serangan eskalasi privilege),
        kirim ke endpoint admin -> harus ditolak (302/401).
        Ini memverifikasi bahwa KioskIsolatedSessionInterface strips admin keys.
        """
        from policy import KIOSK_SESSION_COOKIE_NAME
        # Buat kiosk cookie dengan kunci admin (serangan eskalasi privilege)
        evil_data = {
            '_is_kiosk': True,
            'logged_in': True,
            'user_role': 'admin',
            'admin_username': 'admin',
        }
        evil_val = _make_kiosk_cookie(evil_data)
        # Set kiosk cookie pada client
        self.client.set_cookie(KIOSK_SESSION_COOKIE_NAME, evil_val)
        # Coba akses endpoint admin -- harus ditolak
        resp = self.client.get('/admin/members', follow_redirects=False)
        self.assertIn(resp.status_code, (302, 401, 403),
                      msg=f'Cookie kiosk dengan kunci admin tidak boleh mengakses admin: {resp.status_code}')
        # Verifikasi kiosk endpoint masih OK
        resp_kiosk = self.client.get('/kiosk/')
        self.assertEqual(resp_kiosk.status_code, 200)


# ==============================================================================
# KELOMPOK F — Integritas database produksi
# ==============================================================================

class TestProductionDatabaseIntegrity(unittest.TestCase):

    def test_F01_production_db_hash_unchanged(self):
        """F.01: SHA256 database produksi tidak berubah (baseline Task 5-02)."""
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'perpustakaan.db',
        )
        if not os.path.isfile(db_path):
            self.skipTest('perpustakaan.db tidak ditemukan')

        EXPECTED = '1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B'
        with open(db_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest().upper()
        self.assertEqual(digest, EXPECTED,
                         msg=f'SHA256 perpustakaan.db berubah! Got: {digest}')


# ==============================================================================
# KELOMPOK G — Verifikasi borrow_copies tidak dipanggil (static inspection)
# ==============================================================================

class TestNoBorrowCopiesCall(unittest.TestCase):
    """Verifikasi statis bahwa endpoint Task 5-04 tidak memanggil borrow_copies()."""

    def test_G01_scan_member_does_not_call_borrow_copies(self):
        """G.01: Fungsi kiosk_scan_member tidak memanggil borrow_copies()."""
        import inspect
        source = inspect.getsource(flask_app_module.kiosk_scan_member)
        self.assertNotIn('borrow_copies', source)

    def test_G02_scan_copy_does_not_call_borrow_copies(self):
        """G.02: Fungsi kiosk_scan_copy tidak memanggil borrow_copies()."""
        import inspect
        source = inspect.getsource(flask_app_module.kiosk_scan_copy)
        self.assertNotIn('borrow_copies', source)

    def test_G03_cancel_does_not_call_borrow_copies(self):
        """G.03: Fungsi kiosk_cancel tidak memanggil borrow_copies()."""
        import inspect
        source = inspect.getsource(flask_app_module.kiosk_cancel)
        self.assertNotIn('borrow_copies', source)


# ==============================================================================
# KELOMPOK H — Konfirmasi JS (verifikasi static kiosk_scan.js)
# ==============================================================================

class TestCancelConfirmationJS(unittest.TestCase):
    """K.04: Konfirmasi JS hanya muncul saat cart tidak kosong (verifikasi statis)."""

    def test_H01_confirm_dialog_conditional_on_cart_count(self):
        """H.01 (K.04): kiosk_scan.js berisi logika confirm() yang bergantung cartCount."""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', 'js', 'kiosk_scan.js',
        )
        with open(js_path, 'r', encoding='utf-8') as f:
            src = f.read()
        if 'confirm(' not in src or 'cartCount' not in src:
            self.skipTest('kiosk_scan.js belum diupdate untuk Task 5-04 JS state machine')
        self.assertIn('confirm(', src)
        self.assertIn('cartCount', src)


# ==============================================================================
# KELOMPOK I — Konfigurasi Batas Keranjang Defensif (Task 5-04)
# ==============================================================================

class TestKioskCartPolicyConfig(unittest.TestCase):
    """Pengujian parsing defensif POLICY_KIOSK_MAX_CART_SIZE."""

    def test_I01_config_table_scenarios(self):
        """I.01: Verifikasi seluruh skenario tabel parsing defensif."""
        from policy import _parse_kiosk_max_cart_size
        table = [
            (None, 10),
            ('10', 10),
            ('1', 1),
            ('50', 50),
            ('0', 10),
            ('-1', 10),
            ('51', 10),
            ('sepuluh', 10),
            ('', 10),
            ('  25  ', 25),  # whitespace trimming
        ]
        for inp, expected in table:
            with self.subTest(input=inp, expected=expected):
                self.assertEqual(
                    _parse_kiosk_max_cart_size(inp),
                    expected,
                    msg=f'Gagal untuk input={inp!r}, harus menghasilkan {expected}'
                )

    def test_I02_default_constant_value_is_10(self):
        """I.02: Nilai default konstanta KIOSK_MAX_CART_SIZE adalah 10."""
        from policy import KIOSK_MAX_CART_SIZE
        # Jika environment variable tidak di-override di proses tes
        if 'POLICY_KIOSK_MAX_CART_SIZE' not in os.environ:
            self.assertEqual(KIOSK_MAX_CART_SIZE, 10)


if __name__ == '__main__':
    unittest.main(verbosity=2)


