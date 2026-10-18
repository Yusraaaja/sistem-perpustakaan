# PROGRESS — Sistem Perpustakaan Digital Sekolah

> **Simpan file ini di `docs/PROGRESS.md`.** Ini papan tugas hidup. Setiap AI/pengembang WAJIB membacanya (setelah `docs/DOKUMENTASI_INDUK_v4_2.md`) dan memperbaruinya di akhir sesi.

**Terakhir diperbarui:** 17 Oktober 2026
**Fase aktif:** Fase 1B (skema v2 & migrasi)
**TASK BERIKUTNYA (NEXT):** `1B-03`

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

**Kondisi kode & lingkungan (hasil audit Fase 0/1B):**
- Windows + PowerShell, virtualenv `venv`. Backend: Flask **monolit** `app.py` (~1.800+ baris), template Jinja di `templates/`, SQLite.
- Perintah tes: `.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` (framework: **unittest**, jangan diganti). Baseline terakhir dilaporkan: **54 tes OK** (sebelumnya 43).
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
| 1B | Skema v2 & migrasi (salinan saja) | 2/10 | **AKTIF** |
| 2 | Peminjaman/pengembalian di skema v2 | 0/10 | belum |
| 3 | Katalog, tambah buku, label QR | 0/12 | belum |
| 4 | Anggota, impor, kartu QR | 0/10 | belum |
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

### FASE 1B — Skema v2 & migrasi (AKTIF)
Spec lengkap (revisi R1–R12 telah **disetujui pemilik**): skema v2 + migrasi dari skema P1 **hanya pada salinan**. `app.py` TIDAK diubah di fase ini.
- [x] **1B-01** Inspeksi skema aktual & rencana pemetaan. Bukti: laporan inspeksi Fase 1B (28 eksemplar, peminjam lama teks bebas).
- [x] **1B-02** Rencana disetujui dengan revisi R1–R12 (lihat spec di bawah).
- [ ] **1B-03** `get_connection()` terpusat dengan `PRAGMA foreign_keys=ON` di setiap koneksi. _Selesai bila:_ tes membuktikan insert FK tidak valid ditolak. _Butuh:_ —
- [ ] **1B-04** `id_generator.py`: alfabet `23456789ABCDEFGHJKMNPQRSTVWXYZ`, format `T-/C-/M-/L-XXXXXX`; semua primary key TEXT buatan aplikasi (termasuk `loan_items.id`, `audit_log.id`; tanpa AUTOINCREMENT). _Selesai bila:_ tes 10.000 ID unik, tanpa karakter ambigu, retry tabrakan teruji (mock tabrakan). _Butuh:_ —
- [ ] **1B-05** DDL skema v2 di `migrations/001_schema_v2.sql` + `schema_version` + deteksi versi skema (v1 / P1 / v2). Tabel: `member_categories`, `members`, `catalog_titles` (+`legacy_buku_id` UNIQUE), `copies` (tanpa `barcode_id`/`no_induk`/`kondisi`), `loans` (+`legacy_peminjaman_id` UNIQUE, `legacy_nama_peminjam`), `loan_items` (tanpa kolom denda; `return_condition` IN baik/rusak/lainnya/hilang; `returned_via` IN jalur_a/jalur_b/manual/penyelesaian/legacy), `audit_log`, `legacy_copy_map`, `legacy_loan_item_extra` (baca-saja: denda & penggantian lama). Index unik parsial: satu `copy_id` hanya satu `loan_item` dengan `returned_at IS NULL`. Waktu = TEXT `YYYY-MM-DDTHH:MM:SSZ` hanya dari `timeutil`. _Selesai bila:_ skema terbentuk di DB kosong; tes constraint lulus. _Butuh:_ 1B-03, 1B-04
- [ ] **1B-06** View ketersediaan: `v_copy_availability`, `v_title_availability` (`total_aktif`, `total_semua`, `available_copies`, `borrowed_copies`). _Selesai bila:_ tes angka view cocok dengan data uji. _Butuh:_ 1B-05
- [ ] **1B-07** Migrator mode `--dry-run` (default): menolak skema v1 (pesan: jalankan `migrate_p1_multibook.py` pada salinan dulu), menolak path `perpustakaan.db` asli (bandingkan path hasil resolve), memeriksa nomor registrasi duplikat antar-buku (berhenti & laporkan), membuat laporan rekonsiliasi generik. _Selesai bila:_ dry-run tidak menulis apa pun (tes). _Butuh:_ 1B-05
- [ ] **1B-08** Migrator `--apply` (atomik, idempoten): `buku`→`catalog_titles`; eksemplar = gabungan semua nomor di `id_buku_fisik` + semua `no_registrasi` di `peminjaman_detail` yang tidak ada di JSON (status: Rusak→`rusak`, Hilang→`hilang`, lainnya `aktif`); `peminjaman`→`loans` (`member_id` NULL, nama lama di `legacy_nama_peminjam`; nama berisi "TEST" ditandai `data_uji`); item→`loan_items` (`returned_via='legacy'`, `notes='waktu_lama_perkiraan'`). Konversi waktu: `borrowed_at` = tanggal 00:00:00 WIB; `returned_at` = tanggal 23:59:59 WIB; `due_at` = `tgl_kembali_seharusnya` 23:59:59 WIB, **jangan dihitung ulang jadi 168 jam**. Denda lama → `legacy_loan_item_extra`. _Selesai bila:_ pada salinan: 15 judul, 28 eksemplar, 1 item aktif, 2 item selesai; `--apply` dua kali tidak menambah baris. _Butuh:_ 1B-06, 1B-07
- [ ] **1B-09** Tes: constraint parsial; rollback atomik; migrasi salinan; dry-run tidak menulis; penolakan v1 & path asli; FK; tidak ada jalur DELETE untuk `copies`/`loan_items`; tes lama tetap hijau (jelaskan rincian 43→54→baru). _Butuh:_ 1B-08
- [ ] **1B-10** `docs/MIGRASI_F1B.md` (kamus data, pemetaan kolom, aturan waktu, cara jalankan, rollback, catatan terjemahan PostgreSQL untuk Fase 10); laporan akhir termasuk checksum `perpustakaan.db` sebelum/sesudah. _Butuh:_ 1B-09

