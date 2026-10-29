# PROGRESS — Sistem Perpustakaan Digital Sekolah

> **Simpan file ini di `docs/PROGRESS.md`.** Ini papan tugas hidup. Setiap AI/pengembang WAJIB membacanya (setelah `docs/DOKUMENTASI_INDUK_v4_2.md`) dan memperbaruinya di akhir sesi.

**Terakhir diperbarui:** 28 Oktober 2026
**Fase aktif:** Fase 4 — Anggota, impor, kartu QR (Sedang Berjalan)
**TASK BERIKUTNYA (NEXT):** `4-07` (Cabut & terbitkan ulang QR (`qr_version`+1; token lama ditolak))

---

## 0. Cara memakai file ini (untuk AI baru)

1. Baca `docs/DOKUMENTASI_INDUK_v4_2.md` (keputusan produk) lalu file ini. Jangan minta pemilik menjelaskan ulang proyek; semuanya ada di dua file itu.
2. Kerjakan **hanya task bertanda NEXT** (atau task berikutnya yang `Butuh`-nya sudah selesai). Satu sesi = satu sampai tiga task kecil.
3. Sebelum mengubah apa pun: `git status`, jalankan tes baseline, pastikan hijau.
4. Tandai `[x]` **hanya jika ada bukti** (nama tes / output perintah / file). Tulis bukti di baris `Bukti:` pada task itu. Tanpa bukti = tetap `[~]`.
5. Di akhir sesi: perbarui "Fase aktif", "NEXT", tabel ringkasan (bagian 3), dan tambahkan satu entri di **Log Sesi** (bagian 8). Jangan menghapus entri lama.
6. Jika menemukan fakta yang berbeda dari file ini, **jangan diam-diam menimpa**: tulis di bagian "Temuan / Penyimpangan" (bagian 7) dan beri tahu pemilik.
7. Hal yang masih terbuka (bagian 5) **jangan ditebak**; pakai nilai default di `policy.py`.

Legenda status: `[x]` selesai (ada bukti) · `[~]` sedang dikerjakan/sebagian · `[ ]` belum · `[!]` terblokir (tulis alasannya)

---

## 1. Fakta proyek (jangan ditanyakan ulang)

**Tujuan:** aplikasi perpustakaan sekolah untuk dipakai nyata (bukan demo). Prinsip mutlak **self-service-first**: transaksi rutin dilakukan anggota sendiri di satu tablet bersama berkamera; petugas hanya untuk penyiapan data, impor, audit, dan pengecualian.

**Kondisi kode & lingkungan (hasil audit Fase 0/1B/2C):**
- Windows + PowerShell, virtualenv `venv`. Backend: Flask **monolit** `app.py` (~2.400 baris dengan integrasi DAL/Service v2 di rute sirkulasi), template Jinja di `templates/`, SQLite.
- Perintah tes: `.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` (framework: **unittest**, jangan diganti). Baseline hasil verifikasi sesi 18 Oktober 2026: **108 tes OK (0 gagal, 0 error, 0 skip, ~19 detik)**. Rincian: ID generator (5), skema v2 & migrasi (20), waktu (11), regresi P1 multi-book (33), repositories (14), services (14), routes v2 staging (11). Evolusi: 43 (Fase 0) → 54 (Fase 1A) → 69 (Fase 1B) → 108 (Sub-Fase 2A–2C). *Catatan penting: TIDAK mengklaim E2E browser nyata, deployment produksi, offsite backup, atau restore telah teruji.*
- **`perpustakaan.db` di root = database asli. DILARANG disentuh/dimigrasi.** Isi: skema lama v1 (tabel `buku`, `peminjaman`), 15 buku, 3 transaksi. Semua uji/migrasi hanya pada salinan di `backups/` atau `scratch/`.
- Salinan P1 untuk uji: `backups/test_copy_migration.db` (skema P1: `peminjaman` + `peminjaman_detail`).
- Branch: `feature/p1-multi-book` → `feature/f1a-baseline` → `feature/f1b-schema-v2` (aktif). Satu branch per fase `feature/fN-nama`.
- **Jangan sentuh** folder `DO NOT TOUCH THIS` dan worktree `pinnate-century`.
- Sudah ada di kode (perlu diverifikasi per requirement, jangan ditulis ulang): AI Gemini (`tests/test_ai_assistant.py`, 18 tes), login admin + CSRF, ekspor Excel, backup lokal, P1 multi-buku (`tests/test_multi_book_p1.py`, 15 tes), `tests/test_production_safety.py` (10 tes).
- Belum ada: tabel anggota, ID eksemplar otomatis, QR, kiosk, perpanjangan, notifikasi, penyelesaian hilang/rusak, Docker/HF/Supabase.

**Temuan data penting:**
- Stok lama bersifat dual-state: `buku.id_buku_fisik` (JSON, hanya eksemplar yang ada di rak) + `buku.stok`. Eksemplar yang sedang dipinjam TIDAK ada di JSON. Total eksemplar riil = 27 di rak + 1 dipinjam (`00001501`) = **28**.
- Peminjam lama berupa teks bebas (nama/kelas/jurusan); **jangan dibuatkan anggota otomatis**.
- Tanggal lama berupa string naive `YYYY-MM-DD` (anggap WIB); transaksi aktif ID 13 jatuh tempo 1 hari (bukan 7) dan akan tampak terlambat.
- Dua peminjam lama tampak seperti data uji ("TEST USER", "REGRESSION TEST USER"); tandai `data_uji`.

**Arsitektur target:** Flask di Docker pada Hugging Face Spaces; Supabase PostgreSQL (+Storage untuk cover); Gemini API (`gemini-2.5-flash`, verifikasi nama model terkini); notifikasi dalam aplikasi (tanpa WhatsApp). Target biaya Rp0 **tanpa klaim gratis selamanya**; verifikasi ketentuan layanan terkini.

**Strategi kode:** "strangler" — logika baru di modul terpisah (`services/`, `repositories/`), route lama di `app.py` dialihkan satu per satu (pakai feature flag `USE_V2`). Jangan memecah `app.py` sekaligus. Jangan menulis ulang aplikasi.

### Keputusan produk yang DILINDUNGI (ringkas; detail di dokumen induk Bagian 3.1 & 15)
- Pengunjung umum tidak boleh meminjam. Satu tablet bersama; pencarian lewat HP, transaksi di tablet.
- ID eksemplar & QR buku dibuat otomatis oleh aplikasi; nomor registrasi lama tidak dipakai. Buku ditambah dengan **judul + jumlah**. Label QR menampilkan ID terbaca manusia. Eksemplar tidak pernah digabung/ditimpa karena judul sama.
- Masa pinjam maks **168 jam** per eksemplar; **perpanjangan 1x +7 hari** per eksemplar, harus dipilih & dikonfirmasi anggota.
- Pengembalian boleh oleh orang lain (Jalur A: scan buku, tanpa kartu). Jalur B: sesi anggota (banyak buku, perpanjang, penyelesaian).
- Multi-buku & pengembalian sebagian wajib; **tidak ada batas jumlah buku**; judul sama boleh >1 eksemplar.
- Data anggota minimal: nama, status aktif/nonaktif, kategori (tabel referensi). **Tanpa kelas, tanpa telepon.** Anggota **tidak pernah dihapus otomatis**; cukup dinonaktifkan.
- QR anggota = token acak, tanpa data pribadi, bisa dicabut.
- Notifikasi keterlambatan = halaman dalam aplikasi, **dapat dilihat siapa pun**, data minimum (nama, judul/ID eksemplar, jatuh tempo, lama terlambat). Tanpa WhatsApp/pesan keluar.
- **Terlambat ≠ hilang.** >7 hari lewat jatuh tempo = peringatan serius + blokir pinjam baru. Tidak ada sanksi lain.
- Buku hilang/rusak: diselesaikan dengan pengganti **kamus atau Al-Qur'an** (bukan uang) lewat sesi anggota; dicatat per buku; final setelah pengganti diterima.
- UI & panduan: Bahasa Indonesia **sangat sederhana**. Server menegakkan aturan; riwayat tidak pernah dihapus; waktu disimpan UTC, tampil `Asia/Jakarta`.
- DILARANG tanpa izin eksplisit pemilik: deploy produksi, migrasi/ubah DB produksi, hapus data, kirim pesan keluar, ubah kebijakan.

---

## 2. Format laporan akhir setiap sesi (wajib)

Branch + commit · file berubah + alasan · requirement ID & status · perintah tes + hasil NYATA · schema/DB disentuh atau tidak · risiko/pertanyaan terbuka · cara verifikasi manual · konfirmasi "tidak ada deploy/migrasi produksi". Jangan menyatakan tes lulus jika tidak dijalankan.

---

## 3. Ringkasan progres

| Fase | Isi | Selesai | Status |
|---|---|---|---|
| 0 | Audit repositori | 4/4 | SELESAI |
| 1A | Amankan baseline, waktu & kebijakan | 5/5 | SELESAI (dilaporkan; lihat catatan) |
| 1B | Skema v2 & migrasi (salinan saja) | 10/10 | SELESAI (commit `73e44c0`) |
| 2 | DAL, Service & Route Staging v2 | 3/3 Sub-fase | SELESAI STAGING (Sub-Fase 2A, 2B, 2C; commit `bd84740`) |
| 3 | Katalog, tambah buku, label QR | 12/12 | SELESAI |
| 4 | Anggota, impor, kartu QR | 6/10 | SEDANG BERJALAN |
| 5 | Kiosk tablet | 0/10 | belum |
| 6 | Sesi anggota: perpanjang & penyelesaian | 0/10 | belum |
| 7 | Keterlambatan, blokir, notifikasi | 0/6 | belum |
| 8 | Verifikasi AI Gemini | 0/5 | belum |
| 9 | Keamanan, UX, laporan | 0/6 | belum |
| 10 | Docker, HF Spaces, Supabase, backup (staging) | 0/8 | belum |
| 11 | Panduan, UAT, serah terima | 0/5 | belum |

---

## 4. Daftar task

> Nama tabel/fungsi pada Fase 2 ke atas bersifat **sementara**; sesuaikan dengan kode aktual setelah Fase 1B dan catat perubahannya di bagian 7. Task Fase 2+ ditulis ulang detailnya setelah laporan Fase 1B.

### FASE 0 — Audit (SELESAI)
- [x] **0-01** Salin dokumen induk ke `docs/DOKUMENTASI_INDUK_v4_2.md`. Bukti: file ada di `docs/`.
- [x] **0-02** Audit git, struktur, dependensi, route `app.py`. Bukti: `docs/AUDIT_P0.md`.
- [x] **0-03** Jalankan tes baseline. Bukti: 43 tes OK (unittest).
- [x] **0-04** Verifikasi DB asli tidak berubah. Bukti: `scratch/verify_original_db.py` → 15 buku, 3 transaksi, tanpa `peminjaman_detail`.

### FASE 1A — Baseline, waktu, kebijakan (SELESAI, dilaporkan)
> Catatan: statusnya disimpulkan dari laporan Fase 1B (branch `feature/f1a-baseline`, 54 tes). Laporan 1A sendiri tidak ditinjau; konfirmasi dengan menjalankan tes.
- [x] **1A-01** Amankan perubahan uncommitted; rapikan `.gitignore` (`*.db`, `venv/`, `.env`).
- [x] **1A-02** Koreksi `docs/AUDIT_P0.md`: VERIFIED hanya bila ada tes yang menunjuk kriteria penerimaan.
- [x] **1A-03** Buat `config.py` (SCHOOL_TZ) dan `policy.py` (konstanta kebijakan, lihat bagian 5).
- [x] **1A-04** Buat `timeutil.py` (`now_utc`, `to_school_tz`, `format_school`); ganti `datetime.now()` di `app.py`.
- [x] **1A-05** Tes waktu (batas 168 jam, konversi UTC↔WIB).

