# AUDIT P0 — STATUS AWAL DAN FONDASI SISTEM PERPUSTAKAAN DIGITAL SEKOLAH
**Tanggal Audit:** 17 Oktober 2026  
**Dokumen Acuan:** `docs/DOKUMENTASI_INDUK_v4_2.md`  
**Branch Kerja:** `feature/p1-multi-book`  
**Commit Terakhir:** `2cc852848404ed4ce34f83850b4ce67bf5f3298a` (`oke ai nya bagus`)  
**Status DB Produksi:** `perpustakaan.db` 100% ASLI, TIDAK TERSENTUH, BELUM DIMIGRASI.

---

## 1. Ringkasan Eksekutif & Prinsip Audit
Audit ini dilakukan secara independen terhadap source code, konfigurasi, skema database, dan test suite aktual di repositori `c:\Users\ThinkPad\Desktop\sistem-perpustakaan`. Sesuai dengan **Aturan Keras (Rule 1)**: isi `DOKUMENTASI_INDUK_v4_2.md` diperlakukan sebagai konteks kebutuhan dan keputusan produk, bukan bukti keberadaan kode.

Seluruh temuan di bawah ini didasarkan pada pembuktian kode nyata (`app.py`, template Jinja, migration scripts, test suite) dan eksekusi test pada database terisolasi.

---

## 2. Status Keputusan Produk (DEC-001 s.d. DEC-024)

| Kode | Ringkasan Keputusan Produk | Status Implementasi Aktual di Kode | Bukti & Catatan Teknis |
|---|---|---|---|
| **DEC-001** | Pengunjung umum hanya membaca di tempat; tidak boleh meminjam. | **VERIFIED (Enforced)** | Endpoint sirkulasi `/peminjaman` dan `/proses_pinjam_admin` membutuhkan login admin. Tidak ada alur peminjaman pengunjung umum. |
| **DEC-002** | Satu tablet bersama dengan kamera untuk layanan mandiri. | **PLANNED** | Belum ada antarmuka tablet/kiosk mandiri. Peminjaman saat ini masih dilakukan oleh admin di `/peminjaman`. |
| **DEC-003** | Pencarian katalog via HP; transaksi mandiri di tablet. | **IMPLEMENTED (Katalog)** | Pencarian publik aktif di `/` dan `/search`. Kiosk tablet belum dibangun. |
| **DEC-004** | ID unik eksemplar otomatis; nomor registrasi lama tidak dipakai. | **PLANNED (Gap)** | Kode saat ini masih menyimpan `id_buku_fisik` berupa JSON nomor registrasi lama di tabel `buku`. Perlu transisi ke auto-generated copy ID pada P2. |
| **DEC-005** | Masa pinjam 7 hari (168 jam); perpanjangan 1x 7 hari via konfirmasi anggota. | **PARTIAL (Pinjam 7 hari)** | Default due date 7 hari diatur di `app.py`, namun alur perpanjangan mandiri 1x 7 hari (LIB-RETURN-004) belum dibangun. |
| **DEC-006** | Pengembalian dapat dilakukan oleh orang selain peminjam. | **IMPLEMENTED (Admin)** | Pengembalian per item `/kembalikan_item/<id>` atau transaksi `/kembalikan/<id>` tidak memvalidasi identitas pengembali, namun saat ini baru bisa diakses admin. Jalur A (scan buku publik) belum ada. |
| **DEC-007** | Transaksi multi-buku dan pengembalian sebagian wajib didukung. | **VERIFIED (Lokal P1)** | Backend P1 di `app.py` mendukung multi-book cart, header-detail schema, dan pengembalian sebagian. Lolos 15 unit test P1. |
| **DEC-008** | Kartu anggota dapat dicetak sendiri (hemat tinta). | **PLANNED** | Belum ada modul pembuatan dan pencetakan kartu anggota. |
| **DEC-009** | Impor anggota dari Excel/CSV sesuai template aplikasi. | **PLANNED** | Saat ini hanya ada impor katalog buku (`/import_excel`). Belum ada tabel/impor anggota. |
| **DEC-010** | QR anggota memuat token acak, aman, tanpa data pribadi terbuka. | **PLANNED** | Belum ada generator/validator token QR anggota. |
| **DEC-011** | QR buku dibuat otomatis; label menampilkan ID eksemplar terbaca manusia. | **PLANNED** | Belum ada generator label cetak QR eksemplar. |
| **DEC-012** | Tambah buku isi judul + jumlah eksemplar; ID & QR otomatis. | **PARTIAL (Manual)** | Tambah buku di `/add` menerima jumlah stok dan nomor registrasi manual. Belum auto-generate ID eksemplar. |
| **DEC-013** | Eksemplar baru tidak pernah digabung atau ditimpa walau judul sama. | **PLANNED** | Belum ada tabel `eksemplar_buku` terpisah. |
| **DEC-014** | Hosting backend target: Hugging Face Spaces (Docker). | **IMPLEMENTED (Siap Uji)** | `Dockerfile` (Python 3.11-slim, Gunicorn) dan `.dockerignore` sudah siap. |
| **DEC-015** | Database target: Supabase PostgreSQL. | **PLANNED** | Kode saat ini masih berjalan di SQLite (`perpustakaan.db`). Driver PostgreSQL belum ditambahkan. |
| **DEC-016** | AI Assistant menggunakan Google Gemini API (gemini-2.5-flash). | **VERIFIED (Lokal)** | Terintegrasi di `app.py` via HTTP API langsung (`urllib.request`), grounded pada katalog buku, lolos 18 test. |
| **DEC-017** | Notifikasi keterlambatan in-app publik; WhatsApp TIDAK digunakan. | **PLANNED (WhatsApp ditiadakan: VERIFIED)** | Kode tidak memiliki dependensi WhatsApp (sesuai DEC-017). Halaman notifikasi in-app publik belum dibuat (P4). |
| **DEC-018** | Self-service adalah prinsip mutlak; petugas bukan operator rutin. | **PLANNED** | Alur saat ini masih berpusat pada admin di desktop. Perlu pembangunan antarmuka self-service di P2. |
| **DEC-019** | Tidak ada batas maksimum jumlah buku per transaksi. | **VERIFIED (P1)** | Endpoint `/proses_pinjam_admin` menerima array item buku tanpa batas buatan. |
| **DEC-020** | Anggota tidak aktif dinonaktifkan, bukan dihapus; histori tetap utuh. | **IMPLEMENTED (Policy)** | Penghapusan riwayat dinonaktifkan permanen di `/hapus_peminjaman`. Tabel anggota belum ada. |
| **DEC-021** | Biaya Rp0 adalah target, bukan klaim gratis selamanya. | **VERIFIED (Docs)** | Dokumen dan kode tidak mengklaim jaminan gratis selamanya. |
| **DEC-022** | UI dan panduan berbahasa Indonesia sangat sederhana. | **PARTIAL** | UI katalog dan peminjaman sudah berbahasa Indonesia. Panduan resmi P6 belum disusun. |
| **DEC-023** | Data anggota sederhana: nama, status aktif/nonaktif, kategori referensi; tanpa kelas. | **PLANNED** | Transaksi lama masih menyimpan kolom `kelas` dan `jurusan`. Perlu skema tabel anggota dan kategori di P2. |
| **DEC-024** | Penyelesaian buku hilang/rusak dengan kamus/Al-Qur'an (bukan uang). | **PARTIAL (Data)** | Kolom `status_penggantian` dan `catatan_penggantian` sudah ada di skema P1. Alur self-service QR penggantian buku belum dibuat. |

