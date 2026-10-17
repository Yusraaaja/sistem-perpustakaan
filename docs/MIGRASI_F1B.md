# Dokumentasi Migrasi Skema Database v2 (Fase 1B)

Dokumen ini menjelaskan spesifikasi teknis skema database v2, aturan pemetaan data dari skema legacy P1 ke v2, instruksi pengoperasian migrator `scripts/migrate_legacy_to_v2.py`, hasil verifikasi, serta prosedur keselamatan dan rollback.

---

## 1. Latar Belakang & Tujuan (Fase 1B)

Fase 1B berfokus pada:
1. Menyiapkan skema database v2 yang kuat, terisolasi, dan aman.
2. Mengubah ketersediaan buku (*availability*) dari mutasi kolom angka manual (`stok`) menjadi **satu sumber kebenaran berbasis constraint riwayat (*single source of truth derived state*)**.
3. Menerapkan identifier human-friendly Base32 Crockford tanpa karakter ambigu untuk seluruh entitas publik (`T-`, `C-`, `M-`, `L-`, `LI-`, `AUD-`).
4. Menyediakan migrator offline yang atomik, transaksional, dan sepenuhnya idempoten dari salinan database P1 tanpa menyentuh database produksi.

> [!IMPORTANT]
> **Batasan Lingkup Fase 1B:**
> - `app.py` **TIDAK DIUBAH** pada fase ini (integrasi aplikasi dengan skema v2 dikerjakan pada Fase 2).
> - Database produksi `perpustakaan.db` **TIDAK BOLEH DISENTUH** dan dijaga dengan SHA-256 integrity check.
> - Tidak ada eksekusi migrasi di lingkungan produksi.

---

## 2. Spesifikasi Kamus Data Skema v2

Semua primary key pada skema v2 menggunakan tipe data `TEXT` yang dihasilkan oleh aplikasi (`id_generator.py`) tanpa `AUTOINCREMENT` (memenuhi R2). Seluruh kolom waktu menggunakan format teks ISO8601 UTC seragam: `"YYYY-MM-DDTHH:MM:SSZ"` yang dihasilkan hanya melalui modul `timeutil.py`.

### A. `member_categories`
Kategori keanggotaan perpustakaan dengan data benih (*seed*):
* `id` (`TEXT PRIMARY KEY`): Contoh `MC-MURID`, `MC-GURU-JUR`, `MC-GURU-UMUM`, `MC-STAF`, `MC-TEKNISI`.
* `jenis` (`TEXT NOT NULL UNIQUE`): Nama teknis kategori (`murid`, `guru_jurusan`, `guru_umum`, `staf`, `teknisi`).
* `keterangan` (`TEXT`): Deskripsi peruntukan kategori.

### B. `members`
Tabel anggota perpustakaan (tanpa kolom kelas dan telepon per R2):
* `id` (`TEXT PRIMARY KEY`): Format `M-XXXXXXXX` (Base32 Crockford).
* `nama` (`TEXT NOT NULL`): Nama lengkap anggota.
* `status` (`TEXT NOT NULL DEFAULT 'aktif'`): `CHECK (status IN ('aktif', 'nonaktif'))`.
* `category_id` (`TEXT NOT NULL REFERENCES member_categories(id)`).
* `qr_version` (`INTEGER NOT NULL DEFAULT 1`).
* `created_at` (`TEXT NOT NULL`): ISO8601 UTC.
* `updated_at` (`TEXT NOT NULL`): ISO8601 UTC.

### C. `catalog_titles`
Katalog judul buku (dipetakan dari tabel `buku`):
* `id` (`TEXT PRIMARY KEY`): Format `T-XXXXXXXX` (Base32 Crockford).
* `judul` (`TEXT NOT NULL`): Judul utama buku.
* `subjudul` (`TEXT`): Sub-judul buku jika ada.
* `penulis` (`TEXT`), `penerbit` (`TEXT`), `tahun` (`TEXT`), `isbn` (`TEXT`), `kategori` (`TEXT`), `ddc` (`TEXT`), `sinopsis` (`TEXT`), `cover_path` (`TEXT`).
* `harga_buku` (`INTEGER DEFAULT 0`): Nilai penggantian buku.
* `metadata_json` (`TEXT`): Menyimpan data historis (sumber perolehan, tanggal masuk, kondisi awal).
* `legacy_buku_id` (`INTEGER UNIQUE`): ID referensi tabel `buku` lama untuk menjamin idempotensi (R5).
* `created_at` (`TEXT NOT NULL`), `updated_at` (`TEXT NOT NULL`): ISO8601 UTC.