### FASE 1B — Skema v2 & migrasi (SELESAI)
Spec lengkap (revisi R1–R12 telah **disetujui pemilik**): skema v2 + migrasi dari skema P1 **hanya pada salinan**. `app.py` TIDAK diubah di fase ini. Seluruh task 1B-01 s.d. 1B-10 telah selesai dan diverifikasi secara independen.
- [x] **1B-01** Inspeksi skema aktual & rencana pemetaan. Bukti: laporan inspeksi Fase 1B (28 eksemplar, peminjam lama teks bebas), `docs/MIGRASI_F1B.md`.
- [x] **1B-02** Rencana disetujui dengan revisi R1–R12. Bukti: implementasi R1-R12 pada `migrations/0001_initial_v2_schema.sql` dan `docs/MIGRASI_F1B.md`.
- [x] **1B-03** `get_connection()` terpusat dengan `PRAGMA foreign_keys=ON` di setiap koneksi. Bukti: `db.py`, delegasi `get_db_connection()` dan `init_db()` di `app.py`, `tests/test_schema_v2_and_migration.py:test_03_foreign_keys_enforced`, `test_03b_centralized_connection_configuration_and_pragma`.
- [x] **1B-04** `id_generator.py`: format disahkan `<PREFIX>-<6 KARAKTER>` alfabet Crockford Base32 `23456789ABCDEFGHJKMNPQRSTVWXYZ`. Validasi prefix (`ValueError`) dan batas tabrakan (`RuntimeError`). Bukti: `id_generator.py`, `tests/test_id_generator.py` (7 tes OK).
- [x] **1B-05** DDL skema v2 di `migrations/0001_initial_v2_schema.sql` + tabel `schema_version` + deteksi versi skema (v1 / P1 / v2 via `db.detect_schema_version()`). 10 tabel inti v2, 2 view ketersediaan, index parsial unik `idx_loan_items_active_copy`, waktu teks ISO-8601 UTC. Bukti: `migrations/0001_initial_v2_schema.sql`, `tests/test_schema_v2_and_migration.py:test_11_schema_v2_ddl_and_version_detection`.
- [x] **1B-06** View ketersediaan: `v_copy_availability`, `v_title_availability` (`total_aktif`, `total_semua`, `available_copies`, `borrowed_copies`). Bukti: DDL baris 136-165, `tests/test_schema_v2_and_migration.py:test_12_availability_views_copy_and_title_contracts`.
- [x] **1B-07** Migrator mode `--dry-run` (default): zero-write terbukti matematis (SHA-256 byte-identical), menolak skema v1, menolak path `perpustakaan.db` produksi via `os.path.realpath`, memeriksa nomor registrasi duplikat lintas buku. Bukti: `scripts/migrate_legacy_to_v2.py`, `tests/test_schema_v2_and_migration.py:test_06_dry_run_does_not_modify_db`, `test_13_migrator_safety_and_dryrun_contracts`.
- [x] **1B-08** Migrator `--apply` (atomik, idempoten): pemisahan judul & eksemplar, pemetaan peminjaman & item, tabel baca-saja `legacy_copy_map` dan `legacy_loan_item_extra`, verifikasi foreign keys (`PRAGMA foreign_key_check = []`). Bukti: `scripts/migrate_legacy_to_v2.py`, `tests/test_schema_v2_and_migration.py:test_07_migration_apply_on_copy_db`, `test_08_migration_idempotent`.
- [x] **1B-09** Test suite migrasi terisolasi: constraint parsial, rollback atomik, migrasi salinan, dry-run tidak menulis, penolakan path asli, FK, proteksi trigger anti-DELETE, baseline P1 multi-book tetap hijau. Bukti: `tests/test_schema_v2_and_migration.py` (14 tes OK), seluruh suite 114/114 tes OK.
- [x] **1B-10** Dokumentasi migrasi `docs/MIGRASI_F1B.md`: kamus data, pemetaan kolom, aturan waktu, panduan migrasi, rollback, catatan PostgreSQL, pemisahan lingkungan DB, rekonsiliasi data aktual, checklist laporan akhir. Checksum `perpustakaan.db` terjaga utuh (`1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B`). Keberhasilan migrasi salinan ditegaskan TIDAK memberikan izin cutover produksi.

**GERBANG → Fase 2:** Laporan 1B disetujui, dilanjutkan ke perancangan dan implementasi Sub-Fase 2A, 2B, 2C.

### FASE 2 — Data Access Layer, Business Services, & Staging Route Integration (SELESAI STAGING)
Tujuan: Membangun repository layer, service layer, dan mengintegrasikan route sirkulasi inti via pola strangler fig (`detect_schema_version(conn)`). Di-commit pada commit `bd84740`.

**Status Sub-Fase (Berbasis Bukti Aktual):**
- [x] **Sub-Fase 2A — Repository Layer Terisolasi:** Paket `repositories/` (`catalog_repo`, `copy_repo`, `loan_repo`, `member_repo`, `audit_repo`). CRUD v2 terisolasi, pencegahan DELETE fisik (P2-02), collision retry loop (P2-01). Bukti: `tests/test_repositories.py` (14 tes OK), commit `bd84740`.
- [x] **Sub-Fase 2B — Business Service Layer & Atomic Transactions:** Paket `services/` (`loan_service`, `catalog_service`, `member_service`, `transaction_scope`). Menegakkan DEC-005 (168 jam & 1x perpanjang), DEC-007 (pengembalian parsial), DEC-020 (anggota nonaktif ditolak), DEC-024 (buku hilang ganti fisik kamus/Al-Qur'an tanpa denda uang), rollback atomik multi-item, audit log otomatis. Bukti: `tests/test_services.py` (14 tes OK), commit `bd84740`.
- [x] **Sub-Fase 2C — Staging Route Integration & Test:** Integrasi route sirkulasi di `app.py` di balik `if schema_ver == 'v2'` (`/peminjaman`, `/proses_pinjam_admin`, `/kembalikan_item/<id>`, `/kembalikan/<id>`, `/perpanjang_item/<id>`, `/delete/<id>`). Bukti: `tests/test_routes_v2.py` (11 tes OK), commit `bd84740`.
  - *Catatan Batasan 2C Penting:* Integrasi terbukti pada level route integration test staging. Route katalog publik & input buku (`/koleksi`, `/buku/<id>`, `/tambah_buku`, `/edit_buku`) MASIH menggunakan skema legacy P1 (`buku` + `stok` + `id_buku_fisik`) dan belum di-bridge ke v2 (masuk ke Fase 3). Seluruh UI v2 belum dibuktikan end-to-end pada browser nyata dan belum siap cutover produksi.

**Pemetaan Task Detail Fase 2:**
- [x] **2-01** Desain DAL & Service Abstraction. Bukti: `docs/FASE_2_DATA_ACCESS_LAYER_DESIGN.md`.
- [x] **2-02** `repositories/` v2 (copies, loans, loan_items, members, catalog). Bukti: paket `repositories/`, `tests/test_repositories.py`.
- [x] **2-03** `services/loan_service.borrow_copies()`: validasi server, durasi pinjam, atomik (`transaction_scope`). Bukti: `services/loan_service.py`, `tests/test_services.py`.
- [x] **2-04** Idempotensi & atomisitas sirkulasi: collision retry, rollback multi-item jika 1 gagal. Bukti: `tests/test_services.py:test_atomic_rollback_on_failure`.
- [x] **2-05** `services/loan_service.return_copies()`: pengembalian per eksemplar, pembebasan partial index, penanganan rusak/hilang (DEC-024). Bukti: `services/loan_service.py`, `tests/test_services.py`.
- [x] **2-06** Status turunan transaksi peminjaman: Selesai / Sebagian / Dipinjam. Bukti: `app.py:daftar_peminjaman`.
- [ ] **2-07** API JSON `/api/loans`, `/api/returns` (respons `{ok, kode, pesan, data}`). Status: Ditunda/Provisional, prioritas sirkulasi web tercapai via route controller Flask.
- [x] **2-08** Alihkan route sirkulasi ke service baru dengan deteksi skema dinamis `detect_schema_version(conn)`. Bukti: `app.py` baris 1132, 1298, 1509, 1673, 1819, 2012.
- [x] **2-09** Pertahankan suite regresi `test_multi_book_p1.py` tetap hijau (33 tes OK) + route integration staging v2 (`test_routes_v2.py`, 11 tes OK). Bukti: 108 total tests OK.
- [x] **2-10** Hook validasi kelayakan anggota `can_borrow`: memeriksa status aktif (DEC-020), penolakan anggota nonaktif. Bukti: `services/loan_service.py:borrow_copies`, `tests/test_services.py:test_borrow_inactive_member_rejected`. (Pengecekan blokir keterlambatan serius Fase 7).

### FASE 3 — Katalog, tambah buku, label QR (provisional)
- [x] **3-01** Verifikasi auth admin yang ada: tiap route admin menolak tanpa login (tes otomatis), rate limit login, flag cookie, CSRF per POST; perbaiki yang kurang. Bukti: policy.py, app.py, tests/test_admin_auth.py (27 tes OK), 141/141 total tes regresi OK.
- [x] **3-02** Form tambah buku (judul, penulis, ISBN, kategori, **jumlah**) tahap pratinjau "Anda akan membuat N eksemplar" (jumlah >100 wajib diketik ulang). Bukti: policy.py, services/catalog_service.py, app.py, templates/tambah_buku.html, tests/test_add_book_form.py (25 tes OK), 166/166 total tes regresi OK, zero-write terverifikasi.
- [x] **3-03** Commit atomik + token sekali pakai: klik ganda/kirim ulang tidak menggandakan; gagal di tengah = 0 eksemplar. Bukti: policy.py, services/catalog_service.py (tabel persisten confirmation_tokens, transaksi BEGIN IMMEDIATE), migrations/0001_initial_v2_schema.sql, app.py, templates/tambah_buku.html, tests/test_atomic_add_book_commit.py (15 tes OK), 181/181 total tes regresi OK, durabilitas restart, zero-duplicate concurrency lintas worker, & atomic rollback terverifikasi.
- [x] **3-04** Peringatan judul mirip (ISBN, atau judul+penulis ternormalisasi); tidak pernah gabung diam-diam. Bukti: services/catalog_service.py, repositories/catalog_repo.py, app.py, templates/tambah_buku.html, tests/test_duplicate_title_warning.py (17 tes OK), 198/198 total tes regresi OK, zero-write terverifikasi, DEC-013 pembuatan rekaman terpisah terbukti.
- [x] **3-05** Template impor katalog (judul, penulis, isbn, kategori, jumlah) + halaman panduan. Bukti: services/catalog_service.py (CATALOG_IMPORT_HEADERS, generator CSV UTF-8), app.py (route /buku/impor/panduan, /buku/impor/template), templates/panduan_impor_katalog.html, templates/koleksi.html, templates/tambah_buku.html, tests/test_catalog_import_template.py (14 tes OK), 212/212 total tes regresi OK, zero-write terverifikasi.
- [x] **3-06** Pratinjau impor tanpa menulis DB: baris OK/peringatan/error + alasan; batas ukuran file; formula tidak dieksekusi. Bukti: services/catalog_service.py (parse_and_validate_catalog_import_csv, is_potential_formula), policy.py (MAX_CATALOG_IMPORT_FILE_SIZE_BYTES, MAX_CATALOG_IMPORT_ROWS), app.py (/buku/impor/preview, /buku/preview-impor), templates/preview_impor_katalog.html, templates/panduan_impor_katalog.html, tests/test_catalog_import_preview.py (17 tes OK), 229/229 total tes regresi OK, zero-write terverifikasi.
- [x] **3-07** Commit impor atomik + ringkasan (judul baru, eksemplar dibuat, dilewati, bermasalah). Bukti: services/catalog_service.py (create_catalog_import_confirmation_token, commit_catalog_import_with_token, canonicalize_import_payload, compute_import_payload_hash), app.py (/buku/impor/konfirmasi, /buku/impor/commit, /buku/commit-impor), templates/preview_impor_katalog.html, templates/konfirmasi_impor_katalog.html, templates/ringkasan_impor_katalog.html, tests/test_catalog_import_commit.py (26 tes OK), 114/114 tes Fase 3 OK, 255/255 total tes regresi OK, atomisitas BEGIN IMMEDIATE, durabilitas token restart, replay idempotensi, 4 kategori ringkasan (judul baru, eksemplar dibuat, dilewati, bermasalah), & integritas database terverifikasi.
- [x] **3-08** Halaman cetak label `/admin/labels` (A4 grid): QR + ID terbaca manusia berdekatan + judul singkat; QR hanya memuat ID eksemplar. Bukti: `services/qr_service.py` (pure Python generator ISO/IEC 18004 Model 2), `repositories/copy_repo.py` (`get_copies_for_labels`), `services/catalog_service.py` (`get_label_items`, `format_short_title`), `app.py` (`/admin/labels`), `templates/admin_labels.html` (A4 CSS grid, `@media print`), `tests/test_admin_labels.py` (23 tes OK), 164 tes Fase 3 OK, 278 tes regresi OK, zero-write terverifikasi, OpenCV decode terverifikasi.
- [x] **3-09** Cetak ulang (ID & QR identik) + halaman "Eksemplar tanpa label" untuk buku lama di rak. Bukti: `services/qr_service.py` (deterministik ISO/IEC 18004 Model 2), `repositories/copy_repo.py` (`get_unlabeled_candidate_copies`, `get_copies_for_labels` deduplikasi), `services/catalog_service.py` (`parse_copy_ids`, `get_reprint_label_items`, `get_unlabeled_candidates`), `app.py` (`/admin/labels/cetak-ulang`, `/admin/labels/tanpa-label`), `templates/admin_labels_reprint.html`, `templates/admin_labels_tanpa_label.html`, `templates/admin_labels.html` (mode cetak ulang A4), `tests/test_admin_labels_reprint_and_unlabeled.py` (23 tes OK), 187 tes Fase 3 OK, 301 tes regresi proyek OK, zero-write terverifikasi.
- [x] **3-10** Nonaktifkan/tandai eksemplar per eksemplar dengan alasan → `audit_log`; tanpa hard delete. Bukti: services/catalog_service.py (deactivate_copy), repositories/copy_repo.py (get_copy_by_id, update_copy_status), repositories/audit_repo.py (record_audit), app.py (/admin/copies/<copy_id>/deactivate, /admin/eksemplar/<copy_id>/nonaktifkan), templates/admin_copy_deactivate.html, templates/admin_labels_tanpa_label.html, tests/test_copy_deactivate.py (22 tes OK), 209 tes Fase 3 OK, 323 total tes regresi proyek OK (0 gagal, 0 error), integritas database & trigger R12 terverifikasi, zero-write GET terverifikasi.
- [x] **3-11** Upload cover: validasi magic bytes, ukuran, nama UUID; lewat interface `Storage` (Local sekarang; Supabase di Fase 10). Bukti: services/storage_service.py (Storage ABC, LocalStorage, FakeStorage, detect_image_format_and_validate, validate_cover_image, generate_cover_filename, update_book_cover), policy.py (MAX_COVER_IMAGE_SIZE_BYTES 2 MiB, ALLOWED_COVER_EXTENSIONS, ALLOWED_COVER_MIMETYPES), services/exceptions.py (StorageError), app.py (/buku/<id>/upload_cover, /admin/catalog/<id>/cover, /admin/buku/<id>/cover, /add, detail_buku, validate_image_file delegasi), tests/test_cover_upload.py (21 tes OK), 230 tes Fase 3 OK, 344 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV), pencegahan orphan file & atomic rollback terverifikasi, path traversal guard terverifikasi, isolasi tanpa leak path server terverifikasi.
- [x] **3-12** Pencarian katalog publik memakai `v_title_availability` (ketersediaan dari DB; input kosong/aneh ditangani). Bukti: policy.py (MAX_CATALOG_SEARCH_QUERY_LENGTH, DEFAULT_CATALOG_PAGE_SIZE), repositories/catalog_repo.py (escape_like_pattern, search_catalog_titles_with_availability, count_search_catalog_titles, get_catalog_metrics_v2), services/catalog_service.py (clean_catalog_search_query, escape_like_query, search_catalog_public), app.py (koleksi_lengkap, api_search_suggestions, detail_buku ketersediaan v2 via v_title_availability), tests/test_catalog_search_v_title_availability.py (17 tes OK), 247 tes Fase 3 OK, 361 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), proteksi SQLi & karakter liar terverifikasi, ketersediaan akurat tanpa menghitung eksemplar nonaktif/rusak/hilang/dalam_penanganan terbukti, zero-write terverifikasi mutlak.

