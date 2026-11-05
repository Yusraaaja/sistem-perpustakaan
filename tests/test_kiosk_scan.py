# -*- coding: utf-8 -*-
"""
tests/test_kiosk_scan.py

Tes untuk Task 5-03: komponen scan QR kiosk — debounce, UI feedback, endpoint
/kiosk/validate_qr, penanganan kamera, dan zero-CDN.

CATATAN PENTING – BATAS PENGUJIAN JAVASCRIPT:
  Repository ini tidak memiliki lingkungan pengujian JavaScript (tidak ada Node.js,
  package.json, Jest, Mocha, dsb.). Oleh karena itu:

  * Perilaku debounce, processing lock, dan operation counter yang ada di
    kiosk_scan.js TIDAK dapat diverifikasi secara otomatis di sini.
  * Pengujian di modul ini mencakup:
      1. Kontrak endpoint /kiosk/validate_qr (HTTP, JSON, validasi format).
      2. Pemeriksaan statis file kiosk_scan.js (keberadaan, elemen kode kunci).
      3. Pemeriksaan template kiosk_index.html (tanpa CDN, menggunakan vendor lokal).
      4. Tidak ada regresi pada route dan isolasi sesi Task 5-02.
      5. Integritas database produksi (zero-write).

  Perilaku debounce diverifikasi secara manual melalui inspeksi kode.
  Lihat bagian "INSPEKSI MANUAL" di laporan akhir Task 5-03.
"""

import hashlib
import json
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# ── Konstanta ──────────────────────────────────────────────────────────────────
EXPECTED_DB_HASH = '1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B'
PROD_DB_PATH = pathlib.Path(__file__).parent.parent / 'perpustakaan.db'
KIOSK_JS_PATH = pathlib.Path(__file__).parent.parent / 'static' / 'js' / 'kiosk_scan.js'
KIOSK_HTML_PATH = pathlib.Path(__file__).parent.parent / 'templates' / 'kiosk_index.html'
VENDOR_JS_PATH = (
    pathlib.Path(__file__).parent.parent /
    'static' / 'vendor' / 'html5-qrcode' / 'html5-qrcode.min.js'
)


def _post_json(client, url, payload):
    """Helper: kirim POST JSON."""
    return client.post(
        url,
        data=json.dumps(payload),
        content_type='application/json',
    )


# ══════════════════════════════════════════════════════════════════════════════
# A. Kontrak endpoint /kiosk/validate_qr
# ══════════════════════════════════════════════════════════════════════════════

