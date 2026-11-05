# PANDUAN DEPENDENSI VENDOR LOKAL (`static/vendor/`)

Dokumen ini mencatat seluruh pustaka pihak ketiga (*third-party JavaScript/CSS libraries*) yang di-*vendor* secara lokal di dalam direktori `static/vendor/` Sistem Perpustakaan Digital Sekolah.

## Kebijakan Pustaka Vendor (Zero CDN Policy)
1. **Layanan Mandiri & Offline/Intranet-Ready (DEC-002, DEC-018):**
   * Perangkat tablet bersama di perpustakaan (mode kiosk self-service) harus dapat beroperasi secara andal dalam jaringan lokal/sekolah tanpa ketergantungan pada CDN eksternal (*Content Delivery Network*).
   * CDN pihak ketiga rentan terhadap pemblokiran firewall sekolah, pemadaman jaringan internet luar, pelacakan privasi pihak ketiga, dan risiko keamanan *supply-chain*.
2. **Integritas & Kriptografi:**
   * Setiap aset vendor wajib diperoleh dari registri resmi terpercaya (NPM Registry / repositori resmi).
   * Seluruh berkas biner diverifikasi menggunakan checksum kriptografis (SHA-1 dan SHA-256).
   * Modifikasi kode vendor dilarang kecuali didokumentasikan secara eksplisit dengan alasan teknis yang sah.

---

## Daftar Library yang Di-Vendor

### 1. `html5-qrcode`
* **Nama Paket:** `html5-qrcode`
* **Versi:** `2.3.8`
* **Fungsi / Kegunaan:** Pemindaian kode QR dan barcode multi-platform melalui kamera HTML5 pada browser tablet kiosk perpustakaan (Fase 5: Task 5-01 s.d. 5-10).
* **Penulis / Pembuat:** Minhaz Avab (`minhazav@gmail.com`)
* **Repositori Resmi:** [https://github.com/mebjas/html5-qrcode](https://github.com/mebjas/html5-qrcode)
* **Sumber Distribusi Resmi:** NPM Registry
  * URL Tarball: `https://registry.npmjs.org/html5-qrcode/-/html5-qrcode-2.3.8.tgz`
  * Tarball SHA-1: `0b0cdf7a9926cfd4be530e13a51db47592adfa0d`
  * Tarball SHA-256: `e215fbfb27f4b027519014f5bf462ceb3faf2a46dbf8d6dbd2df0e4acef0224e`
* **Lisensi:** Apache License 2.0 (berkas lisensi disertakan di `static/vendor/html5-qrcode/LICENSE`)
* **Tanggal Vendoring:** 30 Oktober 2026

#### Berkas Lokal yang Disediakan
| Jalur Berkas | Ukuran | Checksum SHA-256 | Keterangan |
|---|---|---|---|
| `static/vendor/html5-qrcode/html5-qrcode.min.js` | 375.364 byte | `660b12437b1d747e3e68b8be0685c08cb728140110ad213f167b14b66f8b1d8e` | Distribusi utama minified mandiri (termasuk ZXing decoders) |
| `static/vendor/html5-qrcode.min.js` | 375.364 byte | `660b12437b1d747e3e68b8be0685c08cb728140110ad213f167b14b66f8b1d8e` | Salinan alias pada root vendor untuk kemudahan impor |
| `static/vendor/html5-qrcode/package.json` | 3.650 byte | Metadata resmi paket NPM |
| `static/vendor/html5-qrcode/LICENSE` | 11.361 byte | Teks lengkap Apache License 2.0 |
| `static/vendor/html5-qrcode/README.md` | 23.220 byte | Dokumentasi asli pustaka |

#### Penggunaan dalam Template Jinja2 Flask
```html
<!-- Rekomendasi jalur utama -->
<script src="{{ url_for('static', filename='vendor/html5-qrcode/html5-qrcode.min.js') }}"></script>

<!-- Atau via alias root vendor -->
<script src="{{ url_for('static', filename='vendor/html5-qrcode.min.js') }}"></script>
```

#### Simbol Global yang Diekspos
Saat dimuat di browser atau konteks DOM, library menyediakan objek global:
* `window.Html5Qrcode`
* `window.Html5QrcodeScanner`
* `window.Html5QrcodeSupportedFormats`
* `window.Html5QrcodeScannerState`
* `window.Html5QrcodeScanType`