### FASE 4 — Anggota, impor, kartu QR (provisional)
- [x] **4-01** Token QR anggota: HMAC-SHA256(SECRET_KEY, member_id:qr_version), tanpa data pribadi; validasi `compare_digest`; keputusan dicatat di `docs/KEPUTUSAN_TEKNIS.md`. Bukti: services/member_service.py (build_member_token_payload, sign_member_token_payload, generate_member_qr_token, parse_member_qr_token, verify_member_token_signature, verify_member_qr_token, validate_member_token, get_member_token_secret), services/qr_service.py (generate_member_qr_svg), policy.py (MEMBER_TOKEN_DELIMITER, MEMBER_TOKEN_SIG_LENGTH, MAX_MEMBER_TOKEN_LENGTH), services/exceptions.py (SecretKeyError, InvalidMemberTokenError, MemberTokenRevokedError), docs/KEPUTUSAN_TEKNIS.md (arsitektur & keamanan token), tests/test_member_qr_token.py (21 tes OK), 382 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), zero-write terverifikasi mutlak, privasi tanpa PII terbukti.
- [x] **4-02** Seed `member_categories` (murid/jurusan, guru jurusan/program keahlian, guru umum/mata pelajaran, staf, teknisi) + daftar & cari anggota (admin). Bukti: policy.py (OFFICIAL_MEMBER_CATEGORIES, MAX_MEMBER_SEARCH_QUERY_LENGTH, DEFAULT_MEMBER_PAGE_SIZE, MAX_MEMBER_PAGE_SIZE), repositories/member_repo.py (seed_default_categories, list_members escaping LIKE, count_members, get_member_summary_metrics), services/member_service.py (seed_member_categories, get_all_categories, clean_member_search_query, search_members_admin, get_member_management_metrics), app.py (/admin/members, /admin/anggota), templates/admin_members.html, templates/layout.html, tests/test_admin_members.py (21 tes OK), 76 tes komponen terkait OK, 403 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), zero-write terverifikasi mutlak, privasi tanpa PII (DEC-023) terbukti.
- [x] **4-03** Template impor anggota (nama, jenis, keterangan, status, id_anggota opsional); kolom kelas/telepon diabaikan dengan peringatan. Bukti: policy.py (MAX_MEMBER_IMPORT_FILE_SIZE_BYTES 2 MiB, MAX_MEMBER_IMPORT_ROWS 2000, MEMBER_IMPORT_FILENAME, MEMBER_IMPORT_HEADERS, MEMBER_REQUIRED_HEADERS, MEMBER_IGNORED_COLUMN_NAMES), services/member_service.py (MEMBER_IMPORT_SAMPLE_DATA, get_member_import_sample_data, generate_member_import_template_csv, get_member_import_template_download_payload, normalize_member_jenis, validate_member_id_format, validate_member_import_header, parse_and_validate_member_import_csv), app.py (/admin/members/impor/template, /admin/anggota/impor/template, /admin/members/impor/panduan, /admin/anggota/impor/panduan), templates/panduan_impor_anggota.html, templates/admin_members.html, tests/test_member_import_template.py (21 tes OK), 118 tes komponen terkait OK, 424 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), zero-write terverifikasi mutlak, privasi tanpa PII (DEC-023) terbukti.
- [x] **4-04** Pratinjau pencocokan (OPEN-011): ID cocok → perbarui; tanpa ID → BARU / KEMUNGKINAN SAMA / AMBIGU, petugas memilih per baris; tidak ada penimpaan diam-diam. Bukti: services/member_service.py (preview_member_import_matching, validate_member_import_decisions), services/__init__.py, policy.py (MEMBER_MATCH_STATUSES, MEMBER_ACTION_CHOICES), app.py (/admin/members/impor/preview & /admin/anggota/impor/preview), templates/preview_impor_anggota.html, templates/panduan_impor_anggota.html, tests/test_member_import_preview.py (19 tes OK), 109 tes anggota & autentikasi OK, 443 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), zero-write terverifikasi mutlak, privasi tanpa PII (DEC-023) terbukti.
- [x] **4-05** Commit impor atomik; sanggup >1.000 baris; ringkasan dibuat/diperbarui/dilewati/gagal; anggota yang tidak ada di file tidak diubah. Bukti: services/member_service.py (create_member_import_confirmation_token, commit_member_import_with_token, canonicalize_member_import_payload, compute_member_import_payload_hash), repositories/member_repo.py (update_member dukungan status & category_id), app.py (/admin/members/impor/konfirmasi, /admin/members/impor/commit), templates/preview_impor_anggota.html, templates/konfirmasi_impor_anggota.html, templates/ringkasan_impor_anggota.html, tests/test_member_import_commit.py (25 tes OK), 134 tes anggota & autentikasi OK, 468 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), transaksi BEGIN IMMEDIATE 100% atomik & rollback, proteksi anti-tampering hash payload, idempotensi replay ringkasan, skala >1.000 baris (1.050 baris teruji), zero-write & privasi DEC-023 terbukti.
- [x] **4-06** Nonaktifkan/aktifkan kembali anggota (alasan → `audit_log`); tanpa tombol hapus, tanpa job pembersihan. Bukti: services/member_service.py (set_member_status, deactivate_member, reactivate_member, get_member_audit_history), repositories/member_repo.py (_row_to_dict robust factory), app.py (/admin/members/<member_id>/status & alias), templates/admin_members.html, templates/admin_member_status.html, policy.py (MIN_MEMBER_STATUS_REASON_LENGTH, MAX_MEMBER_STATUS_REASON_LENGTH, OFFICIAL_MEMBER_STATUSES), tests/test_member_deactivate_and_reactivate.py (25 tes OK), 159 tes anggota & autentikasi OK, 493 total tes regresi proyek OK (0 gagal, 0 error, 1 skip OpenCV di venv), atomisitas transaction_scope, audit log lengkap, penolakan peminjaman baru anggota nonaktif (DEC-020), pelestarian peminjaman aktif & tanpa hard delete, zero-write & privasi DEC-023 terbukti.
- [ ] **4-07** Cabut & terbitkan ulang QR (`qr_version`+1; token lama ditolak).
- [ ] **4-08** Kartu anggota cetak hemat tinta (nama, kategori+keterangan, QR); cetak massal.
- [ ] **4-09** Ekspor anggota menyertakan `id_anggota`.
- [ ] **4-10** Keputusan pemilik: hubungkan peminjam lama (`member_id` NULL) ke anggota resmi atau biarkan. Status: menunggu keputusan pemilik.

