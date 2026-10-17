# AUDIT P0 — STATUS AWAL DAN FONDASI SISTEM PERPUSTAKAAN DIGITAL SEKOLAH
**Tanggal Audit:** 17 Oktober 2026 (Dikoreksi & Diperbarui)  
**Dokumen Acuan:** `docs/DOKUMENTASI_INDUK_v4_2.md`  
**Branch Kerja:** `feature/f1a-baseline` (bercabang dari `feature/p1-multi-book`)  
**Commit Terakhir di feature/p1-multi-book:** `42c4d54` (`docs(p0): add master documentation v4.2 and baseline audit report`)  
**Status DB Produksi:** `perpustakaan.db` 100% ASLI, TIDAK TERSENTUH, BELUM DIMIGRASI.

---

## 1. Ringkasan Eksekutif & Prinsip Audit
Audit ini dilakukan secara independen terhadap source code, konfigurasi, skema database, dan test suite aktual di repositori `c:\Users\ThinkPad\Desktop\sistem-perpustakaan`. Sesuai dengan **Aturan Keras (Rule 1)**: isi `DOKUMENTASI_INDUK_v4_2.md` diperlakukan sebagai konteks kebutuhan dan keputusan produk, bukan bukti keberadaan kode.

Status requirement dievaluasi secara ketat terhadap **Kriteria Penerimaan di Bagian 10**:
- Status **VERIFIED** HANYA disematkan jika ada bukti eksekusi tes unit/integrasi otomatis spesifik yang menguji kriteria penerimaan tersebut.
- Jika fitur sudah ada di kode tetapi belum ada tes otomatis yang menguji kriteria spesifiknya, status ditetapkan sebagai **IMPLEMENTED** dengan mencatat kriteria yang belum teruji.
- Jika fitur belum dibuat kodenya, status ditetapkan sebagai **PLANNED**.

---

## 2. Status Keputusan Produk (DEC-001 s.d. DEC-024)