---

## 3. Status Isu Terbuka (OPEN-016 s.d. OPEN-018)
Sesuai **Aturan Keras (Rule 3)**, hal yang masih terbuka tidak ditebak, melainkan diimplementasikan sebagai konfigurasi kebijakan (policy config):

1. **OPEN-016 (Privasi Halaman Notifikasi Publik):**  
   *Kebijakan Target:* Ditentukan via environment variable/konfigurasi `POLICY_NOTIF_PUBLIC_DISPLAY` dengan opsi `TRUNCATED_NAME` (contoh: "Ahmad S***") atau `FULL_NAME` (default untuk akuntabilitas sosial per DEC-017).
2. **OPEN-017 (Perhitungan Jatuh Tempo Perpanjangan Terlambat):**  
   *Kebijakan Target:* Dikonfigurasi via `POLICY_EXTENSION_FROM_DUE_DATE` (Boolean: default `True` = jatuh tempo baru = jatuh tempo lama + 7 hari; `False` = dihitung dari tanggal konfirmasi perpanjangan).
3. **OPEN-018 (Rentang Peninjauan Pengembalian 24 Jam & Penempatan Kiosk):**  
   *Kebijakan Target:* Dikonfigurasi via `POLICY_RETURN_BATCH_WINDOW_HOURS` (default `24`).

---

## 4. Audit Kode Aktual, Skema, dan Keamanan (Phase 0 & P1)