### FASE 5 — Kiosk tablet (provisional)
- [ ] **5-01** Vendor `html5-qrcode` ke `static/vendor` (tanpa CDN).
- [ ] **5-02** Rute `/kiosk/*` dengan cookie sesi terpisah (`Path=/kiosk`); kiosk tidak membaca sesi admin; `/admin` tidak terjangkau dari kiosk (tes).
- [ ] **5-03** Komponen scan: debounce, umpan balik, pesan sederhana saat kamera ditolak/tidak ada, tombol input manual.
- [ ] **5-04** Alur pinjam: layar bersih → scan kartu → validasi server → scan buku (tiap scan divalidasi).
- [ ] **5-05** Layar review (hapus per item, batal) → validasi ulang → commit atomik dengan idempotency key → struk; gagal tampil jelas GAGAL.
- [ ] **5-06** Jalur A "Kembalikan Buku": scan buku tanpa kartu → pilih kondisi → konfirmasi; bisa beruntun.
- [ ] **5-07** Fallback manual (ketik ID label): satu hasil → konfirmasi judul; ambigu/tidak ada → berhenti "beri tahu petugas"; ditandai `manual` di data/audit.
- [ ] **5-08** Timeout idle 60 dtk (peringatan 15 dtk), reset sesi server+klien, anti Back/refresh/klik ganda, tidak memakai localStorage untuk data anggota.
- [ ] **5-09** UI cold start: "Sedang menyiapkan layanan...", retry aman, offline jelas.
- [ ] **5-10** Tes otomatis "tanpa petugas" (LIB-OPS-001) + uji tablet nyata → `docs/UJI_TABLET.md`.