| Kode | Ringkasan Keputusan Produk | Status Implementasi Aktual di Kode | Bukti & Catatan Teknis |
|---|---|---|---|
| **DEC-001** | Pengunjung umum hanya membaca di tempat; tidak boleh meminjam. | **IMPLEMENTED (Enforced)** | Endpoint sirkulasi `/peminjaman` dan `/proses_pinjam_admin` di `app.py` memvalidasi `session.get('logged_in')`. Belum ada tes spesifik pengujian upaya peminjaman oleh sesi publik. |
| **DEC-002** | Satu tablet bersama dengan kamera untuk layanan mandiri. | **PLANNED** | Belum ada antarmuka tablet/kiosk mandiri. Peminjaman saat ini masih dilakukan oleh admin di `/peminjaman`. |
| **DEC-003** | Pencarian katalog via HP; transaksi mandiri di tablet. | **IMPLEMENTED (Katalog)** | Pencarian publik aktif di `/` dan `/search`. Kiosk tablet belum dibangun. |
| **DEC-004** | ID unik eksemplar otomatis; nomor registrasi lama tidak dipakai. | **PLANNED (Gap)** | Kode saat ini masih menyimpan `id_buku_fisik` berupa JSON nomor registrasi lama di tabel `buku`. Perlu transisi ke auto-generated copy ID pada P2. |
| **DEC-005** | Masa pinjam 7 hari (168 jam); perpanjangan 1x 7 hari via konfirmasi anggota. | **PARTIAL (Pinjam 7 hari)** | Default due date 7 hari diatur di `app.py`, namun alur perpanjangan mandiri 1x 7 hari (LIB-RETURN-004) belum dibangun. |
| **DEC-006** | Pengembalian dapat dilakukan oleh orang selain peminjam. | **IMPLEMENTED (Admin)** | Pengembalian per item `/kembalikan_item/<id>` atau transaksi `/kembalikan/<id>` tidak memvalidasi identitas pengembali, namun saat ini baru bisa diakses admin. Jalur A (scan buku publik) belum ada. |
| **DEC-007** | Transaksi multi-buku dan pengembalian sebagian wajib didukung. | **VERIFIED (Lokal P1)** | Didukung backend P1 di `app.py`. Dibuktikan dengan 4 tes: `test_01_borrow_single_book`, `test_02_borrow_three_books_in_one_transaction`, `test_03_borrow_ten_books_in_one_transaction`, dan `test_04_partial_return_then_complete_remaining`. |
| **DEC-008** | Kartu anggota dapat dicetak sendiri (hemat tinta). | **PLANNED** | Belum ada modul pembuatan dan pencetakan kartu anggota. |
| **DEC-009** | Impor anggota dari Excel/CSV sesuai template aplikasi. | **PLANNED** | Saat ini hanya ada impor katalog buku (`/import_excel`). Belum ada tabel/impor anggota. |
| **DEC-010** | QR anggota memuat token acak, aman, tanpa data pribadi terbuka. | **PLANNED** | Belum ada generator/validator token QR anggota. |
| **DEC-011** | QR buku dibuat otomatis; label menampilkan ID eksemplar terbaca manusia. | **PLANNED** | Belum ada generator label cetak QR eksemplar. |
| **DEC-012** | Tambah buku isi judul + jumlah eksemplar; ID & QR otomatis. | **PARTIAL (Manual)** | Tambah buku di `/add` menerima jumlah stok dan nomor registrasi manual. Belum auto-generate ID eksemplar. |
| **DEC-013** | Eksemplar baru tidak pernah digabung atau ditimpa walau judul sama. | **PLANNED** | Belum ada tabel `eksemplar_buku` terpisah. |
| **DEC-014** | Hosting backend target: Hugging Face Spaces (Docker). | **IMPLEMENTED (Siap Uji)** | `Dockerfile` (Python 3.11-slim, Gunicorn) dan `.dockerignore` sudah siap dan ter-commit. |
| **DEC-015** | Database target: Supabase PostgreSQL. | **PLANNED** | Kode saat ini masih berjalan di SQLite (`perpustakaan.db`). Driver PostgreSQL belum ditambahkan. |
| **DEC-016** | AI Assistant menggunakan Google Gemini API (gemini-2.5-flash). | **VERIFIED (Lokal)** | Terintegrasi di `app.py` via HTTP API langsung (`urllib.request`), grounded pada katalog buku, lolos 18 test unit otomatis. |
| **DEC-017** | Notifikasi keterlambatan in-app publik; WhatsApp TIDAK digunakan. | **PLANNED (WA ditiadakan: VERIFIED)** | Kode bebas dependensi WhatsApp. Halaman notifikasi in-app publik belum dibuat (P4). |
| **DEC-018** | Self-service adalah prinsip mutlak; petugas bukan operator rutin. | **PLANNED** | Alur saat ini masih berpusat pada admin di desktop. Perlu pembangunan antarmuka self-service di P2. |
| **DEC-019** | Tidak ada batas maksimum jumlah buku per transaksi. | **VERIFIED (P1)** | Dibuktikan dengan `test_03_borrow_ten_books_in_one_transaction`: peminjaman 10 buku sekaligus berhasil tanpa penolakan batas kuota buatan. |
| **DEC-020** | Anggota tidak aktif dinonaktifkan, bukan dihapus; histori tetap utuh. | **IMPLEMENTED (Policy)** | Penghapusan riwayat dinonaktifkan permanen di `/hapus_peminjaman`. Entitas tabel anggota belum ada. |
| **DEC-021** | Biaya Rp0 adalah target, bukan klaim gratis selamanya. | **VERIFIED (Docs)** | Dokumen dan kode tidak mengklaim jaminan gratis selamanya. |
| **DEC-022** | UI dan panduan berbahasa Indonesia sangat sederhana. | **PARTIAL** | UI katalog dan peminjaman sudah berbahasa Indonesia. Panduan resmi P6 belum disusun. |
| **DEC-023** | Data anggota sederhana: nama, status aktif/nonaktif, kategori referensi; tanpa kelas. | **PLANNED** | Transaksi lama masih menyimpan kolom `kelas` dan `jurusan`. Perlu skema tabel anggota dan kategori di P2. |
| **DEC-024** | Penyelesaian buku hilang/rusak dengan kamus/Al-Qur'an (bukan uang). | **PARTIAL (Data)** | Kolom `status_penggantian` dan `catatan_penggantian` sudah ada di skema P1. Alur self-service QR penggantian buku belum dibuat. |

---

## 3. Penjelasan Status "IMPLEMENTED (Policy)" pada LIB-MEMBER-002

Keputusan produk **DEC-020** dan kebutuhan **LIB-MEMBER-002** menetapkan:
> *"Anggota yang tidak aktif cukup dinonaktifkan; tidak ada penghapusan otomatis berdasarkan masa tidak aktif. Data inti anggota dan riwayat transaksi tetap tersimpan."*

### Mengapa Berstatus "IMPLEMENTED (Policy)"?
1. **Entitas Anggota Belum Tersedia:**  
   Pada struktur basis data saat ini, belum ada tabel relasional `anggota` (data peminjam masih dicatat langsung sebagai string teks `id_anggota` pada transaksi peminjaman). Oleh karena itu, fitur administrasi penonaktifan/pengaktifan kembali akun anggota (*lifecycle management*) **belum ada**.
