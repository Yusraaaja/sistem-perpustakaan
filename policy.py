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