### D. `copies`
Eksemplar fisik buku. Mengeliminasi `barcode_id`, `no_induk`, dan `kondisi` dari tabel utama (R8 & R9):
* `id` (`TEXT PRIMARY KEY`): Format `C-XXXXXXXX` (Base32 Crockford). Dibuat oleh server, unik, dan tidak pernah digunakan ulang.
* `title_id` (`TEXT NOT NULL REFERENCES catalog_titles(id)`).
* `call_number` (`TEXT`): Nomor panggil rak.
* `status` (`TEXT NOT NULL DEFAULT 'aktif'`): `CHECK (status IN ('aktif', 'nonaktif', 'hilang', 'rusak', 'dalam_penanganan'))`.
* `lokasi_rak` (`TEXT`), `tanggal_masuk` (`TEXT`), `sumber` (`TEXT`), `harga` (`INTEGER DEFAULT 0`).
* `created_at` (`TEXT NOT NULL`): ISO8601 UTC.

### E. `loans`
Header transaksi peminjaman (tanpa kelas/jurusan per R4):
* `id` (`TEXT PRIMARY KEY`): Format `L-XXXXXXXX` (Base32 Crockford).
* `member_id` (`TEXT REFERENCES members(id)`): Bernilai `NULL` untuk pinjaman legacy lama.
* `legacy_nama_peminjam` (`TEXT`): Menyimpan nama asli peminjam data lama.
* `created_at` (`TEXT NOT NULL`): ISO8601 UTC.
* `idempotency_key` (`TEXT UNIQUE`): Kode transaksi unik (contoh `TRX-20260918-0011`).
* `legacy_peminjaman_id` (`INTEGER UNIQUE`): ID peminjaman lama untuk idempotensi (R5).

### F. `loan_items`
Rincian item buku yang dipinjam dalam suatu transaksi:
* `id` (`TEXT PRIMARY KEY`): Format `LI-XXXXXXXX` (Base32 Crockford).
* `loan_id` (`TEXT NOT NULL REFERENCES loans(id)`).
* `copy_id` (`TEXT NOT NULL REFERENCES copies(id)`).
* `borrowed_at` (`TEXT NOT NULL`): Waktu pinjam (ISO8601 UTC).
* `due_at` (`TEXT NOT NULL`): Batas jatuh tempo (ISO8601 UTC).
* `extended_at` (`TEXT`): Waktu perpanjangan jika pernah diperpanjang.
* `extension_count` (`INTEGER NOT NULL DEFAULT 0`).
* `returned_at` (`TEXT`): Waktu pengembalian (ISO8601 UTC, `NULL` jika masih aktif dipinjam).
* `return_condition` (`TEXT`): `CHECK (return_condition IS NULL OR return_condition IN ('baik', 'rusak', 'lainnya', 'hilang'))`.
* `returned_via` (`TEXT`): `CHECK (returned_via IS NULL OR returned_via IN ('jalur_a', 'jalur_b', 'manual', 'penyelesaian', 'legacy'))`.
* `notes` (`TEXT`): Catatan audit transaksi.

> [!IMPORTANT]
> **Constraint Parsial Ketersediaan Tunggal (LIB-LOAN-002):**
> ```sql
> CREATE UNIQUE INDEX IF NOT EXISTS idx_loan_items_active_copy 
> ON loan_items(copy_id) 
> WHERE returned_at IS NULL;
> ```
> Indeks parsial ini menjamin bahwa satu eksemplar fisik buku hanya dapat memiliki **maksimal 1 baris peminjaman aktif** (`returned_at IS NULL`). Percobaan meminjamkan kembali eksemplar yang sedang dipinjam akan ditolak secara mutlak oleh database engine.

