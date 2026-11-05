# Dokumen Desain Arsitektur Fase 2: Data Access Layer (DAL) & Service Abstraction

**Status:** DRAFT DESAIN (Arsitektur & Spesifikasi — Tanpa Modifikasi Kode Aplikasi)  
**Dokumen Induk Acuan:** `docs/DOKUMENTASI_INDUK_v4_2.md` (DEC-001 s.d. DEC-024, OPEN-016 s.d. OPEN-018)  
**Fondasi Database:** Skema v2 (`migrations/0001_initial_v2_schema.sql`, commit `73e44c0`)  
**Target Rilis:** Fase 2 — Refaktor Data Access Layer & Integrasi Lapisan Aplikasi  

---

## 1. Kondisi Arsitektur Saat Ini & Bukti Ketergantungan

### 1.1 Kondisi Aktual Aplikasi (`app.py`)
Saat ini, aplikasi [`app.py`](file:///c:/Users/ThinkPad/Desktop/sistem-perpustakaan/app.py) berukuran ~2.400 baris dengan gaya arsitektur *monolithic route-heavy*:
1. **Pencampuran Tanggung Jawab (*Tight Coupling*):** Logika parsing HTTP request, validasi bisnis, pembentukan query SQL mentah (*raw string SQL*), manajemen transaksi SQLite, penanganan denda, dan perenderan template Jinja berada dalam satu fungsi route yang sama.
2. **Ketergantungan Kuat pada Skema Lama (SQLite v1 / P1):**
   * **Entitas Buku:** Mengandalkan tabel `buku` dengan mutasi imperatif kolom `stok` (dikurangi saat pinjam, ditambah saat kembali) dan serialisasi JSON pada kolom `id_buku_fisik`.
   * **Entitas Transaksi:** Mengandalkan tabel `peminjaman` dan `peminjaman_detail` (hasil migrasi P1) dengan kolom denda numerik (`denda_keterlambatan`, `denda_kondisi`) serta kolom status teks manual (`'Dipinjam'`, `'Kembali'`, `'Rusak'`, `'Hilang'`).
3. **Koneksi Database:** Masih menggunakan fungsi lokal `get_db_connection()` di `app.py` tanpa penegakan `PRAGMA foreign_keys = ON;` secara eksplisit pada setiap sesi route.

### 1.2 Bukti Ketergantungan Kode Aktual
* Peminjaman: `app.py` melakukan `UPDATE buku SET stok = stok - 1, id_buku_fisik = ? WHERE id = ?`.
* Pengembalian: `app.py` melakukan `UPDATE buku SET stok = stok + 1 ...` jika status buku `'Kembali'`, dan menghitung denda keterlambatan uang Rp 1.000/hari (bertentangan dengan DEC-024).
* Riwayat: Menampilkan nama peminjam langsung dari string `peminjaman.id_anggota` tanpa relasi ke tabel anggota formal.

---

## 2. Arsitektur Target Tiga Lapis (*Three-Tier Architecture*)

Fase 2 akan memisahkan kode aplikasi menjadi tiga lapisan bersih (*Clean Separation of Concerns*):

```
┌────────────────────────────────────────────────────────┐
│               Lapisan Route / Controller               │
│ (Flask Blueprints / Routes: HTTP Parsing, Validasi UI) │
└───────────────────────────┬────────────────────────────┘
                            │ memanggil
                            ▼
┌────────────────────────────────────────────────────────┐
│                 Lapisan Business Service               │
│ (LoanService, CatalogService: Validasi Bisnis, Aturan) │
└───────────────────────────┬────────────────────────────┘
                            │ memanggil
                            ▼
┌────────────────────────────────────────────────────────┐
│             Lapisan Data Access / Repository           │
│ (CatalogRepo, CopyRepo, LoanRepo, MemberRepo, Audit)   │
└───────────────────────────┬────────────────────────────┘
                            │ menjalankan query
                            ▼
┌────────────────────────────────────────────────────────┐
│               Basis Data Skema v2 (SQLite)             │
│ (Foreign Keys ON, Partial Index, Triggers, Views)      │
└────────────────────────────────────────────────────────┘
```

### 2.1 Lapisan Route / Controller
* Bertanggung jawab murni atas:
  * Autentikasi sesi admin / user.
  * Ekstraksi dan sanitasi input dari request form / JSON.
  * Pemetaan respon ke template Jinja atau payload JSON.
  * Menerjemahkan domain exception menjadi flash message berbahasa Indonesia sederhana (DEC-022).
* **Dilarang:** Menulis perintah SQL (`SELECT`, `INSERT`, `UPDATE`) secara langsung di dalam controller.

### 2.2 Lapisan Business Service
* Mengimplementasikan aturan bisnis perpustakaan:
  * **Peminjaman:** Memverifikasi anggota aktif (DEC-020), memverifikasi ketersediaan eksemplar fisik via repository, memastikan durasi 168 jam (DEC-005, LOAN_HOURS), dan menghasilkan ID publik melalui `id_generator.py`.
  * **Pengembalian:** Memvalidasi pengembalian per eksemplar (DEC-007), mendukung pengembalian sebagian, dan memetakan kondisi fisik (`'baik'`, `'rusak'`, `'hilang'`).
  * **Penyelesaian Buku Hilang/Rusak:** Menerapkan alur DEC-024 (penggantian berupa kamus atau Al-Qur'an, tanpa denda uang).
  * **Perpanjangan:** Memeriksa kuota perpanjangan maksimal 1 kali (DEC-005) dan batas toleransi keterlambatan sesuai kebijakan di [`policy.py`](file:///c:/Users/ThinkPad/Desktop/sistem-perpustakaan/policy.py).

### 2.3 Lapisan Data Access / Repository
* Berinteraksi langsung dengan database melalui koneksi [`db.get_connection()`](file:///c:/Users/ThinkPad/Desktop/sistem-perpustakaan/db.py).
* Mengelola transaksi atomik (`BEGIN IMMEDIATE ... COMMIT/ROLLBACK`).
* Mengeksekusi query ANSI SQL v2 yang kompatibel dengan SQLite dan PostgreSQL (target Fase 10).
* Repositori yang akan dibuat:
  1. `CatalogRepository`: Operasi CRUD judul buku (`catalog_titles`), pencarian katalog, ketersediaan via view `v_title_availability`.
  2. `CopyRepository`: Operasi eksemplar fisik (`copies`), jejak nomor lama (`legacy_copy_map`), ketersediaan via view `v_copy_availability`.
  3. `LoanRepository`: Operasi peminjaman (`loans`), detail item (`loan_items`), constraint parsial, dan data baca-saja denda lama (`legacy_loan_item_extra`).
  4. `MemberRepository`: Operasi data anggota (`members`, `member_categories`) tanpa kelas/telepon (DEC-023).
  5. `AuditRepository`: Pencatatan log sistem ke tabel `audit_log`.

---

## 3. Strategi Transisi Skema Tanpa Dual-Write

> [!CAUTION]
> **Larangan Keras Dual-Write:**
> Menulis data ke dua skema secara paralel (menulis ke `buku` lama dan `catalog_titles` baru sekaligus) **DILARANG KERAS**. Dual-write dalam aplikasi monolitik tanpa distributed transaction manager rentan menimbulkan *split-brain*, inkonsistensi stok, dan kegagalan parsial yang merusak integritas database.

### 3.1 Strategi Cutover Terkendali (*Controlled Read-Write Cutover*)
Transisi dilakukan dengan metode **Clean Cutover per Domain**:
1. **Langkah 1 (Persiapan Database):** Database aplikasi dialihkan menggunakan database salinan yang telah dimigrasikan ke skema v2 (`test_copy_migration.db` atau `perpustakaan_v2.db`).
2. **Langkah 2 (Arsip Skema Lama):** Tabel-tabel lama (`buku`, `peminjaman`, `peminjaman_detail`) tetap dipertahankan di dalam database v2 sebagai arsip baca-saja (*safety net* historis).
3. **Langkah 3 (Pengalihan Kode Total):** Service Layer dihubungkan 100% ke tabel v2 (`catalog_titles`, `copies`, `loans`, `loan_items`). Tidak ada operasi `INSERT` atau `UPDATE` baru yang menyentuh tabel lama.
4. **Langkah 4 (Fallback & Audit):** Jika terjadi kegagalan sistem pada rilis awal, database lama tetap utuh sebelum proses migrasi cutover dijalankan.

### 3.2 Penanganan Peminjam Historis (`member_id = NULL`)
Data transaksi lama hasil migrasi Fase 1B mencatat:
* `member_id`: `NULL`
* `legacy_nama_peminjam`: Teks asli (contoh: `'TEST USER'`, `'Yusra'`)
* `notes`: `'data_uji; waktu_lama_perkiraan'` atau `'waktu_lama_perkiraan'`

**Aturan Penanganan di Lapisan Service & View:**
1. **Tampilan Riwayat Admin:** Menampilkan nama dari `legacy_nama_peminjam` jika `member_id` bernilai `NULL`, disertai badge visual *"Legacy / Migrasi"*.
2. **Halaman Notifikasi Publik (Fase 7 / DEC-017 / OPEN-016):** Peminjaman dengan `member_id IS NULL` atau bertanda `data_uji` secara otomatis **dikecualikan** dari halaman pengingat sosial publik agar tidak membingungkan warga sekolah.
3. **Penyelesaian Transaksi Lama:** Jika eksemplar transaksi legacy dikembalikan di Fase 2, transaksi diselesaikan secara normal dengan memperbarui `loan_items.returned_at` dan `returned_via = 'legacy'`.

---

## 4. Batas Transaksi, Validasi, Penanganan Error, & Audit Log

### 4.1 Batas Transaksi Atomik (*Transaction Boundary*)
Seluruh operasi yang melibatkan multi-tabel wajib berjalan di dalam satu blok transaksi database atomik:
* **Transaksi Peminjaman Baru:**
  ```python
  with conn:  # BEGIN IMMEDIATE
      # 1. Validasi status anggota
      # 2. Insert ke loans
      # 3. For each copy:
      #      Verifikasi status copy == 'aktif'
      #      Insert ke loan_items (diproteksi partial unique index)
      # 4. Insert ke audit_log
  # COMMIT otomatis jika selesai tanpa error, ROLLBACK otomatis jika raise exception
  ```
* **Transaksi Pengembalian Buku:**
  ```python
  with conn:
      # 1. Update loan_items (set returned_at, return_condition, returned_via)
      # 2. Jika kondisi 'rusak'/'hilang', update copies.status = 'rusak'/'hilang'
      # 3. Insert ke audit_log
  ```

### 4.2 Penanganan Constraint & Error Mapping
Error database tidak boleh bocor sebagai *500 Internal Server Error* ke layar pengguna:
* **Pelanggaran `idx_loan_items_active_copy` (`sqlite3.IntegrityError`):**  
  $\to$ Ditangkap oleh Repository dan diterjemahkan menjadi Domain Exception: `BookAlreadyBorrowedError(copy_id)`.  
  $\to$ Controller menampilkan flash warning: *"Buku dengan kode eksemplar ini sedang dipinjam oleh orang lain dan belum dikembalikan."*
* **Pelanggaran Trigger `trg_prevent_delete_*`:**  
  $\to$ Ditangkap sebagai `DataDeletionForbiddenError`.  
  $\to$ Controller menolak dan memberitahu admin: *"Data eksemplar atau riwayat peminjaman tidak boleh dihapus demi integritas riwayat sekolah. Silakan nonaktifkan status eksemplar jika tidak lagi digunakan."*

### 4.3 Audit Log Otomatis
Setiap perubahan state operasional wajib memanggil `AuditRepository.record()` yang menyimpan:
* `id`: `AUD-XXXXXXXX` (Crockford Base32 dari `id_generator.py`).
* `at`: Timestamp UTC ISO8601 dari `timeutil.format_iso_utc()`.
* `actor`: ID admin yang sedang login atau token sesi.
* `action`: Konstanta aksi (`LOAN_CREATE`, `LOAN_RETURN`, `COPY_DEACTIVATE`, `RESOLVE_LOST`).
* `detail_json`: Snapshot ringkas atribut yang berubah.

---

## 5. Penyelesaian Catatan P2 dari Audit Fase 1B

Dokumen desain ini secara eksplisit mengadopsi rekomendasi audit Fase 1B:

1. **Collision Retry pada Migrator & Batch Operations (P2-01):**
   * Modul Repository diwajibkan mengelola set ID dalam memori (`seen_ids = set()`) saat pembuatan ID batch massal dan meneruskan `is_taken=seen_ids.__contains__` ke `id_generator.py` untuk menjamin eksekusi retry loop aktif.
2. **Koreksi Data Tanpa `DELETE` (P2-02):**
   * Seluruh alur administrasi katalog tidak menyediakan tombol atau endpoint `DELETE /copies/<id>`.
   * Operasi penarikan buku dilakukan melalui endpoint pembaruan status: `PATCH /copies/<id>/deactivate` yang mengubah `copies.status = 'nonaktif'`.
3. **Penyatuan Fungsi Koneksi Database (P2-03):**
   * Menghapus fungsi lokal `get_db_connection()` di `app.py` dan mengarahkannya 100% ke `db.get_connection()` terpusat agar seluruh query aplikasi mendapatkan jaminan `PRAGMA foreign_keys = ON;`.
4. **Semantik Transaksi DDL (P2-04):**
   * Script migrasi tambahan di masa depan tidak lagi menggunakan `conn.executescript()` yang memicu auto-commit DDL terpisah, melainkan mengeksekusi DDL per pernyataan di dalam transaksi terkontrol.

---

## 6. Strategi Pengujian & Penjagaan Regresi

### 6.1 Hubungan & Cakupan 69 Tes Saat Ini
Proyek saat ini memiliki **69 pengujian unit yang valid dan lulus 100%**:
* **43 Tes Baseline P0:** Menjamin proteksi keamanan produksi, brute-force rate limit, isolasi session cookie, serta alur multi-book awal dan AI Assistant.
* **11 Tes Waktu Fase 1A:** Menjamin presisi batas 168 jam eksak, transisi midnight UTC/WIB, dan kompatibilitas string tanggal naive.
* **15 Tes Skema & Migrasi Fase 1B:** Menjamin keunikan 10.000 ID, constraint parsial ketersediaan, trigger anti-delete, rekonsiliasi migrasi, dan idempotensi.

> [!IMPORTANT]
> **Strategi Anti-Regresi Fase 2:**
> 1. Sebanyak 26 tes (Fase 1A + Fase 1B) menguji modul-modul independen (`timeutil`, `id_generator`, `db`, `scripts/migrate_legacy_to_v2.py`). Tes ini **harus tetap 100% hijau** tanpa modifikasi.
> 2. Tes integrasi route web lama di `test_multi_book_p1.py` saat ini masih menggunakan skema P1 lama. Pada Fase 2, fixture database pengujian route akan dimigrasikan menggunakan skema v2, dan seluruh asersi alur peminjaman multi-buku serta pengembalian parsial harus tetap terpenuhi.

### 6.2 Pola Database Uji Terisolasi
Seluruh pengujian unit dan integrasi baru pada Fase 2 wajib mengikuti pola isolasi yang telah terbukti di Fase 1B:
* Menggunakan subdirektori sementara `tests/scratch_test_dbs/` yang diabaikan Git.
* Dibuat saat `setUp()` dan dibersihkan secara mutlak saat `tearDown()`.
* Dilarang keras mengarahkan target pengujian ke `perpustakaan.db` produksi.

---

## 7. Rencana Tahapan Implementasi & Kriteria Penerimaan

Implementasi Fase 2 akan dilakukan secara bertahap dalam beberapa sub-langkah terpisah:

### 7.1 Urutan Sub-Langkah Implementasi
1. **Sub-Fase 2A — Pembangunan Repositories:**
   * Membuat folder `repositories/` dan file:
     * `repositories/catalog_repo.py`
     * `repositories/copy_repo.py`
     * `repositories/loan_repo.py`
     * `repositories/member_repo.py`
     * `repositories/audit_repo.py`
   * Menambahkan unit test komprehensif di `tests/test_repositories.py`.
2. **Sub-Fase 2B — Pembangunan Business Services:**
   * Membuat folder `services/` dan file:
     * `services/catalog_service.py`
     * `services/loan_service.py`
     * `services/member_service.py`
   * Menambahkan unit test komprehensif di `tests/test_services.py`.
3. **Sub-Fase 2C — Pengalihan Route Aplikasi (`app.py`):**
   * Mengganti pemanggilan SQL langsung di route katalog (`/koleksi`, `/buku/<id>`, `/tambah_buku`, `/edit_buku`) dengan `CatalogService`.
   * Mengganti pemanggilan SQL di route peminjaman (`/pinjam`, `/proses_pinjam`, `/kembalikan_buku`, `/riwayat`) dengan `LoanService`.
   * Menyesuaikan template HTML agar membaca data dari DTO/Dict v2 (`catalog_titles`, `copies`, `loans`, `loan_items`).

### 7.2 Daftar Berkas yang Akan Disentuh pada Fase 2
* **Berkas Baru:**
  * `repositories/__init__.py`
  * `repositories/catalog_repo.py`
  * `repositories/copy_repo.py`
  * `repositories/loan_repo.py`
  * `repositories/member_repo.py`
  * `repositories/audit_repo.py`
  * `services/__init__.py`
  * `services/catalog_service.py`
  * `services/loan_service.py`
  * `services/member_service.py`
  * `tests/test_repositories.py`
  * `tests/test_services.py`
* **Berkas yang Dimodifikasi:**
  * `app.py` (refaktor route untuk memanggil Service Layer)
  * `templates/` (penyesuaian rendering properti objek v2)

---

## 8. Fitur yang Dilarang Dikerjakan pada Fase 2 (*Out of Scope*)

Sesuai arahan arsitektur, fitur-fitur berikut **DILARANG DIKERJAKAN** pada Fase 2:
1. **Fitur Kiosk Mandiri Tablet & QR Scanner Kamera (DEC-002, DEC-003):** Ditunda hingga Fase 3 & 4 setelah backend DAL stabil.
2. **Fitur Notifikasi Publik In-App (DEC-017, OPEN-016):** Dikerjakan pada Fase 7.
3. **Penyusunan Ulang Modul AI Gemini (DEC-016):** Integrasi AI tetap berjalan pada controller yang ada tanpa perombakan besar di Fase 2.
4. **Deploy ke Hugging Face Spaces & Supabase PostgreSQL (DEC-014, DEC-015):** Dikerjakan pada Fase 10 (Production Deployment).
5. **Migrasi Data Produksi `perpustakaan.db`:** Dilarang keras dijalankan sebelum seluruh tahapan aplikasi selesai diuji dan mendapat persetujuan rilis.