**GERBANG → Fase 2:** kirim laporan 1B ke pemilik/perencana; Fase 2 ditulis ulang dengan nama kode aktual.

### FASE 2 — Peminjaman/pengembalian di skema v2 (provisional)
Tujuan: memindahkan logika P1 di `app.py` ke skema v2 secara bertahap, tanpa memecah monolit.
- [ ] **2-01** Petakan route & fungsi di `app.py` yang menyentuh pinjam/kembali/stok → `docs/PETA_APP.md` (read-only). _Selesai bila:_ tiap route punya catatan "akan diganti service apa".
- [ ] **2-02** `repositories/` v2: baca copies/loans/loan_items/anggota (query via `get_connection`). _Butuh:_ 1B-10
- [ ] **2-03** `services/loan_service.checkout(member_id, copy_ids, idempotency_key)`: validasi server (anggota aktif, copy aktif & tersedia, tanpa duplikat), `due_at = borrowed_at + 168 jam` per item, atomik (`BEGIN IMMEDIATE`). _Selesai bila:_ tes multi-item + rollback lulus.
- [ ] **2-04** Idempotensi & konkurensi: `idempotency_key` sama tidak membuat pinjaman ganda; dua proses berebut satu copy → satu menang. _Selesai bila:_ tes konkurensi lulus.
- [ ] **2-05** `services/return_service.return_copy(copy_id, condition, via)` Jalur A: tanpa melihat pengembali; tolak copy tanpa pinjaman aktif/ganda; kondisi `rusak` → copy `dalam_penanganan`.
- [ ] **2-06** Status turunan loan induk: berjalan / sebagian_selesai / selesai.
- [ ] **2-07** API JSON `/api/loans`, `/api/returns` (respons `{ok, kode, pesan, data}`; kode HTTP benar; pesan Indonesia sederhana).
- [ ] **2-08** Alihkan route lama ke service baru di balik flag `USE_V2` (satu route per commit).
- [ ] **2-09** Adaptasi `test_multi_book_p1.py` ke v2 + tes batas 168 jam dan lintas hari.
- [ ] **2-10** Hook `can_borrow(member)` (sementara selalu True; diisi di Fase 7).

