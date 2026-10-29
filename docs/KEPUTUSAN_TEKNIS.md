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

