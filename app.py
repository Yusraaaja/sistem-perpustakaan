from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import sqlite3
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import pandas as pd
import json
from io import BytesIO

app = Flask(__name__)
# Konfigurasi Keamanan Aplikasi (Satu Secret Key yang Valid)
app.secret_key = 'supersecretkey_pilihan_aman'

# Konfigurasi Unggahan File Aset Media
UPLOAD_FOLDER = 'static/covers'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Pastikan infrastruktur folder media tersedia
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Kredensial Akses Administratif (Simulasi Otentikasi)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = '123' 

# ==========================================
# HELPER FUNCTIONS (Optimalisasi & Standarisasi Data)
# ==========================================

def allowed_file(filename):
    """Validasi ekstensi file cover yang diunggah."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """Mengelola koneksi database SQLite dengan factory row."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'perpustakaan.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def parse_registration_numbers(raw_reg):
    """
    Helper DRY: Menangani ekstraksi Nomor Registrasi Buku Fisik 
    secara kokoh dari berbagai format input (JSON String, Comma-Separated, atau Space-Separated).
    """
    if not raw_reg:
        return []
    raw_reg = str(raw_reg).strip()
    
    # Antisipasi format JSON List
    if raw_reg.startswith('['):
        try:
            return [str(r).strip() for r in json.loads(raw_reg) if str(r).strip()]
        except Exception:
            pass
            
    # Antisipasi format Comma-Separated
    if ',' in raw_reg:
        return [r.strip() for r in raw_reg.split(',') if r.strip()]
        
    # Antisipasi format Space-Separated
    return [r.strip() for r in raw_reg.split() if r.strip()]

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

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
            flash('Gagal Login! Username atau password salah.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Anda telah keluar.', 'info')
    return redirect(url_for('index'))

# ==========================================
# CORE REPOSITORY / KATALOG ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search_redirect():
    query = request.args.get('query', '').strip()
    return redirect(url_for('koleksi_lengkap', query=query))

@app.route('/add', methods=['POST'])
def tambah_buku():
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
        
    # 1. Ekstraksi Data Umum Katalog
    judul = request.form.get('judul')
    sub_judul = request.form.get('sub_judul', '')
    penulis = request.form.get('penulis')
    penerbit = request.form.get('penerbit', '')
    tahun_terbit = request.form.get('tahun_terbit', '')
    isbn = request.form.get('isbn', '')
    kategori = request.form.get('kategori')
    sinopsis = request.form.get('sinopsis', '')
    
    # 2. Ekstraksi Logistik Inventaris Internal
    id_buku_fisik = request.form.get('id_buku_fisik', '').strip()
    lokasi_rak = request.form.get('lokasi_rak', '')
    sumber_perolehan = request.form.get('sumber_perolehan', 'Pembelian')
    tanggal_masuk = request.form.get('tanggal_masuk', datetime.now().strftime('%Y-%m-%d'))
    kondisi_buku = request.form.get('kondisi_buku', 'Baik')

    # Sinkronisasi Otomatis Nilai Stok Berdasarkan Jumlah Nomor Registrasi Input
    list_seri = parse_registration_numbers(id_buku_fisik)
    stok = len(list_seri) if list_seri else 1
    
    # Proteksi tipe data numerik
    try:
        harga_buku = int(request.form.get('harga_buku', 0))
    except (ValueError, TypeError):
        harga_buku = 0

    # 3. Pemrosesan Unggah Cover Buku
    file = request.files.get('cover_img')
    filename = None
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    # 4. Transaksi Persistensi Database
    conn = get_db_connection()
    try:
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
            
        return redirect(back_url_post)

@app.route('/delete/<int:id>')
def hapus_buku(id):
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM buku WHERE id = ?', (id,))
        conn.commit()
        flash('Aset buku berhasil dihapus dari sistem.', 'success')
    except sqlite3.Error as e:
        flash(f'Gagal menghapus buku: {str(e)}', 'danger')
    finally:
        conn.close()
    
    prev_page = request.referrer
    if prev_page and '/koleksi' in prev_page:
        return redirect(url_for('koleksi_lengkap'))
    return redirect(url_for('index'))