### 4.1 Status Database Produksi
- File `perpustakaan.db`:
  - **Tabel:** `buku` (15 baris), `sqlite_sequence`, `peminjaman` (3 baris: ID 11, 12, 13).
  - **Skema `peminjaman`:** Masih skema lama single-book (kolom `id_buku`, `id_anggota`, `status`, `denda`, dll.).
  - **Status:** 100% utuh, belum dimigrasi ke multi-book. Migrasi produksi ditahan hingga instruksi eksplisit user.
- Skema Target Multi-Book (telah diverifikasi di test suite terisolasi):
  - `peminjaman` (Header): `id`, `kode_transaksi`, `id_anggota`, `tipe_user`, `kelas`, `jurusan`, `jurusan_asli`, `tgl_pinjam`, `tgl_kembali_seharusnya`, `status`, `total_denda`, `denda_historis_asli`, `catatan`.
  - `peminjaman_detail` (Item): `id`, `id_peminjaman`, `id_buku`, `no_registrasi`, `status`, `tgl_dikembalikan`, `denda_keterlambatan`, `denda_kondisi`, `status_penggantian`, `catatan_penggantian`, `catatan`.

### 4.2 Audit Keamanan Produksi (Phase 0 Hardening)
1. **SECRET_KEY Guard (`app.py` L51-66):**  
   - Pada mode produksi (`IS_PRODUCTION = True`), aplikasi **gagal startup (raise RuntimeError)** jika `SECRET_KEY` kosong, merupakan placeholder (`changeme`, `default`, dll.), atau panjangnya < 16 karakter.
   - Tidak ada silent dynamic random key di mode produksi (mencegah session drop saat restart).
2. **Kredensial Admin (`app.py` L86-126):**  
   - Password plaintext default tidak ada di source code (menggunakan hash scrypt).
   - Mode produksi memvalidasi dan menolak password default `'123'` atau placeholder.
3. **Cookie Session (`app.py` L67-77):**  
   - `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`.
   - `SESSION_COOKIE_SECURE` otomatis `True` di produksi (HTTPS) dan `False` di pengujian lokal/HTTP.
4. **Brute Force Rate Limiter (`app.py` L129-239):**  
   - In-memory rate limiting thread-safe (maksimal 5 percobaan gagal per IP, lockout 300 detik).
   - Reset counter otomatis setelah login sukses.
5. **Koneksi Database SQLite (`app.py` L279-300):**  
   - `PRAGMA foreign_keys = ON` diterapkan di setiap koneksi.
   - `PRAGMA busy_timeout = 30000` (30 detik) untuk mencegah locking error saat antrian tulis.
6. **Proteksi Riwayat Transaksi (`app.py` L1795-1804):**  
   - Route `/hapus_peminjaman/<id>` menolak penghapusan permanen riwayat demi integritas data dan audit trail.
7. **Proteksi Reset Katalog (`app.py` L1168-1205):**  
   - Menolak reset jika masih ada peminjaman aktif.
   - Wajib konfirmasi teks `'KOSONGKAN'`.
   - Dinonaktifkan di produksi kecuali flag `ALLOW_CATALOG_RESET=1`.

### 4.3 Gap Kritis Terhadap Dokumentasi Induk v4.2
1. **Penanganan Zona Waktu (Rule 7):**  
   - `app.py` saat ini masih menggunakan `datetime.now()` (waktu lokal server).  
   - *Rencana Koreksi:* Wajib menyimpan timestamp dalam format ISO-8601 UTC di database, dan mengonversinya ke zona waktu sekolah (`SCHOOL_TZ`, default `Asia/Jakarta`) saat ditampilkan ke user.
2. **Tabel Anggota & Kategori (DEC-020, DEC-023):**  
   - Belum ada tabel `anggota` dan `kategori_anggota`. Transaksi saat ini mencatat nama anggota secara ad-hoc sebagai teks string.
3. **Modul Kiosk Layanan Mandiri & QR (DEC-002, DEC-018):**  
   - Seluruh transaksi peminjaman saat ini masih membutuhkan otentikasi admin.

---

## 5. Hasil Pengujian Test Suite Aktual

Pengujian dijalankan langsung pada environment lokal menggunakan Python virtual environment:
```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

**Verbatim Output Pengujian:**
```text
Ran 43 tests in 9.121s

