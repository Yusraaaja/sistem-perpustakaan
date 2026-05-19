from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime, timedelta
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

@app.route('/add', methods=['GET', 'POST'])
def tambah_buku():
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        # 1. Mengambil Data Umum Buku
        judul = request.form.get('judul')
        sub_judul = request.form.get('sub_judul', '')
        penulis = request.form.get('penulis')
        penerbit = request.form.get('penerbit')
        tahun_terbit = request.form.get('tahun_terbit')
        isbn = request.form.get('isbn')
        kategori = request.form.get('kategori')
        sinopsis = request.form.get('sinopsis')
        
        # 2. Mengambil Data Inventaris Internal (Form Baru)
        id_buku_fisik = request.form.get('id_buku_fisik')
        nomor_panggil = request.form.get('nomor_panggil')
        lokasi_rak = request.form.get('lokasi_rak')
        sumber_perolehan = request.form.get('sumber_perolehan')
        tanggal_masuk = request.form.get('tanggal_masuk', datetime.now().strftime('%Y-%m-%d'))
        kondisi_buku = request.form.get('kondisi_buku', 'Baik')
        
        # Penanganan data angka (Harga & Stok)
        harga_input = request.form.get('harga_buku')
        harga_buku = int(harga_input) if harga_input else 0
        
        stok_input = request.form.get('stok')
        stok = int(stok_input) if stok_input else 1

        # 3. Proses Unggah Cover Buku
        file = request.files.get('cover_img')
        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # 4. Simpan ke Database perpustakaan.db
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO buku (
                    judul, sub_judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis, cover_img,
                    id_buku_fisik, nomor_panggil, lokasi_rak, sumber_perolehan, tanggal_masuk, kondisi_buku, harga_buku, stok
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                judul, sub_judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis, filename,
                id_buku_fisik, nomor_panggil, lokasi_rak, sumber_perolehan, tanggal_masuk, kondisi_buku, harga_buku, stok
            ))
            conn.commit()
            flash('Buku baru beserta data inventaris berhasil ditambahkan!', 'success')
        except sqlite3.IntegrityError:
            flash('Gagal! Barcode / ID Buku Fisik sudah terdaftar di sistem.', 'danger')
        finally:
            conn.close()
            
        return redirect(url_for('koleksi_lengkap'))
        
    # Jika sekiranya ada yang mengakses /add via GET langsung
    return redirect(url_for('koleksi_lengkap'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_buku(id):
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    buku = conn.execute('SELECT * FROM buku WHERE id = ?', (id,)).fetchone()
    
    if buku is None:
        conn.close()
        flash('Data buku tidak ditemukan!', 'danger')
        return redirect(url_for('koleksi_lengkap'))

    if request.method == 'GET':
        # Mengambil URL halaman sebelumnya secara dinamis, jika tidak terdeteksi default ke /koleksi
        back_url = request.referrer or url_for('koleksi_lengkap')
        conn.close()
        return render_template('edit.html', buku=buku, back_url=back_url)
        
    if request.method == 'POST':
        judul = request.form.get('judul')
        sub_judul = request.form.get('sub_judul', '')
        penulis = request.form.get('penulis')
        penerbit = request.form.get('penerbit')
        tahun_terbit = request.form.get('tahun_terbit')
        isbn = request.form.get('isbn')
        kategori = request.form.get('kategori')
        sinopsis = request.form.get('sinopsis')
        kondisi_buku = request.form.get('kondisi_buku', 'Baik')
        nomor_panggil = request.form.get('nomor_panggil')
        lokasi_rak = request.form.get('lokasi_rak')
        
        harga_input = request.form.get('harga_buku')
        harga_buku = int(harga_input) if harga_input else 0
        
        stok_input = request.form.get('stok')
        stok = int(stok_input) if stok_input else 1
        
        # Ambil kembali back_url yang dikirim tersembunyi dari form HTML
        back_url_post = request.form.get('back_url') or url_for('koleksi_lengkap')

        try:
            conn.execute('''
                UPDATE buku SET 
                    judul=?, sub_judul=?, penulis=?, penerbit=?, tahun_terbit=?, isbn=?, kategori=?, sinopsis=?,
                    kondisi_buku=?, nomor_panggil=?, lokasi_rak=?, harga_buku=?, stok=?
                WHERE id=?
            ''', (judul, sub_judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis,
                  kondisi_buku, nomor_panggil, lokasi_rak, harga_buku, stok, id))
            conn.commit()
            flash('Data logistik aset buku berhasil diperbarui!', 'success')
        except sqlite3.Error as e:
            flash(f'Gagal memperbarui data: {str(e)}', 'danger')
        finally:
            conn.close()
            
        # Mengembalikan admin ke halaman asal klik tadi setelah berhasil menyimpan data
        return redirect(back_url_post)

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

@app.route('/pinjam/<int:buku_id>', methods=['POST'])
def pinjam_buku(buku_id):
    nama = request.form.get('nama_peminjam')
    tipe_user = request.form.get('tipe_user')
    kelas = request.form.get('kelas', '-')
    jurusan = request.form.get('jurusan', '-')
    
    # Menangkap durasi dinamis (7 atau 14 hari) dari formulir baru
    durasi_input = request.form.get('durasi_pinjam')
    durasi = int(durasi_input) if durasi_input else 14
    
    tgl_sekarang = datetime.now()
    tgl_pinjam_str = tgl_sekarang.strftime('%Y-%m-%d')
    tgl_kembali_str = (tgl_sekarang + timedelta(days=durasi)).strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    buku = conn.execute('SELECT stok FROM buku WHERE id = ?', (buku_id,)).fetchone()
    
    if buku and buku['stok'] > 0:
        # Kurangi stok buku di rak
        conn.execute('UPDATE buku SET stok = stok - 1 WHERE id = ?', (buku_id,))
        # Simpan data transaksi ke database
        conn.execute('''
            INSERT INTO peminjaman (id_buku, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, tgl_kembali_seharusnya, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (buku_id, nama, tipe_user, kelas, jurusan, tgl_pinjam_str, tgl_kembali_str, 'Dipinjam'))
        conn.commit()
        flash('Buku berhasil dipinjam! Selamat membaca.', 'success')
    else:
        flash('Mohon maaf, stok buku ini sedang kosong.', 'danger')
        
    conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/peminjaman')
def daftar_peminjaman():
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # Menarik seluruh kolom transaksi yang dibutuhkan oleh UI baru
    peminjaman_data = conn.execute('''
        SELECT p.id, b.judul, p.id_anggota as nama, p.tipe_user, p.kelas, p.jurusan, 
               p.tgl_pinjam, p.tgl_kembali_seharusnya, p.tgl_dikembalikan, p.status, p.denda
        FROM peminjaman p
        JOIN buku b ON p.id_buku = b.id
        ORDER BY p.status DESC, p.tgl_pinjam DESC
    ''').fetchall()
    conn.close()

    peminjaman_final = []
    tgl_sekarang = datetime.now().date()

    for row in peminjaman_data:
        p = dict(row)
        
        # Logika menghitung keterlambatan secara riil
        if p['status'] == 'Dipinjam' and p['tgl_kembali_seharusnya']:
            tgl_tenggat = datetime.strptime(p['tgl_kembali_seharusnya'], '%Y-%m-%d').date()
            selisih = (tgl_sekarang - tgl_tenggat).days
            
            if selisih > 0:
                p['terlambat'] = True
                p['durasi_terlambat'] = selisih
            else:
                p['terlambat'] = False
                p['durasi_terlambat'] = 0
        else:
            p['terlambat'] = False
            p['durasi_terlambat'] = 0
            
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

@app.route('/pinjam/<int:buku_id>', methods=['POST'])
def proses_pinjam(buku_id):
    nama = request.form.get('nama_peminjam')
    tipe_user = request.form.get('tipe_user')
    kelas = request.form.get('kelas')
    jurusan = request.form.get('jurusan')
    durasi = int(request.form.get('durasi_pinjam')) # 7 atau 14 hari
    
    tgl_sekarang = datetime.now()
    tgl_pinjam_str = tgl_sekarang.strftime('%Y-%m-%d')
    tgl_kembali_str = (tgl_sekarang + timedelta(days=durasi)).strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    # Cek stok
    buku = conn.execute('SELECT stok FROM buku WHERE id = ?', (buku_id,)).fetchone()
    if buku and buku['stok'] > 0:
        # Kurangi stok dan masukkan data peminjaman
        conn.execute('UPDATE buku SET stok = stok - 1 WHERE id = ?', (buku_id,))
        conn.execute('''
            INSERT INTO peminjaman (id_buku, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, tgl_kembali_seharusnya)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (buku_id, nama, tipe_user, kelas, jurusan, tgl_pinjam_str, tgl_kembali_str))
        conn.commit()
        flash('Buku berhasil dipinjam! Selamat membaca.', 'success')
    else:
        flash('Stok buku kosong!', 'danger')
    conn.close()
    return redirect(url_for('detail_buku', id=buku_id))

@app.route('/kembalikan/<int:pinjam_id>', methods=['POST'])
def proses_kembalikan(pinjam_id):
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))

    status_kembali = request.form.get('status_kembali') # 'Normal', 'Rusak', 'Hilang'
    tgl_sekarang = datetime.now()
    tgl_sekarang_str = tgl_sekarang.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    pinjaman = conn.execute('''
        SELECT p.*, b.harga_buku, b.id as buku_id 
        FROM peminjaman p 
        JOIN buku b ON p.id_buku = b.id 
        WHERE p.id = ?
    ''', (pinjam_id,)).fetchone()
    
    if pinjaman:
        # 1. Hitung denda keterlambatan (Rp 1.000 / hari jika melewati batas seharusnya)
        denda_keterlambatan = 0
        if pinjaman['tgl_kembali_seharusnya']:
            tgl_seharusnya = datetime.strptime(pinjaman['tgl_kembali_seharusnya'], '%Y-%m-%d')
            hari_terlambat = (tgl_sekarang - tgl_seharusnya).days
            if hari_terlambat > 0:
                denda_keterlambatan = hari_terlambat * 1000
            
        # 2. Logika Aturan Opsi A (Buku Rusak / Hilang)
        denda_kondisi = 0
        # Jika kolom harga_buku kosong di db, berikan nilai default 0
        harga_buku_asli = pinjaman['harga_buku'] if pinjaman['harga_buku'] else 0
        
        if status_kembali in ['Rusak', 'Hilang']:
            denda_kondisi = harga_buku_asli  # Membebankan harga buku riil ke denda siswa
            conn.execute('UPDATE buku SET kondisi_buku = ? WHERE id = ?', (status_kembali, pinjaman['buku_id']))
        else:
            # Jika kembali normal, kembalikan 1 eksemplar stok ke rak buku
            conn.execute('UPDATE buku SET stok = stok + 1 WHERE id = ?', (pinjaman['buku_id']))
            
        total_denda = denda_keterlambatan + denda_kondisi
        status_final = f"Selesai ({status_kembali})"
        
        # 3. Kunci data transaksi peminjaman
        conn.execute('''
            UPDATE peminjaman 
            SET tgl_dikembalikan = ?, status = ?, denda = ? 
            WHERE id = ?
        ''', (tgl_sekarang_str, status_final, total_denda, pinjam_id))
        conn.commit()
        
        flash(f'Buku berhasil diproses! Status Fisik: {status_kembali}. Total Akumulasi Denda: Rp {total_denda:,}', 'success')
    
    conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/koleksi')