@app.route('/buku/<int:id>')
def detail_buku(id):
    conn = get_db_connection()
    buku_row = conn.execute('SELECT * FROM buku WHERE id = ?', (id,)).fetchone()
    
    if buku_row is None:
        conn.close()
        return "Buku tidak ditemukan", 404
        
    buku = dict(buku_row)

    # Memanfaatkan Helper Terpusat untuk Ekstraksi Nomor Registrasi Asli
    list_no_registrasi_asli = parse_registration_numbers(buku.get('id_buku_fisik'))

    # Sinkronisasi Transaksi Aktif Sirkulasi
    peminjaman_aktif = conn.execute('''
        SELECT jurusan FROM peminjaman 
        WHERE id_buku = ? AND status = 'Dipinjam'
    ''', (id,)).fetchall()
    
    reg_sedang_dipinjam = []
    # FIX BUG KRITIS: Perubahan dari 'peminan_aktif' menjadi 'peminjaman_aktif' untuk mencegah NameError
    for row in peminjaman_aktif:
        raw_jurusan = row['jurusan'] if row['jurusan'] else ''
        if "| Reg:" in raw_jurusan:
            try:
                no_reg = raw_jurusan.split("| Reg:")[-1].strip()
                reg_sedang_dipinjam.append(no_reg)
            except Exception:
                pass

    # Filter Sterilisasi: Dapatkan daftar nomor seri buku yang siap dipinjam di rak
    list_no_registrasi_ready = [reg for reg in list_no_registrasi_asli if reg not in reg_sedang_dipinjam]

    # Sinkronisasi Nilai Stok Riil
    buku['stok'] = len(list_no_registrasi_ready)
    conn.close()
    
    back_url = request.referrer if request.referrer else url_for('index')
    
    return render_template('detail_buku.html', 
                           buku=buku, 
                           list_no_registrasi=list_no_registrasi_ready, 
                           back_url=back_url)

@app.route('/reset_katalog_buku', methods=['POST'])
def reset_katalog_buku():
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM buku')
        conn.execute("DELETE FROM sqlite_sequence WHERE name='buku'")
        conn.commit()
        flash('Seluruh database katalog buku berhasil dikosongkan!', 'success')
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'Gagal mengosongkan database: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('koleksi_lengkap'))

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
        filename = secure_filename(file.filename)
        unique_filename = f"buku_{id}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        
        conn = get_db_connection()
        conn.execute('UPDATE buku SET cover_img = ? WHERE id = ?', (unique_filename, id))
        conn.commit()
        conn.close()
        
        flash('Cover buku berhasil diunggah!', 'success')
    else:
        flash('Tipe file tidak diizinkan.', 'danger')
        
    return redirect(url_for('detail_buku', id=id))

# ==========================================
# CIRCULATION / SIRKULASI & LOAN ROUTES
# ==========================================

