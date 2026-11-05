import sqlite3
import re
import datetime
import json
import os
import sys

def parse_registration_from_jurusan(jurusan_str):
    """
    Ekstrak nomor registrasi dan nama jurusan bersih dari format lama '<jurusan> | Reg: <no_reg>'.
    Toleran terhadap variasi spasi atau format case-insensitive.
    Tidak mengarang nomor registrasi jika tidak ada pola 'Reg:'.
    """
    if not jurusan_str:
        return "-", None

    jurusan_str = str(jurusan_str).strip()
    match = re.search(r'\|\s*Reg:\s*([A-Za-z0-9_-]+)', jurusan_str, re.IGNORECASE)
    if match:
        no_reg = match.group(1).strip()
        jurusan_murni = jurusan_str[:match.start()].strip()
        if not jurusan_murni:
            jurusan_murni = "-"
        return jurusan_murni, no_reg

    return jurusan_str, None

def generate_legacy_transaction_code(old_id, tgl_pinjam):
    """Format kode transaksi unik: TRX-YYYYMMDD-XXXX."""
    date_part = tgl_pinjam.replace("-", "") if tgl_pinjam else "HIST"
    return f"TRX-{date_part}-{int(old_id):04d}"

def is_database_migrated(conn):
    """Cek apakah database sudah memiliki schema target peminjaman_detail dan kode_transaksi."""
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if 'peminjaman_detail' not in tables:
        return False

    peminjaman_cols = [r[1] for r in cursor.execute("PRAGMA table_info(peminjaman)").fetchall()]
    return 'kode_transaksi' in peminjaman_cols