2. **Kebijakan Anti-Penghapusan Riwayat Telah Ditegakkan:**  
   Prinsip inti dari DEC-020—yaitu **riwayat transaksi tidak boleh hilang atau dihapus secara permanen**—telah diimplementasikan secara aktif melalui kebijakan proteksi server-side pada route `/hapus_peminjaman/<int:id>` (`app.py` L1795-1804).
3. **Pembuktian Otomatis:**  
   Kebijakan penolakan penghapusan ini diverifikasi oleh 3 tes otomatis:
   - `test_11_completed_loan_deletion_rejected_preserves_history` (transaksi Selesai tidak bisa dihapus)
   - `test_12_active_loan_deletion_rejected_preserves_state` (transaksi Dipinjam tidak bisa dihapus)
   - `test_13_partial_loan_deletion_rejected_preserves_state` (transaksi Sebagian tidak bisa dihapus)
   
*Kesimpulan:* Prinsip perlindungan data historis telah aktif (*policy enforced*), tetapi siklus hidup anggota nonaktif baru akan lengkap setelah tabel `anggota` dibuat pada fase P2.

---

## 4. Status Isu Terbuka (OPEN-016 s.d. OPEN-018)
Sesuai **Aturan Keras (Rule 3)**, hal yang masih terbuka tidak ditebak, melainkan diimplementasikan sebagai konfigurasi kebijakan (*policy config*):

1. **OPEN-016 (Privasi Halaman Notifikasi Publik):**  
   *Kebijakan Target:* Ditentukan via konfigurasi `NOTIF_NAME_MODE` di `policy.py` dengan opsi `"full"` (default per DEC-017) atau `"truncated"` (contoh: "Ahmad S***").
2. **OPEN-017 (Perhitungan Jatuh Tempo Perpanjangan Terlambat):**  
   *Kebijakan Target:* Dikonfigurasi via `ALLOW_RENEW_AFTER_DUE` (default `False`). Jika diizinkan di masa depan, opsi perhitungan jatuh tempo baru diatur via kebijakan terpusat.
3. **OPEN-018 (Rentang Peninjauan Pengembalian 24 Jam & Pemblokiran):**  
   *Kebijakan Target:* Dikonfigurasi via `GROUP_WINDOW_HOURS = 24` dan `BLOCK_MODE = "serious_only"` (hanya keterlambatan > 7 hari yang memblokir pinjaman baru).

---

## 5. Audit Kode Aktual, Skema, dan Keamanan (Phase 0 & P1)

### 5.1 Status Database Produksi
- File `perpustakaan.db`:
  - **Tabel:** `buku` (15 baris), `sqlite_sequence`, `peminjaman` (3 baris: ID 11, 12, 13).
  - **Skema `peminjaman`:** Masih skema lama single-book (`id_buku`, `id_anggota`, `status`, `denda`, dll.).
  - **Status:** 100% utuh, belum dimigrasi ke multi-book. Migrasi produksi ditahan hingga instruksi eksplisit user.
- Skema Target Multi-Book (telah diverifikasi di test suite terisolasi):
  - `peminjaman` (Header): `id`, `kode_transaksi`, `id_anggota`, `tipe_user`, `kelas`, `jurusan`, `jurusan_asli`, `tgl_pinjam`, `tgl_kembali_seharusnya`, `status`, `total_denda`, `denda_historis_asli`, `catatan`.
  - `peminjaman_detail` (Item): `id`, `id_peminjaman`, `id_buku`, `no_registrasi`, `status`, `tgl_dikembalikan`, `denda_keterlambatan`, `denda_kondisi`, `status_penggantian`, `catatan_penggantian`, `catatan`.

### 5.2 Audit Keamanan Produksi (Phase 0 Hardening)
1. **SECRET_KEY Guard (`app.py` L51-66):**  
   - Pada mode produksi (`IS_PRODUCTION = True`), aplikasi **gagal startup (raise RuntimeError)** jika `SECRET_KEY` kosong, merupakan placeholder, atau panjangnya < 16 karakter.
   - Teruji di `test_02_production_guards_reject_weak_secret_key` dan `test_03_production_guards_require_strong_secret_key`.
2. **Kredensial Admin (`app.py` L86-126):**  
   - Password plaintext default tidak ada di source code (menggunakan hash scrypt).
   - Teruji di `test_07_admin_credentials_reject_insecure_defaults_in_production` dan `test_08_admin_credentials_allow_custom_hash_or_strong_password`.
