from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import pandas as pd
import json
from io import BytesIO
from flask import send_file

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
            # Notifikasi ini sekarang akan langsung tampil di login.html berkat layout.html global
            flash('Gagal Login! Username atau password salah.', 'danger')
            
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
def search_redirect():
    query = request.args.get('query', '').strip()
    return redirect(url_for('koleksi_lengkap', query=query))

@app.route('/add', methods=['GET', 'POST'])
def tambah_buku():
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        # 1. Mengambil Data Umum Buku (Gunakan default '' jika opsional)
        judul = request.form.get('judul')
        sub_judul = request.form.get('sub_judul', '')
        penulis = request.form.get('penulis')
        penerbit = request.form.get('penerbit', '')
        tahun_terbit = request.form.get('tahun_terbit', '')
        isbn = request.form.get('isbn', '')
        kategori = request.form.get('kategori')
        sinopsis = request.form.get('sinopsis', '')
        
        # 2. Mengambil Data Inventaris Internal
        id_buku_fisik = request.form.get('id_buku_fisik', '').strip()
        lokasi_rak = request.form.get('lokasi_rak', '')
        sumber_perolehan = request.form.get('sumber_perolehan', 'Pembelian')
        tanggal_masuk = request.form.get('tanggal_masuk', datetime.now().strftime('%Y-%m-%d'))
        kondisi_buku = request.form.get('kondisi_buku', 'Baik')

        if id_buku_fisik:
            # Memecah nomor registrasi berdasarkan koma dan membuang ruang kosong/spasi
            list_seri = [r.strip() for r in id_buku_fisik.split(',') if r.strip()]
            stok = len(list_seri)  # Jika ada 4 nomor registrasi, stok otomatis menjadi 4
        else:
            stok = 1
        
        # Penanganan aman data angka (Harga & Stok)
        try:
            harga_buku = int(request.form.get('harga_buku', 0))
        except (ValueError, TypeError):
            harga_buku = 0
            
        try:
            stok = int(request.form.get('stok', 1))
        except (ValueError, TypeError):
            stok = 1

        # 3. Proses Unggah Cover Buku
        file = request.files.get('cover_img')
        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # 4. Simpan ke Database perpustakaan.db
        conn = get_db_connection()
        try:
            # FIX: Jumlah kolom (16), Tanda Tanya (16), dan Variabel (16) SEKARANG SINKRON
            conn.execute('''
                INSERT INTO buku (
                    judul, sub_judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis, cover_img,
                    id_buku_fisik, lokasi_rak, sumber_perolehan, tanggal_masuk, kondisi_buku, harga_buku, stok
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                judul, sub_judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis, filename,
                id_buku_fisik, lokasi_rak, sumber_perolehan, tanggal_masuk, kondisi_buku, harga_buku, stok
            ))
            conn.commit()
            flash('Buku baru beserta data inventaris berhasil ditambahkan!', 'success')
        except sqlite3.IntegrityError:
            flash('Gagal! No Registrasi / ID Buku Fisik sudah terdaftar di sistem.', 'danger')
        except sqlite3.Error as e:
            flash(f'Terjadi kesalahan database: {str(e)}', 'danger')
        finally:
            conn.close()
            
        return redirect(url_for('koleksi_lengkap'))
        
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
                    kondisi_buku=?, lokasi_rak=?, harga_buku=?, stok=?
                WHERE id=?
            ''', (judul, sub_judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis,
                  kondisi_buku, lokasi_rak, harga_buku, stok, id))
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
    # Menggunakan sqlite3.Row agar data bisa diakses dengan sintaks kamus/dict
    conn.row_factory = sqlite3.Row
    buku = conn.execute('SELECT * FROM buku WHERE id = ?', (id,)).fetchone()
    conn.close()
    
    if buku is None:
        return "Buku tidak ditemukan", 404
    
    # --- PROSES OPTIMASI: PECAH NOMOR REGISTRASI JIKA ADA TANDA KOMA ---
    list_no_registrasi = []
    if buku['id_buku_fisik']:
        raw_reg = str(buku['id_buku_fisik']).strip()
        
        # Proteksi jika suatu saat formatnya berupa JSON list (dari fitur lain)
        if raw_reg.startswith('['):
            try:
                list_no_registrasi = json.loads(raw_reg)
            except Exception:
                list_no_registrasi = [raw_reg]
        else:
            # MEMECAH STRING: "001, 002, 003" menjadi ['001', '002', '003']
            # if r.strip() memastikan jika ada koma di akhir (misal: "001, 002,") tidak menghasilkan data kosong
            list_no_registrasi = [r.strip() for r in raw_reg.split(',') if r.strip()]
            
    # Deteksi apakah datang dari database atau pencarian
    back_url = request.referrer if request.referrer else url_for('index')
    
    # Kirim variabel list_no_registrasi ke detail_buku.html
    return render_template('detail_buku.html', 
                           buku=buku, 
                           list_no_registrasi=list_no_registrasi, 
                           back_url=back_url)

