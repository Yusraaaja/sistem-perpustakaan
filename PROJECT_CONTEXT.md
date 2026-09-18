# PROJECT_CONTEXT — Sistem Perpustakaan Digital

> Dokumen konteks untuk AI coding assistant. Source of truth tetap project di VS Code.
> Jangan menganggap dokumen ini menggantikan pemeriksaan file aktual.

## 1. Identitas Project

Nama project: Sistem Perpustakaan Digital
Stack utama:
- Python
- Flask 3.1.3
- SQLite
- Jinja2
- HTML/CSS/JavaScript
- Tailwind CSS dan Alpine.js digunakan pada sebagian fondasi UI
- Bootstrap masih digunakan pada sebagian halaman existing
- Gunakan library frontend yang sudah ada sebelum menambah dependency baru.

## 2. Struktur Aktual yang Terdeteksi

Root project berisi antara lain:
- app.py
- database_setup.py
- fix_db.py
- generate_sample.py
- requirements.txt
- perpustakaan.db
- Procfile
- Jalankan_Perpus_Selamanya.bat
- data_contoh_perpustakaan.xlsx
- editable_data.xlsx
- laporan_peminjaman.xlsx
- templates/
- static/covers/
- venv/
- .git/

Template yang ada:
- base.html
- dashboard.html
- detail_buku.html
- edit.html
- index.html
- koleksi.html
- layout.html
- login.html
- peminjaman.html

## 3. Arsitektur Backend

Backend utama saat ini terpusat di `app.py`.

Route yang terdeteksi:
- /login
- /logout
- /
- /search
- /add
- /edit/<int:id>
- /delete/<int:id>
- /buku/<int:id>
- /reset_katalog_buku
- /buku/<int:id>/upload_cover
- /peminjaman
- /proses_pinjam_admin
- /kembalikan/<int:pinjam_id>
- /lunasi_denda/<int:pinjam_id>
- /hapus_peminjaman/<int:id>
- /api/riwayat_buku/<int:buku_id>
- /koleksi
- /export_peminjaman
- /import_excel

`app.py` juga menangani:
- autentikasi/session
- koneksi database
- CRUD buku
- upload cover
- peminjaman/pengembalian
- denda
- riwayat buku
- koleksi
- import/export Excel
- inisialisasi database

## 4. Database Aktual

Database: `perpustakaan.db`

Tabel utama:

### buku
Kolom yang terdeteksi:
- id
- judul
- sub_judul
- penulis
- penerbit
- tahun_terbit
- isbn
- kategori
- sinopsis
- cover_img
- id_buku_fisik
- lokasi_rak
- sumber_perolehan
- tanggal_masuk
- kondisi_buku
- harga_buku
- stok

`id_buku_fisik` memiliki UNIQUE constraint.

### peminjaman
Kolom:
- id
- id_buku
- id_anggota
- tipe_user
- kelas
- jurusan
- tgl_pinjam
- tgl_kembali_seharusnya
- tgl_dikembalikan
- status
- denda

`id_buku` memiliki foreign key ke `buku.id`.

## 5. Template Inheritance Saat Ini

Saat ini ada DUA fondasi template:

### base.html
Dipakai oleh:
- dashboard.html

### layout.html
Dipakai oleh:
- detail_buku.html
- edit.html
- index.html
- koleksi.html
- login.html
- peminjaman.html

Ini adalah area arsitektur yang harus diperiksa sebelum melakukan redesign besar. Jangan menyatukan atau menghapus salah satunya secara otomatis.

## 6. Fitur Existing yang Harus Dipertahankan

Sebelum menambah fitur, jangan merusak:
- login/logout
- katalog buku
- pencarian
- tambah/edit/hapus buku
- detail buku
- upload cover
- peminjaman
- pengembalian
- denda
- riwayat buku
- koleksi
- import Excel
- export peminjaman
- dashboard/statistik yang sudah ada
- struktur database existing

## 7. Kondisi Arsitektur yang Perlu Audit

Temuan awal:
1. `app.py` menangani banyak tanggung jawab sekaligus.
2. Ada dua base/layout template.
3. Sebagian UI memakai Bootstrap, sementara fondasi modern juga memakai Tailwind/Alpine.
4. `database_setup.py` dan `app.py` perlu dibandingkan dengan schema database aktual sebelum perubahan database.
5. Database existing (`perpustakaan.db`) adalah bagian penting dari kondisi project saat ini.
6. Project ZIP juga membawa `venv/` dan `.git/`; jangan menjadikan keduanya bagian dari source code aplikasi saat melakukan refactor/deployment.

## 8. Keamanan yang Harus Diperhatikan

Audit menemukan secret key dan kredensial admin berada langsung di source code `app.py`.

Jangan menyalin nilai secret/password tersebut ke dokumentasi AI.
Jangan mempublikasikan kredensial.
Perubahan keamanan harus dilakukan setelah fungsi existing dipahami dan diuji.

## 9. Aturan Pengembangan

Source of truth:
`VS Code project`

AI assistant:
`Gemini Chatbot`

AI tidak boleh menganggap dirinya memiliki akses ke project kecuali file/struktur benar-benar tersedia di konteks/workspace.

Jika informasi yang dibutuhkan tidak tersedia:
- katakan file apa yang kurang
- jangan mengarang isi file
- jangan membuat struktur folder berdasarkan asumsi

## 10. Roadmap yang Direncanakan

Urutan pengembangan:
1. Audit dan stabilisasi project
2. Rapikan fondasi UI/template
3. Modernisasi UI/UX
4. Webcam QR/Barcode Scanner
5. Analytics Dashboard
6. E-KTA Digital QR
7. AI Book Assistant
8. WhatsApp Reminder Automation

Satu fitur/fase dikerjakan dan diuji sebelum lanjut ke berikutnya.

## 11. Prinsip Perubahan

Prefer:
- perubahan minimal
- reuse file existing
- reuse dependency existing
- backward compatibility
- testing setelah perubahan
- perubahan yang mudah di-rollback

Hindari:
- rewrite total
- mengganti framework
- migrasi database tanpa rencana
- membuat banyak file baru tanpa kebutuhan
- menghapus fitur existing hanya demi desain