@app.route('/peminjaman')
def daftar_peminjaman():
    if not session.get('logged_in'):
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
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
        p['terlambat'] = False
        p['durasi_terlambat'] = 0
        
        # Kalkulasi Durasi Keterlambatan Finansial Dinamis
        if p['status'] == 'Dipinjam' and p['tgl_kembali_seharusnya']:
            try:
                tgl_tenggat = datetime.strptime(p['tgl_kembali_seharusnya'], '%Y-%m-%d').date()
                selisih = (tgl_sekarang - tgl_tenggat).days
                if selisih > 0:
                    p['terlambat'] = True
                    p['durasi_terlambat'] = selisih
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
    except Exception:
        durasi_pinjam = 7
    
    back_url = request.form.get('back_url', '').strip()
    default_redirect = back_url if back_url else url_for('daftar_peminjaman')
    
    if not no_registrasi_input or not id_anggota:
        flash('Data input wajib diisi!', 'danger')
        return redirect(default_redirect)
    
    conn = get_db_connection()
    semua_buku = conn.execute('SELECT * FROM buku WHERE stok > 0').fetchall()
    buku_ditemukan = None
    list_reg_terupdate = []
    
    for b in semua_buku:
        if b['id_buku_fisik']:
            list_reg = parse_registration_numbers(b['id_buku_fisik'])
            list_reg = [str(item) for item in list_reg]
            
            if no_registrasi_input in list_reg:
                buku_ditemukan = b
                list_reg.remove(no_registrasi_input)
                list_reg_terupdate = list_reg
                break
                
    if buku_ditemukan:
        tgl_sekarang = datetime.now()
        tgl_pinjam_str = tgl_sekarang.strftime('%Y-%m-%d')
        tgl_kembali_str = (tgl_sekarang + timedelta(days=durasi_pinjam)).strftime('%Y-%m-%d')
        
        try:
            stok_baru = len(list_reg_terupdate)
            conn.execute('UPDATE buku SET stok = ?, id_buku_fisik = ? WHERE id = ?', 
                         (stok_baru, json.dumps(list_reg_terupdate), buku_ditemukan['id']))
            
            info_jurusan_reg = f"{jurusan} | Reg: {no_registrasi_input}"
            
            conn.execute('''
                INSERT INTO peminjaman (id_buku, id_anggota, tipe_user, kelas, jurusan, tgl_pinjam, tgl_kembali_seharusnya, status, denda)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Dipinjam', 0)
            ''', (buku_ditemukan['id'], id_anggota, tipe_user, kelas, info_jurusan_reg, tgl_pinjam_str, tgl_kembali_str))
            
            conn.commit()
            flash(f'Transaksi sirkulasi berhasil dibuat!', 'success')
        except sqlite3.Error as e:
            conn.rollback()
            flash(f'Gagal memproses sirkulasi: {str(e)}', 'danger')
    else:
        flash('Nomor Registrasi tidak tersedia atau sedang dipinjam!', 'danger')
        
    conn.close()
    return redirect(default_redirect)