@app.route('/reset_katalog_buku', methods=['POST'])
def reset_katalog_buku():
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM buku')
        # Reset juga auto increment ID agar bersih dari nol lagi
        conn.execute("DELETE FROM sqlite_sequence WHERE name='buku'")
        conn.commit()
        flash('Seluruh database katalog buku berhasil dikosongkan! Silakan masukkan data baru via Import Excel.', 'success')
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'Gagal mengosongkan database: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('koleksi_lengkap'))

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

@app.route('/peminjaman')
def daftar_peminjaman():
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    
    # OPTIMASI 1: Ubah alias dari 'judul_buku' menjadi 'judul' agar singkron dengan {{ p.judul }} di HTML kamu
    peminjaman_data = conn.execute('''
        SELECT p.*, b.judul AS judul, b.cover_img
        FROM peminjaman p
        LEFT JOIN buku b ON p.id_buku = b.id
        ORDER BY p.status DESC, p.tgl_pinjam DESC
    ''').fetchall()
    conn.close()

    peminjaman_final = []
    tgl_sekarang = datetime.now().date()

    for row in peminjaman_data:
        p = dict(row)
        
        # OPTIMASI 2: Deklarasikan nilai default di awal
        p['terlambat'] = False
        p['durasi_terlambat'] = 0
        
        # OPTIMASI 3: Proteksi konversi tanggal dengan blok try-except + auto-hitung denda dinamis (jika diperlukan)
        if p['status'] == 'Dipinjam' and p['tgl_kembali_seharusnya']:
            try:
                tgl_tenggat = datetime.strptime(p['tgl_kembali_seharusnya'], '%Y-%m-%d').date()
                selisih = (tgl_sekarang - tgl_tenggat).days
                
                if selisih > 0:
                    p['terlambat'] = True
                    p['durasi_terlambat'] = selisih
                    # Opsional: Jika kamu ingin denda otomatis terupdate di halaman log (misal Rp 1.000 / hari)
                    # p['denda'] = selisih * 1000 
            except ValueError:
                pass
                
        peminjaman_final.append(p)

    return render_template('peminjaman.html', peminjaman=peminjaman_final)

@app.route('/proses_pinjam_admin', methods=['POST'])
def proses_pinjam_admin():
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))
        
    no_registrasi_input = request.form.get('no_registrasi', '').strip()
    id_anggota = request.form.get('id_anggota', '').strip()
    kelas = request.form.get('kelas', '-')
    jurusan = request.form.get('jurusan', '-')
    tipe_user = request.form.get('tipe_user', 'Siswa')
    
    try:
        durasi_pinjam = int(request.form.get('durasi_pinjam', 7))
    except:
        durasi_pinjam = 7
    
    back_url = request.form.get('back_url', '').strip()
    default_redirect = back_url if back_url else url_for('daftar_peminjaman')
    
    if not no_registrasi_input or not id_anggota:
        flash('Data input wajib diisi!', 'danger')
        return redirect(default_redirect)
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    
    semua_buku = conn.execute('SELECT * FROM buku WHERE stok > 0').fetchall()
    buku_ditemukan = None
    list_reg_terupdate = []
    
    for b in semua_buku:
        if b['id_buku_fisik']:
            raw_reg = str(b['id_buku_fisik']).strip()
            try:
                if raw_reg.startswith('['):
                    list_reg = json.loads(raw_reg)
                else:
                    list_reg = [r.strip() for r in raw_reg.split(',') if r.strip()]
                
                list_reg = [str(item) for item in list_reg]
                
                if no_registrasi_input in list_reg:
                    buku_ditemukan = b
                    list_reg.remove(no_registrasi_input)
                    list_reg_terupdate = list_reg
                    break
            except:
                continue
                
    if buku_ditemukan:
        tgl_sekarang = datetime.now()
        tgl_pinjam_str = tgl_sekarang.strftime('%Y-%m-%d')
        tgl_kembali_str = (tgl_sekarang + timedelta(days=durasi_pinjam)).strftime('%Y-%m-%d')
        
        try:
            # SINKRONISASI STOK: Jika list_reg_terupdate kosong, otomatis stok jadikan 0 secara paksa!
            stok_baru = len(list_reg_terupdate)
            conn.execute('UPDATE buku SET stok = ?, id_buku_fisik = ? WHERE id = ?', 
                         (stok_baru, json.dumps(list_reg_terupdate), buku_ditemukan['id']))
            
            info_jurusan_reg = f"{jurusan} | Reg: {no_registrasi_input}"
            
            conn.execute('''
                INSERT INTO peminjaman (id_buku, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, tgl_kembali_seharusnya, status, denda)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Dipinjam', 0)
            ''', (buku_ditemukan['id'], id_anggota, tipe_user, kelas, info_jurusan_reg, tgl_pinjam_str, tgl_kembali_str))
            
            conn.commit()
            flash(f'Berhasil dipinjam!', 'success')
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'Gagal: {str(e)}', 'danger')
    else:
        flash('Nomor Registrasi tidak tersedia!', 'danger')
        
    conn.close()
    return redirect(default_redirect)