### FASE 3 — Katalog, tambah buku, label QR (provisional)
- [ ] **3-01** Verifikasi auth admin yang ada: tiap route admin menolak tanpa login (tes otomatis), rate limit login, flag cookie, CSRF per POST; perbaiki yang kurang.
- [ ] **3-02** Form tambah buku (judul, penulis, ISBN, kategori, **jumlah**) tahap pratinjau "Anda akan membuat N eksemplar" (jumlah >100 wajib diketik ulang).
- [ ] **3-03** Commit atomik + token sekali pakai: klik ganda/kirim ulang tidak menggandakan; gagal di tengah = 0 eksemplar.
- [ ] **3-04** Peringatan judul mirip (ISBN, atau judul+penulis ternormalisasi); tidak pernah gabung diam-diam.
- [ ] **3-05** Template impor katalog (judul, penulis, isbn, kategori, jumlah) + halaman panduan.
- [ ] **3-06** Pratinjau impor tanpa menulis DB: baris OK/peringatan/error + alasan; batas ukuran file; formula tidak dieksekusi.
- [ ] **3-07** Commit impor atomik + ringkasan (judul baru, eksemplar dibuat, dilewati, bermasalah).
- [ ] **3-08** Halaman cetak label `/admin/labels` (A4 grid): QR + ID terbaca manusia berdekatan + judul singkat; QR hanya memuat ID eksemplar.
- [ ] **3-09** Cetak ulang (ID & QR identik) + halaman "Eksemplar tanpa label" untuk buku lama di rak.
- [ ] **3-10** Nonaktifkan/tandai eksemplar per eksemplar dengan alasan → `audit_log`; tanpa hard delete.
- [ ] **3-11** Upload cover: validasi magic bytes, ukuran, nama UUID; lewat interface `Storage` (Local sekarang; Supabase di Fase 10).
- [ ] **3-12** Pencarian katalog publik memakai `v_title_availability` (ketersediaan dari DB; input kosong/aneh ditangani).

### FASE 4 — Anggota, impor, kartu QR (provisional)
- [ ] **4-01** Token QR anggota: HMAC-SHA256(SECRET_KEY, member_id:qr_version), tanpa data pribadi; validasi `compare_digest`; keputusan dicatat di `docs/KEPUTUSAN_TEKNIS.md`.
- [ ] **4-02** Seed `member_categories` (murid/jurusan, guru jurusan/program keahlian, guru umum/mata pelajaran, staf, teknisi) + daftar & cari anggota (admin).
- [ ] **4-03** Template impor anggota (nama, jenis, keterangan, status, id_anggota opsional); kolom kelas/telepon diabaikan dengan peringatan.
- [ ] **4-04** Pratinjau pencocokan (OPEN-011): ID cocok → perbarui; tanpa ID → BARU / KEMUNGKINAN SAMA / AMBIGU, petugas memilih per baris; tidak ada penimpaan diam-diam.
- [ ] **4-05** Commit impor atomik; sanggup >1.000 baris; ringkasan dibuat/diperbarui/dilewati/gagal; anggota yang tidak ada di file tidak diubah.
- [ ] **4-06** Nonaktifkan/aktifkan kembali anggota (alasan → `audit_log`); tanpa tombol hapus, tanpa job pembersihan.
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

---

## 8. Log sesi (tambahkan entri baru di bawah; jangan hapus yang lama)

```text
[2026-10-17] Fase 0 selesai: audit, dokumen induk disalin ke docs/, 43 tes OK.
[2026-10-17] Fase 1A selesai (dilaporkan): baseline diamankan, config/policy/timeutil dibuat; 54 tes OK.
[2026-10-17] Fase 1B: inspeksi + rencana pemetaan selesai; rencana DISETUJUI dengan revisi R1-R12. NEXT = 1B-03.
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