3. **Cookie Session (`app.py` L67-77):**  
   - `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`.
   - Teruji di `test_01_session_cookie_security_flags`.
4. **Brute Force Rate Limiter (`app.py` L129-239):**  
   - In-memory rate limiting thread-safe (maksimal 5 percobaan gagal per IP, lockout 300 detik).
   - Teruji di `test_04_admin_login_rate_limiting_lockout` dan `test_05_admin_login_rate_limiting_reset_on_success`.
5. **Koneksi Database SQLite (`app.py` L279-300):**  
   - `PRAGMA foreign_keys = ON` diterapkan di setiap koneksi.
   - `PRAGMA busy_timeout = 30000` (30 detik).
   - Teruji di `test_09_database_connection_enforces_pragmas` dan `test_10_database_initialization_protects_legacy_schema`.
6. **Proteksi Riwayat Transaksi (`app.py` L1795-1804):**  
   - Route `/hapus_peminjaman/<id>` menolak penghapusan permanen riwayat.
   - Teruji di `test_11_completed_loan_deletion_rejected_preserves_history`, `test_12_active_loan_deletion_rejected_preserves_state`, dan `test_13_partial_loan_deletion_rejected_preserves_state`.
7. **Proteksi Reset Katalog (`app.py` L1168-1205):**  
   - Menolak reset jika masih ada peminjaman aktif. Wajib konfirmasi teks `'KOSONGKAN'`.
   - Teruji di `test_06_catalog_reset_security_guards`.

---

## 6. Koreksi Requirement Matrix Terhadap Kriteria Penerimaan Bagian 10