def run_migration(db_path, dry_run=False):
    """
    Menjalankan migrasi secara atomik dan idempotent pada db_path.
    Jika terjadi kesalahan sekecil apa pun, rollback dilakukan secara penuh.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database tidak ditemukan: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Cek status idempotensi
    if is_database_migrated(conn):
        print(f"[IDEMPOTENT] Database {db_path} sudah dalam skema target. Tidak ada tindakan migrasi yang dilakukan.")
        conn.close()
        return {
            'status': 'already_migrated',
            'headers_migrated': 0,
            'details_migrated': 0
        }

    print(f"[*] Memulai migrasi database pada: {db_path}")

    try:
        # SQLite Best Practice: Matikan foreign keys di luar transaksi sebelum rekonstruksi tabel
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Gunakan transaksi eksplisit
        cursor.execute("BEGIN TRANSACTION")

        # Ambil data peminjaman lama
        old_loans = cursor.execute("""
            SELECT id, id_buku, id_anggota, tipe_user, kelas, jurusan,
                   tgl_pinjam, tgl_kembali_seharusnya, tgl_dikembalikan, status, denda
            FROM peminjaman
            ORDER BY id ASC
        """).fetchall()

        print(f"[*] Membaca {len(old_loans)} data transaksi peminjaman lama.")

        # Ambil inventaris buku untuk referensi validitas
        existing_books = {r['id']: dict(r) for r in cursor.execute("SELECT id, judul, stok, id_buku_fisik FROM buku").fetchall()}

        # 2. Buat tabel target baru
        cursor.execute("""
            CREATE TABLE peminjaman_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode_transaksi TEXT UNIQUE NOT NULL,
                id_anggota TEXT NOT NULL,
                tipe_user TEXT DEFAULT 'Siswa',
                kelas TEXT DEFAULT '-',
                jurusan TEXT DEFAULT '-',
                jurusan_asli TEXT,
                tgl_pinjam TEXT NOT NULL,
                tgl_kembali_seharusnya TEXT NOT NULL,
                status TEXT DEFAULT 'Dipinjam',
                total_denda INTEGER DEFAULT 0,
                denda_historis_asli INTEGER DEFAULT 0,
                catatan TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE peminjaman_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_peminjaman INTEGER NOT NULL,
                id_buku INTEGER NOT NULL,
                no_registrasi TEXT,
                status TEXT DEFAULT 'Dipinjam',
                tgl_dikembalikan TEXT,
                denda_keterlambatan INTEGER DEFAULT 0,
                denda_kondisi INTEGER DEFAULT 0,
                status_penggantian TEXT DEFAULT 'Tidak Perlu',
                catatan_penggantian TEXT,
                catatan TEXT,
                FOREIGN KEY(id_peminjaman) REFERENCES peminjaman_new(id) ON DELETE CASCADE,
                FOREIGN KEY(id_buku) REFERENCES buku(id)
            )
        """)

        headers_count = 0
        details_count = 0

        for row in old_loans:
            old_id = row['id']
            old_id_buku = row['id_buku']
            old_jurusan = row['jurusan'] or '-'
            old_status = (row['status'] or 'Dipinjam').strip()
            old_denda = row['denda'] or 0

            # Validasi FK buku
            if old_id_buku not in existing_books:
                raise ValueError(f"Integritas data gagal: id_buku {old_id_buku} pada peminjaman {old_id} tidak ada di tabel buku!")

            # Parsing jurusan dan no registrasi secara toleran
            jurusan_bersih, no_reg = parse_registration_from_jurusan(old_jurusan)

            # Mapping status historis
            # Jika status 'Selesai' / 'Kembali' -> Header 'Selesai', Detail 'Kembali'
            # Jika status 'Dipinjam' -> Header 'Dipinjam', Detail 'Dipinjam'
            # Jika status 'Rusak' -> Header 'Selesai', Detail 'Rusak'
            # Jika status 'Hilang' -> Header 'Selesai', Detail 'Hilang'
            # Jika status 'Dibayar/Lunas' -> Header 'Selesai', Detail 'Dibayar/Lunas'
            # Lainnya -> Pertahankan apa adanya
            if old_status in ['Selesai', 'Kembali']:
                header_status = 'Selesai'
                detail_status = 'Kembali'
            elif old_status == 'Dipinjam':
                header_status = 'Dipinjam'
                detail_status = 'Dipinjam'
            elif old_status == 'Rusak':
                header_status = 'Selesai'
                detail_status = 'Rusak'
            elif old_status == 'Hilang':
                header_status = 'Selesai'
                detail_status = 'Hilang'
            elif old_status in ['Dibayar/Lunas', 'Lunas']:
                header_status = 'Selesai'
                detail_status = old_status
            else:
                header_status = old_status
                detail_status = old_status

            kode_trx = generate_legacy_transaction_code(old_id, row['tgl_pinjam'])

            catatan_migrasi = None
            if not no_reg:
                catatan_migrasi = "Nomor registrasi fisik tidak ditemukan pada kolom jurusan historis."

            # Insert Header (mempertahankan ID historis!)
            cursor.execute("""
                INSERT INTO peminjaman_new (
                    id, kode_transaksi, id_anggota, tipe_user, kelas, jurusan,
                    jurusan_asli, tgl_pinjam, tgl_kembali_seharusnya, status,
                    total_denda, denda_historis_asli, catatan
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                old_id, kode_trx, row['id_anggota'], row['tipe_user'], row['kelas'],
                jurusan_bersih, old_jurusan, row['tgl_pinjam'], row['tgl_kembali_seharusnya'],
                header_status, old_denda, old_denda, "Migrasi otomatis P1 dari skema peminjaman v1"
            ))
            headers_count += 1

            # Insert Detail
            cursor.execute("""
                INSERT INTO peminjaman_detail (
                    id_peminjaman, id_buku, no_registrasi, status, tgl_dikembalikan,
                    denda_keterlambatan, denda_kondisi, status_penggantian, catatan
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                old_id, old_id_buku, no_reg, detail_status, row['tgl_dikembalikan'],
                0, 0, 'Tidak Perlu', catatan_migrasi
            ))
            details_count += 1

        # Ganti tabel peminjaman lama dengan peminjaman_new
        cursor.execute("DROP TABLE peminjaman")
        cursor.execute("ALTER TABLE peminjaman_new RENAME TO peminjaman")

        # Buat indeks pendukung performa
        cursor.execute("CREATE INDEX idx_peminjaman_detail_peminjaman ON peminjaman_detail(id_peminjaman)")
        cursor.execute("CREATE INDEX idx_peminjaman_detail_buku ON peminjaman_detail(id_buku)")
        cursor.execute("CREATE INDEX idx_peminjaman_detail_status ON peminjaman_detail(status)")
        cursor.execute("CREATE INDEX idx_peminjaman_detail_no_reg ON peminjaman_detail(no_registrasi)")

        # Validasi integritas Foreign Key sebelum COMMIT
        fk_violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise ValueError(f"Pelanggaran Foreign Key terdeteksi setelah migrasi: {fk_violations}")

        if dry_run:
            cursor.execute("ROLLBACK")
            print("[DRY-RUN] Migrasi berhasil divalidasi tetapi di-rollback sesuai permintaan dry_run.")
            status = 'dry_run_success'
        else:
            cursor.execute("COMMIT")
            print(f"[SUCCESS] Migrasi selesai. {headers_count} header dan {details_count} detail tersimpan.")
            status = 'success'

        # Aktifkan kembali Foreign Keys di luar transaksi
        cursor.execute("PRAGMA foreign_keys = ON")

        return {
            'status': status,
            'headers_migrated': headers_count,
            'details_migrated': details_count
        }

    except Exception as e:
        cursor.execute("ROLLBACK")
        cursor.execute("PRAGMA foreign_keys = ON")
        print(f"[ERROR] Migrasi gagal dan di-rollback: {str(e)}")
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Penggunaan: python migrate_p1_multibook.py <path_database> [--dry-run]")
        sys.exit(1)

    target_db = sys.argv[1]
    is_dry = '--dry-run' in sys.argv
    res = run_migration(target_db, dry_run=is_dry)
    print(res)

