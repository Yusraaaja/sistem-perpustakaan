from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('perpustakaan.db')
    conn.row_factory = sqlite3.Row # memanggil data dengan nama kolom
    return conn

@app.route('/')
def index():
    return render_template('index.html')

# Rute Pencarian
@app.route('/search')
def search():
    query = request.args.get('query')
    results = []
    if query:
        conn = get_db_connection()
        # mencari buku berdasarkan judul (case insensisive)
        results = conn.execute('SELECT * FROM buku WHERE judul LIKE ?', ('%' + query + '%',)).fetchall()
        conn.close()

    return render_template('index.html', query=query, results=results)

from datetime import datetime, timedelta

# Rute Peminjaman
@app.route('/pinjam', methods=['POST'])
def pinjam():
    id_buku = request.form.get('id_buku')
    nama_peminjam = request.form.get('nama_peminjam')
    nis = request.form.get('nis')

    if id_buku and nama_peminjam:
        conn = get_db_connection()
        # Set tanggal pinjam hari ini dan kembali 7 hari lagi
        tgl_pinjam = datetime.now().strftime('%Y-%m-%d')
        tgl_kembali = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        #Simpan ke tabel peminjaman
        conn.execute('INSERT INTO peminjaman (id_buku, id_anggota, tgl_pinjam, tgl_kembali) VALUES (?, ?, ?, ?)',
                     (id_buku, nama_peminjam, tgl_pinjam, tgl_kembali))
        
        # Kurangi stok buku
        conn.execute('UPDATE buku SET stok = stok - 1 WHERE id = ?', (id_buku,))

        conn.commit()
        conn.close()
        return "Berhasil meminjam! Buku harus kembali dalam 7 hari."
    return "Gagal meminjam, data tidak lengkap."

from flask import redirect, url_for

# Rute tambah buku
@app.route('/add', methods=['POST'])
def add_book():
    # Mengambil data dari form
    judul = request.form.get('judul')
    penulis = request.form.get('penulis')
    kategori = request.form.get('kategori')
    kode_rak = request.form.get('kode_rak')
    baris_rak = request.form.get('baris_rak')
    stok = request.form.get('stok')

    if judul:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO buku (judul, penulis, kategori, kode_rak, baris_rak, stok)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (judul, penulis, kategori, kode_rak, baris_rak, stok))
        conn.commit()
        conn.close()

    return redirect(url_for('index')) # Kembali ke halaman utama setelah disimpan

# Rute Hapus
@app.route('/delete/<int:id>')
def delete_book(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM buku WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# Rute Edit
@app.route('/edit/<int:id>')
def edit_book(id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM buku WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        judul = request.form['judul']
        penulis = request.form['penulis']
        kategori = request.form['kategori']
        kode_rak = request.form['kode_rak']
        baris_rak = request.form['baris_rak']
        stok = request.form['stok']

        conn.execute('''
            UPDATE buku SET judul=?, penulis=?, kategori=?, kode_rak=?, baris_rak=?, stok=?
            WHERE id=?
        ''', (judul, penulis, kategori, kode_rak, baris_rak, stok, id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    conn.close()
    return render_template('edit.html', buku=book)

if __name__ == '__main__':
    app.run(debug=True)