### G. `legacy_loan_item_extra` (Tabel Baca-Saja)
Menyimpan data historis denda dan status penggantian dari sistem lama (R4, DEC-024: perpustakaan baru tidak memberlakukan denda uang):
* `loan_item_id` (`TEXT PRIMARY KEY REFERENCES loan_items(id)`).
* `fine_overdue` (`INTEGER DEFAULT 0`): Denda keterlambatan lama.
* `fine_condition` (`INTEGER DEFAULT 0`): Denda kerusakan/kehilangan lama.
* `status_penggantian` (`TEXT`), `catatan_penggantian` (`TEXT`).

### H. `legacy_copy_map`
Peta jejak balik nomor registrasi legacy ke ID eksemplar v2 (R9):
* `old_ref` (`TEXT PRIMARY KEY`): Nomor registrasi fisik lama (contoh: `'00000101'`).
* `copy_id` (`TEXT NOT NULL REFERENCES copies(id)`).
* `legacy_buku_id` (`INTEGER`): ID buku lama.

### I. `audit_log`
Catatan jejak audit sistem:
* `id` (`TEXT PRIMARY KEY`): Format `AUD-XXXXXXXX`.
* `at` (`TEXT NOT NULL`), `actor` (`TEXT NOT NULL`), `action` (`TEXT NOT NULL`), `object_type` (`TEXT NOT NULL`), `object_id` (`TEXT NOT NULL`), `reason` (`TEXT`), `detail_json` (`TEXT`).

### J. Database Triggers Proteksi Penghapusan (R12)
Mencegah mutasi destruktif `DELETE` pada data eksemplar dan riwayat pinjaman:
```sql
CREATE TRIGGER IF NOT EXISTS trg_prevent_delete_copies
BEFORE DELETE ON copies
BEGIN
    SELECT RAISE(ABORT, 'DELETE pada tabel copies dilarang demi integritas riwayat perpustakaan');
END;

CREATE TRIGGER IF NOT EXISTS trg_prevent_delete_loan_items
BEFORE DELETE ON loan_items
BEGIN
    SELECT RAISE(ABORT, 'DELETE pada tabel loan_items dilarang demi integritas riwayat perpustakaan');
END;
```

---

## 3. Matriks Pemetaan Data Lama ke v2

| Sumber Lama (P1) | Target v2 | Logika Transformasi & Catatan |
|---|---|---|
| `buku.id` | `catalog_titles.legacy_buku_id` | Menjadi referensi idempotensi 1:1. |
| `buku.judul` s.d. `sinopsis` | `catalog_titles.*` | Dipetakan langsung. |
| `buku.id_buku_fisik` (JSON) | `copies` & `legacy_copy_map` | Diekstrak menjadi baris-baris eksemplar baru dengan ID `C-XXXXXXXX`. |
| `peminjaman_detail.no_registrasi` | `copies` (bila belum ada di rak) | Menangkap eksemplar yang sedang dipinjam (`00001501`) agar total fisik utuh. |
| `peminjaman_detail.status` | `copies.status` | `'Rusak'` $\to$ `'rusak'`, `'Hilang'` $\to$ `'hilang'`, lainnya $\to$ `'aktif'`. |
| `peminjaman.id` | `loans.legacy_peminjaman_id` | Referensi idempotensi transaksi. |
| `peminjaman.id_anggota` | `loans.legacy_nama_peminjam` | Disimpan sebagai teks bebas, `member_id` diset `NULL` (tanpa membuat anggota fiktif). |
| `peminjaman_detail.status` | `loan_items.return_condition` | `'Kembali'` $\to$ `'baik'`, `'Rusak'` $\to$ `'rusak'`, `'Hilang'` $\to$ `'hilang'`, Aktif $\to$ `NULL`. |
| `peminjaman_detail.tgl_dikembalikan` | `loan_items.returned_via` | Terisi $\to$ `'legacy'`, `NULL` $\to$ `NULL`. |
| `peminjaman_detail.denda_*` | `legacy_loan_item_extra.*` | Dipindahkan ke tabel baca-saja; dihapus dari `loan_items`. |

---

## 4. Konversi Waktu & Zona Waktu (R7)

