# -*- coding: utf-8 -*-
"""
Kebijakan Operasional Sistem Perpustakaan Digital Sekolah.
Menampung nilai-nilai kebijakan bisnis (DEC-001 s.d. DEC-024) dan isu terbuka (OPEN-016 s.d. OPEN-018).
Semua nilai dapat dioverride melalui environment variable untuk fleksibilitas operasional.
"""
import os

# ==============================================================================
# KEBIJAKAN PEMINJAMAN & PENGEMBALIAN (DEC-005, 4.6)
# ==============================================================================

# Durasi pinjam awal: 7 hari = 168 jam (DEC-005)
LOAN_HOURS = int(os.environ.get('POLICY_LOAN_HOURS', 168))

# Durasi perpanjangan: 7 hari (DEC-005)
EXTEND_DAYS = int(os.environ.get('POLICY_EXTEND_DAYS', 7))

# Batas maksimal perpanjangan per eksemplar: 1 kali (DEC-005)
MAX_EXTENSIONS = int(os.environ.get('POLICY_MAX_EXTENSIONS', 1))

# Batas keterlambatan serius: 7 hari setelah jatuh tempo (4.6, 7.3)
SERIOUS_OVERDUE_DAYS = int(os.environ.get('POLICY_SERIOUS_OVERDUE_DAYS', 7))

# ==============================================================================
# KEBIJAKAN ISU TERBUKA (OPEN-016, OPEN-017, OPEN-018)
# Dilarang ditebak secara hardcode; implementasikan sebagai configurable policy.
# ==============================================================================

# OPEN-017: Apakah buku yang sudah melewati jatuh tempo masih boleh diperpanjang?
# Default: False (perpanjangan hanya sebelum jatuh tempo; jika lewat harus dikembalikan).
ALLOW_RENEW_AFTER_DUE = os.environ.get('POLICY_ALLOW_RENEW_AFTER_DUE', 'false').strip().lower() in ('1', 'true', 'yes')

# OPEN-018: Rentang jam untuk mengelompokkan buku yang dipinjam bersamaan saat sesi pengembalian
# Default: 24 jam.
GROUP_WINDOW_HOURS = int(os.environ.get('POLICY_GROUP_WINDOW_HOURS', 24))

# OPEN-016: Format tampilan nama peminjam pada halaman notifikasi keterlambatan in-app publik
# Opsi: "full" (nama lengkap per DEC-017 untuk akuntabilitas sosial) atau "truncated" (misal: "Ahmad S***")
# Default: "full".
NOTIF_NAME_MODE = os.environ.get('POLICY_NOTIF_NAME_MODE', 'full').strip().lower()

# OPEN-018 / 7.3: Mode pemblokiran akun peminjam
# Opsi: "serious_only" (blokir jika telat > 7 hari atau ada ganti rugi pending) atau "any_overdue"
# Default: "serious_only".
BLOCK_MODE = os.environ.get('POLICY_BLOCK_MODE', 'serious_only').strip().lower()

# ==============================================================================
# KEBIJAKAN AUTENTIKASI & SESI ADMIN (TASK 3-01)
# ==============================================================================

# Batas umur sesi absolut (session lifetime): 8 jam (rentang hari sekolah)
ADMIN_SESSION_LIFETIME_HOURS = int(os.environ.get('POLICY_ADMIN_SESSION_LIFETIME_HOURS', 8))

# Batas ketidakaktifan (idle timeout): 120 menit (2 jam)
ADMIN_IDLE_TIMEOUT_MINUTES = int(os.environ.get('POLICY_ADMIN_IDLE_TIMEOUT_MINUTES', 120))

# ==============================================================================
# KEBIJAKAN KATALOG & PENAMBAHAN BUKU (TASK 3-02, DEC-004, DEC-013)
# ==============================================================================

# Ambang batas jumlah eksemplar yang mewajibkan konfirmasi pengetikan ulang (>100)
CONFIRMATION_THRESHOLD_COPIES = int(os.environ.get('POLICY_CONFIRMATION_THRESHOLD_COPIES', 100))