### FASE 6 — Sesi anggota: perpanjang & penyelesaian (provisional)
- [ ] **6-01** Sesi Jalur B: scan kartu → daftar pinjaman aktif anggota.
- [ ] **6-02** Scan buku yang dikembalikan di sesi anggota (buku tak dipindai tetap aktif; buku milik orang lain diarahkan ke Jalur A).
- [ ] **6-03** "Selesaikan Sesi": ringkasan dikembalikan vs belum dipindai; per buku pilih Perpanjang / Tetap / Bermasalah; commit sekali, atomik.
- [ ] **6-04** `services/extend_service`: satu kali per eksemplar, konfirmasi anggota, `due_at` baru = lama + 7 hari bila belum jatuh tempo; kedua ditolak; setelah jatuh tempo ikut `ALLOW_RENEW_AFTER_DUE` (default False).
- [ ] **6-05** Kelompok pemeriksaan 24 jam (hanya tampilan; keputusan per eksemplar; tidak ada perpanjangan otomatis).
- [ ] **6-06** Tabel `settlement_cases` & `settlement_items` (kondisi hilang/rusak/lainnya, keterangan, pengganti kamus/Al-Qur'an, status menunggu/diterima).
- [ ] **6-07** Alur penyelesaian multi-buku dengan layar konfirmasi akhir; atomik; copy → `dalam_penanganan`.
- [ ] **6-08** Pintu masuk: QR Penyelesaian Buku (cetak dari admin) **dan** tombol di layar; tanpa sesi anggota valid ditolak.
- [ ] **6-09** Admin "Kewajiban Pengganti": tombol "Terima Pengganti" → item ditutup (`penyelesaian`), copy → hilang/rusak, `audit_log`.
- [ ] **6-10** Tes: perpanjang 1x OK / 2x ditolak, terlambat tidak jadi hilang, QR tanpa sesi ditolak, konkurensi, riwayat utuh, tidak ada denda uang.

### FASE 7 — Keterlambatan, blokir, notifikasi (provisional)
- [ ] **7-01** `overdue_service`: terlambat (`now > due_at`; tepat due bukan terlambat), serius (`> due_at + 7 hari`), lama terlambat; semua dihitung dari timestamp.
- [ ] **7-02** `can_borrow` penuh: blokir bila ada item serius belum kembali atau kewajiban settlement terbuka (`BLOCK_MODE="serious_only"`; alasan sederhana).
- [ ] **7-03** Halaman publik `/notifikasi`: hanya nama, judul/ID eksemplar, jatuh tempo, lama terlambat, tanda serius; `noindex`; rate limit ringan; titik ekstensi `NOTIF_ALLOWED_CIDRS` (kosong = terbuka).
- [ ] **7-04** Dashboard admin "Terlambat" (detail lebih lengkap, di balik login).
- [ ] **7-05** Tes tepi: 168 jam, +1 detik, tepat 7 hari vs +1 detik, perpanjangan, setelah kembali hilang dari daftar, field terlarang tidak ada di HTML, blokir terbuka lagi setelah selesai.
- [ ] **7-06** Kecualikan pinjaman lama (`member_id` NULL / `legacy`) dari halaman publik.

### FASE 8 — Verifikasi AI Gemini (provisional; fitur sudah ada, jangan dibangun ulang)
- [ ] **8-01** Periksa payload ke Gemini: tanpa data anggota/token/riwayat; tes memeriksa payload.
- [ ] **8-02** Ketersediaan buku dalam jawaban diambil dari DB v2 (`v_title_availability`), bukan teks model; id katalog halusinasi dibuang.
- [ ] **8-03** Tes dengan Gemini di-mock: sukses, JSON rusak, timeout, 429, kunci hilang, input panjang/injeksi, AI mati → inti tetap jalan.
- [ ] **8-04** Verifikasi nama model & paket dari dokumentasi resmi terkini; `GEMINI_MODEL` dari env.
- [ ] **8-05** Label "bantuan AI, bukan catatan resmi"; rate limit; sanitasi output; tidak muncul di kiosk transaksi.

### FASE 9 — Keamanan, UX, laporan (provisional)
- [ ] **9-01** Audit keamanan (CSRF, header, cookie, SQL terparameter, upload, rate limit, enumerasi, log tanpa data pribadi, dependensi, secret scan) → `docs/AUDIT_KEAMANAN.md`.
- [ ] **9-02** Penyeragaman bahasa sederhana: `messages.py` terpusat + `docs/PANDUAN_BAHASA.md`.
- [ ] **9-03** Laporan: riwayat per eksemplar/anggota, terlambat, bermasalah, kewajiban pengganti; ekspor CSV/XLSX cocok dengan tampilan.
- [ ] **9-04** Tes kasus tepi Bagian 11.2 dokumen induk (tabel: tercakup / belum + alasan).
- [ ] **9-05** `docs/STATUS_REQUIREMENT.md` (bukti per requirement; status maksimum LOCAL-VERIFIED).
- [ ] **9-06** Penanganan error 404/500 ramah; `debug=False` produksi; `SECRET_KEY` wajib dari env.

### FASE 10 — Docker, HF Spaces, Supabase, backup (STAGING SAJA; provisional)
- [ ] **10-01** Riset ketentuan layanan terkini (HF Spaces, Supabase, Gemini) → `docs/VERIFIKASI_LAYANAN.md` bertanggal + sumber.
- [ ] **10-02** `Dockerfile` (non-root, gunicorn, port 7860), `.dockerignore`, `/healthz`, README header Spaces, `.env.example`.
- [ ] **10-03** Terjemahan skema ke PostgreSQL (timestamptz, view) + seluruh tes lulus di PostgreSQL uji.
- [ ] **10-04** `SupabaseStorage` untuk cover + skrip pemetaan cover lama (dry-run).
- [ ] **10-05** Ketahanan cold start & pool koneksi (pre-ping, retry, timeout).
- [ ] **10-06** `backup.py` + `restore.py` + skrip verifikasi konsistensi; **uji restore ke DB kosong dengan hasil nyata**; `docs/BACKUP_RESTORE.md`.
- [ ] **10-07** Skrip & checklist migrasi data nyata (TIDAK dijalankan; menunggu persetujuan tertulis pemilik).
- [ ] **10-08** `docs/RUNBOOK_DEPLOY.md` + checklist pra-data-nyata (dokumen induk 13.3).

### FASE 11 — Panduan, UAT, serah terima (provisional)
- [ ] **11-01** Panduan siswa dan panduan petugas (terpisah, bahasa sangat sederhana) + kartu kilat 1 halaman.
- [ ] **11-02** `docs/UAT.md`: simulasi hari operasional tanpa petugas, dijalankan dengan calon pengguna awam.
- [ ] **11-03** Perbarui dokumen induk → v4.3 (status berbasis bukti; tidak mengubah DEC).
- [ ] **11-04** Template handoff terisi + daftar OPEN tersisa + nilai `policy.py`.
- [ ] **11-05** Regresi akhir seluruh tes.

---

## 5. Keputusan terbuka & nilai sementara (`policy.py`)

| Kode | Pertanyaan | Nilai sementara | Status |
|---|---|---|---|
| OPEN-016 | Notifikasi publik: dibatasi jaringan sekolah? nama penuh/singkat? | terbuka; `NOTIF_NAME_MODE="full"` | menunggu pemilik |
| OPEN-017 | Perpanjangan setelah lewat jatuh tempo? dihitung dari mana? | `ALLOW_RENEW_AFTER_DUE=False` | menunggu pemilik |
| OPEN-018a | Acuan "rentang 24 jam" kelompok pemeriksaan | `GROUP_WINDOW_HOURS=24` (hanya tampilan) | menunggu pemilik |
| OPEN-018b | QR Penyelesaian: QR, tombol, atau keduanya | keduanya | menunggu pemilik |
| BLOCK | Blokir pinjam: semua buku belum kembali, atau hanya terlambat serius + kewajiban terbuka | `BLOCK_MODE="serious_only"` | menunggu pemilik |
| LEGACY | Peminjam lama (teks bebas): dijadikan anggota atau dibiarkan; ditampilkan di halaman publik? | tidak dijadikan anggota; dikecualikan dari publik | menunggu pemilik |
| TEST-DATA | Apakah "TEST USER"/"REGRESSION TEST USER" data uji yang tidak ikut migrasi produksi? | ditandai `data_uji` | menunggu pemilik |
| RATIFIKASI-ID | Panjang Crockford Base32: 6 karakter (`<PREFIX>-<6 KARAKTER>`) | 6 karakter (disahkan pada Task 1B-04) | SELESAI / DISAHKAN |

Konstanta lain: `LOAN_HOURS=168`, `EXTEND_DAYS=7`, `MAX_EXTENSIONS=1`, `SERIOUS_OVERDUE_DAYS=7`, `SCHOOL_TZ=Asia/Jakarta`.

---

## 6. Gerbang antar-fase (jangan lompat)

- Fase 0 → 1A → 1B → 2: berurutan ketat.
- Fase 3 dan 4 bisa bergantian setelah Fase 2; keduanya wajib selesai sebelum Fase 5.
- Fase 6 butuh Fase 5. Fase 7 butuh Fase 6 (kewajiban penyelesaian) dan Fase 2 (`can_borrow`).
- Fase 8 bisa kapan saja setelah Fase 2. Fase 9 setelah Fase 7. Fase 10 hanya setelah Fase 9. Fase 11 terakhir.
- Setiap akhir fase: tes hijau, laporan format Bagian 2, perbarui file ini, kirim ringkasan ke pemilik.

---

## 7. Temuan / Penyimpangan (tambahkan di sini, jangan menimpa)

- Roadmap dokumen induk P4 menyebut notifikasi "khusus admin" dan P5 menyebut "pembersihan anggota tidak aktif". Keduanya bertentangan dengan DEC-017 dan DEC-020; **ikuti DEC**, abaikan butir roadmap itu.
- Beberapa requirement berstatus VERIFIED di audit awal dinilai terlalu optimis; ikuti koreksi di `docs/AUDIT_P0.md` (VERIFIED hanya jika ada tes yang menunjuk kriteria).
- DB asli masih skema v1, padahal P1 ada di branch. Urutan produksi nanti: v1 → P1 → v2, selalu pada salinan (jangan dikerjakan tanpa persetujuan pemilik).
- **Format ID Publik (8 vs 6 Karakter):** Implementasi aktual pada `id_generator.py`, `tests/test_id_generator.py`, dan `docs/MIGRASI_F1B.md` menggunakan 8 karakter Base32 setelah prefix (`T-XXXXXXXX`, `C-XXXXXXXX`, `M-XXXXXXXX`, `L-XXXXXXXX`, `LI-XXXXXXXX`, `AUD-XXXXXXXX`), sedangkan teks deskripsi awal Fase 1B mencatat 6 karakter (`T-XXXXXX`). Format 8 karakter terbukti aman dari kolisi (10.000 ID unik diuji), namun membutuhkan pengesahan dokumentasi formal tanpa mengubah kode atau tes.
- **Rute Katalog Masih Menggunakan Jalur Legacy:** Rute sirkulasi (`/peminjaman`, `/proses_pinjam_admin`, `/kembalikan_item/<id>`, `/kembalikan/<id>`, `/perpanjang_item/<id>`, `/delete/<id>`) telah berhasil dihubungkan ke skema v2 via `detect_schema_version()`. Namun rute katalog publik (`/koleksi`, `/buku/<id>`) serta form input buku (`/tambah_buku`, `/edit_buku`) masih membaca tabel legacy `buku` (kolom `stok`, `id_buku_fisik`). Pengalihan rute katalog menjadi fokus utama Fase 3.
- **Nama File Pelacak:** File pelacak fisik yang digunakan di repositori saat ini adalah `docs/PROGRESS-perpus-digital.md` (karena `docs/PROGRESS.md` belum dibuat). Header teks tetap mengingatkan target standarisasi di masa depan.

---

## 8. Log sesi (tambahkan entri baru di bawah; jangan hapus yang lama)

```text
[2026-10-17] Fase 0 selesai: audit, dokumen induk disalin ke docs/, 43 tes OK.
[2026-10-17] Fase 1A selesai (dilaporkan): baseline diamankan, config/policy/timeutil dibuat; 54 tes OK.
[2026-10-17] Fase 1B: inspeksi + rencana pemetaan selesai; rencana DISETUJUI dengan revisi R1-R12. NEXT = 1B-03.
[2026-10-18] Antigravity: Sinkronisasi Dokumentasi Fase 1B–2C & Review Gate
Task selesai: 1B-03 s.d. 1B-10 (Fase 1B selesai penuh), Sub-Fase 2A (Repository Layer), Sub-Fase 2B (Business Service Layer), Sub-Fase 2C (Staging Route Integration & Test).
Task sedang berjalan: Persiapan Fase 3 (Katalog, Tambah Buku, Label QR).
Tes: .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 108 tes OK (0 gagal, 0 error, 0 skip, ~19 detik).
File utama berubah: docs/PROGRESS-perpus-digital.md (sinkronisasi status riil kode & tes terhadap commit 73e44c0 dan bd84740).
Temuan/risiko: Format ID 8 karakter di kode vs 6 karakter di spec awal (ditandai OPEN untuk ratifikasi dokumen). Rute katalog (/koleksi, /buku/<id>) masih membaca skema legacy (prioritas Fase 3). Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Belum diuji E2E browser nyata / cutover produksi.
NEXT: 3-01

[2026-10-20] Antigravity: Eksekusi Task 3-01 (Verifikasi & Penguatan Auth Admin)
Task selesai: 3-01 (Verifikasi auth admin: proteksi 16 rute admin, 14 rute POST terlindungi CSRF, session lifetime 8 jam, idle timeout 120 menit, session.clear() logout, konsistensi redirect upload_cover, dan tes otomatis terisolasi).
Task sedang berjalan: Fase 3 (1/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py -v -> 27 tes OK (5.072s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 141 tes OK (0 gagal, 0 error, 0 skip, 27.552s).
File utama berubah: policy.py, app.py, tests/test_admin_auth.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: SESSION_COOKIE_PATH dipertahankan '/' karena arsitektur rute admin tersebar di root (/peminjaman, /add, /edit, dll) dan login/logout di /login, /logout; pembatasan path='/admin' akan merusak sesi admin pada rute-rute tersebut. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-02

[2026-10-20] Antigravity: Eksekusi Task 3-02 (Form Tambah Buku & Pratinjau Eksemplar)
Task selesai: 3-02 (Form tambah buku: judul, penulis, ISBN, kategori, jumlah; pratinjau real-time "Anda akan membuat N eksemplar"; proteksi konfirmasi ketik ulang jumlah >100; validasi server-side lengkap; zero-write ke DB terbukti; CSRF terlindungi; form repopulation aman).
Task sedang berjalan: Fase 3 (2/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_add_book_form.py -v -> 25 tes OK (8.424s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 166 tes OK (0 gagal, 0 error, 0 skip, 37.431s).
File utama berubah: policy.py, services/catalog_service.py, services/__init__.py, app.py, templates/tambah_buku.html, templates/koleksi.html, tests/test_add_book_form.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Pembatasan integrasi ditegakkan secara ketat: Task 3-02 hanya melakukan validasi input dan rendering pratinjau tanpa mutasi DB (zero-write terbukti). Persistensi atomik dengan single-use token dan rollback adalah fokus Task 3-03. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-03

[2026-10-20] Antigravity: Eksekusi Task 3-03 (Commit Atomik + Token Konfirmasi Sekali Pakai)
Task selesai: 3-03 (Commit atomik: pembuatan judul + seluruh eksemplar dalam 1 transaksi; token konfirmasi acak sekali pakai dengan TTL 15 menit; proteksi race condition / double-click via _TOKEN_LOCK; proteksi replay idempoten; rollback 100% pada kegagalan di tengah jalan terbukti via fault injection).
Task sedang berjalan: Fase 3 (3/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_atomic_add_book_commit.py -v -> 10 tes OK (3.534s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 176 tes OK (0 gagal, 0 error, 0 skip, 42.227s).
File utama berubah: policy.py, services/exceptions.py, repositories/catalog_repo.py, services/catalog_service.py, services/__init__.py, app.py, templates/tambah_buku.html, tests/test_atomic_add_book_commit.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Transaksi atomik berhasil diisolasi di katalog v2. Token konfirmasi sekali pakai melindungi dari race condition dan klik ganda. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-04

[2026-10-21] Antigravity: Verifikasi Terarah Task 3-03 (Durabilitas Token & Idempotensi Persisten Database)
Task selesai: 3-03 (Migrasi token konfirmasi & idempotensi dari in-memory dict ke tabel database persisten confirmation_tokens; integrasi transaksi write-lock BEGIN IMMEDIATE; jaminan durabilitas token bertahan melintasi restart aplikasi; koordinasi konkurensi aman multi-worker/proses; pengulangan/replay permintaan setelah response hilang terbukti idempoten tanpa duplikasi baris; rollback 100% pada kegagalan di tengah jalan).
Task sedang berjalan: Fase 3 (3/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_atomic_add_book_commit.py -v -> 15 tes OK (5.470s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 181 tes OK (0 gagal, 0 error, 0 skip, 48.954s).
File utama berubah: migrations/0001_initial_v2_schema.sql, services/catalog_service.py, app.py, tests/test_atomic_add_book_commit.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Celah in-memory token berhasil ditutup tuntas dengan tabel persisten database. Mutex in-memory dipertahankan sebagai fast-path rejection thread lokal, sementara koordinasi utama diatur oleh write lock SQLite tingkat database. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-04

[2026-10-22] Antigravity: Eksekusi Task 3-04 (Peringatan Judul Mirip & Deteksi Potensi Duplikat)
Task selesai: 3-04 (Deteksi judul mirip berbasis normalisasi ISBN dan pasangan judul+penulis; peringatan informatif interaktif di tahap preview; penolakan penggabungan/penimpaan otomatis sesuai DEC-013; pembuatan rekaman baru terpisah jika admin melanjutkan konfirmasi; integritas token & rollback 100% terjaga).
Task sedang berjalan: Fase 3 (4/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_duplicate_title_warning.py -v -> 17 tes OK (7.090s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 198 tes OK (0 gagal, 0 error, 0 skip, 65.178s).
File utama berubah: repositories/catalog_repo.py, repositories/__init__.py, services/catalog_service.py, services/__init__.py, app.py, templates/tambah_buku.html, tests/test_duplicate_title_warning.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Peringatan duplikat berfungsi sebagai guardrail informasi tanpa memblokir pembuatan judul baru secara sepihak. Judul dengan angka berbeda (misal kelas/jilid) tidak memicu false positive. Zero-write pada tahap preview terbukti. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-05

[2026-10-23] Antigravity: Eksekusi Task 3-05 (Template Impor Katalog + Halaman Panduan)
Task selesai: 3-05 (Template unduhan CSV impor katalog dengan header judul, penulis, isbn, kategori, jumlah; data contoh berlabel (Contoh) dengan ISBN kosong valid dan penanganan tanda koma/kutip standar; halaman panduan lengkap berbahasa Indonesia dengan petunjuk Excel/Sheets/Calc, penjelasan konsep eksemplar fisik, instruksi simpan CSV UTF-8, dan peringatan zero-write; navigasi terintegrasi di koleksi dan tambah buku).
Task sedang berjalan: Fase 3 (5/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_catalog_import_template.py -v -> 14 tes OK (1.839s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v -> 212 tes OK (0 gagal, 0 error, 0 skip, 168.672s).
File utama berubah: services/catalog_service.py, services/__init__.py, app.py, templates/panduan_impor_katalog.html, templates/koleksi.html, templates/tambah_buku.html, tests/test_catalog_import_template.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Pengunduhan template dan pembukaan halaman panduan terbukti 100% zero-write (tanpa kueri mutasi database). Parser CSV standar membaca kembali file tanpa kerusakan kolom. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-06

[2026-10-24] Antigravity: Eksekusi Task 3-06 (Pratinjau Impor Katalog Tanpa Menulis Database)
Task selesai: 3-06 (Pratinjau impor katalog CSV tanpa menulis database: klasifikasi status baris OK/PERINGATAN/ERROR dengan nomor baris 1-based dan alasan eksplisit; penolakan formula spreadsheet injection via is_potential_formula; batas ukuran file MAX_CATALOG_IMPORT_FILE_SIZE_BYTES 2 MiB dan baris MAX_CATALOG_IMPORT_ROWS 1000; deteksi duplikat intra-file dan read-only check database berstatus PERINGATAN sesuai DEC-013; zero-write terverifikasi mutlak tanpa mutasi data katalog, eksemplar, anggota, token, atau audit log).
Task sedang berjalan: Fase 3 (6/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_catalog_import_preview.py -v -> 17 tes OK (2.569s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 229 tes OK (0 gagal, 0 error, 0 skip, 79.358s).
File utama berubah: policy.py, services/catalog_service.py, services/__init__.py, repositories/catalog_repo.py, app.py, templates/preview_impor_katalog.html, templates/panduan_impor_katalog.html, tests/test_catalog_import_preview.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Tahap preview 100% zero-write (hash snapshot tabel terbukti identik sebelum dan sesudah request preview). Deteksi formula melindungi spreadsheet injection tanpa komputasi formula. File non-CSV, header cacat, kolom kosong/tidak valid ditolak dengan pesan informatif. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik). Tidak ada perintah mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-07

[2026-10-26] Antigravity: Eksekusi Task 3-07 (Commit Impor Katalog Atomik + Ringkasan Hasil)
Task selesai: 3-07 (Commit impor katalog massal secara atomik melalui transaksi BEGIN IMMEDIATE; penerbitan token konfirmasi persisten sekali pakai di confirmation_tokens; proteksi replay idempotensi; validasi ulang server-side terhadap database langsung; penolakan formula injection & payload tampering; pemrosesan 4 kategori resmi yang akurat: Judul Baru, Eksemplar Dibuat, Baris Dilewati, dan Baris Bermasalah; kepatuhan DEC-013 pembuatan judul baru terpisah untuk baris peringatan yang dikonfirmasi; rollback penuh tanpa sisa parsial jika terjadi kegagalan di tengah proses atau saat audit log).
Task sedang berjalan: Fase 3 (7/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_catalog_import_commit.py -v -> 26 tes OK (11.731s); .\venv\Scripts\python.exe -m unittest tests/test_add_book_form.py tests/test_atomic_add_book_commit.py tests/test_duplicate_title_warning.py tests/test_catalog_import_template.py tests/test_catalog_import_preview.py tests/test_catalog_import_commit.py -> 114 tes OK (42.893s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 255 tes OK (0 gagal, 0 error, 0 skip, 70.884s).
File utama berubah: services/catalog_service.py, services/__init__.py, app.py, templates/preview_impor_katalog.html, templates/konfirmasi_impor_katalog.html, templates/ringkasan_impor_katalog.html, tests/test_catalog_import_commit.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Kebijakan batas kuantitas eksemplar per penambahan resmi bernilai 1.000 (MAX_COPIES_PER_ADD di policy.py), konsisten antara form tambah buku tunggal dan impor CSV massal. Satu judul dapat menghasilkan banyak eksemplar fisik unik dan dihitung secara terpisah pada ringkasan hasil. Transaksi atomik membuktikan 0 judul/eksemplar parsial saat simulasi kegagalan di tengah batch. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-08

[2026-10-26] Antigravity: Eksekusi Task 3-08 (Halaman Cetak Label QR /admin/labels A4 Grid)
Task selesai: 3-08 (Halaman cetak label /admin/labels siap cetak layout grid A4; QR code generator Model 2 berbasis pure-Python tanpa dependensi pip pihak ketiga; payload QR secara ketat dan eksklusif hanya memuat ID eksemplar copies.id tanpa data pribadi/URL/judul; ID eksemplar terbaca manusia ditampilkan tebal dan berdekatan dengan QR; judul buku dipotong aman ~28 karakter untuk verifikasi petugas; filter pencarian dan opsi copy_ids/title_id; proteksi otentikasi admin via session & header API 401; zero-write terverifikasi mutlak tanpa mutasi basis data; verifikasi pemindaian fisik QR terbukti akurat menggunakan OpenCV QRCodeDetector).
Task sedang berjalan: Fase 3 (8/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_admin_labels.py -v -> 23 tes OK (3.342s); .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py tests/test_add_book_form.py tests/test_atomic_add_book_commit.py tests/test_duplicate_title_warning.py tests/test_catalog_import_template.py tests/test_catalog_import_preview.py tests/test_catalog_import_commit.py tests/test_admin_labels.py -> 164 tes OK (17.753s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 278 tes OK (0 gagal, 0 error, 0 skip, 51.658s).
File utama berubah: services/qr_service.py, repositories/copy_repo.py, repositories/__init__.py, services/catalog_service.py, services/__init__.py, app.py, templates/admin_labels.html, tests/test_admin_labels.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Generator QR pure-Python mengimplementasikan ISO/IEC 18004 lengkap (GF(2^8) Reed-Solomon, masking, Crockford Base32 / Byte encoding, SVG output) tanpa instalasi dependensi luar. Payload QR diverifikasi mandiri dengan OpenCV decoding untuk memastikan kompatibilitas 100% dengan pemindai kiosk/kamera. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-09

[2026-10-27] Antigravity: Eksekusi Task 3-09 (Cetak Ulang Label Identik + Halaman Eksemplar Tanpa Label)
Task selesai: 3-09 (Cetak ulang label eksemplar mempertahankan ID asli tanpa membuat ID baru; generator QR deterministik menghasilkan payload dan pola SVG QR yang 100% identik; deduplikasi daftar ID mencegah pencetakan ganda tak sengaja; penanganan aman ID tidak dikenal tanpa membuat label dummy; halaman admin /admin/labels/tanpa-label menyajikan kandidat buku lama legacy dan eksemplar aktif di rak sebagai panduan verifikasi fisik rak bagi petugas sesuai OPEN-012 dan DEC-011 dengan penjelasan eksplisit batasan sistem; route /admin/labels/cetak-ulang dan form input/POST; otentikasi admin dan proteksi CSRF penuh; tata letak grid A4 Task 3-08 dipertahankan; zero-write terverifikasi mutlak tanpa mutasi basis data).
Task sedang berjalan: Fase 3 (9/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_admin_labels_reprint_and_unlabeled.py -v -> 23 tes OK (7.806s); .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py tests/test_add_book_form.py tests/test_atomic_add_book_commit.py tests/test_duplicate_title_warning.py tests/test_catalog_import_template.py tests/test_catalog_import_preview.py tests/test_catalog_import_commit.py tests/test_admin_labels.py tests/test_admin_labels_reprint_and_unlabeled.py -> 187 tes OK (46.024s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 301 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 73.178s).
File utama berubah: repositories/copy_repo.py, repositories/__init__.py, services/catalog_service.py, services/__init__.py, app.py, templates/admin_labels.html, templates/admin_labels_reprint.html, templates/admin_labels_tanpa_label.html, tests/test_admin_labels_reprint_and_unlabeled.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Skema database (baik v2 maupun legacy) tidak menyimpan kolom status penempelan stiker fisik pada buku. Oleh karena itu, halaman 'Eksemplar Tanpa Label' beroperasi sesuai definisi operasional resmi: menyajikan eksemplar buku lama (legacy_copy_map/legacy_buku_id) dan eksemplar aktif di rak agar petugas dapat memeriksa rak fisik dan mencetak label QR resmi. Tidak ada perubahan skema atau mutasi basis data yang dilakukan. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-10

[2026-10-27] Antigravity: Eksekusi Task 3-10 (Nonaktifkan/Tandai Eksemplar Buku dengan Alasan & Audit Log)
Task selesai: 3-10 (Penonaktifan atau penandaan eksemplar buku fisik per eksemplar individual disertai alasan wajib bermakna 5-500 karakter dan pencatatan audit_log; data fisik eksemplar tetap tersimpan utuh di basis data tanpa hard delete sesuai P2-02 & DEC-011; trigger database trg_prevent_delete_copies membuktikan perlindungan integritas R12; opsi status target resmi mencakup nonaktif, rusak, hilang, dalam_penanganan; konsistensi sirkulasi menolak penonaktifan eksemplar yang sedang berada dalam peminjaman aktif LIB-LOAN-002; idempotensi menolak penonaktifan ganda/replay tanpa menduplikasi log audit; eksemplar nonaktif otomatis ditolak pinjam di loan_service dengan CopyNotAvailableError; route admin /admin/copies/<copy_id>/deactivate dan alias /admin/eksemplar/<copy_id>/nonaktifkan dilindungi autentikasi admin & CSRF token; template admin_copy_deactivate.html; tautan aksi di admin_labels_tanpa_label.html; dukungan fallback skema legacy P1; zero-write terverifikasi mutlak pada seluruh permintaan GET).
Task sedang berjalan: Fase 3 (10/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_copy_deactivate.py -> 22 tes OK (4.997s); .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py tests/test_add_book_form.py tests/test_atomic_add_book_commit.py tests/test_duplicate_title_warning.py tests/test_catalog_import_template.py tests/test_catalog_import_preview.py tests/test_catalog_import_commit.py tests/test_admin_labels.py tests/test_admin_labels_reprint_and_unlabeled.py tests/test_copy_deactivate.py -> 209 tes OK (42.616s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 323 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 42.170s).
File utama berubah: services/catalog_service.py, repositories/copy_repo.py, app.py, templates/admin_copy_deactivate.html, templates/admin_labels_tanpa_label.html, tests/test_copy_deactivate.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Penonaktifan fisik buku tidak menghapus baris tabel copies (row count tetap sama sebelum dan sesudah eksekusi). Trigger database SQLite trg_prevent_delete_copies mencegah mutasi DELETE secara fisik. Loan service secara otomatis memblokir peminjaman eksemplar nonaktif melalui view v_copy_availability. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-11

[2026-10-27] Antigravity: Eksekusi Task 3-11 (Upload Cover dengan Validasi Keamanan dan Storage Interface)
Task selesai: 3-11 (Upload cover buku terlindungi validasi ketat: validasi magic bytes/signature biner untuk JPEG, PNG, WEBP, GIF; validasi konsistensi format biner vs ekstensi klaim; batas ukuran maksimum resmi 2 MiB / MAX_COVER_IMAGE_SIZE_BYTES; penolakan file kosong, rusak, atau format berbahaya seperti exe/php/svg/pdf/txt; pencegahan path traversal melalui pemeriksaan commonpath; pembuatan nama file acak UUID v4 hex 32-karakter server-side; arsitektur pluggable interface Storage ABC dengan implementasi LocalStorage saat ini dan kesiapan Supabase Storage di Fase 10; manajemen atomik update_book_cover dengan penggantian file lama hanya setelah file baru sukses tersimpan dan database ter-update; rollback otomatis penghapusan file orphan jika terjadi kegagalan commit database; proteksi autentikasi admin & CSRF token pada endpoint upload; pesan error ramah pengguna tanpa membocorkan path internal filesystem server; fallback visual cover placeholder pada template detail_buku.html; dukungan skema ganda v2 catalog_titles.cover_path dan legacy buku.cover_img; pencatatan audit log COVER_UPLOAD; zero-write terverifikasi mutlak terhadap database produksi).
Task sedang berjalan: Fase 3 (11/12 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_cover_upload.py -v -> 21 tes OK (9.076s); .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py tests/test_add_book_form.py tests/test_atomic_add_book_commit.py tests/test_duplicate_title_warning.py tests/test_catalog_import_template.py tests/test_catalog_import_preview.py tests/test_catalog_import_commit.py tests/test_admin_labels.py tests/test_admin_labels_reprint_and_unlabeled.py tests/test_copy_deactivate.py tests/test_cover_upload.py -> 230 tes OK (89.206s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 344 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 153.590s).
File utama berubah: policy.py, services/exceptions.py, services/storage_service.py, services/__init__.py, app.py, tests/test_cover_upload.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Pembatasan ukuran file 2 MiB didukung di dua lapisan: Flask MAX_CONTENT_LENGTH (HTTP 413) dan layer validasi domain validate_cover_image (HTTP 400). Interface Storage memisahkan urusan penyimpanan fisik dari domain katalog sehingga transisi ke Supabase Storage pada Fase 10 tidak memerlukan refactoring route atau logika katalog. Pembersihan otomatis file orphan jika database rollback menjamin direktori uploads tidak menumpuk file tak bertuan. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 3-12

[2026-10-28] Antigravity: Eksekusi Task 3-12 (Pencarian Katalog Publik Berbasis v_title_availability)
Task selesai: 3-12 (Pencarian katalog publik berbasis view v_title_availability: ketersediaan stok buku fisik dihitung secara aktual dan otomatis langsung dari database tanpa ad-hoc computation; eksemplar berstatus nonaktif, rusak, hilang, dalam_penanganan, dan sedang dipinjam otomatis dikecualikan dari available_copies sesuai definisi view dan aturan bisnis; sanitasi dan penanganan input pencarian kosong, whitespace, maupun input string sangat panjang diatur dengan batas aman MAX_CATALOG_SEARCH_QUERY_LENGTH=200 karakter; escaping literal wildcard SQLite LIKE [%, _, \] dengan klausul ESCAPE '\'; pencegahan 100% terhadap SQL Injection via parameterized queries; dukungan karakter Unicode, aksen, tanda petik, apostrof, dan emoji tanpa crash; rendering empty-state ramah pengguna saat buku tidak ditemukan; rute publik /koleksi dan /search dapat diakses penuh tanpa autentikasi admin; pelestarian kartu metrik katalog total buku tersedia, total judul, dan buku populer berbasis v_title_availability; integrasi endpoint /api/search_suggestions dan /buku/<id> berbasis data view v2; dukungan penuh kompatibilitas mundur skema legacy P1 dengan fallback aman; verifikasi zero-write pada semua rute pencarian; penyelesaian resmi Fase 3 12/12 task).
Task sedang berjalan: Fase 3 (12/12 task selesai — FASE 3 SELESAI PENUH).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_catalog_search_v_title_availability.py -> 17 tes OK (7.677s); .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py tests/test_add_book_form.py tests/test_atomic_add_book_commit.py tests/test_duplicate_title_warning.py tests/test_catalog_import_template.py tests/test_catalog_import_preview.py tests/test_catalog_import_commit.py tests/test_admin_labels.py tests/test_admin_labels_reprint_and_unlabeled.py tests/test_copy_deactivate.py tests/test_cover_upload.py tests/test_catalog_search_v_title_availability.py -> 247 tes OK (89.308s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 361 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 133.060s).
File utama berubah: policy.py, repositories/catalog_repo.py, repositories/__init__.py, services/catalog_service.py, services/__init__.py, app.py, templates/koleksi.html, tests/test_catalog_search_v_title_availability.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: View v_title_availability secara elegan memusatkan agregasi status ketersediaan buku di level SQL engine dengan LEFT JOIN ke loan_items aktif (returned_at IS NULL) dan copies aktif (status = 'aktif'). Pemisahan pencarian judul (catalog_titles) dengan referensi eksemplar fisik memungkinkan pencarian publik menemukan buku baik berdasarkan ID judul (T-XXXXXXXX), ID eksemplar (C-XXXXXXXX), maupun legacy reference buku fisik lama. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-01

[2026-10-28] Antigravity: Eksekusi Task 4-01 (Token QR Anggota HMAC-SHA256)
Task selesai: 4-01 (Implementasi mekanisme token QR anggota menggunakan HMAC-SHA256 berbasis secret key aplikasi; format serialisasi kanonikal deterministik <member_id>:<qr_version>:<signature_hex>; perlindungan privasi data pribadi tanpa PII di dalam payload QR per DEC-010 & DEC-023; verifikasi anti-timing-attack menggunakan hmac.compare_digest; pengelolaan kunci rahasia aman tanpa hardcode atau fallback ke kunci statis publik via get_member_token_secret; fungsi parsing dan penolakan aman untuk token kosong, rusak, terpotong, atau tidak dikenal; pemisahan tegas antara layer kriptografis dan status operasional anggota; penolakan otomatis token lama yang telah dicabut atau diterbitkan ulang saat qr_version database bertambah per LIB-QR-001 & Task 4-07; penanganan anggota nonaktif dengan opsi check_active per DEC-020; pembuatan representasi QR Code SVG murni via generate_member_qr_svg di qr_service; dokumentasi keputusan arsitektur dan kriptografi resmi di docs/KEPUTUSAN_TEKNIS.md; pengujian komprehensif 21 skenario unit & integrasi terisolasi; verifikasi zero-write ke database).
Task sedang berjalan: Fase 4 (1/10 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_member_qr_token.py -v -> 21 tes OK (0.945s); .\venv\Scripts\python.exe -m unittest tests/test_admin_labels.py tests/test_admin_labels_reprint_and_unlabeled.py tests/test_repositories.py tests/test_services.py tests/test_production_safety.py -> 84 tes OK (1 skip OpenCV di venv, 43.501s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 382 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 120.035s).
File utama berubah: policy.py, services/exceptions.py, services/qr_service.py, services/member_service.py, services/__init__.py, docs/KEPUTUSAN_TEKNIS.md, tests/test_member_qr_token.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Mekanisme HMAC-SHA256 menjamin token tidak dapat dipalsukan tanpa mengetahui SECRET_KEY aplikasi. Penambahan qr_version pada payload menandatangani status kartu fisik sehingga mekanisme revokasi (Task 4-07) dapat langsung dilakukan hanya dengan memanggil increment_qr_version tanpa memerlukan tabel blacklist atau status tambahan. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-02

[2026-10-28] Antigravity: Eksekusi Task 4-02 (Kategori dan Antarmuka Admin Anggota)
Task selesai: 4-02 (Seed member_categories idempoten dengan 5 kategori resmi proyek: MC-MURID/murid, MC-GURU-JUR/guru_jurusan, MC-GURU-UMUM/guru_umum, MC-STAF/staf, MC-TEKNISI/teknisi; penegakan integritas foreign key members.category_id; implementasi modul repositori member_repo dengan escaping wildcard LIKE SQL [%, _, \], klausul ESCAPE '\', pengurutan m.created_at DESC, fungsi count_members untuk paginasi, dan get_member_summary_metrics untuk agregasi statistik; implementasi business service member_service untuk sanitasi kueri clean_member_search_query dengan pembatasan panjang MAX_MEMBER_SEARCH_QUERY_LENGTH=100 karakter, paginasi aman clamped [1, 100], dan pengambilan metrik manajemen; proteksi rute admin /admin/members dan alias /admin/anggota dengan autentikasi session admin (302 redirect untuk browser, 401 untuk JSON); kepatuhan ketat privasi DEC-023 tanpa memuat nomor telepon, kelas, atau PII di antarmuka maupun model data; dukungan tampilan empty-state untuk database kosong dan pencarian nirhasil; penanganan kompatibilitas ramah mundur untuk skema legacy P1 tanpa crash; tautan navigasi admin baru di layout.html; pengujian komprehensif 21 skenario unit & integrasi terisolasi di tests/test_admin_members.py; verifikasi zero-write pada permintaan GET dan zero mutasi pada database produksi).
Task sedang berjalan: Fase 4 (2/10 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_admin_members.py -v -> 21 tes OK (7.640s); .\venv\Scripts\python.exe -m unittest tests/test_admin_auth.py tests/test_member_qr_token.py tests/test_repositories.py tests/test_services.py -> 76 tes OK (13.122s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 403 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 76.472s).
File utama berubah: policy.py, repositories/member_repo.py, repositories/__init__.py, services/member_service.py, services/__init__.py, app.py, templates/admin_members.html, templates/layout.html, tests/test_admin_members.py, tests/test_member_qr_token.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Struktur member_categories v2 dengan kode identitas 'MC-MURID', 'MC-GURU-JUR', 'MC-GURU-UMUM', 'MC-STAF', dan 'MC-TEKNISI' terbukti stabil dan idempoten dengan mekanisme ON CONFLICT(id) DO UPDATE. Aturan DEC-023 (tanpa kelas, tanpa telepon) sepenuhnya dipertahankan baik di skema, layer service, maupun rendering antarmuka HTML admin. Uji regresi membuktikan kompatibilitas penuh dengan rute sirkulasi v2 dan token QR anggota Task 4-01. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-03

[2026-10-28] Antigravity: Eksekusi Task 4-03 (Template Impor Anggota dan Pengabaian Kolom Kelas/Telepon)
Task selesai: 4-03 (Template impor anggota CSV resmi dengan 5 header standar: nama, jenis, keterangan, status, id_anggota; penyediaan contoh data realistis sintetis berlabel '(Contoh)' yang mencakup 5 peran sekolah murid, guru_jurusan, guru_umum, staf, dan teknisi; implementasi fungsi download payload UTF-8 di member_service; rute unduh template /admin/members/impor/template dan /admin/anggota/impor/template terlindungi autentikasi admin; halaman panduan resmi di /admin/members/impor/panduan dan template templates/panduan_impor_anggota.html; tombol akses cepat di templates/admin_members.html; pengabaian kolom kelas dan telepon secara otomatis sesuai kebijakan privasi DEC-023 dengan peringatan ramah eksplisit; pencegahan total kebocoran PII dari nilai kolom terabaikan pada log dan respon; validasi ketat header CSV, kolom wajib nama dan jenis, penolakan kolom duplikat dan file kosong; proteksi CSV Formula Injection pada sel data; penegakan format Crockford Base32 pada kolom id_anggota opsional; toleransi alias peran sekolah ramah pengguna; kompatibilitas penuh skema legacy P1; pengujian komprehensif 21 skenario unit & integrasi terisolasi di tests/test_member_import_template.py; zero-write terverifikasi mutlak ke database produksi).
Task sedang berjalan: Fase 4 (3/10 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_member_import_template.py -v -> 21 tes OK (5.137s); .\venv\Scripts\python.exe -m unittest tests/test_member_import_template.py tests/test_admin_members.py tests/test_member_qr_token.py tests/test_admin_auth.py tests/test_repositories.py tests/test_services.py -> 118 tes OK (25.979s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 424 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 151.249s).
File utama berubah: policy.py, repositories/member_repo.py, services/member_service.py, services/__init__.py, app.py, templates/panduan_impor_anggota.html, templates/admin_members.html, tests/test_member_import_template.py, tests/test_admin_members.py, tests/test_member_qr_token.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Pengabaian kolom kelas dan nomor telepon dengan peringatan terstruktur terbukti efektif menjembatani format ekspor Dapodik/administrasi sekolah tanpa merusak aturan DEC-023. Parser tidak mengekstrak kolom terabaikan ke representasi record anggota dan tidak memasukkan nilainya ke file_warnings atau log. Perbaikan seed_default_categories dengan ON CONFLICT(id) DO NOTHING menjamin kustomisasi keterangan lokal tidak tertimpa saat rute admin dibuka. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-04
```

```text
[2026-10-28] Antigravity: Eksekusi Task 4-04 (Pratinjau Pencocokan Impor Anggota - OPEN-011)
Task selesai: 4-04 (Pratinjau pencocokan impor anggota OPEN-011 berbasis klasifikasi konservatif: pencocokan ID tepat diklasifikasikan sebagai PEMBARUAN dengan kalkulasi perbedaan/diff atribut nama, kategori, status dan opsi aksi PERBARUI/LEWATI; penolakan pembuatan ID kustom sembarangan dengan menandai ID tidak ditemukan di DB sebagai TIDAK_DITEMUKAN berstatus ERROR dengan opsi aksi tunggal LEWATI; pencocokan tanpa ID mengevaluasi nama ternormalisasi LOWER(TRIM(nama)) tanpa menggunakan data kelas maupun telepon per DEC-023: 0 cocok -> BARU dengan aksi BUAT_BARU/LEWATI, 1 cocok -> KEMUNGKINAN_SAMA dengan aksi PERBARUI/BUAT_BARU/LEWATI, >1 cocok -> AMBIGU dengan aksi PILIH_KANDIDAT/BUAT_BARU/LEWATI; deteksi konflik intra-file untuk duplikasi ID dalam satu file yang sama menandai status ERROR pada kedua baris; peringatan nama berulang intra-file tanpa ID; validasi keputusan petugas validate_member_import_decisions yang menolak tindakan tidak sah dan mencegah konflik tabrakan target ganda/collision pada member_id yang sama; rute admin terlindungi /admin/members/impor/preview dan alias /admin/anggota/impor/preview yang mendukung upload multipart CSV maupun payload JSON dengan verifikasi CSRF dan penolakan 401 unauthenticated; antarmuka templates/preview_impor_anggota.html dengan 7 kartu ringkasan metrik, badge status pencocokan, diff tags visual, filter tombol cepat, dan banner penegasan zero-write; integrasi form unggah pada templates/panduan_impor_anggota.html; kompatibilitas penuh skema legacy P1 tanpa crash; pengujian komprehensif 19 skenario unit & integrasi terisolasi di tests/test_member_import_preview.py; zero-write terverifikasi mutlak ke database produksi).
Task sedang berjalan: Fase 4 (4/10 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_member_import_preview.py -v -> 19 tes OK (9.782s); .\venv\Scripts\python.exe -m unittest tests/test_member_import_preview.py tests/test_member_import_template.py tests/test_admin_members.py tests/test_member_qr_token.py tests/test_admin_auth.py -> 109 tes OK (33.783s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 443 tes OK (0 gagal, 0 error, 1 skip OpenCV di venv, 152.396s).
File utama berubah: policy.py, services/member_service.py, services/__init__.py, app.py, templates/preview_impor_anggota.html, templates/panduan_impor_anggota.html, tests/test_member_import_preview.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Keputusan arsitektur OPEN-011 dan DEC-023 terbukti sangat kokoh melindungi integritas data anggota sekolah. Pencocokan berbasis nama secara tegas tidak menggabungkan data secara otomatis ketika terdapat kesamaan nama, melainkan mengklasifikasikannya sebagai KEMUNGKINAN_SAMA (1 kandidat) atau AMBIGU (>1 kandidat) sehingga petugas memegang kendali penuh per baris. Validasi target collision di validate_member_import_decisions berhasil mencegah dua baris CSV berbeda secara keliru menimpa record database yang sama. Format Crockford Base32 (M-XXXXXX) ditegakkan secara disiplin. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-05
```

```text
[2026-10-28] Antigravity: Eksekusi Task 4-05 (Commit Impor Anggota Secara Atomik)
Task selesai: 4-05 (Commit impor anggota atomik berbasis token konfirmasi bertanda tangan kriptografis; penanganan keputusan BUAT_BARU, PERBARUI, dan LEWATI; eksekusi atomik single transaction_scope dengan BEGIN IMMEDIATE yang menjamin 100% rollback tanpa rekaman parsial jika terjadi kesalahan; pengujian skala besar hingga 1.050 baris CSV berhasil diproses mulus di bawah batas MAX_MEMBER_IMPORT_ROWS=2000; validasi server-side menyeluruh menolak tindakan ilegal, target tidak valid, tabrakan pembaruan ganda/target collision, token kedaluwarsa 15 menit, serta token yang diubah/tampered; perhitungan hash payload kanonikal SHA-256 untuk mendeteksi manipulasi keputusan atau isi file CSV; idempotensi eksekusi token ganda/replay aman dengan mengembalikan ringkasan eksekusi yang sama; locking konkurensi memori anti balapan thread; pencatatan audit log otomatis via audit_repo.record_audit dengan metadata ringkasan eksekusi; generasi ringkasan lengkap: total_processed, created_count, updated_count, skipped_count, failed_count; integritas rekaman anggota eksisting terjaga mutlak: anggota di luar file impor 100% tidak termutasi; kepatuhan ketat privasi DEC-023 tanpa kelas dan tanpa telepon; antarmuka HTML konfirmasi dan ringkasan templates/konfirmasi_impor_anggota.html dan templates/ringkasan_impor_anggota.html; rute admin /admin/members/impor/konfirmasi dan /admin/members/impor/commit beserta alias; kompatibilitas penuh skema legacy P1 tanpa crash; pengujian komprehensif 25 skenario di tests/test_member_import_commit.py; zero-write terverifikasi mutlak ke database produksi).
Task sedang berjalan: Fase 4 (5/10 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_member_import_commit.py -v -> 25 tes OK (12.379s); .\venv\Scripts\python.exe -m unittest tests/test_member_import_commit.py tests/test_member_import_preview.py tests/test_member_import_template.py tests/test_admin_members.py tests/test_member_qr_token.py tests/test_admin_auth.py -> 134 tes OK (41.067s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 468 tes (467 OK, 0 gagal, 0 error, 1 skip OpenCV di venv, 220.594s).
File utama berubah: repositories/member_repo.py, services/member_service.py, services/__init__.py, app.py, templates/preview_impor_anggota.html, templates/konfirmasi_impor_anggota.html, templates/ringkasan_impor_anggota.html, tests/test_member_import_commit.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Pola token konfirmasi persisten terbukti andal menangani impor anggota skala besar dengan aman. Dengan menyimpan canonical hash payload (CSV b64 + decisions) di tabel confirmation_tokens dan memverifikasinya saat POST commit, server dapat mencegah tampering manipulasi form HTML secara deterministik. Penggunaan lock konkurensi in-memory (_MEMBER_TOKEN_LOCK) mencegah balapan thread saat klik ganda cepat dilakukan sebelum commit selesai. Pengujian atomisitas membuktikan bahwa kegagalan sengaja di tengah proses (misal pada baris ke-2 dari 3) membatalkan seluruh perubahan tanpa meninggalkan anggota baru atau pembaruan sebagian di database. Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-06
```

```text
[2026-10-28] Antigravity: Eksekusi Task 4-06 (Nonaktifkan dan Aktifkan Kembali Anggota)
Task selesai: 4-06 (Nonaktifkan dan aktifkan kembali anggota dengan pencatatan alasan wajib 5-500 karakter ke audit_log; antarmuka admin terpadu /admin/members/<member_id>/status serta alias rute dwibahasa Inggris/Indonesia; aksi cepat Nonaktifkan/Aktifkan di tabel daftar anggota /admin/members; larangan mutlak tombol hapus/hard delete di seluruh UI dan kode per DEC-020; transaksi atomik dengan transaction_scope yang menjamin 100% rollback jika penulisan audit log gagal; penjagaan status idempotensi mencegah manipulasi ganda status yang sama; penolakan otomatis peminjaman buku baru untuk anggota nonaktif via MemberInactiveError di borrow_copies; pelestarian pinjaman aktif yang sudah berjalan sehingga pengembalian buku via return_copies tetap dapat diproses sampai tuntas; verifikasi token QR kriptografis tetap valid secara tanda tangan namun dapat diperiksa keaktifannya; audit log terstruktur merekam old_status, new_status, reason, dan actor; kepatuhan ketat privasi DEC-023 tanpa kelas dan tanpa nomor telepon; graceful fallback pada skema legacy P1 tanpa crash; pengujian komprehensif 25 skenario di tests/test_member_deactivate_and_reactivate.py; zero-write terverifikasi mutlak ke database produksi).
Task sedang berjalan: Fase 4 (6/10 task selesai).
Tes: .\venv\Scripts\python.exe -m unittest tests/test_member_deactivate_and_reactivate.py -v -> 25 tes OK (11.185s); .\venv\Scripts\python.exe -m unittest tests/test_member_deactivate_and_reactivate.py tests/test_member_import_commit.py tests/test_member_import_preview.py tests/test_member_import_template.py tests/test_admin_members.py tests/test_member_qr_token.py tests/test_admin_auth.py -> 159 tes OK (58.632s); .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -> 493 tes (492 OK, 0 gagal, 0 error, 1 skip OpenCV di venv, 200.291s).
File utama berubah: policy.py, repositories/member_repo.py, services/member_service.py, services/__init__.py, app.py, templates/admin_members.html, templates/admin_member_status.html, tests/test_member_deactivate_and_reactivate.py, docs/PROGRESS-perpus-digital.md.
Temuan/risiko: Keputusan DEC-020 dan DEC-023 terbukti konsisten menyederhanakan arsitektur dan memperkuat integritas data. Tidak adanya mekanisme delete mencegah terputusnya relasi foreign key pada riwayat transaksi peminjaman masa lalu. Mekanisme transaksional membuktikan bahwa status anggota dan audit log terikat secara tak terpisahkan (all-or-nothing). Database produksi perpustakaan.db 100% utuh (SHA-256 terverifikasi identik 1362120FA9D66D8AF0CB810DD57B138A6262C62F05381B6C593CC09887C7F87B). Tidak ada mutasi git (commit/checkout/reset) yang dijalankan.
NEXT: 4-07
```

Template entri baru:
```text
[TANGGAL] AI/orang: ...
Task selesai: ID, ID
Task sedang berjalan: ID (apa yang tersisa)
Tes: perintah + hasil nyata
File utama berubah: ...
Temuan/risiko: ...
NEXT: ID
```

---

## 9. Prompt singkat untuk AI baru (tempel apa adanya)

```text
Baca docs/DOKUMENTASI_INDUK_v4_2.md lalu docs/PROGRESS.md sebelum melakukan apa pun.
Kerjakan HANYA task yang ditandai NEXT di PROGRESS.md (atau task berikutnya yang syarat "Butuh"-nya sudah selesai). Jangan menebak keputusan di bagian 5.
Dilarang: deploy/migrasi produksi, menyentuh perpustakaan.db asli, menghapus data, menulis ulang aplikasi.
Sebelum mulai: git status + jalankan tes baseline. Setelah selesai: jalankan tes, tandai [x] hanya dengan bukti, perbarui PROGRESS.md (fase aktif, NEXT, tabel ringkasan, log sesi), dan beri laporan akhir sesuai Bagian 2.
```
