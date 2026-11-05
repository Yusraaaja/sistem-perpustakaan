# KEPUTUSAN TEKNIS: TOKEN QR ANGGOTA HMAC-SHA256

**Dokumen Keputusan Arsitektur & Keamanan**
* **ID Tugas Terkait:** Task 4-01 (Fase 4: Anggota, Impor, Kartu QR)
* **Kebutuhan Terkait:** DEC-010, DEC-020, DEC-023, LIB-QR-001, LIB-MEMBER-001
* **Tanggal Pengesahan:** 28 Oktober 2026
* **Status:** Disahkan / Aktif

---

## 1. Konteks & Latar Belakang

Sistem Perpustakaan Digital Sekolah beroperasi dengan prinsip utama **self-service-first** (DEC-018), di mana anggota melakukan transaksi peminjaman mandiri menggunakan tablet bersama berkamera di perpustakaan. Untuk mengidentifikasi anggota secara cepat, praktis, dan dapat diandalkan, setiap anggota dibekali kartu anggota yang memuat kode QR.

Namun demikian, lingkungan sekolah memerlukan perlindungan data pribadi dan pencegahan pemalsuan tanda pengenal:
1. **Privasi Data (DEC-010, DEC-023):** Kartu anggota tidak boleh mengekspos data pribadi seperti nama lengkap, kelas, alamat, atau nomor telepon dalam teks terbuka di dalam payload QR.
2. **Pencegahan Pemalsuan (Anti-Forgery):** Siswa tidak boleh dapat merekayasa QR sembarangan (misalnya hanya mengganti string ID siswa lain). Integritas payload harus dapat diverifikasi secara matematis oleh server menggunakan kunci rahasia.
3. **Pencabutan & Rotasi (Revocation / Reissue - LIB-QR-001, Task 4-07):** Jika kartu anggota hilang atau rusak, penerbitan kartu baru harus secara otomatis membatalkan kartu lama tanpa menghapus riwayat peminjaman sebelumnya.

---

## 2. Format & Serialisasi Token

Token QR anggota menggunakan serialisasi string deterministik dengan pemisah titik dua (`:`), yang memisahkan identitas anggota, versi QR, dan tanda tangan digital HMAC-SHA256:

$$\text{Token} = \langle \text{member\_id} \rangle : \langle \text{qr\_version} \rangle : \langle \text{signature\_hex} \rangle$$

### Contoh Konkret
```text
M-3K9X7W:1:d4c3b2a1e8f70912456789abcdef0123456789abcdef0123456789abcdef0123
```

### Rincian Komponen:
1. **`member_id` (Identitas Internal):**
   * Format: `M-XXXXXX` (Crockford Base32 tanpa karakter ambigu `0, O, 1, I, L` per Task 1B-04).
   * Menjamin pengenal unik internal tanpa mengungkap data identitas asli secara terbuka.
2. **`qr_version` (Nomor Versi Token):**
   * Tipe: Integer positif ($\ge 1$).
   * Mengacu langsung pada kolom `members.qr_version` di database skema v2.
   * Ketika kartu hilang atau diterbitkan ulang (Task 4-07), `qr_version` dinaikkan ($+1$), sehingga token fisik lama langsung tidak valid.
3. **`signature_hex` (Tanda Autentikasi Kriptografis):**
   * Tipe: String heksadesimal lowercase 64 karakter.
   * Dihasilkan dari perhitungan $\text{HMAC-SHA256}(\text{SECRET\_KEY}, \text{"member\_id:qr\_version"})$.

---

## 3. Spesifikasi Kriptografi & Implementasi Keamanan

### A. Algoritma HMAC-SHA256 Standar
* Implementasi menggunakan modul bawaan standar Python: `hmac` dan `hashlib.sha256`.
* Dilarang menggunakan algoritma buatan sendiri atau algoritma hash tanpa kunci rahasia (seperti MD5 atau SHA1 biasa).

### B. Perlindungan Timing Attack (`hmac.compare_digest`)
* Verifikasi tanda tangan digital **wajib** menggunakan fungsi `hmac.compare_digest()` dari pustaka standar Python.
* Penggunaan operator pembanding biasa (`==`) dilarang keras karena rentan terhadap serangan analisis waktu (timing attack) yang dapat mengekstrak byte tanda tangan secara inkremental.