@app.route('/kembalikan/<int:pinjam_id>', methods=['POST'])
def proses_kembalikan(pinjam_id):
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))

    status_kembali = request.form.get('status_kembali')  # 'Normal', 'Rusak', 'Hilang'
    tgl_sekarang = datetime.now()
    tgl_sekarang_str = tgl_sekarang.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    
    pinjaman = conn.execute('''
        SELECT p.*, b.harga_buku, b.id as buku_id, b.id_buku_fisik 
        FROM peminjaman p 
        JOIN buku b ON p.id_buku = b.id 
        WHERE p.id = ?
    ''', (pinjam_id,)).fetchone()
    
    if pinjaman:
        denda_keterlambatan = 0
        if pinjaman['tgl_kembali_seharusnya']:
            tgl_seharusnya = datetime.strptime(pinjaman['tgl_kembali_seharusnya'], '%Y-%m-%d')
            hari_terlambat = (tgl_sekarang.date() - tgl_seharusnya.date()).days
            if hari_terlambat > 0:
                denda_keterlambatan = hari_terlambat * 1000
            
        denda_kondisi = 0
        harga_buku_asli = pinjaman['harga_buku'] if pinjaman['harga_buku'] else 0
        
        # Ekstrak No Registrasi
        no_reg_kembali = None
        raw_jurusan = pinjaman['jurusan'] if pinjaman['jurusan'] else ''
        if "| Reg:" in raw_jurusan:
            try:
                no_reg_kembali = raw_jurusan.split("| Reg:")[-1].strip()
            except:
                no_reg_kembali = None

        if status_kembali in ['Rusak', 'Hilang']:
            denda_kondisi = harga_buku_asli
            # BUG FIX: JANGAN update status tabel buku global menjadi 'Hilang/Rusak' agar buku aman lain tidak tertular!
            # Biarkan kondisi buku utama tetap 'Baik', pelacakan kondisi rusak/hilang dibaca lewat histori transaksi.
            status_final = status_kembali  # Status peminjaman menjadi 'Rusak' atau 'Hilang'
        else:
            # PENGEMBALIAN NORMAL: Masukkan kembali nomor seri ke rak buku asal
            status_final = "Selesai"
            raw_buku_reg = pinjaman['id_buku_fisik'] if pinjaman['id_buku_fisik'] else '[]'
            try:
                current_regs = json.loads(raw_buku_reg) if raw_buku_reg.startswith('[') else [r.strip() for r in raw_buku_reg.split(',') if r.strip()]
            except:
                current_regs = []

            if no_reg_kembali and no_reg_kembali not in current_regs:
                current_regs.append(no_reg_kembali)

            conn.execute('UPDATE buku SET stok = ?, id_buku_fisik = ? WHERE id = ?', 
                         (len(current_regs), json.dumps(current_regs), pinjaman['buku_id']))
            
        total_denda = denda_keterlambatan + denda_kondisi
        
        try:
            conn.execute('''
                UPDATE peminjaman 
                SET tgl_dikembalikan = ?, status = ?, denda = ? 
                WHERE id = ?
            ''', (tgl_sekarang_str, status_final, total_denda, pinjam_id))
            conn.commit()
            flash(f'Berhasil memproses pengembalian ({status_kembali})!', 'success')
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'Gagal: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/lunasi_denda/<int:pinjam_id>', methods=['POST'])
def lunasi_denda(pinjam_id):
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        conn.execute("UPDATE peminjaman SET status = 'Dibayar/Lunas', denda = 0 WHERE id = ?", (pinjam_id,))
        conn.commit()
        flash('Status sirkulasi berhasil diperbarui menjadi Dibayar/Lunas!', 'success')
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'Gagal memperbarui data: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/api/riwayat_buku/<int:buku_id>')
def api_riwayat_buku(buku_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    riwayat = conn.execute('''
        SELECT id_anggota, kelas, jurusan, tgl_pinjam, tgl_dikembalikan, status, denda 
        FROM peminjaman 
        WHERE id_buku = ? 
        ORDER BY id DESC
    ''', (buku_id,)).fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in riwayat])

