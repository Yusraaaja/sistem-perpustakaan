from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import pandas as pd
import json

app = Flask(__name__)
app.secret_key = 'kuncirahasia'

# Data login admin
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = '123' 

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Selamat datang, Admin!', 'success')
            return redirect(url_for('koleksi_lengkap'))
        else:
            flash('Username atau password salah!', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Anda telah keluar.', 'info')
    return redirect(url_for('index'))

# Konfigurasi unggahan file
UPLOAD_FOLDER = 'static/covers' # Folder tempat menyimpan gambar
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} # Ekstensi file yang diizinkan

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'supersecretkey' # Diperlukan untuk flash message

# Pastikan folder unggahan ada
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    # Mengambil jalur folder tempat app.py berada
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'perpustakaan.db')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def cari_buku():
    query = request.args.get('query')
    results = []
    if query:
        conn = get_db_connection()
        results = conn.execute('SELECT * FROM buku WHERE judul LIKE ?', ('%' + query + '%',)).fetchall()
        conn.close()
    return render_template('index.html', query=query, results=results)

@app.route('/add', methods=['POST'])
def tambah_buku():
    if not session.get('logged_in'): # Tambahkan ini
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    judul = request.form.get('judul')
    penulis = request.form.get('penulis')
    kategori = request.form.get('kategori')
    kode_rak = request.form.get('kode_rak')
    baris_rak = request.form.get('baris_rak')
    stok = request.form.get('stok')
    # Ambil tanggal hari ini secara otomatis
    tgl_masuk = datetime.now().strftime('%Y-%m-%d')

    if judul:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO buku (judul, penulis, kategori, kode_rak, baris_rak, stok, tanggal_masuk)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (judul, penulis, kategori, kode_rak, baris_rak, stok, tgl_masuk))
        conn.commit()
        conn.close()
    return redirect(url_for('koleksi_lengkap'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_buku(id):
    if not session.get('logged_in'): # Tambahkan ini
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM buku WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        conn.execute('''
            UPDATE buku SET judul=?, penulis=?, kategori=?, kode_rak=?, baris_rak=?, stok=?
            WHERE id=?
        ''', (request.form['judul'], request.form['penulis'], request.form['kategori'], 
              request.form['kode_rak'], request.form['baris_rak'], request.form['stok'], id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    conn.close()
    return render_template('edit.html', buku=book)

# UPDATE FUNGSI HAPUS: Supaya tetap di halaman terakhir
@app.route('/delete/<int:id>')
def hapus_buku(id):

    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM buku WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    # Ambil URL halaman sebelumnya (referrer)
    # Jika tidak ada, default kembali ke koleksi_lengkap
    prev_page = request.referrer
    if prev_page and '/koleksi' in prev_page:
        return redirect(url_for('koleksi_lengkap'))
    return redirect(url_for('index'))

# UPDATE FUNGSI DETAIL: Mengirim data asal halaman
@app.route('/buku/<int:id>')
def detail_buku(id):
    conn = get_db_connection()
    buku = conn.execute('SELECT * FROM buku WHERE id = ?', (id,)).fetchone()
    conn.close()
    
    # Deteksi apakah datang dari database atau pencarian
    back_url = request.referrer if request.referrer else url_for('index')
    
    return render_template('detail_buku.html', buku=buku, back_url=back_url)

# Rute Upload Gambar
@app.route('/buku/<int:id>/upload_cover', methods=['POST'])
def upload_cover(id):
    if not session.get('logged_in'):
        flash('Akses ditolak! Anda harus login sebagai admin.', 'danger')
        return redirect(url_for('detail_buku', id=id))

    if 'cover_file' not in request.files:
        flash('Tidak ada file yang dipilih', 'danger')
        return redirect(url_for('detail_buku', id=id))
    
    file = request.files['cover_file']
    
    if file.filename == '':
        flash('Tidak ada file yang dipilih', 'danger')
        return redirect(url_for('detail_buku', id=id))
    
    if file and allowed_file(file.filename):
        # Amankan nama file dan tambahkan ID buku agar unik
        filename = secure_filename(file.filename)
        unique_filename = f"buku_{id}_{filename}"
        
        # Simpan file ke folder static/covers
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        
        # Update nama file ke database
        conn = get_db_connection()
        conn.execute('UPDATE buku SET cover_img = ? WHERE id = ?', (unique_filename, id))
        conn.commit()
        conn.close()
        
        flash('Cover buku berhasil diunggah!', 'success')
    else:
        flash('Tipe file tidak diizinkan. Gunakan PNG, JPG, JPEG, atau GIF.', 'danger')
        
    return redirect(url_for('detail_buku', id=id))

@app.route('/pinjam/<int:id>', methods=['POST'])
def pinjam_buku(id):
    tipe = request.form.get('tipe_user')
    nama = request.form.get('nama_peminjam')
    kelas = request.form.get('kelas', '-')
    jurusan = request.form.get('jurusan', '-')
    tgl_pinjam = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    buku = conn.execute('SELECT stok FROM buku WHERE id = ?', (id,)).fetchone()
    
    if buku and buku['stok'] > 0:
        conn.execute('''
            INSERT INTO peminjaman (id_buku, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (id, nama, tipe, kelas, jurusan, tgl_pinjam, 'Dipinjam'))
        conn.execute('UPDATE buku SET stok = stok - 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/peminjaman')
def daftar_peminjaman():
    if not session.get('logged_in'): # Tambahkan ini
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    peminjaman_data = conn.execute('''
        SELECT p.id, b.judul, p.id_anggota as nama, p.tipe_user, p.kelas, p.jurusan, p.tgl_pinjam, p.status
        FROM peminjaman p
        JOIN buku b ON p.id_buku = b.id
        ORDER BY p.tgl_pinjam DESC
    ''').fetchall()
    conn.close()

    # Logika Python untuk deteksi keterlambatan (> 7 hari)
    peminjaman_final = []
    tgl_sekarang = datetime.now().date()

    for row in peminjaman_data:
        p = dict(row)
        tgl_pinjam = datetime.strptime(p['tgl_pinjam'], '%Y-%m-%d').date()
        selisih = (tgl_sekarang - tgl_pinjam).days
        
        # Tambahkan flag terlambat jika status masih 'Dipinjam' dan lewat 7 hari
        p['terlambat'] = True if selisih > 7 and p['status'] == 'Dipinjam' else False
        p['durasi'] = selisih
        peminjaman_final.append(p)

    return render_template('peminjaman.html', peminjaman=peminjaman_final)

@app.route('/return/<int:peminjaman_id>')
def kembali_buku(peminjaman_id):
    conn = get_db_connection()
    peminjaman = conn.execute('SELECT id_buku FROM peminjaman WHERE id = ?', (peminjaman_id,)).fetchone()
    if peminjaman:
        conn.execute('UPDATE peminjaman SET status = ? WHERE id = ?', ('Kembali', peminjaman_id))
        conn.execute('UPDATE buku SET stok = stok + 1 WHERE id = ?', (peminjaman['id_buku'],))
        conn.commit()
    conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/koleksi')
def koleksi_lengkap():
    # if not session.get('logged_in'):
       # return redirect(url_for('login'))
        
    conn = get_db_connection()
    all_books = conn.execute('SELECT * FROM buku ORDER BY id DESC').fetchall()
    
    # Statistik Dasar
    total_judul = conn.execute('SELECT COUNT(*) FROM buku').fetchone()[0]
    total_dipinjam = conn.execute('SELECT COUNT(*) FROM peminjaman WHERE status = "Dipinjam"').fetchone()[0]

    top_kategori = conn.execute('''
        SELECT kategori, COUNT(*) as jumlah 
        FROM buku 
        GROUP BY kategori 
        ORDER BY jumlah DESC LIMIT 1
    ''').fetchone()
    
    # Data untuk Grafik: Menghitung jumlah buku per kategori
    query_chart = conn.execute('SELECT kategori, COUNT(*) as jumlah FROM buku GROUP BY kategori').fetchall()
    
    # Ubah ke format list agar bisa dibaca JavaScript
    labels = [row['kategori'] for row in query_chart]
    values = [row['jumlah'] for row in query_chart]
    
    conn.close()
    
    return render_template('koleksi.html', 
                           books=all_books, 
                           total_judul=total_judul,
                           total_dipinjam=total_dipinjam,
                           top_kategori=top_kategori['kategori'] if top_kategori else '-',
                           labels=json.dumps(labels), # Kirim sebagai JSON
                           values=json.dumps(values)) # Kirim sebagai JSON

@app.route('/search_database')
def search_database():
    query = request.args.get('query')
    results = []
    if query:
        conn = get_db_connection()
        # Mencari buku dan menampilkan hasilnya di format tabel koleksi
        results = conn.execute('SELECT * FROM buku WHERE judul LIKE ? OR penulis LIKE ?', 
                               ('%' + query + '%', '%' + query + '%')).fetchall()
        conn.close()
    
    # Kita kirim hasil pencarian ke koleksi.html menggunakan variabel 'books'
    return render_template('koleksi.html', books=results, query=query)

import pandas as pd # Tambahkan import ini di bagian atas app.py

@app.route('/export_peminjaman')
def export_peminjaman():
    # Pastikan hanya admin yang bisa download laporan
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Ambil data peminjaman lengkap dengan judul buku
    query = '''
        SELECT p.tgl_pinjam, p.id_anggota as Nama_Peminjam, p.tipe_user, 
               p.kelas, p.jurusan, b.judul as Judul_Buku, p.status
        FROM peminjaman p
        JOIN buku b ON p.id_buku = b.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Tentukan nama file
    file_path = 'static/laporan_peminjaman.xlsx'
    
    # Simpan ke Excel menggunakan pandas
    df.to_excel(file_path, index=False)

    # Kirim file ke browser untuk di-download
    from flask import send_file
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)