### C. Manajemen Kunci Rahasia (`SECRET_KEY`)
* Kunci rahasia diambil dari variabel lingkungan `SECRET_KEY` atau `FLASK_SECRET_KEY`.
* Kunci **tidak boleh** ditanam langsung (*hardcoded*) di dalam kode sumber maupun disimpan di repositori publik.
* Dilarang membuat fallback ke kunci statis publik (seperti "default" atau "secret"). Jika konfigurasi kunci tidak tersedia, sistem wajib menggagalkan operasi secara aman dengan melempar `SecretKeyError`.
* Nilai kunci rahasia tidak boleh dimunculkan pada log, pesan error, pesan flash antarmuka pengguna, maupun traceback.

---

## 4. Pemisahan Tanggung Jawab (Separation of Concerns)

Sistem membedakan secara tegas antara **integritas kriptografis token** dan **kelayakan operasional bisnis**:

1. **Layer Kriptografis (`verify_member_token_signature`):**
   * Hanya memeriksa keaslian tanda tangan dan struktur sintaks token.
   * Dapat dijalankan secara *stateless* tanpa koneksi database.
2. **Layer Status Anggota (`verify_member_qr_token` & `validate_member_for_borrowing`):**
   * Token yang valid secara kriptografis **tidak serta merta** mengizinkan transaksi peminjaman.
   * Server memeriksa apakah anggota terdaftar (`MemberNotFoundError`).
   * Server memeriksa apakah token cocok dengan versi database terkini (`MemberTokenRevokedError`).
   * Server memeriksa apakah akun anggota berstatus aktif (`MemberInactiveError` per DEC-020).
   * Pengecekan riwayat keterlambatan serius atau kewajiban penggantian buku (Fase 7) tetap berjalan secara independen di layer layanan bisnis (`loan_service`).

---

## 5. Ringkasan Fungsi Layanan (`services/member_service.py`)

| Nama Fungsi | Deskripsi |
|---|---|
| `get_member_token_secret()` | Mengambil kunci rahasia aplikasi secara aman tanpa membocorkan nilai. |
| `build_member_token_payload()` | Membentuk string kanonikal deterministik `member_id:qr_version`. |
| `sign_member_token_payload()` | Menghasilkan tanda tangan HMAC-SHA256 64-karakter hex. |
| `generate_member_qr_token()` | Menghasilkan token lengkap `member_id:qr_version:signature`. |
| `parse_member_qr_token()` | Mem-parsing sintaks string token dan memvalidasi batas panjang serta format. |
| `verify_member_token_signature()` | Memverifikasi keabsahan tanda tangan secara timing-safe. |
| `verify_member_qr_token()` | Memverifikasi token dan mencocokkan status/versi aktif di database. |
| `validate_member_token()` | Wrapper aman exception untuk controller / kiosk / API. |
| `generate_member_qr_svg()` | (`services/qr_service.py`) Menghasilkan SVG kode QR dari token anggota. |

---

# KEPUTUSAN TEKNIS: PERLAKUAN TRANSAKSI HISTORIS (MEMBER_ID = NULL)

**Dokumen Keputusan Arsitektur & Kebijakan Data**
* **ID Tugas Terkait:** Task 4-10 (Fase 4: Anggota, Impor, Kartu QR)
* **Kebutuhan Terkait:** DEC-018, DEC-020, DEC-023, OPEN-011, LEGACY (Bagian 5), Task 1B-01, Task 7-06
* **Tanggal Pengesahan:** 30 Oktober 2026
* **Status:** Disahkan / Opsi A (Definitif)

---

## 1. Pernyataan Keputusan Resmi Pemilik Proyek

Pemilik proyek telah menetapkan keputusan resmi dan mengikat:

> **OPSI A: Biarkan seluruh transaksi peminjaman lama dengan `member_id = NULL` tetap tidak terhubung dengan anggota resmi.**

---

## 2. Makna & Prinsip Inti Keputusan

1. **Preservasi Data Historis Murni (Zero Modification / Anti-Mutation):**
   * Transaksi masa lampau yang tersimpan dengan nilai `member_id = NULL` (atau data peminjam berupa string teks bebas dari skema legacy v1/P1) dibiarkan utuh dalam kondisi aslinya.
   * Dilarang keras melakukan backfill, update spekulatif, atau mutasi pada kolom `loans.member_id` hanya demi mengisi nilai foreign key pada data lama.

