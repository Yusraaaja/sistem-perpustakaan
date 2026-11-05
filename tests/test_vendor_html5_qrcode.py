"""
Uji Terisolasi Task 5-01: Vendor html5-qrcode ke static/vendor Tanpa CDN.

Memverifikasi:
1. Keberadaan dan kelengkapan berkas vendor di static/vendor/html5-qrcode/ dan static/vendor/
2. Validitas isi, ukuran byte, dan checksum SHA-256 kriptografis library html5-qrcode
3. Lisensi resmi Apache-2.0 dan metadata versi 2.3.8
4. Berkas adalah distribusi JavaScript yang valid (bukan halaman HTML error)
5. Flask test client dapat melayani aset statis vendor dengan status 200 dan Content-Type yang sesuai
6. Klien anonim/kiosk dapat mengakses aset vendor tanpa sesi admin
7. Seluruh template proyek bebas dari referensi CDN untuk html5-qrcode
8. Database produksi perpustakaan.db 100% tidak tersentuh (Zero-Write)
"""

import os
import unittest
import hashlib
import json
import subprocess
from app import app

EXPECTED_MIN_JS_SHA256 = "660b12437b1d747e3e68b8be0685c08cb728140110ad213f167b14b66f8b1d8e"
EXPECTED_MIN_JS_SIZE = 375364
EXPECTED_VERSION = "2.3.8"
EXPECTED_LICENSE = "Apache-2.0"
ORIGINAL_DB_SHA256 = "1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B"