| Requirement ID | Deskripsi Kebutuhan | Status Terkoreksi | Bukti Tes Spesifik atau Kriteria yang Belum Teruji |
|---|---|---|---|
| **LIB-CAT-001** | Pencarian dan detail katalog buku | **IMPLEMENTED** *(Diturunkan dari VERIFIED)* | **Teruji:** `test_search_suggestions_match_title`, `test_search_suggestions_empty_query`.<br>**Belum teruji:** View endpoint `/search` halaman penuh, feedback pesan jika buku tidak ditemukan, dan detail buku publik `/buku/<id>`. |
| **LIB-COPY-001** | Identitas unik eksemplar fisik | **PLANNED** | Belum ada entitas tabel eksemplar unik otomatis. |
| **LIB-COPY-002** | Perubahan status eksemplar | **PARTIAL** | Transisi status baru ada pada level item transaksi di `peminjaman_detail`. |
| **LIB-LOAN-001** | Transaksi multi-item atomik | **VERIFIED (Lokal)** | **Teruji spesifik:**<br>- `test_01_borrow_single_book` (1 buku)<br>- `test_02_borrow_three_books_in_one_transaction` (3 buku)<br>- `test_03_borrow_ten_books_in_one_transaction` (10 buku, tanpa batas buatan)<br>- `test_07_invalid_registration_number_rejected` (no reg invalid ditolak)<br>- `test_08_unavailable_book_atomic_rollback` (batal atomik jika 1 buku tak tersedia).<br>*Catatan:* Uji konkurensi multi-klien paralel belum ada. |
| **LIB-LOAN-002** | Riwayat peminjaman per eksemplar | **IMPLEMENTED** *(Diturunkan dari VERIFIED)* | **Teruji:** `test_10_book_history_api_and_excel_export` menguji riwayat per buku pada API.<br>**Belum teruji:** Format waktu UTC vs zona waktu sekolah (sedang dikerjakan di f1a). |
| **LIB-RETURN-001**| Pengembalian sebagian dan penuh | **VERIFIED (Lokal)** | **Teruji spesifik:**<br>- `test_04_partial_return_then_complete_remaining` (kembalikan 7 lalu sisa 3)<br>- `test_05_return_same_item_twice_idempotency` (pencegahan kembalikan dobel)<br>- `test_06_two_items_different_status_in_same_transaction` (kondisi berbeda dalam 1 transaksi)<br>- `test_15_lost_book_sets_header_status_menunggu_penggantian` (header status update). |
| **LIB-RETURN-002**| Durasi aktual dan keterlambatan 168 jam | **PARTIAL** | **Teruji sebagian:** `test_09_fine_calculation_per_item` (hitung denda keterlambatan).<br>**Belum teruji:** Batas tepat 168 jam vs 168 jam + 1 detik dan konversi zona waktu UTC<->WIB (fokus task saat ini). |
| **LIB-RETURN-003**| Kondisi buku saat kembali | **IMPLEMENTED** | **Teruji:** `test_06_two_items_different_status_in_same_transaction` mencatat status Normal, Rusak, Hilang. |
| **LIB-RETURN-004**| Perpanjangan 1x 7 hari per eksemplar | **PLANNED** | Alur perpanjangan mandiri belum diimplementasikan di kode. |
| **LIB-QR-001 s.d. 004** | Modul QR anggota, QR buku, manual path, label cetak | **PLANNED** | Belum ada generator/scanner QR. |
| **LIB-OPS-001** | Transaksi mandiri tanpa operator petugas | **PLANNED** | Peminjaman saat ini masih membutuhkan login admin. |
| **LIB-KIOSK-001**| Peminjaman mandiri melalui tablet | **PLANNED** | Antarmuka tablet mandiri belum dibangun. |
| **LIB-MEMBER-001**| Siklus hidup anggota | **PLANNED** | Tabel `anggota` relasional belum ada di skema. |
| **LIB-MEMBER-002**| Penonaktifan anggota tanpa penghapusan otomatis | **IMPLEMENTED (Policy)** | **Teruji spesifik:** `test_11_completed_loan_deletion_rejected_preserves_history`, `test_12_active_loan_deletion_rejected_preserves_state`, `test_13_partial_loan_deletion_rejected_preserves_state` (riwayat transaksi dilindungi permanen). |
| **LIB-IMPORT-001**| Impor Excel anggota | **PLANNED** | Belum ada modul impor anggota. |
| **LIB-IMPORT-002**| Tambah buku judul + jumlah (ID & QR otomatis) | **PLANNED** | Saat ini penambahan buku masih memakai stok manual dan nomor registrasi manual. |
| **LIB-ADMIN-001** | Hak akses server-side | **IMPLEMENTED** *(Diturunkan dari VERIFIED)* | **Teruji:** Rate limiter login (`test_04_admin_login_rate_limiting_lockout`), proteksi reset katalog (`test_06_catalog_reset_security_guards`).<br>**Belum teruji:** Penolakan akses unauthenticated pada seluruh rute admin secara sistematis. |
| **LIB-REPORT-001**| Riwayat dan ekspor Excel | **IMPLEMENTED** *(Diturunkan dari VERIFIED)* | **Teruji:** `test_10_book_history_api_and_excel_export` (format berkas Excel terunduh).<br>**Belum teruji:** Pengujian filter rentang tanggal laporan. |
| **LIB-BACKUP-001**| Prosedur backup dan restore teruji | **IMPLEMENTED (Local)** | Skrip migrasi mendukung backup lokal otomatis (`backups/`), uji restore formal cloud belum dijalankan. |
| **LIB-LOSS-001**  | Penyelesaian buku hilang | **PARTIAL** | Kolom `status_penggantian` ada, alur self-service QR penggantian belum ada. |
| **LIB-AI-001**    | Asisten AI aman (Gemini) | **VERIFIED (Lokal)** | **Teruji spesifik (11 tes):**<br>- `test_ai_chat_success_returns_answer_and_grounded_books`<br>- `test_ai_chat_strips_api_key_from_error_output`<br>- `test_ai_chat_returns_fallback_when_gemini_500`<br>- `test_ai_chat_returns_fallback_when_network_timeout`<br>- `test_ai_chat_rejects_csrf_missing`<br>- `test_ai_chat_empty_message`<br>- `test_extract_skips_thought_parts_and_joins_text`<br>- `test_payload_uses_raised_token_limit_and_disables_thinking`<br>- `test_max_tokens_retries_once_then_returns_complete_text`<br>- `test_max_tokens_twice_is_not_treated_as_success`<br>- `test_home_page_includes_srax_widget_without_secrets`. |
| **LIB-NOTIF-001** | Notifikasi keterlambatan in-app publik | **PLANNED** | WhatsApp terverifikasi ditiadakan; halaman in-app publik belum dibuat. |
| **LIB-FINE-001**  | Penyelesaian buku rusak/hilang via Kamus/Al-Qur'an | **PARTIAL** | Field database tersedia, alur mandiri belum dibuat. |
| **LIB-UX-001**    | Bahasa Indonesia sangat sederhana | **PARTIAL** | Teks UI berbahasa Indonesia, panduan resmi belum disusun. |

---

## 7. Pernyataan Keamanan Data
**Dikonfirmasi:**  
- **TIDAK ADA deploy produksi yang dilakukan.**  
- **TIDAK ADA migrasi atau modifikasi pada database produksi `perpustakaan.db`.**  
- **Database produksi tetap utuh dengan skema asli.**
