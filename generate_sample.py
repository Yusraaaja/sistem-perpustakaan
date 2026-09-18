import pandas as pd

# Data contoh yang disesuaikan persis dengan row.get() di app.py
data = {
    'judul': [
        'Python Crash Course, 3rd Edition',
        'Dasar Pemrograman Web dengan HTML, CSS, dan JavaScript',
        'Rekayasa Perangkat Lunak Berorientasi Objek',
        'Jaringan Komputer Dasar & Keamanan Jaringan',
        'Logika & Algoritma Pemrograman Dasar',
        'Atomic Habits',
        'Rich Dad Poor Dad',
        'Zero to One: Catatan tentang Startup',
        'Berani Tidak Disukai',
        'Keamanan Siber (Cybersecurity) untuk Pemula',
        'Bumi',
        'Laskar Pelangi',
        'Negeri 5 Menara',
        'Laut Bercerita',
        'Filosofi Teras'
    ],
    'penulis': [
        'Eric Matthes', 'Rismon Hasiholan', 'Wahana Komputer', 'Iwan Sofana', 'Siahaan Vivian',
        'James Clear', 'Robert T. Kiyosaki', 'Peter Thiel', 'Ichiro Kishimi', 'Putra Prasetya',
        'Tere Liye', 'Andrea Hirata', 'A. Fuadi', 'Leila S. Chudori', 'Henry Manampiring'
    ],
    'penerbit': [
        'No Starch Press', 'Informatika', 'Andi Offset', 'Informatika', 'Elex Media Komputindo',
        'Gramedia Pustaka Utama', 'Gramedia Pustaka Utama', 'Gramedia Pustaka Utama', 'Gramedia Pustaka Utama', 'Cerdas Digital',
        'Gramedia Pustaka Utama', 'Bentang Pustaka', 'Gramedia Pustaka Utama', 'Kepustakaan Populer Gramedia', 'Kompas'
    ],
    'tahun_terbit': [
        '2023', '2022', '2021', '2020', '2023',
        '2019', '2016', '2015', '2019', '2024',
        '2014', '2005', '2009', '2017', '2019'
    ],
    'isbn': [
        '9781718502703', '9786237131342', '9786230110436', '9786237131229', '9786230045227',
        '9786020624716', '9786020333120', '9786020315720', '9786020623252', '9786239001122',
        '9786020332956', '9789793062792', '9789792248456', '9786024246938', '9786024125189'
    ],
    'kategori': [
        'Teknologi (RPL)', 'Teknologi (RPL)', 'Teknologi (RPL)', 'Teknologi (TKJ)', 'Teknologi (RPL)',
        'Pengembangan Diri', 'Kewirausahaan', 'Kewirausahaan', 'Pengembangan Diri', 'Teknologi (Cybersecurity)',
        'Fiksi / Novel', 'Fiksi / Novel', 'Fiksi / Novel', 'Fiksi / Novel', 'Pengembangan Diri'
    ],
    'sinopsis': [
        'Panduan cepat belajar pemrograman Python pemula hingga tingkat lanjut.',
        'Panduan lengkap membangun website modern menggunakan teknologi SPA.',
        'Buku panduan pemodelan sistem perangkat lunak menggunakan UML.',
        'Konsep dasar jaringan komputer, routing, switching, dan pengamanan fisik.',
        'Melatih logika berpikir komputasional untuk penyusunan algoritma SMK.',
        'Sistem praktis untuk membangun kebiasaan baik dan menghilangkan kebiasaan buruk.',
        'Mengubah pola pikir finansial tentang uang dan aset sejak usia muda.',
        'Bagaimana membangun masa depan dengan menciptakan inovasi yang benar-benar baru.',
        'Konsep psikologi Adlerian untuk meraih kebebasan dan kebahagiaan sejati.',
        'Mengenal dasar pertahanan siber, ethical hacking, dan keamanan data.',
        'Kisah petualangan dunia paralel remaja bernama Raib, Seli, dan Ali.',
        'Perjuangan sebelas anak belitong meraih mimpi di tengah keterbatasan sekolah.',
        'Kehidupan santri di pondok madani dengan prinsip Man Jadda Wajada.',
        'Kisah reflektif perjuangan aktivis mahasiswa di masa reformasi.',
        'Penerapan filsafat Stoikisme kuno untuk mental tangguh generasi masa kini.'
    ],
    'lokasi_rak': [
        'RAK-RPL-01', 'RAK-RPL-01', 'RAK-RPL-02', 'RAK-TKJ-01', 'RAK-RPL-02',
        'RAK-UMUM-03', 'RAK-UMUM-04', 'RAK-UMUM-04', 'RAK-UMUM-03', 'RAK-SEC-01',
        'RAK-FIKSI-01', 'RAK-FIKSI-01', 'RAK-FIKSI-02', 'RAK-FIKSI-02', 'RAK-UMUM-03'
    ],
    'sumber_perolehan': [
        'Pembelian', 'Dana BOS', 'Dana BOS', 'Pembelian', 'Pembelian',
        'Dana BOS', 'Sumbangan', 'Pembelian', 'Sumbangan', 'Pembelian',
        'Dana BOS', 'Dana BOS', 'Sumbangan', 'Pembelian', 'Dana BOS'
    ],
    'tanggal_masuk': [
        '2026-01-15', '2026-01-15', '2026-02-10', '2026-02-10', '2026-03-01',
        '2026-03-01', '2026-03-15', '2026-03-15', '2026-04-05', '2026-04-20',
        '2026-05-02', '2026-05-02', '2026-05-10', '2026-05-10', '2026-05-12'
    ],
    'kondisi_buku': [
        'Baik', 'Baik', 'Baik', 'Baik', 'Baik',
        'Baik', 'Baik', 'Baik', 'Baik', 'Baik',
        'Baik', 'Baik', 'Baik', 'Baik', 'Baik'
    ],
    'harga_buku': [
        '145000', '95000', '85000', '110000', '75000',
        '88000', '78000', '92000', '98000', '120000',
        '95000', '69000', '80000', '115000', '85000'
    ],
    'no_registrasi_list': [
        '00000101, 00000102', 
        '00000201, 00000202, 00000203', 
        '00000301', 
        '00000401, 00000402', 
        '00000501, 00000502, 00000503, 00000504',
        '00000601, 00000602', 
        '00000701', 
        '00000801', 
        '00000901, 00000902', 
        '00001001',
        '00001101, 00001102, 00001103', 
        '00001201, 00001202', 
        '00001301', 
        '00001401', 
        '00001501, 00001502'
    ]
}

df = pd.DataFrame(data)
df.to_excel('data_contoh_perpustakaan.xlsx', index=False)
print("Berhasil! File 'data_contoh_perpustakaan.xlsx' siap digunakan demonstrasi.")