class TestVendorHtml5Qrcode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.vendor_dir = os.path.join(cls.project_root, "static", "vendor")
        cls.pkg_dir = os.path.join(cls.vendor_dir, "html5-qrcode")
        cls.min_js_path = os.path.join(cls.pkg_dir, "html5-qrcode.min.js")
        cls.root_min_js_path = os.path.join(cls.vendor_dir, "html5-qrcode.min.js")
        cls.pkg_json_path = os.path.join(cls.pkg_dir, "package.json")
        cls.license_path = os.path.join(cls.pkg_dir, "LICENSE")
        cls.vendor_readme_path = os.path.join(cls.vendor_dir, "README.md")
        cls.db_path = os.path.join(cls.project_root, "perpustakaan.db")

        app.config["TESTING"] = True
        cls.client = app.test_client()

    def test_01_vendor_files_exist(self):
        """Seluruh berkas vendor wajib tersedia pada direktori static/vendor/."""
        self.assertTrue(os.path.isdir(self.vendor_dir), "Direktori static/vendor/ wajib ada.")
        self.assertTrue(os.path.isdir(self.pkg_dir), "Direktori static/vendor/html5-qrcode/ wajib ada.")
        self.assertTrue(os.path.isfile(self.min_js_path), "Berkas html5-qrcode.min.js di subdirektori wajib ada.")
        self.assertTrue(os.path.isfile(self.root_min_js_path), "Berkas html5-qrcode.min.js alias root vendor wajib ada.")
        self.assertTrue(os.path.isfile(self.pkg_json_path), "Berkas package.json wajib ada.")
        self.assertTrue(os.path.isfile(self.license_path), "Berkas LICENSE wajib ada.")
        self.assertTrue(os.path.isfile(self.vendor_readme_path), "Berkas static/vendor/README.md wajib ada.")

    def test_02_min_js_exact_size_and_sha256(self):
        """Ukuran berkas dan checksum SHA-256 html5-qrcode.min.js wajib presisi cocok dengan rilis resmi."""
        with open(self.min_js_path, "rb") as f:
            content = f.read()

        self.assertEqual(len(content), EXPECTED_MIN_JS_SIZE, f"Ukuran berkas harus tepat {EXPECTED_MIN_JS_SIZE} bytes.")
        sha256_hash = hashlib.sha256(content).hexdigest()
        self.assertEqual(sha256_hash, EXPECTED_MIN_JS_SHA256, "SHA-256 html5-qrcode.min.js harus cocok.")

        # Periksa juga alias root
        with open(self.root_min_js_path, "rb") as f:
            root_content = f.read()
        self.assertEqual(content, root_content, "Salinan alias pada root vendor wajib identik byte-for-byte.")

    def test_03_min_js_is_valid_javascript_not_html(self):
        """Berkas html5-qrcode.min.js adalah JavaScript murni dan bukan halaman HTML error."""
        with open(self.min_js_path, "r", encoding="utf-8", errors="ignore") as f:
            header = f.read(500)

        # Tidak boleh diawali tag HTML kesalahan unduh
        self.assertNotIn("<!DOCTYPE html", header.lower())
        self.assertNotIn("<html", header.lower())
        self.assertNotIn("<head", header.lower())
        self.assertNotIn("<body", header.lower())

        # Wajib memuat inisialisasi library JavaScript
        self.assertTrue(
            header.startswith("var __Html5QrcodeLibrary__") or "Html5Qrcode" in header,
            "Berkas harus diawali struktur JavaScript html5-qrcode."
        )

    def test_04_min_js_contains_core_symbols(self):
        """Berkas min.js memuat simbol-simbol inti publik Html5Qrcode."""
        with open(self.min_js_path, "r", encoding="utf-8") as f:
            full_text = f.read()

        required_symbols = [
            "Html5Qrcode",
            "Html5QrcodeScanner",
            "Html5QrcodeSupportedFormats",
            "Html5QrcodeScannerState",
            "Html5QrcodeScanType"
        ]
        for sym in required_symbols:
            self.assertIn(sym, full_text, f"Simbol {sym} harus didefinisikan dalam kode minified.")

    def test_05_package_metadata_version_and_license(self):
        """package.json mendokumentasikan versi 2.3.8 dan lisensi Apache-2.0 secara akurat."""
        with open(self.pkg_json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertEqual(meta.get("name"), "html5-qrcode")
        self.assertEqual(meta.get("version"), EXPECTED_VERSION)
        self.assertEqual(meta.get("license"), EXPECTED_LICENSE)
        self.assertIn("mebjas/html5-qrcode", meta.get("homepage", ""))

    def test_06_license_text_is_apache_2_0(self):
        """Berkas LICENSE memuat teks resmi lisensi Apache License 2.0."""
        with open(self.license_path, "r", encoding="utf-8") as f:
            lic = f.read()

        self.assertIn("Apache License", lic)
        self.assertIn("Version 2.0, January 2004", lic)
        self.assertIn("http://www.apache.org/licenses/", lic)

    def test_07_vendor_readme_documents_zero_cdn_and_hashes(self):
        """Berkas static/vendor/README.md mendokumentasikan kebijakan Zero CDN dan checksum kriptografis."""
        with open(self.vendor_readme_path, "r", encoding="utf-8") as f:
            doc = f.read()

        self.assertIn("Zero CDN", doc)
        self.assertIn("html5-qrcode", doc)
        self.assertIn("2.3.8", doc)
        self.assertIn("Apache License 2.0", doc)
        self.assertIn(EXPECTED_MIN_JS_SHA256, doc)

    def test_08_flask_serves_vendor_script_successfully(self):
        """Flask melayani static/vendor/html5-qrcode/html5-qrcode.min.js dengan status 200 dan mimetype javascript."""
        resp = self.client.get("/static/vendor/html5-qrcode/html5-qrcode.min.js")
        try:
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(
                "javascript" in resp.content_type.lower() or "text/plain" in resp.content_type.lower(),
                f"Content-type harus javascript, didapat: {resp.content_type}"
            )
            self.assertEqual(len(resp.data), EXPECTED_MIN_JS_SIZE)
            self.assertEqual(hashlib.sha256(resp.data).hexdigest(), EXPECTED_MIN_JS_SHA256)
        finally:
            resp.close()

    def test_09_flask_serves_root_alias_successfully(self):
        """Flask melayani static/vendor/html5-qrcode.min.js dengan status 200 dan isi identik."""
        resp = self.client.get("/static/vendor/html5-qrcode.min.js")
        try:
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(resp.data), EXPECTED_MIN_JS_SIZE)
            self.assertEqual(hashlib.sha256(resp.data).hexdigest(), EXPECTED_MIN_JS_SHA256)
        finally:
            resp.close()

    def test_10_anonymous_client_can_access_vendor_scripts(self):
        """Klien tanpa sesi admin (seperti kiosk tablet mandiri) dapat mengunduh aset vendor tanpa 302/401."""
        # Pastikan sesi bersih tanpa cookie
        with self.client.session_transaction() as sess:
            sess.clear()

        resp = self.client.get("/static/vendor/html5-qrcode/html5-qrcode.min.js")
        try:
            self.assertEqual(resp.status_code, 200)
        finally:
            resp.close()

    def test_11_zero_cdn_across_all_project_templates(self):
        """Seluruh template HTML di proyek dilarang keras memuat script html5-qrcode dari CDN eksternal."""
        templates_dir = os.path.join(self.project_root, "templates")
        cdn_domains = [
            "unpkg.com",
            "cdn.jsdelivr.net",
            "cdnjs.cloudflare.com",
            "cdn.jsdelivr.net/npm/html5-qrcode",
            "unpkg.com/html5-qrcode",
            "raw.githubusercontent.com"
        ]

        violations = []
        for root, _, files in os.walk(templates_dir):
            for file in files:
                if file.endswith(".html"):
                    path = os.path.join(root, file)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().lower()
                        if "html5-qrcode" in content:
                            for domain in cdn_domains:
                                if domain in content:
                                    violations.append((file, domain))

        self.assertEqual(
            violations,
            [],
            f"Ditemukan pelanggaran CDN html5-qrcode pada template: {violations}"
        )

    def test_12_node_execution_smoke_test(self):
        """Verifikasi bahwa file JavaScript dapat di-parse dan dieksekusi secara sukses oleh Node.js tanpa syntax error."""
        try:
            test_script = """
            let code = '';
            process.stdin.setEncoding('utf-8');
            process.stdin.on('data', chunk => code += chunk);
            process.stdin.on('end', () => {
                const vm = require('vm');
                const sandbox = { window: {}, navigator: { userAgent: 'test' }, document: { createElement: () => ({}) } };
                sandbox.window = sandbox;
                vm.createContext(sandbox);
                vm.runInContext(code, sandbox);
                if (typeof sandbox.Html5Qrcode === 'undefined') {
                    console.error('Html5Qrcode not exported');
                    process.exit(1);
                }
                process.exit(0);
            });
            """
            with open(self.min_js_path, "r", encoding="utf-8") as f:
                code_text = f.read()

            proc = subprocess.run(
                ["node", "-e", test_script],
                input=code_text,
                capture_output=True,
                text=True
            )
            self.assertEqual(proc.returncode, 0, f"Eksekusi Node gagal: {proc.stderr}")
        except FileNotFoundError:
            # Jika lingkungan tidak memiliki node di PATH, lewati tanpa error fatal
            self.skipTest("Node.js tidak terpasang di sistem.")

    def test_13_production_database_untouched(self):
        """Database perpustakaan.db produksi tidak boleh tersentuh atau termutasi (Zero-Write)."""
        self.assertTrue(os.path.isfile(self.db_path), "File perpustakaan.db harus ada.")
        with open(self.db_path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest().upper()
        self.assertEqual(h, ORIGINAL_DB_SHA256, "Hash SHA-256 perpustakaan.db berubah!")


if __name__ == "__main__":
    unittest.main()