2. **Larangan Pencocokan Otomatis (Strict Anti-Guessing):**
   * Sistem tidak boleh mencoba menebak, mencocokkan, atau mengasosiasikan transaksi lama dengan anggota terdaftar secara otomatis (misalnya dengan mencocokkan kemiripan teks string `legacy_nama_peminjam` dengan nama anggota baru).
   * Prinsip ini mencegah kesalahan atribusi data dan tanggung jawab pinjaman buku di lingkungan sekolah.

3. **Larangan Pembuatan Anggota Fiktif (No Artificial Members):**
   * Dilarang membuat rekaman anggota baru sintetis, akun "dummy", atau anggota bayangan hanya demi memaksakan relasi foreign key `member_id` pada transaksi lama.

4. **Integritas Catatan Audit & Riwayat (Immutable Audit History):**
   * Tidak boleh ada penghapusan data transaksi, pengubahan tanggal/waktu, atau pembersihan catatan historis. Riwayat masa lalu adalah dokumen fakta institusional perpustakaan sekolah.

5. **Pemisahan Jalur Sirkulasi (Dual Path Separation):**
   * **Transaksi Baru (Fase 5, 6, 7 dst.):** Wajib menggunakan mekanisme anggota resmi (verifikasi token QR HMAC-SHA256, validasi keaktifan, aturan batasan pinjam).
   * **Transaksi Historis:** Berfungsi sebagai rekaman arsip audit. Pada Fase 7 (Task 7-06), transaksi lama dengan `member_id = NULL` / `legacy` dikecualikan dari halaman notifikasi keterlambatan publik untuk melindungi privasi siswa dan menghindari kebingungan.

6. **Klausul Masa Depan (Future Manual Correction Clause):**
   * Keputusan ini tidak menutup kemungkinan koreksi historis manual di masa mendatang apabila di kemudian hari pemilik proyek memberikan persetujuan tertulis eksplisit melalui keputusan terpisah. Tanpa adanya persetujuan terpisah tersebut, status Opsi A berlaku definitif dan permanen.

---

## 3. Implikasi Teknis & Panduan Pengembang

| Komponen / Modul | Perlakuan Teknis & Batasan Arsitektur |
|---|---|
| `repositories/loan_repo.py` | Query join riwayat peminjaman wajib menggunakan `LEFT JOIN members m ON l.member_id = m.id`, sehingga transaksi dengan `member_id IS NULL` tetap terbaca dengan nama peminjam dari `legacy_nama_peminjam` / teks lama tanpa error. |
| `services/loan_service.py` | Transaksi peminjaman baru (`borrow_copies`) mewajibkan `member_id` valid dan aktif. Tidak ada logika backfill otomatis untuk transaksi lama. |
| `services/overdue_service.py` (Fase 7 / Task 7-06) | Filter notifikasi keterlambatan publik wajib menyaring klausul `l.member_id IS NOT NULL` sehingga catatan lama tidak bocor ke publik. |
| Database (`perpustakaan.db`) | Kolom `loans.member_id` tetap nullable (`TEXT REFERENCES members(id) ON DELETE RESTRICT`). Integritas byte-identical database produksi dipertahankan 100%. |

---

# KEPUTUSAN TEKNIS: VENDOR HTML5-QRCODE SECARA LOKAL (ZERO CDN POLICY)

**Dokumen Keputusan Arsitektur & Manajemen Dependensi**
* **ID Tugas Terkait:** Task 5-01 (Fase 5: Kiosk Tablet)
* **Kebutuhan Terkait:** DEC-002, DEC-018, LIB-KIOSK-001, LIB-OPS-001
* **Tanggal Pengesahan:** 30 Oktober 2026
* **Status:** Disahkan / Aktif

---

## 1. Konteks & Latar Belakang

Sistem perpustakaan sekolah dirancang dengan prinsip **self-service-first** (DEC-018), di mana siswa melakukan transaksi peminjaman mandiri menggunakan tablet bersama berkamera di ruang perpustakaan (DEC-002).

Lingkungan jaringan sekolah sering kali menghadapi kendala:
1. Pembatasan internet / firewall yang memblokir akses ke domain CDN publik pihak ketiga (seperti `unpkg.com`, `cdn.jsdelivr.net`, atau `cdnjs.cloudflare.com`).
2. Ketidakstabilan sambungan internet luar (WAN) saat kegiatan sekolah berlangsung, sementara jaringan lokal sekolah (LAN/Wi-Fi) tetap berfungsi.
3. Kebutuhan operasional mandiri (LIB-OPS-001): kiosk tablet harus tetap dapat memindai QR kartu anggota dan QR buku tanpa memerlukan koneksi ke internet global.

