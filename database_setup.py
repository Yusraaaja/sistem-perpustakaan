import sqlite3
import os

def inisialisasi_db():
    # Koneksi ke database secara otomatis
    conn = sqlite3.connect('perpustakaan.db')
    cursor = conn.cursor()

    # 1. Tabel buku
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buku (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            judul TEXT NOT NULL,
            penulis TEXT,
            kategori TEXT,
            kode_rak TEXT, -- A (Rak Besar)
            baris_rak INTEGER, -- 1 (Barisan rak dari paling atas)
            stok INTEGER DEFAULT 1,
            tanggal_masuk DATE,
            cover_img TEXT
        )
    ''')

    # 3. Tabel Transaksi (Peminjaman buku)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS peminjaman (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_buku INTEGER,
            id_anggota INTEGER,
            tipe_user TEXT,
            kelas TEXT,
            jurusan TEXT,
            tgl_pinjam DATE,
            tgl_kembali DATE,
            status TEXT DEFAULT 'Dipinjam',
            FOREIGN KEY (id_buku) REFERENCES buku (id),
            FOREIGN KEY (id_anggota) REFERENCES anggota (id)
        )
    ''')

    # Data Dummy Untuk Testing
    buku_dummy = [
        ('Atomic Habits', 'James Clear', 'Pengembangan Diri', 'A', 1, 5),
        ('Filosofi Teras', 'Henry Manampiring', 'Pengembangan Diri', 'A', 2, 3),
        ('Clean Code', 'Robert C. Martin', 'Teknologi', 'B', 1, 2),
        ('Laskar Pelangi', 'Andrea Hirata', 'Fiksi', 'C', 3, 4)
    ]

    cursor.executemany('INSERT INTO buku (judul, penulis, kategori, kode_rak, baris_rak, stok) VALUES (?,?,?,?,?,?)', buku_dummy)

    conn.commit()
    conn.close()
    print("Database Berhasil Dibuat dan Data Dummy Dimasukkan!")

if __name__ == "__main__":
    inisialisasi_db()

def update_db():
    conn = sqlite3.connect('perpustakaan.db')
    cursor = conn.cursor()
    
    # Tambah kolom di tabel buku (jika belum ada)
    try:
        cursor.execute("ALTER TABLE buku ADD COLUMN tanggal_masuk DATE DEFAULT CURRENT_DATE")
    except: pass # Lewati jika kolom sudah ada

    # Tambah kolom di tabel peminjaman
    try:
        cursor.execute("ALTER TABLE peminjaman ADD COLUMN tipe_user TEXT")
        cursor.execute("ALTER TABLE peminjaman ADD COLUMN kelas TEXT")
        cursor.execute("ALTER TABLE peminjaman ADD COLUMN jurusan TEXT")
    except: pass
    
    conn.commit()
    conn.close()

update_db()