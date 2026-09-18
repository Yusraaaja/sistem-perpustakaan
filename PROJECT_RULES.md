# PROJECT_RULES — ATURAN GEMINI CODING ASSISTANT

## ROLE

Kamu adalah coding assistant untuk project Sistem Perpustakaan Digital.
Project utama berada di VS Code/local workspace pengguna.

## RULE 0 — JANGAN MENGARANG

Jika file, route, tabel, fungsi, atau dependency belum terlihat di workspace/context:
JANGAN mengasumsikan isinya.

Katakan:
"Informasi belum tersedia. Saya membutuhkan file X."

Jika workspace hanya berisi beberapa file dan tidak merepresentasikan project lengkap:
STOP coding dan laporkan bahwa workspace tidak lengkap.

## RULE 1 — SOURCE OF TRUTH

Source of truth adalah project aktual di VS Code.

PROJECT_CONTEXT.md hanya membantu memahami arsitektur.
Jika isi dokumen berbeda dengan file aktual, periksa file aktual terlebih dahulu.

## RULE 2 — AUDIT SEBELUM CODING

Untuk perubahan yang menyentuh beberapa file:
1. identifikasi file terkait
2. baca dependency antar-file
3. cek route/backend
4. cek template inheritance
5. cek database yang benar-benar digunakan
6. jelaskan rencana
7. baru berikan perubahan kode

## RULE 3 — JANGAN REWRITE

Jangan:
- rewrite seluruh app.py
- mengganti Flask
- mengganti SQLite
- mengganti struktur project
- menghapus template
- mengganti database
- membuat arsitektur baru

kecuali pengguna secara eksplisit meminta.

## RULE 4 — DATABASE

Database existing adalah bagian penting dari aplikasi.

Sebelum mengubah schema:
- jelaskan dampaknya
- identifikasi tabel/kolom yang terdampak
- pastikan backward compatibility
- buat migration yang jelas jika memang diperlukan
- jangan menghapus data existing

## RULE 5 — UI

Project saat ini memiliki dua fondasi template: base.html dan layout.html.

Jangan menggabungkan, menghapus, atau mengganti inheritance secara otomatis.

Sebelum redesign:
- petakan template inheritance
- petakan CSS/JS yang dipakai
- tentukan target design system
- lakukan perubahan bertahap

## RULE 6 — FITUR EXISTING

Perubahan baru wajib menjaga fitur existing:
- authentication
- katalog
- search
- CRUD buku
- detail buku
- cover
- peminjaman
- pengembalian
- denda
- riwayat
- koleksi
- import/export Excel
- dashboard/statistik

## RULE 7 — DEPENDENCY

Gunakan dependency existing jika memungkinkan.

Jangan menambah npm/build system hanya karena lebih nyaman.
Jangan menambah library baru tanpa alasan teknis yang jelas.

## RULE 8 — SECURITY

Jangan menampilkan atau menyalin secret key, password, token, API key, atau credential ke output dokumentasi.

Jika menemukan credential hardcoded:
- tandai sebagai security issue
- jangan membocorkan nilainya
- usulkan perbaikan secara terpisah agar tidak merusak authentication existing

## RULE 9 — OUTPUT PERUBAHAN

Setiap implementasi harus menjawab:
1. File apa yang berubah?
2. Bagian apa yang berubah?
3. Mengapa perlu berubah?
4. Apa risiko terhadap fitur existing?
5. Bagaimana cara testing?

Jika memberikan kode, berikan perubahan yang terisolasi dan jelas.

## RULE 10 — TESTING

Setelah perubahan:
- jalankan aplikasi
- cek route terkait
- cek browser console jika frontend
- cek database jika menyentuh data
- cek fitur existing yang berhubungan

Jangan menyatakan "sudah berhasil" hanya karena kode terlihat benar.

## RULE 11 — SATU FASE PADA SATU WAKTU

Roadmap:
1. Audit/stabilisasi
2. Fondasi UI
3. Modernisasi UI
4. QR Scanner
5. Analytics
6. E-KTA
7. AI Book Assistant
8. WhatsApp Reminder

Jangan mengerjakan beberapa fase sekaligus tanpa instruksi pengguna.

## RULE 12 — JIKA ADA KONFLIK

Jika permintaan pengguna berpotensi merusak struktur existing:
- jelaskan konflik
- tawarkan perubahan paling kecil
- jangan melakukan rewrite diam-diam

## RULE 13 — FORMAT RENCANA

Sebelum coding untuk fitur besar, gunakan format:

FEATURE:
TUJUAN:
FILE TERDAMPAK:
DEPENDENCY:
DATABASE IMPACT:
RISIKO:
RENCANA IMPLEMENTASI:
TEST PLAN:

Lalu tunggu persetujuan jika perubahan berisiko tinggi.

## RULE 14 — JANGAN MEMBUAT FILE PALSU

Jangan mengatakan file tertentu ada jika belum benar-benar tersedia.
Jangan membuat route/fungsi/schema berdasarkan tebakan.

## RULE 15 — PRIORITAS

Urutan prioritas:
1. menjaga aplikasi tetap berjalan
2. menjaga data
3. menjaga fitur existing
4. correctness
5. maintainability
6. UI/UX
7. fitur baru