OK
[*] Memulai migrasi database pada: backups/test_p1_regression.db
[*] Membaca 3 data transaksi peminjaman lama.
[SUCCESS] Migrasi selesai. 3 header dan 3 detail tersimpan.
```

**Rincian Test Suite:**
1. `tests/test_ai_assistant.py`: **18/18 PASS** (AI grounding, fallback, CSRF, security header, non-streaming response).
2. `tests/test_multi_book_p1.py`: **15/15 PASS** (Migrasi P1, multi-book cart, partial return, stock integrity, delete protection).
3. `tests/test_production_safety.py`: **10/10 PASS** (SECRET_KEY validation, scrypt password guard, rate limiter, SQLite pragma, secure cookies).

*Semua test terbukti berjalan 100% pada database uji sementara terisolasi tanpa menyentuh `perpustakaan.db`.*

---

## 6. Status Kebutuhan Fungsional (Requirement Matrix)

| Requirement ID | Deskripsi Singkat | Status Aktual |
|---|---|---|
| **LIB-CAT-001** | Pencarian dan detail katalog buku | **VERIFIED** |
| **LIB-COPY-001** | Identitas unik eksemplar fisik | **PLANNED** |
| **LIB-COPY-002** | Perubahan status eksemplar | **PARTIAL** |
| **LIB-LOAN-001** | Transaksi multi-item atomik | **VERIFIED (P1 Local)** |
| **LIB-LOAN-002** | Riwayat peminjaman per eksemplar | **VERIFIED (P1 Local)** |
| **LIB-RETURN-001**| Pengembalian sebagian dan penuh | **VERIFIED (P1 Local)** |
| **LIB-RETURN-002**| Durasi aktual dan keterlambatan 168 jam | **PARTIAL** (Perlu penyeragaman UTC + `SCHOOL_TZ`) |
| **LIB-RETURN-003**| Kondisi buku saat kembali | **IMPLEMENTED** |
| **LIB-RETURN-004**| Perpanjangan 1x 7 hari per eksemplar | **PLANNED** |
| **LIB-QR-001**   | Token QR anggota aman | **PLANNED** |
| **LIB-QR-002**   | QR eksemplar buku | **PLANNED** |
| **LIB-QR-003**   | Jalur manual untuk QR rusak | **PLANNED** |
| **LIB-QR-004**   | Label cetak QR dan kartu anggota | **PLANNED** |
| **LIB-OPS-001**  | Transaksi mandiri tanpa ketergantungan operator | **PLANNED** |
| **LIB-KIOSK-001**| Antarmuka peminjaman mandiri tablet | **PLANNED** |
| **LIB-MEMBER-001**| Siklus hidup anggota | **PLANNED** |
| **LIB-MEMBER-002**| Penonaktifan anggota tanpa hapus otomatis | **IMPLEMENTED (Policy)** |
| **LIB-IMPORT-001**| Impor Excel anggota | **PLANNED** |
| **LIB-IMPORT-002**| Tambah buku judul + jumlah (ID auto) | **PLANNED** |
| **LIB-ADMIN-001** | Otorisasi server-side rute admin | **VERIFIED** |
| **LIB-REPORT-001**| Ekspor riwayat ke Excel | **VERIFIED** |
| **LIB-BACKUP-001**| Prosedur backup dan restore teruji | **IMPLEMENTED (Local)** |
| **LIB-LOSS-001**  | Penyelesaian buku hilang | **PARTIAL** |
| **LIB-AI-001**    | Asisten AI aman (Gemini) | **VERIFIED** |
| **LIB-NOTIF-001** | Notifikasi keterlambatan in-app publik | **PLANNED** |
| **LIB-FINE-001**  | Penyelesaian denda via Kamus/Al-Qur'an | **PARTIAL** |
| **LIB-UX-001**    | UI Bahasa Indonesia sangat sederhana | **PARTIAL** |

---

## 7. Rencana Kerja Bertahap (Next Steps)
1. **Stabilisasi P1 & UTC Timezone (`SCHOOL_TZ`):**
   - Terapkan fungsi utilitas waktu terpusat (`get_now_utc()`, `to_school_tz()`) sesuai Rule 7.
   - Sempurnakan perhitungan durasi dan due date 168 jam berbasis UTC.
2. **Pembangunan Modul P2 (QR & Self-Service Tablet):**
   - Buat skema tabel `anggota` dan `kategori_anggota` sederhana (DEC-023).
   - Rancang antarmuka tablet `/kiosk` mandiri (DEC-002, DEC-018) untuk peminjaman dan pengembalian.
3. **Pembangunan Modul P4 (Notifikasi Keterlambatan In-App Publik):**
   - Buat halaman publik `/notifikasi` yang menghitung pinjaman overdue secara real-time tanpa WhatsApp (DEC-017).

---

## 8. Pernyataan Keamanan Data
**Dikonfirmasi:**  
- **TIDAK ADA deploy produksi yang dilakukan.**  
- **TIDAK ADA migrasi atau modifikasi pada database produksi `perpustakaan.db`.**  
- **Database produksi tetap utuh dengan skema asli.**