# Batas maksimum jumlah eksemplar dalam satu penambahan (proteksi beban sistem / input ekstrem)
MAX_COPIES_PER_ADD = int(os.environ.get('POLICY_MAX_COPIES_PER_ADD', 1000))

# Masa berlaku token konfirmasi sekali pakai (detik): default 15 menit = 900 detik (TASK 3-03)
CONFIRMATION_TOKEN_TTL_SECONDS = int(os.environ.get('POLICY_CONFIRMATION_TOKEN_TTL_SECONDS', 900))

# ==============================================================================
# KEBIJAKAN IMPOR KATALOG CSV (TASK 3-05, TASK 3-06, TASK 3-07)
# ==============================================================================

# Batas maksimum ukuran file unggahan CSV impor katalog: default 2 MiB (2 * 1024 * 1024 bytes)
MAX_CATALOG_IMPORT_FILE_SIZE_BYTES = int(os.environ.get('POLICY_MAX_CATALOG_IMPORT_FILE_SIZE_BYTES', 2 * 1024 * 1024))

# Batas maksimum baris data CSV yang diproses dalam satu kali unggahan (Task 3-06)
MAX_CATALOG_IMPORT_ROWS = int(os.environ.get('POLICY_MAX_CATALOG_IMPORT_ROWS', 1000))

# ==============================================================================
# KEBIJAKAN UPLOAD COVER BUKU (TASK 3-11)
# ==============================================================================

# Batas maksimum ukuran file unggahan gambar cover: default 2 MiB (2 * 1024 * 1024 bytes)
MAX_COVER_IMAGE_SIZE_BYTES = int(os.environ.get('POLICY_MAX_COVER_IMAGE_SIZE_BYTES', 2 * 1024 * 1024))

# Ekstensi file gambar cover yang didukung
ALLOWED_COVER_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp', 'gif')

# MIME types gambar yang diizinkan
ALLOWED_COVER_MIMETYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')

# ==============================================================================
# KEBIJAKAN PENCARIAN KATALOG PUBLIK (TASK 3-12)
# ==============================================================================

# Batas maksimum panjang string input pencarian (karakter): default 200 karakter
MAX_CATALOG_SEARCH_QUERY_LENGTH = int(os.environ.get('POLICY_MAX_CATALOG_SEARCH_QUERY_LENGTH', 200))

# Batas default dan maksimum jumlah hasil katalog per halaman
DEFAULT_CATALOG_PAGE_SIZE = int(os.environ.get('POLICY_DEFAULT_CATALOG_PAGE_SIZE', 50))
MAX_CATALOG_PAGE_SIZE = int(os.environ.get('POLICY_MAX_CATALOG_PAGE_SIZE', 200))

# ==============================================================================
# KEBIJAKAN TOKEN QR ANGGOTA (TASK 4-01, DEC-010, LIB-QR-001)
# ==============================================================================

# Pemisah komponen token QR anggota (member_id:qr_version:signature)
MEMBER_TOKEN_DELIMITER = ":"

# Panjang tanda tangan heksadesimal HMAC-SHA256 (64 karakter)
MEMBER_TOKEN_SIG_LENGTH = 64

# Batas maksimum panjang string token QR anggota (proteksi DOS / input ekstrem)
MAX_MEMBER_TOKEN_LENGTH = int(os.environ.get('POLICY_MAX_MEMBER_TOKEN_LENGTH', 256))

# ==============================================================================
# KEBIJAKAN KATEGORI & PENCARIAN ANGGOTA ADMIN (TASK 4-02, DEC-023)
# ==============================================================================

# Batas maksimum panjang string kueri pencarian anggota (karakter)
MAX_MEMBER_SEARCH_QUERY_LENGTH = int(os.environ.get('POLICY_MAX_MEMBER_SEARCH_QUERY_LENGTH', 100))

# Batas default dan maksimum jumlah anggota per halaman pada antarmuka admin
DEFAULT_MEMBER_PAGE_SIZE = int(os.environ.get('POLICY_DEFAULT_MEMBER_PAGE_SIZE', 20))
MAX_MEMBER_PAGE_SIZE = int(os.environ.get('POLICY_MAX_MEMBER_PAGE_SIZE', 100))