Data lama hanya mencatat tanggal kalender lokal (WIB / Asia/Jakarta, UTC+7). Konversi dilakukan presisi oleh modul `timeutil.py`:
1. `borrowed_at`: Tanggal pinjam jam `00:00:00` WIB $\to$ UTC (`YYYY-MM-DDTHH:MM:SSZ`).
2. `returned_at`: Tanggal pengembalian jam `23:59:59` WIB $\to$ UTC (menjamin `returned_at >= borrowed_at` pada hari yang sama).
3. `due_at`: Tanggal `tgl_kembali_seharusnya` asli jam `23:59:59` WIB $\to$ UTC. **Tidak dihitung ulang menjadi 168 jam** untuk data lama (durasi asli 1 hari pada transaksi 13 dipertahankan).
4. `notes`: Ditandai dengan `waktu_lama_perkiraan`. Jika nama peminjam mengandung kata `TEST`, ditandai `data_uji; waktu_lama_perkiraan`.

> [!NOTE]
> **Status Transaksi Aktif Lama (ID 13):**
> Transaksi peminjaman aktif ID 13 memiliki `due_at` setara `2026-10-05T16:59:59Z`. Karena pembacaan sistem dilakukan setelah tanggal tersebut, transaksi ini secara otomatis terdeteksi berstatus **terlambat (*overdue*)** oleh mesin waktu `timeutil.check_overdue()`.

---

## 5. Cara Menjalankan Skrip Migrasi

Skrip migrasi terletak di `scripts/migrate_legacy_to_v2.py`.

### A. Mode Simulasi Aman (Dry-Run, Default)
```powershell
.\venv\Scripts\python.exe scripts/migrate_legacy_to_v2.py --source backups/test_copy_migration.db
```
Menjalankan simulasi lengkap: deteksi versi skema, pemeriksaan keunikan nomor registrasi antar-buku, rekonsiliasi angka, dan menampilkan rencana eksekusi tanpa mengubah isi database.

### B. Mode Terapkan Migrasi (--apply)
```powershell
.\venv\Scripts\python.exe scripts/migrate_legacy_to_v2.py --source backups/test_copy_migration.db --apply
```
Mengeksekusi migrasi di dalam transaksi atomik (`BEGIN IMMEDIATE ... COMMIT`).

### C. Mekanisme Keamanan (Guardrails)
1. **Penolakan Target Produksi:** Jika `--source` atau target mengarah ke `perpustakaan.db` di root (baik relatif maupun absolut), skrip langsung berhenti dengan pesan error fatal dan exit code 1.
2. **Penolakan Skema v1:** Jika database masih berskema v1 (tanpa tabel `peminjaman_detail`), skrip menolak dan meminta operator menjalankan `scripts/migrate_p1_multibook.py` terlebih dahulu pada salinan.
3. **Pemeriksaan Duplikasi Eksemplar Antar-Buku:** Jika ditemukan nomor registrasi fisik yang sama terdaftar di dua buku berbeda, skrip berhenti sebelum melakukan penulisan apa pun.

---

## 6. Prosedur Rollback

Karena migrasi dijalankan sepenuhnya dalam transaksi atomik:
1. **Rollback Otomatis:** Jika terjadi kesalahan eksepsional di tengah eksekusi, blok `try ... except` langsung memanggil `conn.rollback()` sehingga file database kembali 100% ke kondisi sebelum migrasi dimulai tanpa meninggalkan baris parsial (*dirty state*).
2. **Rollback Manual Salinan:** Karena proses migrasi hanya dijalankan pada file salinan di folder `backups/`, pemulihan kondisi awal dapat dilakukan dengan menyalin kembali file backup asli:
   ```powershell
   Copy-Item backups/backup_sebelum_v2.db backups/test_copy_migration.db -Force
   ```

---

## 7. Catatan Portabilitas PostgreSQL (Fase 10)

DDL skema v2 saat ini ditulis dan diuji secara spesifik untuk SQLite 3. Penerjemahan ke dialek PostgreSQL akan dikerjakan pada **Fase 10 (Production Deployment)** dengan penyesuaian:
- Mengganti tipe kolom waktu `TEXT` menjadi `TIMESTAMPTZ`.
- Menggunakan `CREATE OR REPLACE VIEW` untuk `v_copy_availability` dan `v_title_availability`.
- Menggunakan PostgreSQL trigger function (`BEFORE DELETE ... RAISE EXCEPTION`) menggantikan SQLite `RAISE(ABORT, ...)`.
- Indeks parsial `CREATE UNIQUE INDEX ... WHERE returned_at IS NULL` identik dan didukung secara native oleh kedua database.