def koleksi_lengkap():
    # Fitur ini sengaja dibuka untuk umum agar siswa bisa melihat katalog
    conn = get_db_connection()
    
    # Menangani input dari form pencarian (Gabungan dengan fungsi search_database lama)
    query = request.args.get('query', '').strip()
    if query:
        # Jika ada pencarian, filter datanya
        buku = conn.execute('''
            SELECT * FROM buku 
            WHERE judul LIKE ? OR penulis LIKE ? OR id_buku_fisik LIKE ?
            ORDER BY id DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    else:
        # Jika tidak ada pencarian, tampilkan semua
        buku = conn.execute('SELECT * FROM buku ORDER BY id DESC').fetchall()
    
    # 1. Statistik Dasar & Riil
    total_buku = conn.execute('SELECT SUM(stok) FROM buku').fetchone()[0] or 0
    total_judul = conn.execute('SELECT COUNT(*) FROM buku').fetchone()[0] or 0
    total_dipinjam = conn.execute('SELECT COUNT(*) FROM peminjaman WHERE status = "Dipinjam"').fetchone()[0] or 0

    # 2. Data Buku Populer (Paling sering dipinjam)
    buku_populer = conn.execute('''
        SELECT b.judul, b.kategori, COUNT(p.id) as total_dipinjam
        FROM buku b
        JOIN peminjaman p ON b.id = p.id_buku
        GROUP BY b.id
        ORDER BY total_dipinjam DESC
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    # Mengirim semua variabel dengan nama yang tepat ke koleksi.html
    return render_template('koleksi.html', 
                           buku=buku, 
                           query=query,
                           total_buku=total_buku,
                           total_judul=total_judul,
                           total_dipinjam=total_dipinjam,
                           buku_populer=buku_populer)

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

def init_db():
    conn = sqlite3.connect('perpustakaan.db')
    cursor = conn.cursor()
    
    # 1. TABEL BUKU (Katalog & Inventaris Lengkap)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buku (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            -- Data Katalog (Publik)
            judul TEXT NOT NULL,
            sub_judul TEXT,
            penulis TEXT,
            penerbit TEXT,
            tahun_terbit TEXT,
            isbn TEXT,
            kategori TEXT,
            sinopsis TEXT,
            cover_img TEXT,
            -- Data Inventaris (Internal Pustakawan)
            id_buku_fisik TEXT UNIQUE, -- Barcode / ID Unik Eksemplar
            nomor_panggil TEXT,        -- Call Number di Rak
            lokasi_rak TEXT,
            sumber_perolehan TEXT,     -- Pembelian / Hadiah / Sumbangan
            tanggal_masuk TEXT,
            kondisi_buku TEXT DEFAULT 'Baik', -- Baik / Rusak / Hilang
            harga_buku INTEGER DEFAULT 0,     -- Untuk Pelaporan Aset & Denda Opsi A
            stok INTEGER DEFAULT 1
        )
    ''')
    
    # 2. TABEL PEMINJAMAN (Mendukung Batas Waktu & Denda)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS peminjaman (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_buku INTEGER,
            id_anggota TEXT, -- Nama Peminjam
            tipe_user TEXT,  -- Siswa / Guru
            kelas TEXT,
            jurusan TEXT,
            tgl_pinjam TEXT,
            tgl_kembali_seharusnya TEXT,
            tgl_dikembalikan TEXT,
            status TEXT DEFAULT 'Dipinjam', -- Dipinjam / Kembali / Rusak / Hilang
            denda INTEGER DEFAULT 0,
            FOREIGN KEY(id_buku) REFERENCES buku(id)
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    app.run(debug=True)