@app.route('/kembalikan/<int:pinjam_id>', methods=['POST'])
def proses_kembalikan(pinjam_id):
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))

    status_kembali = request.form.get('status_kembali')
    tgl_sekarang = datetime.now()
    tgl_sekarang_str = tgl_sekarang.strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    pinjaman = conn.execute('''
        SELECT p.*, b.harga_buku, b.id as buku_id, b.id_buku_fisik 
        FROM peminjaman p 
        JOIN buku b ON p.id_buku = b.id 
        WHERE p.id = ?
    ''', (pinjam_id,)).fetchone()
    
    if pinjaman:
        # Perhitungan Denda Keterlambatan (Rp 1.000 / hari)
        denda_keterlambatan = 0
        if pinjaman['tgl_kembali_seharusnya']:
            tgl_seharusnya = datetime.strptime(pinjaman['tgl_kembali_seharusnya'], '%Y-%m-%d')
            hari_terlambat = (tgl_sekarang.date() - tgl_seharusnya.date()).days
            if hari_terlambat > 0:
                denda_keterlambatan = hari_terlambat * 1000
            
        denda_kondisi = 0
        harga_buku_asli = pinjaman['harga_buku'] if pinjaman['harga_buku'] else 0
        
        # Ekstraksi nomor registrasi yang dikembalikan
        no_reg_kembali = None
        raw_jurusan = pinjaman['jurusan'] if pinjaman['jurusan'] else ''
        if "| Reg:" in raw_jurusan:
            try:
                no_reg_kembali = raw_jurusan.split("| Reg:")[-1].strip()
            except Exception:
                no_reg_kembali = None

        if status_kembali in ['Rusak', 'Hilang']:
            denda_kondisi = harga_buku_asli
            status_final = status_kembali
        else:
            status_final = "Selesai"
            current_regs = parse_registration_numbers(pinjaman['id_buku_fisik'])

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
            flash(f'Gagal memproses pengembalian: {str(e)}', 'danger')
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
        flash(f'Gagal memperbarui data denda: {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('daftar_peminjaman'))

@app.route('/hapus_peminjaman/<int:id>', methods=['POST'])
def hapus_peminjaman(id):
    if not session.get('logged_in'):
        flash('Akses ditolak!', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM peminjaman WHERE id = ?', (id,))
        conn.commit()
        flash('Log riwayat transaksi peminjaman berhasil dihapus permanen!', 'success')
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'Gagal menghapus log transaksi: {str(e)}', 'danger')
    finally:
        conn.close()
        
    return redirect(request.referrer or url_for('daftar_peminjaman'))

# ==========================================
# DATA METRICS & EXCHANGES (API, EXCEL IMPORT/EXPORT)
# ==========================================

@app.route('/api/riwayat_buku/<int:buku_id>')
def api_riwayat_buku(buku_id):
    conn = get_db_connection()
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
    query = request.args.get('query', '').strip()
    
    if query:
        buku = conn.execute('''
            SELECT * FROM buku 
            WHERE judul LIKE ? OR penulis LIKE ? OR id_buku_fisik LIKE ?
            ORDER BY id DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    else:
        buku = conn.execute('SELECT * FROM buku ORDER BY id DESC').fetchall()
    
    # Perhitungan Stok Riil Komparatif global
    total_buku = 0
    for b in buku:
        if b['id_buku_fisik']:
            regs = parse_registration_numbers(b['id_buku_fisik'])
            total_buku += len(regs) if regs else b['stok']
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

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Laporan Sirkulasi')
    
    output.seek(0)
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
            df = pd.read_excel(file, dtype=str)
            df = df.fillna('')
            
            conn = get_db_connection()
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
                
                tanggal_masuk = row.get('tanggal_masuk', '').strip()
                if ' ' in tanggal_masuk:
                    tanggal_masuk = tanggal_masuk.split(' ')[0]
                tanggal_masuk = tanggal_masuk.replace('/', '-')
                
                kondisi_buku = row.get('kondisi_buku', 'Baik').strip()
                if not kondisi_buku:
                    kondisi_buku = 'Baik'
                    
                harga_buku_raw = row.get('harga_buku', '0').strip()
                try:
                    harga_buku = int(float(harga_buku_raw)) if harga_buku_raw else 0
                except Exception:
                    harga_buku = 0
                    
                no_registrasi_list = row.get('no_registrasi_list', '').strip()
                regs = [r.strip() for r in str(no_registrasi_list).split(',') if r.strip()]
                
                cleaned_regs = []
                for r in regs:
                    if r.isdigit() and len(r) < 8:
                        r = r.zfill(8)
                    cleaned_regs.append(r)
                
                # OPTIMALISASI PORTFOLIO: Simpan SELURUH list nomor registrasi ke db dalam format JSON 
                # agar data inventaris lengkap tidak hilang saat di-import.
                id_buku_fisik = json.dumps(cleaned_regs) if cleaned_regs else '[]'
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

# ==========================================
# DATABASE INITIALIZATION & APPLICATION RUNNER
# ==========================================

def init_db():
    """Inisialisasi tabel skema database relasional."""
    conn = sqlite3.connect('perpustakaan.db')
    cursor = conn.cursor()
    
    # 1. TABEL BUKU (Katalog & Logistik Inventaris Lengkap)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buku (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            judul TEXT NOT NULL,
            sub_judul TEXT,
            penulis TEXT,
            penerbit TEXT,
            tahun_terbit TEXT,
            isbn TEXT,
            kategori TEXT,
            sinopsis TEXT,
            cover_img TEXT,
            id_buku_fisik TEXT UNIQUE, 
            lokasi_rak TEXT,
            sumber_perolehan TEXT,     
            tanggal_masuk TEXT,
            kondisi_buku TEXT DEFAULT 'Baik', 
            harga_buku INTEGER DEFAULT 0,     
            stok INTEGER DEFAULT 1
        )
    ''')
    
    # 2. TABEL PEMINJAMAN (Log Sirkulasi Transaksi)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS peminjaman (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_buku INTEGER,
            id_anggota TEXT, 
            tipe_user TEXT,  
            kelas TEXT,
            jurusan TEXT,
            tgl_pinjam TEXT,
            tgl_kembali_seharusnya TEXT,
            tgl_dikembalikan TEXT,
            status TEXT DEFAULT 'Dipinjam', 
            denda INTEGER DEFAULT 0,
            FOREIGN KEY(id_buku) REFERENCES buku(id)
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db() 
    # Menjalankan aplikasi Flask
    app.run(host='0.0.0.0', port=5000, debug=False)