# Definisi resmi 5 kategori anggota (Task 4-02 & MIGRASI_F1B)
OFFICIAL_MEMBER_CATEGORIES = (
    ("MC-MURID", "murid", "Siswa / Murid berdasarkan jurusan"),
    ("MC-GURU-JUR", "guru_jurusan", "Guru kejuruan berdasarkan program keahlian"),
    ("MC-GURU-UMUM", "guru_umum", "Guru mata pelajaran umum"),
    ("MC-STAF", "staf", "Tenaga kependidikan / staf tata usaha"),
    ("MC-TEKNISI", "teknisi", "Laboran / teknisi bengkel/lab"),
)

# ==============================================================================
# KEBIJAKAN IMPOR ANGGOTA CSV (TASK 4-03, TASK 4-04, TASK 4-05, DEC-023)
# ==============================================================================

# Batas maksimum ukuran file unggahan CSV impor anggota: default 2 MiB (2 * 1024 * 1024 bytes)
MAX_MEMBER_IMPORT_FILE_SIZE_BYTES = int(os.environ.get('POLICY_MAX_MEMBER_IMPORT_FILE_SIZE_BYTES', 2 * 1024 * 1024))

# Batas maksimum baris data CSV anggota yang diproses dalam satu kali unggahan (Task 4-03 / Task 4-05: sanggup >1.000 baris)
MAX_MEMBER_IMPORT_ROWS = int(os.environ.get('POLICY_MAX_MEMBER_IMPORT_ROWS', 2000))

# Nama file template CSV impor anggota standar
MEMBER_IMPORT_FILENAME = "template_impor_anggota.csv"

# Header resmi standar template impor anggota
MEMBER_IMPORT_HEADERS = ("nama", "jenis", "keterangan", "status", "id_anggota")

# Kolom wajib yang harus ada dalam header file impor anggota
MEMBER_REQUIRED_HEADERS = ("nama", "jenis")

# Daftar nama kolom yang diabaikan sesuai kebijakan privasi DEC-023 (tanpa kelas, tanpa telepon)
MEMBER_IGNORED_COLUMN_NAMES = (
    "kelas", "rombel", "tingkat", "class",
    "telepon", "no_telepon", "no_hp", "hp", "telp", "wa", "kontak", "phone", "nomor_telepon", "nomor_hp",
)

# Status klasifikasi pencocokan pratinjau impor anggota (Task 4-04, OPEN-011)
MEMBER_MATCH_STATUSES = ("BARU", "PEMBARUAN", "KEMUNGKINAN_SAMA", "AMBIGU", "TIDAK_DITEMUKAN", "ERROR")

# Pilihan keputusan petugas per baris pada pratinjau impor anggota
MEMBER_ACTION_CHOICES = ("BUAT_BARU", "PERBARUI", "PILIH_KANDIDAT", "LEWATI")

# Batasan alasan perubahan status anggota (Task 4-06, DEC-020)
MIN_MEMBER_STATUS_REASON_LENGTH = int(os.environ.get('POLICY_MIN_MEMBER_STATUS_REASON_LENGTH', 5))
MAX_MEMBER_STATUS_REASON_LENGTH = int(os.environ.get('POLICY_MAX_MEMBER_STATUS_REASON_LENGTH', 500))
OFFICIAL_MEMBER_STATUSES = ("aktif", "nonaktif")

# Batasan alasan pencabutan & penerbitan ulang kartu QR anggota (Task 4-07, LIB-QR-001)
MIN_MEMBER_QR_REISSUE_REASON_LENGTH = int(os.environ.get('POLICY_MIN_MEMBER_QR_REISSUE_REASON_LENGTH', 5))
MAX_MEMBER_QR_REISSUE_REASON_LENGTH = int(os.environ.get('POLICY_MAX_MEMBER_QR_REISSUE_REASON_LENGTH', 500))