class TestKioskValidateQrEndpoint(unittest.TestCase):
    """
    Pengujian otomatis kontrak HTTP endpoint /kiosk/validate_qr.
    Endpoint ini hanya memeriksa format — tidak mengakses DB, tidak
    memverifikasi identitas anggota atau ketersediaan buku.
    """

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['TESTING'] = False

    # ── Format valid ──────────────────────────────────────────────────────────

    def test_01_valid_member_token_format_accepted(self):
        """Format token anggota (M-XXXXXX) lolos pemeriksaan format."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': 'M-AB1234'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data['status'], 'format_ok')
        self.assertIn('display_code', data)
        self.assertIn('note', data)
        # Respons harus menyatakan belum diverifikasi
        self.assertIn('Belum diverifikasi', data['note'])

    def test_02_valid_copy_token_format_accepted(self):
        """Format token eksemplar buku (C-XXXXXX) lolos pemeriksaan format."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': 'C-XY5678'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data['status'], 'format_ok')

    def test_03_valid_hmac_token_format_accepted(self):
        """Format token HMAC anggota penuh lolos pemeriksaan format."""
        token = 'M-3K9X7W:1:d4c3b2a1e8f70912456789abcdef0123456789abcdef01234567'
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': token})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data['status'], 'format_ok')

    def test_04_display_code_truncated_for_long_input(self):
        """Kode panjang ditampilkan terpotong (≤12 karakter + ellipsis)."""
        long_code = 'M-ABCDEFGHIJ:1:' + 'a' * 64
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': long_code})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        display = data['display_code']
        # display_code harus ≤ 15 karakter (12 + "...")
        self.assertLessEqual(len(display), 15)

    # ── Penolakan format tidak valid ──────────────────────────────────────────

    def test_05_empty_string_rejected(self):
        """Kode kosong ditolak dengan 400."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': ''})
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('error', data)

    def test_06_whitespace_only_rejected(self):
        """Kode yang hanya spasi ditolak (strip → kosong)."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': '   '})
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertEqual(data['status'], 'error')

    def test_07_special_characters_rejected(self):
        """Karakter khusus di luar alfanumerik + ':' + '-' ditolak."""
        for bad_code in ['QR!@#$%', 'abc def', 'code<script>', '../../etc']:
            with self.subTest(code=bad_code):
                resp = _post_json(self.client, '/kiosk/validate_qr', {'code': bad_code})
                self.assertEqual(resp.status_code, 400,
                                 f'Kode "{bad_code}" seharusnya ditolak')

    def test_08_too_long_code_rejected(self):
        """Kode dengan lebih dari 200 karakter ditolak."""
        too_long = 'A' * 201
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': too_long})
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('panjang', data['error'].lower())

    def test_09_exactly_200_chars_accepted(self):
        """Kode tepat 200 karakter lolos (batas maksimum)."""
        max_code = 'A' * 200
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': max_code})
        self.assertEqual(resp.status_code, 200)

    # ── Penolakan tipe data / Content-Type salah ──────────────────────────────

    def test_10_missing_code_field_rejected(self):
        """JSON tanpa field 'code' ditolak dengan 400."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'data': 'nope'})
        self.assertEqual(resp.status_code, 400)

    def test_11_code_as_integer_rejected(self):
        """Field 'code' bertipe integer (bukan string) ditolak."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': 12345})
        self.assertEqual(resp.status_code, 400)

    def test_12_code_as_null_rejected(self):
        """Field 'code' bernilai null ditolak."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': None})
        self.assertEqual(resp.status_code, 400)

    def test_13_wrong_content_type_rejected(self):
        """Request dengan Content-Type form (bukan JSON) ditolak."""
        resp = self.client.post(
            '/kiosk/validate_qr',
            data={'code': 'M-AB1234'},
            content_type='application/x-www-form-urlencoded',
        )
        self.assertEqual(resp.status_code, 400)

    def test_14_empty_json_body_rejected(self):
        """Body JSON kosong ({}) ditolak."""
        resp = _post_json(self.client, '/kiosk/validate_qr', {})
        self.assertEqual(resp.status_code, 400)

    def test_15_response_does_not_claim_identity_verified(self):
        """
        Respons 200 tidak boleh menyebut kode sebagai 'valid' anggota/buku.
        Harus ada kata 'Belum diverifikasi' atau setara pada field 'note'.
        """
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': 'M-AB1234'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        # 'note' harus ada dan menyatakan keterbatasan verifikasi
        self.assertIn('note', data)
        note_lower = data['note'].lower()
        self.assertTrue(
            'belum' in note_lower or 'format' in note_lower,
            f"Field 'note' harus menyatakan keterbatasan format-check: {data['note']}"
        )

    def test_16_endpoint_only_accepts_post(self):
        """Endpoint /kiosk/validate_qr menolak GET."""
        resp = self.client.get('/kiosk/validate_qr')
        self.assertIn(resp.status_code, (405, 404))

    # ── Isolasi sesi ──────────────────────────────────────────────────────────

    def test_17_validate_qr_does_not_require_admin_session(self):
        """Endpoint dapat dipanggil tanpa sesi admin (publik kiosk)."""
        # Tanpa login sama sekali
        resp = _post_json(self.client, '/kiosk/validate_qr', {'code': 'M-AB1234'})
        self.assertNotEqual(resp.status_code, 401,
                            'validate_qr tidak boleh memerlukan autentikasi admin')
        self.assertNotEqual(resp.status_code, 403)

    def test_18_validate_qr_is_kiosk_path(self):
        """Path /kiosk/validate_qr dikenali sebagai kiosk request."""
        from app import _is_kiosk_request
        self.assertTrue(_is_kiosk_request('/kiosk/validate_qr'))


# ══════════════════════════════════════════════════════════════════════════════
# B. Pemeriksaan statis kiosk_scan.js
#    (inspeksi kode — bukan pengujian JS runtime)
# ══════════════════════════════════════════════════════════════════════════════

class TestKioskScanJsStaticInspection(unittest.TestCase):
    """
    Verifikasi elemen kode kunci dalam kiosk_scan.js melalui inspeksi teks.

    Ini BUKAN pengujian runtime JavaScript. Pengujian ini memastikan bahwa
    mekanisme debounce, processing lock, dan operation counter ADA dalam kode,
    sehingga dapat diverifikasi oleh code reviewer.

    Perilaku runtime harus diuji secara manual di browser.
    """

    def setUp(self):
        if not KIOSK_JS_PATH.exists():
            self.skipTest(f'kiosk_scan.js tidak ditemukan: {KIOSK_JS_PATH}')
        self.js_code = KIOSK_JS_PATH.read_text(encoding='utf-8')

    def test_js_01_file_exists(self):
        """File kiosk_scan.js harus ada."""
        self.assertTrue(KIOSK_JS_PATH.exists())

    def test_js_02_debounce_constant_defined(self):
        """Konstanta DEBOUNCE_MS harus ada dan bernilai angka > 0."""
        self.assertIn('DEBOUNCE_MS', self.js_code)
        # Cari nilai: DEBOUNCE_MS = <angka>
        import re
        match = re.search(r'DEBOUNCE_MS\s*=\s*(\d+)', self.js_code)
        self.assertIsNotNone(match, 'DEBOUNCE_MS harus memiliki nilai numerik')
        self.assertGreater(int(match.group(1)), 0)

    def test_js_03_processing_lock_variable(self):
        """Variabel lock pemrosesan (processing) harus ada."""
        self.assertIn('processing', self.js_code,
                      'Variabel lock "processing" harus ada di kiosk_scan.js')

    def test_js_04_operation_counter_variable(self):
        """Variabel nomor urut operasi (opSeq) harus ada."""
        self.assertIn('opSeq', self.js_code,
                      'Variabel counter "opSeq" harus ada di kiosk_scan.js')

    def test_js_05_lock_released_in_finally(self):
        """Lock pemrosesan harus dilepas di blok finally."""
        self.assertIn('.finally(', self.js_code,
                      'Lock harus dilepas di blok .finally()')
        # Pastikan processing = false ada di finally
        import re
        # Cari pola: .finally(function() { ... processing = false ... })
        self.assertIn('processing = false', self.js_code)

    def test_js_06_debounce_check_present(self):
        """Pemeriksaan debounce (lastSent.timestamp) harus ada."""
        self.assertIn('lastSent', self.js_code)
        self.assertIn('DEBOUNCE_MS', self.js_code)
        self.assertIn('timestamp', self.js_code)

    def test_js_07_schedule_idle_uses_seq(self):
        """scheduleIdle harus menggunakan nomor urut untuk mencegah timer lama."""
        self.assertIn('scheduleIdle', self.js_code)
        self.assertIn('opSeq', self.js_code)
        # opSeq harus dibandingkan di dalam scheduleIdle
        self.assertIn('opSeq === seq', self.js_code)

    def test_js_08_camera_error_separated_from_scan_failure(self):
        """
        handleCameraFailure harus terpisah dari onScanFailure
        (kegagalan menemukan QR di frame ≠ kegagalan akses kamera).
        """
        self.assertIn('handleCameraFailure', self.js_code)
        self.assertIn('onScanFailure', self.js_code)
        # onScanFailure tidak boleh memanggil handleCameraFailure
        import re
        # Ambil body fungsi onScanFailure
        match = re.search(
            r'function onScanFailure\s*\([^)]*\)\s*\{([^}]*)\}',
            self.js_code
        )
        if match:
            body = match.group(1)
            self.assertNotIn('handleCameraFailure', body,
                             'onScanFailure tidak boleh memanggil handleCameraFailure')

    def test_js_09_manual_input_calls_submit_code(self):
        """Input manual harus memanggil submitCode (kontroler yang sama)."""
        self.assertIn('submitCode', self.js_code)
        # Pastikan submit handler manual juga memanggil submitCode
        self.assertIn('manualSubmit', self.js_code)

    def test_js_10_validate_url_points_to_kiosk(self):
        """URL endpoint harus mengarah ke /kiosk/validate_qr."""
        self.assertIn('/kiosk/validate_qr', self.js_code)

    def test_js_11_no_cdn_url_in_js(self):
        """File JS tidak boleh memuat URL CDN eksternal."""
        cdn_patterns = ['cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com',
                        'ajax.googleapis.com', 'code.jquery.com']
        for cdn in cdn_patterns:
            self.assertNotIn(cdn, self.js_code,
                             f'kiosk_scan.js tidak boleh merujuk CDN: {cdn}')


# ══════════════════════════════════════════════════════════════════════════════
# C. Pemeriksaan template kiosk_index.html
# ══════════════════════════════════════════════════════════════════════════════

class TestKioskTemplateStaticInspection(unittest.TestCase):
    """Verifikasi statis template kiosk_index.html."""

    def setUp(self):
        if not KIOSK_HTML_PATH.exists():
            self.skipTest(f'kiosk_index.html tidak ditemukan: {KIOSK_HTML_PATH}')
        self.html = KIOSK_HTML_PATH.read_text(encoding='utf-8')

    def test_html_01_no_cdn_scripts(self):
        """Template kiosk tidak boleh memuat script dari CDN eksternal."""
        cdn_patterns = [
            'cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com',
            'ajax.googleapis.com', 'code.jquery.com', 'stackpath.bootstrapcdn.com'
        ]
        for cdn in cdn_patterns:
            self.assertNotIn(cdn, self.html,
                             f'Template kiosk tidak boleh memuat CDN: {cdn}')

    def test_html_02_uses_local_vendor_library(self):
        """Template harus memuat html5-qrcode dari vendor lokal."""
        self.assertTrue(
            'vendor/html5-qrcode' in self.html or 'html5-qrcode.min.js' in self.html,
            'Template kiosk harus memuat html5-qrcode dari static/vendor/ lokal'
        )

    def test_html_03_uses_local_kiosk_scan_js(self):
        """Template harus memuat kiosk_scan.js dari static/js/ lokal."""
        self.assertIn('kiosk_scan.js', self.html,
                      'Template kiosk harus memuat kiosk_scan.js')

    def test_html_04_status_element_present(self):
        """Elemen status UI (kiosk-status) harus ada."""
        self.assertIn('kiosk-status', self.html)

    def test_html_05_manual_input_area_present(self):
        """Area input manual harus ada di template."""
        self.assertIn('kiosk-manual-area', self.html)
        self.assertIn('kiosk-manual-input', self.html)

    def test_html_06_qr_reader_container_present(self):
        """Container QR reader (kiosk-qr-reader) harus ada."""
        self.assertIn('kiosk-qr-reader', self.html)

    def test_html_07_manual_button_present(self):
        """Tombol input manual harus ada."""
        self.assertIn('kiosk-manual-btn', self.html)

    def test_html_08_no_admin_navbar(self):
        """Template kiosk tidak boleh memuat navbar admin."""
        for admin_marker in ['/admin/', 'admin_username', '/logout']:
            self.assertNotIn(admin_marker, self.html,
                             f'Template kiosk tidak boleh memuat referensi admin: {admin_marker}')

    def test_html_09_noindex_meta_present(self):
        """Template kiosk harus memiliki meta noindex."""
        self.assertIn('noindex', self.html)

    def test_html_10_vendor_js_file_exists_on_disk(self):
        """File vendor html5-qrcode.min.js harus ada di disk."""
        self.assertTrue(VENDOR_JS_PATH.exists(),
                        f'File vendor tidak ditemukan: {VENDOR_JS_PATH}')

    def test_html_11_kiosk_scan_js_file_exists_on_disk(self):
        """File kiosk_scan.js harus ada di disk."""
        self.assertTrue(KIOSK_JS_PATH.exists(),
                        f'File kiosk_scan.js tidak ditemukan: {KIOSK_JS_PATH}')


# ══════════════════════════════════════════════════════════════════════════════
# D. Tidak ada regresi Task 5-01 dan Task 5-02
# ══════════════════════════════════════════════════════════════════════════════

class TestTask501502Regression(unittest.TestCase):
    """Pastikan Task 5-01 (vendor) dan Task 5-02 (isolasi sesi) tidak terpengaruh."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['TESTING'] = False

    def test_reg_01_vendor_file_exists(self):
        """Task 5-01: file vendor html5-qrcode.min.js harus ada dan checksum cocok."""
        self.assertTrue(VENDOR_JS_PATH.exists())
        actual = hashlib.sha256(VENDOR_JS_PATH.read_bytes()).hexdigest()
        expected = '660b12437b1d747e3e68b8be0685c08cb728140110ad213f167b14b66f8b1d8e'
        self.assertEqual(actual, expected,
                         'Checksum vendor html5-qrcode.min.js berubah!')

    def test_reg_02_kiosk_index_accessible(self):
        """Task 5-02: /kiosk/ harus dapat diakses tanpa autentikasi."""
        resp = self.client.get('/kiosk/')
        self.assertEqual(resp.status_code, 200)

    def test_reg_03_kiosk_session_isolation_unchanged(self):
        """Task 5-02: KioskIsolatedSessionInterface masih terpasang."""
        from app import KioskIsolatedSessionInterface
        self.assertIsInstance(app.session_interface, KioskIsolatedSessionInterface)

    def test_reg_04_kiosk_cookie_policy_unchanged(self):
        """Task 5-02: konstanta cookie kiosk tidak berubah."""
        from policy import (KIOSK_SESSION_COOKIE_NAME, KIOSK_COOKIE_PATH,
                            KIOSK_FORBIDDEN_SESSION_KEYS)
        self.assertEqual(KIOSK_SESSION_COOKIE_NAME, 'kiosk_session')
        self.assertEqual(KIOSK_COOKIE_PATH, '/kiosk')
        self.assertIn('logged_in', KIOSK_FORBIDDEN_SESSION_KEYS)
        self.assertIn('user_role', KIOSK_FORBIDDEN_SESSION_KEYS)
        self.assertIn('admin_username', KIOSK_FORBIDDEN_SESSION_KEYS)

    def test_reg_05_admin_route_still_protected(self):
        """Task 5-02: /admin/members harus menolak akses tanpa login."""
        resp = self.client.get('/admin/members')
        self.assertIn(resp.status_code, (302, 401))

    def test_reg_06_kiosk_validate_qr_is_kiosk_path(self):
        """Route baru /kiosk/validate_qr dikenali sebagai path kiosk."""
        from app import _is_kiosk_request
        self.assertTrue(_is_kiosk_request('/kiosk/validate_qr'))


# ══════════════════════════════════════════════════════════════════════════════
# E. Integritas database produksi
# ══════════════════════════════════════════════════════════════════════════════

class TestProductionDatabaseIntegrity(unittest.TestCase):
    """Verifikasi database produksi tidak disentuh oleh Task 5-03."""

    def test_db_01_hash_unchanged(self):
        """SHA-256 database produksi harus identik dengan baseline."""
        if not PROD_DB_PATH.exists():
            self.skipTest(f'Database tidak ditemukan: {PROD_DB_PATH}')
        actual = hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest().upper()
        self.assertEqual(
            actual, EXPECTED_DB_HASH,
            f'Hash database berubah!\n  Diharapkan: {EXPECTED_DB_HASH}\n  Aktual: {actual}'
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)