@app.route('/koleksi')
def koleksi_lengkap():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    
    query = request.args.get('query', '').strip()
    if query:
        buku = conn.execute('''
            SELECT * FROM buku 
            WHERE judul LIKE ? OR penulis LIKE ? OR id_buku_fisik LIKE ?
            ORDER BY id DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    else:
        buku = conn.execute('SELECT * FROM buku ORDER BY id DESC').fetchall()
    
    # Perbaikan Stok Riil: Hitung total stok dari buku yang id_buku_fisik-nya tidak kosong/habis
    total_buku = 0
    for b in buku:
        if b['id_buku_fisik']:
            try:
                regs = json.loads(b['id_buku_fisik']) if b['id_buku_fisik'].startswith('[') else [r.strip() for r in b['id_buku_fisik'].split(',') if r.strip()]
                total_buku += len(regs)
            except:
                total_buku += b['stok']
        else:
            total_buku += 0

    total_judul = conn.execute('SELECT COUNT(*) FROM buku').fetchone()[0] or 0
    total_dipinjam = conn.execute('SELECT COUNT(*) FROM peminjaman WHERE status = "Dipinjam"').fetchone()[0] or 0

    buku_populer = conn.execute('''
        SELECT b.judul, b.kategori, COUNT(p.id) as total_dipinjam
        FROM buku b
        JOIN peminjaman p ON b.id = p.id_buku
        GROUP BY b.id
        ORDER BY total_dipinjam DESC
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    return render_template('koleksi.html', 
                           buku=buku, 
                           query=query,
                           total_buku=total_buku,
                           total_judul=total_judul,
                           total_dipinjam=total_dipinjam,
                           buku_populer=buku_populer)

@app.route('/export_peminjaman')
def export_peminjaman():
    if not session.get('logged_in'):
        flash('Akses ditolak! Anda harus login sebagai admin.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Menggunakan LEFT JOIN agar transaksi tetap muncul meskipun data buku induknya terhapus
    query = '''
        SELECT 
            p.tgl_pinjam AS [Tanggal Pinjam], 
            p.tgl_kembali_seharusnya AS [Tenggat Kembali],
            p.id_anggota AS [Nama Peminjam], 
            p.tipe_user AS [Tipe Pengguna], 
            p.kelas AS [Kelas], 
            p.jurusan AS [Jurusan / Info Reg], 
            b.judul AS [Judul Buku], 
            p.status AS [Status Peminjaman],
            p.denda AS [Total Denda]
        FROM peminjaman p
        LEFT JOIN buku b ON p.id_buku = b.id
        ORDER BY p.id DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Optimasi: Tulis file langsung ke dalam Memory Buffer (BytesIO) tanpa menyimpan ke disk lokal
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Laporan Sirkulasi')
    
    output.seek(0)
    
    # Generate nama file dinamis menggunakan timestamp waktu download sekarang
    nama_file = f"Laporan_Peminjaman_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output, 
        as_attachment=True, 
        download_name=nama_file, 
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/import_excel', methods=['POST'])
def import_excel():
    if not session.get('logged_in'):
        flash('Anda harus login sebagai admin!', 'danger')
        return redirect(url_for('login'))
        
    if 'excel_file' not in request.files:
        flash('Tidak ada file yang diunggah!', 'danger')
        return redirect(url_for('koleksi_lengkap'))
        
    file = request.files['excel_file']
    if file.filename == '':
        flash('Tidak ada file yang dipilih!', 'danger')
        return redirect(url_for('koleksi_lengkap'))
        
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        try:
            # MEMAKSA PANDAS MEMBACA SEMUA KOLOM SEBAGAI STRING
            df = pd.read_excel(file, dtype=str)
            df = df.fillna('')
            
            conn = sqlite3.connect('perpustakaan.db')
            cursor = conn.cursor()
            
            sukses = 0
            gagal = 0
            
            for index, row in df.iterrows():
                judul = row.get('judul', '').strip()
                if not judul:
                    continue
                    
                penulis = row.get('penulis', '').strip()
                penerbit = row.get('penerbit', '').strip()
                tahun_terbit = row.get('tahun_terbit', '').strip()
                isbn = row.get('isbn', '').strip()
                kategori = row.get('kategori', '').strip()
                sinopsis = row.get('sinopsis', '').strip()
                lokasi_rak = row.get('lokasi_rak', '').strip()
                sumber_perolehan = row.get('sumber_perolehan', '').strip()
                
                # NORMALISASI FORMAT TANGGAL MASUK (Menjamin pemisah menggunakan strip)
                tanggal_masuk = row.get('tanggal_masuk', '').strip()
                if ' ' in tanggal_masuk:  # Membuang format jam jika terbuat otomatis oleh timestamp
                    tanggal_masuk = tanggal_masuk.split(' ')[0]
                tanggal_masuk = tanggal_masuk.replace('/', '-')
                
                kondisi_buku = row.get('kondisi_buku', 'Baik').strip()
                if not kondisi_buku:
                    kondisi_buku = 'Baik'
                    
                harga_buku_raw = row.get('harga_buku', '0').strip()
                try:
                    harga_buku = int(float(harga_buku_raw)) if harga_buku_raw else 0
                except:
                    harga_buku = 0
                    
                no_registrasi_list = row.get('no_registrasi_list', '').strip()
                regs = [r.strip() for r in str(no_registrasi_list).split(',') if r.strip()]
                
                # PROTEKSI BACKEND: Kembalikan Angka Nol yang Hilang Akibat Auto-Format Excel
                cleaned_regs = []
                for r in regs:
                    if r.isdigit() and len(r) < 8:
                        r = r.zfill(8)  # Mengubah "412355" menjadi "00412355"
                    cleaned_regs.append(r)
                
                id_buku_fisik = cleaned_regs[0] if cleaned_regs else ''
                stok = len(cleaned_regs) if cleaned_regs else 1
                
                try:
                    cursor.execute('''
                        INSERT INTO buku (judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis, lokasi_rak, sumber_perolehan, tanggal_masuk, kondisi_buku, harga_buku, id_buku_fisik, stok)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (judul, penulis, penerbit, tahun_terbit, isbn, kategori, sinopsis, lokasi_rak, sumber_perolehan, tanggal_masuk, kondisi_buku, harga_buku, id_buku_fisik, stok))
                    sukses += 1
                except sqlite3.IntegrityError:
                    gagal += 1
                    
            conn.commit()
            conn.close()
            flash(f'Berhasil mengimpor {sukses} data buku. Gagal {gagal} (kemungkinan duplikat No Registrasi).', 'success')
            
        except Exception as e:
            flash(f'Error saat memproses excel: {str(e)}', 'danger')
    else:
        flash('Format file wajib .xlsx atau .xls', 'danger')
        
    return redirect(url_for('koleksi_lengkap'))

@app.route('/hapus_peminjaman/<int:id>', methods=['POST'])
def hapus_peminjaman(id):
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        # Hapus data transaksi berdasarkan ID
        conn.execute('DELETE FROM peminjaman WHERE id = ?', (id,))
        conn.commit()
        flash('Log riwayat transaksi peminjaman berhasil dihapus permanen!', 'success')
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'Gagal menghapus data: {str(e)}', 'danger')
    finally:
        conn.close()
        
    # Redirect kembali ke halaman log peminjaman
    return redirect(request.referrer or url_for('daftar_peminjaman'))

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
            id_buku_fisik TEXT UNIQUE, -- No Registrasi
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
    init_db() 
    app.run(host='0.0.0.0', port=5000, debug=False)