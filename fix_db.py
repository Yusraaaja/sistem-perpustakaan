import sqlite3

def fix_database():
    conn = sqlite3.connect('perpustakaan.db')
    cursor = conn.cursor()
    
    print("Memperbarui struktur database...")
    
    # Menambah kolom tanggal_masuk jika belum ada
    try:
        cursor.execute("ALTER TABLE buku ADD COLUMN tanggal_masuk DATE")
        print("- Kolom 'tanggal_masuk' berhasil ditambahkan.")
    except sqlite3.OperationalError:
        print("- Kolom 'tanggal_masuk' sudah ada.")

    # Menambah kolom cover_img jika belum ada
    try:
        cursor.execute("ALTER TABLE buku ADD COLUMN cover_img TEXT")
        print("- Kolom 'cover_img' berhasil ditambahkan.")
    except sqlite3.OperationalError:
        print("- Kolom 'cover_img' sudah ada.")
        
    conn.commit()
    conn.close()
    print("Database siap digunakan kembali!")

if __name__ == '__main__':
    fix_database()