Oleh karena itu, sistem menetapkan **Zero CDN Policy** untuk seluruh komponen pemindaian QR kiosk, dengan menempatkan pustaka pemindaian `html5-qrcode` langsung di dalam aset statis lokal (`static/vendor/`).

---

## 2. Pemilihan & Spesifikasi Pustaka

* **Pustaka:** `html5-qrcode`
* **Versi Terpilih:** `2.3.8` (Rilis stabil resmi NPM)
* **Lisensi:** Apache License 2.0 (Bebas digunakan untuk software institusional/open source tanpa royalti).
* **Ukuran Berkas:** 375.364 byte (`html5-qrcode.min.js`).
* **Integritas Kriptografis:**
  * Tarball NPM SHA-1: `0b0cdf7a9926cfd4be530e13a51db47592adfa0d`
  * Tarball NPM SHA-256: `e215fbfb27f4b027519014f5bf462ceb3faf2a46dbf8d6dbd2df0e4acef0224e`
  * `html5-qrcode.min.js` SHA-256: `660b12437b1d747e3e68b8be0685c08cb728140110ad213f167b14b66f8b1d8e`

---

## 3. Lokasi Penyimpanan & Aturan Integrasi

1. Berkas utama disimpan di `static/vendor/html5-qrcode/html5-qrcode.min.js`.
2. Salinan alias disediakan di `static/vendor/html5-qrcode.min.js`.
3. Template kiosk di masa mendatang (Fase 5 / Task 5-02 s.d. 5-10) wajib memuat skrip menggunakan helper Jinja2 Flask:
   ```html
   <script src="{{ url_for('static', filename='vendor/html5-qrcode/html5-qrcode.min.js') }}"></script>
   ```
4. Dilarang keras menyisipkan tag `<script>` yang mengarah ke domain CDN luar untuk pemindaian QR di template kiosk.




---

# Keputusan Teknis: Isolasi Sesi Kiosk (Task 5-02, DEC-002, DEC-018)

**ID Keputusan:** DEC-KSI-001
**Tanggal:** 1 November 2026
**Status:** Ditetapkan

## Masalah

Flask default menggunakan satu cookie sesi (`session`, `Path=/`) untuk seluruh aplikasi. Karena `Path=/` mencakup semua sub-path, browser mengirim cookie admin ke `/kiosk/` juga — risiko kebocoran hak akses silang jika kiosk membaca cookie yang sama.

## Keputusan

Implementasi `KioskIsolatedSessionInterface` (subclass `SecureCookieSessionInterface`) yang menggantikan `app.session_interface` default Flask.

| Aspek | Sesi Admin | Sesi Kiosk |
|---|---|---|
| Nama Cookie | `session` | `kiosk_session` |
| Path Cookie | `/` | `/kiosk` |
| Lifetime | 8 jam | 1 jam (KIOSK_SESSION_LIFETIME_SECONDS) |
| Kunci terlarang | — | `logged_in`, `user_role`, `admin_username` |

**Prinsip:** `open_session` membaca cookie berdasarkan path request. Kiosk HANYA baca `kiosk_session`; admin HANYA baca `session`. Kunci admin dihapus paksa dari sesi kiosk (defense-in-depth). Cookie `Path=/kiosk` mencegah browser mengirim `kiosk_session` ke endpoint admin.

## Mengapa Cookie Path Saja Tidak Cukup

Browser mengirim cookie berdasarkan **request path**, bukan berdasarkan cookie path sendiri. Cookie admin `Path=/` tetap dikirim ke `/kiosk/`. Isolasi wajib dilakukan **server-side** dengan menolak membaca cookie admin saat melayani request kiosk.

## File yang Diubah (Task 5-02)

- `policy.py`: konstanta kiosk (`KIOSK_SESSION_COOKIE_NAME`, `KIOSK_COOKIE_PATH`, `KIOSK_SESSION_LIFETIME_SECONDS`, `KIOSK_FORBIDDEN_SESSION_KEYS`).
- `app.py`: `_is_kiosk_request()`, `KioskIsolatedSessionInterface`, route `/kiosk/`, guard idle timeout kiosk.
- `templates/kiosk_index.html`: halaman placeholder kiosk.
- `tests/test_kiosk_session.py`: 34 tes keamanan isolasi sesi.
