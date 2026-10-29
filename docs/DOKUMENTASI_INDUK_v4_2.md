# DOKUMENTASI INDUK PROYEK
# SISTEM PERPUSTAKAAN DIGITAL SEKOLAH

**Versi dokumen:** 4.2  
**Tanggal penyusunan:** 17 Oktober 2026  
**Bahasa utama:** Bahasa Indonesia  
**Jenis dokumen:** Konteks produk, kebutuhan, keputusan, arsitektur yang dituju, roadmap, dan aturan kerja AI  
**Status:** Perapian konsistensi atas v4.1 (keputusan produk tidak diubah; hal yang menunggu konfirmasi dicatat sebagai OPEN-016 sampai OPEN-018), berdasarkan klarifikasi pengguna pada 17 Oktober 2026 (notifikasi keterlambatan dapat dilihat siapa pun; data anggota sederhana; akun tidak aktif dinonaktifkan tanpa penghapusan otomatis; pengembalian parsial, perpanjangan satu kali, dan alur penyelesaian buku hilang/rusak); **belum merupakan hasil audit menyeluruh terhadap repositori kode atau verifikasi langsung terhadap ketentuan paket hosting/API saat ini**.

> **Peringatan akurasi penting:** Dokumen ini menjelaskan maksud proyek, keputusan yang telah disampaikan, perilaku yang diharapkan, rencana, serta hal-hal yang belum diketahui. Dokumen ini tidak membuktikan bahwa fitur tertentu sudah ada atau berjalan di kode. AI yang membaca dokumen ini wajib memeriksa repositori, konfigurasi, database, dan pengujian aktual sebelum menyatakan status implementasi.

---

# 0. Petunjuk untuk AI yang Membaca Dokumen Ini

Dokumen ini dibuat agar AI chatbot, AI coding agent, atau pengembang baru dapat memahami konteks proyek tanpa mengandalkan potongan percakapan yang terpisah. Baca seluruh dokumen sebelum membuat perubahan besar, menyusun arsitektur baru, mengubah skema database, atau mengimplementasikan fitur.

## 0.1 Instruksi inti

1. **Pahami tujuan sebelum mengubah kode.** Ini adalah sistem perpustakaan sekolah yang ditujukan untuk digunakan dalam proses nyata, bukan sekadar demo, tugas singkat, atau kumpulan fitur yang tidak terintegrasi.
2. **Jangan mengarang keadaan repositori.** Keberadaan fitur, file, tabel, tes, branch, atau deployment harus dibuktikan dari keadaan aktual. Laporan AI terdahulu adalah petunjuk historis, bukan bukti final.
3. **Jangan mengubah keputusan produk secara diam-diam.** Jika ada benturan antara dokumen, kode, dan permintaan terbaru pengguna, catat benturannya dan minta persetujuan ketika keputusan tersebut memengaruhi kebijakan atau data penting. Jangan mengubah aturan bisnis karena terasa lebih mudah secara teknis.
4. **Bedakan empat kategori:** keputusan yang dikonfirmasi, arah/rencana yang disetujui bersyarat, laporan historis yang belum diverifikasi, dan pertanyaan terbuka.
5. **Utamakan data yang benar dan dapat dipulihkan.** Konsistensi transaksi, jejak audit, backup, pemulihan, keamanan akun, serta perlindungan data siswa lebih penting daripada sekadar menyelesaikan UI.
6. **Kerjakan secara bertahap.** Audit dahulu, tentukan lingkup tugas, jelaskan file yang akan diubah, implementasikan secukupnya, tambahkan atau perbaiki tes, jalankan tes yang relevan, lalu laporkan hasil secara jujur.
7. **Jangan melakukan operasi berisiko tanpa izin eksplisit.** Jangan deploy ke produksi, memigrasikan database produksi, menghapus data, mengubah skema produksi, mengirim pesan kepada anggota, atau mengubah kebijakan resmi tanpa persetujuan pengguna.
8. **Jangan menjanjikan sistem bebas kecurangan 100%.** QR dapat difoto atau disalin. Sistem dapat menurunkan risiko dan membuat aktivitas lebih dapat ditelusuri, tetapi pemindaian QR saja tidak membuktikan bahwa buku fisik benar-benar berada di hadapan kamera.
9. **Pertahankan Bahasa Indonesia yang mudah dipahami.** Antarmuka dan panduan pengguna utama harus ramah untuk petugas perpustakaan serta pengguna sekolah yang tidak terbiasa dengan istilah teknis.
10. **Jika konteks belum cukup, jangan menebak sebagai fakta.** Catat hal yang belum diketahui, buat opsi dengan konsekuensi yang jelas, dan tanyakan hanya bila keputusan tersebut diperlukan untuk melanjutkan dengan aman.
11. **Arsitektur target yang ditetapkan pengguna:** Flask dalam Docker di Hugging Face Spaces, Supabase PostgreSQL sebagai database persisten, Google Gemini API untuk asisten AI, dan notifikasi keterlambatan di dalam aplikasi yang dapat dilihat siapa pun yang membuka halaman notifikasi (WhatsApp tidak digunakan). Jangan kembali mengusulkan Render/Neon sebagai arsitektur utama kecuali pengguna meminta evaluasi ulang.
12. **Jangan membuat klaim “gratis selamanya” atau “data dijamin aman selamanya” sebagai fakta teknis.** Target biaya adalah Rp0 selama paket dan batas layanan memungkinkan. AI wajib memverifikasi ketentuan terkini, keterbatasan tidur/jeda, kuota, retensi, penyimpanan, dan biaya. Data wajib memiliki strategi ekspor, backup terpisah, dan uji pemulihan.
13. **Notifikasi keterlambatan di dalam aplikasi adalah fitur inti dan dapat dilihat siapa pun yang membuka halaman notifikasi.** Notifikasi berfungsi sebagai pengingat sosial bagi peminjam dan teman-temannya. WhatsApp tidak digunakan (DEC-017); jangan mengusulkannya kembali kecuali pengguna meminta.
14. **ID eksemplar dan QR buku dibuat otomatis oleh aplikasi.** Nomor registrasi lama sekolah tidak dipakai (DEC-004 direvisi). Jangan meminta petugas memasukkan nomor registrasi satu per satu.
15. **Jangan menghapus anggota secara otomatis.** Anggota yang tidak aktif cukup dinonaktifkan; identitas minimal dan riwayat transaksi dipertahankan (DEC-020 revisi v4.1).
16. **Perpanjangan hanya satu kali untuk setiap eksemplar selama 7 hari tambahan.** Perpanjangan harus dipilih dan dikonfirmasi oleh anggota, bukan dilakukan otomatis tanpa tindakan anggota.
17. **Buku belum dikembalikan tidak otomatis dianggap hilang.** Setelah lebih dari 7 hari lewat jatuh tempo, tandai sebagai keterlambatan serius, blokir peminjaman baru, dan arahkan ke pengembalian atau penyelesaian kehilangan/kerusakan.

## 0.2 Cara menggunakan dokumen ini

- Untuk **chatbot perencanaan**, gunakan Bagian 1–8, 13, dan 15.
- Untuk **AI coding agent**, sertakan seluruh dokumen; agent harus memulai dari Bagian 9–12 dan 14 lalu melakukan audit repositori.
- Untuk **evaluasi fitur**, cari requirement ID dan kriteria penerimaannya di Bagian 10.
- Untuk **handoff antar-AI**, isi templat di Bagian 14.4.
- Saat dokumen diperbarui, tambahkan tanggal, alasan, dan sumber keputusan. Jangan sekadar menimpa keputusan lama tanpa catatan perubahan.

## 0.3 Aturan prioritas informasi

Jika dua sumber berbeda, gunakan urutan berikut dengan mempertimbangkan konteks dan tanggal:

1. **Instruksi terbaru pengguna yang jelas dan spesifik**, selama tidak bertentangan dengan keputusan lain yang lebih baru.
2. **Keputusan produk yang secara eksplisit dikonfirmasi pengguna** dan belum dibatalkan.
3. **Dokumen kebutuhan/keputusan proyek terbaru yang telah dikonfirmasi pengguna.**
4. **Kondisi aktual repositori, konfigurasi, database, dan hasil tes** untuk menjawab apa yang benar-benar sudah diimplementasikan.
5. Laporan AI/agent sebelumnya, dokumentasi draft, serta usulan arsitektur—hanya sebagai petunjuk yang perlu diverifikasi.
6. Asumsi AI sendiri—tidak boleh mengalahkan sumber di atas.

Ada dua macam kebenaran yang harus dibedakan:

- **Kebenaran produk:** perilaku yang pengguna inginkan atau telah setujui.
- **Kebenaran implementasi:** perilaku yang benar-benar dilakukan kode saat ini.

Jika keduanya berbeda, jangan menganggap salah satunya otomatis menggantikan yang lain. Catat sebagai *gap* untuk direncanakan dan diperbaiki.

---

# 1. Ringkasan Eksekutif

## 1.1 Apa proyek ini?

**Sistem Perpustakaan Digital Sekolah** adalah aplikasi pengelolaan perpustakaan yang mendigitalkan katalog buku, eksemplar fisik, anggota, transaksi peminjaman dan pengembalian, riwayat, kondisi buku, administrasi, serta proses layanan mandiri berbasis QR.

Sistem ini tidak dimaksudkan hanya sebagai katalog buku di internet. Fokus utamanya adalah **membuat alur kerja perpustakaan lebih tertib, cepat, mudah dipakai, dapat ditelusuri, dan tetap dapat dikelola oleh sekolah dengan biaya operasional serendah mungkin**.

Sistem ini harus dirancang dengan prinsip **self-service-first**: petugas perpustakaan bukan operator utama untuk transaksi rutin. Dalam kondisi operasional normal, anggota harus dapat menyelesaikan peminjaman dan pengembalian sendiri melalui satu tablet bersama yang memiliki kamera, tanpa petugas harus memindai, mengetik, menyetujui, atau mencatat setiap transaksi. Siswa dapat mencari buku melalui ponsel, sedangkan transaksi mandiri dilakukan di tablet bersama. QR anggota mengidentifikasi akun anggota; QR buku mengidentifikasi satu eksemplar fisik tertentu. Petugas/admin tetap mungkin diperlukan untuk penyiapan awal, pemeliharaan data, kebijakan, audit, dan pengecualian tertentu—tetapi keterlibatan itu tidak boleh menjadi ketergantungan dalam alur rutin.

## 1.2 Masalah yang ingin diselesaikan

Sistem ingin membantu mengurangi masalah yang lazim terjadi dalam pengelolaan perpustakaan sekolah, antara lain:

- pencatatan buku dan transaksi secara manual atau tersebar;
- kesulitan mengetahui eksemplar fisik mana yang sedang dipinjam;
- pencarian riwayat pinjaman, pengembalian, buku terlambat, atau buku bermasalah yang lambat;
- beban petugas untuk mencatat transaksi satu per satu;
- sulitnya melayani banyak siswa secara efisien;
- risiko data ganda, transaksi tidak konsisten, atau status buku yang tidak sesuai kondisi aktual;
- sulitnya menjaga data saat aplikasi dipindahkan ke hosting atau komputer lain;
- kurangnya dokumentasi yang menjelaskan kepada AI/pengembang berikutnya apa yang sebenarnya dimaksud oleh pemilik proyek.

Daftar ini adalah masalah yang hendak ditangani proyek, bukan klaim bahwa setiap masalah tersebut sudah terukur di sekolah.

## 1.3 Mengapa proyek ini dibuat?

Tujuan utamanya adalah menghasilkan alat yang bisa benar-benar membantu kegiatan perpustakaan sekolah, bukan hanya menambah daftar fitur untuk portofolio. Portofolio dan pengembangan kemampuan teknis adalah manfaat tambahan, tetapi kebutuhan pengguna perpustakaan dan integritas data tetap menjadi prioritas.

Alasan penting lainnya adalah mengurangi ketergantungan pada proses manual tanpa membuat operasional sekolah terbebani biaya layanan bulanan yang tidak realistis. Karena itu, solusi hosting, penyimpanan, AI, dan infrastruktur lain harus dinilai dari biaya aktual, batas layanan gratis, risiko, dan kemampuan berpindah platform.

## 1.4 Gambaran pengguna

Pengguna yang diperkirakan terlibat:

- **Anggota aktif:** menjalankan sendiri transaksi rutin melalui kiosk/tablet layanan mandiri.
- **Administrator/pengelola yang berwenang:** menyiapkan dan memperbarui katalog/eksemplar/anggota, mengelola kebijakan dan konfigurasi, mengakses laporan dan notifikasi keterlambatan, melakukan koreksi yang diizinkan, serta menangani audit dan kasus pengecualian. Peran ini tidak boleh disamakan dengan operator transaksi rutin; belum tentu harus dijalankan oleh petugas perpustakaan khusus.
- **Siswa/anggota aktif:** mencari buku, menggunakan kartu anggota digital, serta meminjam dan mengembalikan buku melalui prosedur yang diizinkan.
- **Guru/staf sekolah yang terdaftar sebagai anggota:** menggunakan layanan sesuai kebijakan sekolah yang nantinya dikonfirmasi.
- **Pengunjung umum:** hanya membaca buku di dalam perpustakaan; **tidak diperbolehkan meminjam atau menggunakan alur peminjaman mandiri** berdasarkan keputusan pengguna saat ini.
- **Pengelola teknis/pemilik proyek:** memelihara aplikasi, menguji, melakukan backup, menangani deployment, serta memastikan dokumentasi dan repositori tetap terpelihara.

Hak akses terperinci per kategori pengguna masih harus diverifikasi dan ditetapkan dengan pihak sekolah. Jangan mengarang kebijakan keanggotaan hanya dari daftar peran di atas.

## 1.5 Ukuran arah keberhasilan

Sistem dianggap bergerak ke arah yang benar ketika:

- petugas dapat menemukan buku dan riwayat transaksi dengan mudah;
- setiap eksemplar fisik dapat dibedakan dan statusnya dapat dipercaya;
- peminjaman beberapa buku dan pengembalian sebagian tidak merusak konsistensi data;
- transaksi gagal tidak meninggalkan keadaan setengah jadi;
- anggota dapat diimpor dalam jumlah besar dengan validasi yang jelas;
- anggota dapat menyelesaikan peminjaman dan pengembalian rutin secara mandiri tanpa petugas menjadi operator transaksi;
- kegagalan umum memiliki pemulihan mandiri yang aman dan jelas, atau berhenti secara aman tanpa merusak data;
- QR rusak atau tidak terbaca memiliki prosedur alternatif yang dapat diaudit;
- backup bisa diuji pulih, bukan hanya sekadar file backup yang tersimpan;
- sistem dapat dijalankan kembali pada lingkungan yang didokumentasikan;
- fitur yang disebut “terverifikasi” memiliki bukti tes atau pemeriksaan yang sesuai.

Target kuantitatif—misalnya waktu maksimal transaksi, jumlah maksimal pinjaman per anggota, target waktu pulih, atau target ketersediaan layanan—belum ditetapkan dan tidak boleh diisi dengan angka rekaan.

---

# 2. Visi, Prinsip, dan Batas Proyek

## 2.1 Visi produk

Membangun sistem perpustakaan sekolah yang praktis, bisa diandalkan, berbiaya rendah, ramah pengguna, dapat berkembang secara bertahap, serta mudah dipahami dan dipelihara oleh pengembang berikutnya.

## 2.2 Prinsip desain

1. **Data terlebih dahulu.** Setiap tampilan dan proses transaksi harus mencerminkan keadaan data yang benar.
2. **Satu sumber kebenaran.** Status transaksi dan eksemplar tidak boleh tersebar pada beberapa catatan yang dapat saling bertentangan.
3. **Per-eksemplar, bukan hanya per-judul.** Dua salinan buku dengan judul sama tetap merupakan dua benda fisik berbeda.
4. **Transaksi atomik.** Jika satu operasi harus mengubah beberapa catatan yang saling berkaitan, perubahan harus seluruhnya berhasil atau seluruhnya dibatalkan.
5. **Keamanan proporsional dan transparan.** Gunakan perlindungan yang masuk akal tanpa menjanjikan bahwa QR tidak bisa disalahgunakan.
6. **Biaya operasional rendah, tetapi realistis.** “Gratis” berarti sesuai batas layanan yang berlaku, bukan dijamin gratis selamanya.
7. **Mudah dipakai oleh pengguna nonteknis.** Instruksi, pesan kesalahan, serta proses pemulihan harus jelas.
8. **Riwayat dapat ditelusuri.** Koreksi dan tindakan penting sebaiknya memiliki identitas pelaku, waktu, serta alasan.
9. **Bisa dipindahkan dan dipulihkan.** Data penting tidak boleh terperangkap pada filesystem sementara atau layanan yang tidak dapat diekspor.
10. **Pengembangan bertahap.** Fitur baru harus menyatu dengan arsitektur dan kebijakan yang ada, bukan memaksa penulisan ulang tanpa alasan kuat.

## 2.3 Bukan tujuan utama proyek

Hal-hal berikut bukan tujuan inti dan tidak boleh menggeser prioritas tanpa persetujuan pengguna:

- membangun sistem enterprise kompleks hanya demi memakai teknologi tertentu;
- menambah fitur AI yang tidak menyelesaikan kebutuhan perpustakaan;
- mengganti seluruh aplikasi atau framework secara impulsif;
- menambahkan denda berupa uang, pembayaran denda online, atau kebijakan denda di luar yang ditetapkan (DEC-024) tanpa keputusan pemilik proyek;
- memperbolehkan pengunjung umum meminjam buku;
- mengklaim QR sebagai bukti fisik yang tidak dapat dipalsukan;
- memindahkan data nyata ke hosting sebelum pengujian, privasi, backup, dan pemulihannya layak;
- mengoptimalkan jumlah fitur dengan mengorbankan keutuhan catatan transaksi.

## 2.4 Batas ruang lingkup

**Ruang lingkup inti:** katalog, data eksemplar fisik, data anggota, peminjaman, pengembalian, kondisi buku, riwayat, admin, QR, impor/ekspor, keamanan, backup, hosting, dan panduan.

**Fitur inti termasuk:** Asisten AI/pencarian pintar berbasis Google Gemini API, notifikasi keterlambatan yang dapat dilihat siapa pun yang membuka halaman notifikasi, pembuatan ID dan QR eksemplar otomatis, perpanjangan satu kali, dan alur penyelesaian buku hilang/rusak dengan pengganti berupa kamus atau Al-Qur’an. Semuanya bukan fitur opsional. Batas penggunaan, biaya, privasi, dan penanganan kegagalan tetap wajib dirancang dan diverifikasi. Fitur analitik lanjutan dapat diprioritaskan setelah alur inti stabil.

**Di luar cakupan tanpa keputusan baru:** peminjaman pengunjung umum, pengiriman pesan keluar ke anggota (WhatsApp/SMS/email), perubahan kebijakan resmi sekolah, integrasi ke database sekolah yang belum disetujui, dan tindakan otomatis yang berdampak pada data nyata tanpa tinjauan yang sesuai.

---

# 3. Status Informasi: Keputusan, Rencana, Laporan Lama, dan Hal Terbuka

Bagian ini penting untuk mencegah AI membuat klaim yang tidak benar.

## 3.1 Keputusan produk dan arsitektur yang telah ditetapkan pengguna

Keputusan berikut menjadi acuan utama dan hanya boleh diubah oleh pengguna. Detail teknis paket gratis tetap harus diverifikasi, karena ketentuan penyedia dapat berubah.

| ID | Keputusan | Dampak terhadap implementasi |
|---|---|---|
| DEC-001 | Pengunjung umum hanya boleh membaca buku di tempat dan tidak boleh meminjam. | Tidak ada akun peminjaman pengunjung umum. |
| DEC-002 | Layanan mandiri memakai satu tablet bersama yang memiliki kamera. | UX scan, sesi bersama, dan reset otomatis harus dirancang untuk tablet. |
| DEC-003 | Siswa dapat mencari buku lewat ponsel; transaksi mandiri dilakukan di tablet perpustakaan. | Pisahkan penjelajahan katalog dari transaksi kiosk. |
| DEC-004 | **[REVISI v4.0]** Identitas unik eksemplar fisik adalah ID unik yang dibuat otomatis oleh aplikasi. Nomor registrasi lama sekolah tidak digunakan lagi. | Petugas tidak perlu memasukkan nomor registrasi satu per satu. Cukup tentukan judul dan jumlah eksemplar; aplikasi membuat ID unik untuk tiap eksemplar. ID harus pendek serta mudah dibaca dan diketik. Judul bukan identitas fisik. |
| DEC-005 | Masa pinjam adalah **maksimal 7 hari/168 jam** sejak transaksi pinjam berhasil. Setiap eksemplar dapat diperpanjang satu kali selama 7 hari tambahan. | Jatuh tempo dibuat otomatis per eksemplar. Perpanjangan hanya setelah anggota memilihnya dan mengonfirmasi lewat alur QR/perpanjangan yang disediakan sistem. Setelah perpanjangan digunakan, buku harus dikembalikan. |
| DEC-006 | Pengembalian tidak harus dilakukan oleh peminjam asli. | Pengembalian dicocokkan berdasarkan eksemplar dan pinjaman aktif, bukan identitas orang yang sedang mengembalikan. |
| DEC-007 | Satu transaksi dapat berisi banyak eksemplar dan pengembalian bisa sebagian. | Setiap eksemplar memiliki status/waktu pinjam dan kembali masing-masing. |
| DEC-008 | Kartu anggota digital dapat dicetak sendiri. | Tidak diwajibkan memakai kartu plastik. |
| DEC-009 | **[REVISI v4.0]** Data anggota diimpor dari file Excel/CSV (sumber: Tata Usaha) sesuai template dan panduan yang disediakan layanan impor aplikasi. Data yang disimpan minimal (DEC-023). | Jangan mengakses sistem TU langsung kecuali ada persetujuan dan integrasi resmi. Format kolom ditentukan oleh template aplikasi, bukan format bawaan TU. |
| DEC-010 | QR anggota boleh memakai metode teknis yang sesuai, asalkan sistem dapat mengidentifikasi anggota dengan benar dan aman. | Pilihan token/ID ditentukan berdasarkan keamanan; QR tidak boleh membocorkan data pribadi secara terbuka. |
| DEC-011 | **[REVISI v4.0]** QR buku dibuat otomatis oleh aplikasi untuk tiap eksemplar dan dapat dicetak dari aplikasi. Label cetak menampilkan ID eksemplar yang mudah dibaca manusia. | Aplikasi menyediakan cetak label/lembar QR per judul atau per batch. Label sebaiknya juga memuat judul singkat agar tidak salah tempel (usulan, perlu persetujuan). |
| DEC-012 | **[REVISI v4.0]** Impor/ekspor anggota dan buku adalah fungsi administrasi utama. Buku ditambah dengan memasukkan judul dan jumlah eksemplar (manual atau lewat Excel/CSV), lalu aplikasi membuat ID dan QR otomatis. | File Excel lengkap berisi semua buku tidak diwajibkan. Impor memberi pratinjau dan ringkasan hasil serta tidak menghapus histori transaksi. |
| DEC-013 | **[DIGANTIKAN v4.0]** Eksemplar tidak dicocokkan lewat nomor registrasi. Menambah jumlah buku berarti membuat eksemplar baru dengan ID baru; eksemplar yang sudah ada tidak pernah digabung atau ditimpa hanya karena judulnya sama. | Satu judul katalog dapat memiliki banyak eksemplar. Kunci pencocokan katalog (agar judul tidak terduplikasi saat impor) masih perlu diputuskan (OPEN-012). |
| DEC-014 | Hosting backend target adalah Hugging Face Spaces menggunakan Docker. | Jangan menganggap filesystem lokal Space sebagai penyimpanan permanen. Rancang aplikasi agar bisa tidur/restart/deploy tanpa kehilangan data penting. |
| DEC-015 | Database target adalah Supabase PostgreSQL. | Data transaksi dan katalog disimpan di PostgreSQL, bukan hanya file SQLite lokal pada container. Siapkan ekspor, backup terpisah, dan uji restore. |
| DEC-016 | Google Gemini API menjadi layanan Asisten AI/pencarian pintar. | Model yang direncanakan adalah Gemini 2.5 Flash; nama model, kuota, dan harga/free tier harus diverifikasi sebelum implementasi/deploy. |
| DEC-017 | **[REVISI v4.1]** Pengingat keterlambatan menggunakan notifikasi dalam aplikasi yang dapat dilihat siapa pun yang membuka halaman notifikasi. WhatsApp tidak digunakan. | Halaman notifikasi menampilkan informasi secukupnya tentang pinjaman terlambat agar peminjam dan teman-temannya dapat saling mengingatkan. Data dihitung dari transaksi aktual; tidak memerlukan provider pesan. |
| DEC-018 | Prinsip mutlak adalah self-service-first. | Petugas tidak mengoperasikan peminjaman rutin. Peran petugas dibatasi terutama pada impor/ekspor data anggota/buku dan tugas administrasi yang memang diperlukan. |
| DEC-019 | Tidak ada batas maksimum jumlah buku per transaksi yang ditetapkan pengguna; judul sama boleh dipinjam lebih dari satu eksemplar. | Jangan membuat batas buatan. Tetap cegah peminjaman ganda atas eksemplar fisik yang sama dan validasi setiap eksemplar. |
| DEC-020 | **[REVISI v4.1]** Anggota yang tidak aktif cukup dinonaktifkan; tidak ada penghapusan otomatis berdasarkan masa tidak aktif. | Data inti anggota dan riwayat transaksi tetap tersimpan. Akun nonaktif tidak dapat memulai peminjaman baru, tetapi dapat diaktifkan kembali oleh petugas yang berwenang. Penghapusan permanen bukan bagian dari versi pertama. |
| DEC-021 | Target biaya operasional adalah Rp0 jika memungkinkan. | Jangan menjanjikan layanan gratis selamanya; cek ketentuan paket dan biaya terbaru serta laporkan batas dan risiko. |
| DEC-022 | Panduan dan UI harus berbahasa Indonesia yang sangat sederhana, mudah dipahami orang awam bahkan anak kecil. | Gunakan kalimat pendek, istilah sehari-hari, instruksi satu langkah demi satu langkah, contoh konkret, dan pesan error yang menjelaskan tindakan berikutnya. |
| DEC-023 | **[REVISI v4.1]** Data anggota sederhana: nama, status aktif/nonaktif, dan kategori yang mengacu pada tabel kategori anggota. Kelas tidak disimpan sebagai data inti. | Kategori dikelola sebagai tabel referensi, bukan kumpulan kolom khusus per jenis anggota. Simpan hanya data yang diperlukan untuk identifikasi dan operasional. QR tidak menampilkan data pribadi lebih dari yang diperlukan. |
| DEC-024 | **[REVISI v4.1]** Buku yang dinyatakan hilang atau rusak dapat diselesaikan dengan penggantian berupa kamus atau Al-Qur’an, bukan uang. | Melalui sesi pengembalian, anggota memilih eksemplar bermasalah, kondisi, keterangan, dan jenis pengganti untuk tiap buku. Sistem meminta konfirmasi akhir dan menyimpan audit trail. Status penyelesaian baru final setelah pengganti diterima/dikonfirmasi sesuai prosedur sekolah. Keterlambatan saja tidak otomatis berarti hilang. |

## 3.1.1 Riwayat perubahan keputusan

| ID | Sebelum (v4.0) | Sesudah (v4.1) | Alasan |
|---|---|---|---|
| DEC-005 | Maksimal 7 hari; perpanjangan belum ditetapkan. | Maksimal 7 hari dan satu kali perpanjangan 7 hari per eksemplar, melalui tindakan/konfirmasi anggota. | Klarifikasi pengguna 17 Oktober 2026. |
| DEC-017 | Notifikasi hanya untuk admin. | Notifikasi dalam aplikasi dapat dilihat siapa pun yang membuka halaman notifikasi; WhatsApp tetap tidak digunakan. | Pengingat sosial agar peminjam dan teman dapat saling mengingatkan. |
| DEC-020 | Penghapusan otomatis setelah 3 tahun tidak aktif. | Tidak ada penghapusan otomatis; nonaktifkan akun dan pertahankan riwayat. | Pengguna menyerahkan keputusan efisiensi kepada rancangan sistem; menjaga histori lebih aman dan sederhana. |
| DEC-023 | Nama/status dengan beberapa keterangan kategori yang belum konsisten. | Nama, status aktif/nonaktif, dan kategori dari tabel kategori anggota. | Klarifikasi bahwa data anggota harus sederhana. |
| DEC-024 | Pemicu dan proses penggantian masih terbuka. | Alur penyelesaian hilang/rusak ditetapkan: pilih buku, kondisi, deskripsi, jenis pengganti per buku, konfirmasi, dan pencatatan penerimaan. | Klarifikasi pengguna 17 Oktober 2026. |
| LIB-LOSS-001 | Proses penggantian belum ditetapkan. | Penyelesaian dapat mencakup beberapa buku dalam satu sesi, tetapi keputusan dan pengganti dicatat per eksemplar. | Mempercepat operasional tanpa kehilangan jejak audit. |

**Catatan perapian v4.2** (tidak mengubah keputusan v4.1):
- Glosarium, judul P3, dan butir roadmap yang masih memakai istilah lama (notifikasi untuk admin, denda berupa buku) disesuaikan.
- 4.9.1 diselaraskan dengan DEC-023: data inti nama, status aktif/nonaktif, dan kategori dari tabel referensi.
- 4.4, 4.8, dan 6.5 diselaraskan menjadi dua jalur pengembalian (lihat 4.8). Ini penyelarasan atas dua teks yang saling bertentangan dan perlu dikonfirmasi pengguna.
- Pengecualian halaman notifikasi publik ditulis eksplisit di 6.8; pembatasan aksesnya menjadi OPEN-016.
- Kejelasan aturan perpanjangan dan hal kecil lainnya dicatat sebagai OPEN-017 dan OPEN-018. Tidak ada aturan baru yang ditebak.
- Urutan LIB-RETURN dan riwayat dokumen dirapikan.

## 3.2 Rencana yang telah dibahas, tetapi status implementasinya belum dipastikan

- Implementasi/penyempurnaan transaksi multi-buku, QR mandiri, dan impor/ekspor berdasarkan audit kode aktual.
- Implementasi notifikasi keterlambatan dalam aplikasi yang dapat dilihat siapa pun di halaman notifikasi.
- Pembuatan ID eksemplar dan QR otomatis dari judul dan jumlah, serta cetak label.
- Template dan panduan impor anggota dan buku.
- Implementasi alur penyelesaian kehilangan/kerusakan dengan penggantian kamus/Al-Qur’an per eksemplar sesuai DEC-024.
- Integrasi Supabase PostgreSQL dan migrasi dari database pengembangan saat ini bila diperlukan.
- Deployment Flask melalui Docker di Hugging Face Spaces.
- Penyimpanan cover/aset di Supabase Storage atau solusi persisten yang diputuskan setelah memeriksa kebutuhan dan ketentuan aktual.
- Asisten AI/pencarian pintar menggunakan Gemini API.
- Penonaktifan anggota dan pemeliharaan histori sesuai DEC-020; tidak ada penghapusan otomatis.
- Backup terpisah, pengujian pemulihan, pemantauan kegagalan, dan panduan operasional yang sangat sederhana.

Keputusan arsitektur target tidak sama dengan bukti bahwa layanan sudah dikonfigurasi atau fitur sudah berjalan.

## 3.3 Laporan historis yang wajib diverifikasi

Riwayat diskusi pernah menyebut hal-hal berikut. Arsitektur Render/Neon yang ada dalam dokumen lama sudah digantikan oleh keputusan terbaru: Hugging Face Spaces + Docker dan Supabase PostgreSQL. AI wajib memeriksa repositori saat ini sebelum mengandalkannya:

- Aplikasi menggunakan Python Flask, SQLite, HTML/CSS/JavaScript, dan Jinja.
- File yang pernah disebut: `app.py`, `perpustakaan.db`, folder `templates/`, `layout.html`, `peminjaman.html`, `detail_buku.html`, `index.html`, `migrate_p1_multibook.py`, serta folder `tests/`.
- Fitur yang pernah dilaporkan ada: katalog/pencarian/detail buku, tambah/edit buku, cover upload, impor/ekspor Excel, peminjaman/pengembalian, kondisi normal/rusak/hilang, riwayat, denda, login admin, AI Book Assistant/SraX AI melalui Gemini.
- Model Gemini pernah dilaporkan sebagai `gemini-2.5-flash` dengan variabel lingkungan `GEMINI_API_KEY`.
- P1 multi-buku pernah dilaporkan memiliki header `peminjaman` dan detail `peminjaman_detail`, migrasi dengan dry-run/transaksi atomik/pemeriksaan integritas, 14 tes P1 dan total 32 tes.
- Pernah dilaporkan ada branch `feature/p1-multi-book` dan migrasi belum dijalankan ke database produksi.
- Pernah disebut ID fisik buku tersimpan sebagai JSON `id_buku_fisik` pada data `buku` lama.
- Denda pada versi lama pernah dilaporkan berbentuk uang. Itu tidak berlaku lagi (DEC-024).
- Data lama mungkin memuat nomor registrasi atau ID fisik buku. Nomor registrasi tidak dipakai lagi, tetapi data lama perlu dipetakan saat migrasi (OPEN-012).

Seluruh informasi tersebut berstatus **laporan historis, belum diverifikasi di dokumen ini**. Jangan menyimpulkan bahwa branch masih ada, file sama persis, tes masih lulus, atau database belum/sudah bermigrasi sebelum memeriksa bukti aktual.

## 3.4 Hal yang masih perlu dipastikan atau dirancang

Keputusan produk utama berikut sudah ditutup dan tidak boleh ditanyakan ulang. Yang masih tersisa adalah hal implementasi yang harus dipastikan lewat audit kode atau konfigurasi, bukan alasan untuk menunda implementasi. Pada v4.2 ditambahkan tiga butir konfirmasi kecil (OPEN-016 sampai OPEN-018); butir itu tidak menunda bagian lain.

| ID | Hal | Status | Ketentuan |
|---|---|---|---|
| OPEN-001 | Format impor anggota | DITUTUP v4.0 | Gunakan template dan panduan dari aplikasi. |
| OPEN-002 | Identitas eksemplar | DITUTUP v4.0 | ID eksemplar dibuat otomatis oleh aplikasi; nomor registrasi lama tidak digunakan sebagai ID utama. |
| OPEN-003 | Provider WhatsApp | DITUTUP v4.0 | WhatsApp tidak digunakan. |
| OPEN-004 | Ketentuan hosting/API | PERLU VERIFIKASI TEKNIS | Verifikasi kuota, tidur/jeda, cold start, penyimpanan, rate limit, dan biaya aktual. Jangan menjanjikan gratis selamanya. |
| OPEN-005 | Penghapusan anggota tidak aktif | DITUTUP v4.1 | Tidak ada penghapusan otomatis; nonaktifkan akun dan pertahankan histori (DEC-020). |
| OPEN-006 | Buku hilang/rusak | DITUTUP UNTUK VERSI PERTAMA v4.1 | Gunakan alur penyelesaian dan penggantian di Bagian 7; jenis pengganti kamus atau Al-Qur’an. Detail administratif yang diwajibkan sekolah dapat dikonfigurasi tanpa mengubah alur inti. |
| OPEN-007 | Retensi log, backup, dan data pribadi | PRINSIP DISETUJUI | Pertahankan histori yang diperlukan, minimalkan data pribadi, dan siapkan backup/restore. Jadwal retensi log operasional dapat ditetapkan saat deployment. |
| OPEN-008 | Pengguna serentak dan pemulihan | PERLU VERIFIKASI TEKNIS | Uji beban ringan dan pemulihan backup. |
| OPEN-009 | Persetujuan sekolah | CATATAN ADMINISTRATIF | Ikuti proses persetujuan sekolah untuk penggunaan data nyata dan penerimaan barang pengganti. |
| OPEN-010 | Apakah denda berupa uang | DITUTUP v4.0 | Tidak ada pembayaran uang/online; penyelesaian berupa penggantian buku sesuai DEC-024. |
| OPEN-011 | Pencocokan anggota saat impor ulang | ATURAN IMPLEMENTASI DITETAPKAN v4.1 | ID anggota buatan aplikasi menjadi identitas utama dan harus ikut ekspor. Jika file impor tidak membawa ID, sistem menampilkan pratinjau dan menandai nama yang cocok/ambigu; jangan menimpa anggota secara diam-diam. Petugas memilih apakah baris adalah anggota baru atau pembaruan. |
| OPEN-012 | Pencocokan judul katalog dan buku lama | ATURAN IMPLEMENTASI DITETAPKAN v4.1 | ID eksemplar dibuat otomatis. Impor katalog dicocokkan dengan ID katalog jika tersedia; jika tidak, gunakan judul + penulis/ISBN yang tersedia dan tandai kecocokan meragukan di pratinjau. Jangan menggabungkan eksemplar hanya karena judul sama. Label baru dicetak untuk setiap eksemplar yang belum memiliki QR aplikasi. |
| OPEN-013 | Notifikasi keterlambatan | DITUTUP v4.1 | Halaman notifikasi dapat dilihat siapa pun yang membuka halaman tersebut. Tampilkan hanya data minimum yang dibutuhkan untuk pengingat; daftar bersumber dari pinjaman aktual. |
| OPEN-014 | Penghapusan otomatis anggota | DITUTUP v4.1 | Tidak ada pembersihan/penghapusan otomatis berdasarkan masa tidak aktif. Penonaktifan cukup untuk versi pertama. |
| OPEN-015 | Aturan penyelesaian buku hilang/rusak | DITUTUP UNTUK VERSI PERTAMA v4.1 | Satu QR penyelesaian membuka alur dalam sesi anggota yang sah. Satu sesi dapat menyelesaikan beberapa buku; kondisi, deskripsi, dan pilihan kamus/Al-Qur’an dicatat terpisah per buku. Keterlambatan tidak otomatis menyatakan buku hilang. Peminjaman baru diblokir selama ada buku belum kembali atau kewajiban belum selesai. |
| OPEN-016 | Akses dan isi halaman notifikasi publik | TERBUKA | Halaman dapat dilihat siapa pun (DEC-017) dan memuat nama anggota, yang sebagian besar siswa. Putuskan: apakah hanya dapat dibuka dari tablet/jaringan sekolah, apakah nama ditampilkan penuh atau singkat. Sampai diputuskan, tampilkan hanya data minimum di 7.4. |
| OPEN-017 | Perpanjangan setelah lewat jatuh tempo | TERBUKA | Apakah boleh diperpanjang setelah jatuh tempo, dan jatuh tempo barunya dihitung dari jatuh tempo lama atau dari saat konfirmasi. Contoh: buku telat 5 hari lalu diperpanjang. Untuk perpanjangan sebelum jatuh tempo, jatuh tempo baru = jatuh tempo lama + 7 hari. |
| OPEN-018 | Hal kecil yang perlu dikonfirmasi | TERBUKA | (a) Acuan waktu “rentang 24 jam” untuk kelompok pemeriksaan buku. (b) Letak dan bentuk QR Penyelesaian Buku (QR atau tombol di layar tablet). (c) Konfirmasi bahwa keterlambatan tidak dikenai sanksi selain penandaan dan pemblokiran. (d) Konfirmasi bahwa pembatalan penghapusan otomatis anggota (DEC-020) disengaja. |

## 3.5 Arsitektur teknis target yang ditetapkan pengguna

Bagian ini mencatat pilihan arsitektur yang terbaru. Ini adalah arsitektur target; AI tetap harus memeriksa kode aktual dan ketentuan layanan terbaru sebelum mengklaim semuanya sudah dikonfigurasi.

### A. Frontend

Antarmuka responsif untuk katalog, detail buku, dashboard, formulir administrasi, pemindaian QR, transaksi mandiri, serta chat/pencarian pintar dengan Asisten AI. Antarmuka utama berbahasa Indonesia yang sangat sederhana—mudah dipahami orang awam dan anak kecil. Gunakan kalimat pendek, satu instruksi per langkah, tombol yang jelas, dan pesan error yang memberitahu pengguna apa yang harus dilakukan selanjutnya.

### B. Backend: Python + Flask di Hugging Face Spaces (Docker)

Flask menjalankan aturan bisnis, validasi QR, pinjam/kembali/perpanjangan/penyelesaian, laporan, integrasi Gemini, dan sumber data notifikasi dalam aplikasi yang dapat dilihat siapa pun yang membuka halaman notifikasi. Backend ditargetkan berjalan di Hugging Face Spaces menggunakan Docker. Karena layanan gratis dapat tidur atau mengalami cold start, aplikasi harus menampilkan status memuat yang jelas dan menangani timeout/retry tanpa menggandakan transaksi. Angka cold start sekitar 30 detik yang disebut pengguna adalah perkiraan operasional yang perlu diverifikasi, bukan SLA terjamin.

### C. Database: Supabase PostgreSQL

Database target adalah Supabase PostgreSQL untuk anggota, katalog, eksemplar, transaksi, histori, dan status pesan. Data penting tidak boleh hanya disimpan di filesystem container Hugging Face. Gunakan migrasi terkontrol, transaksi database, indeks, batasan unik, dan strategi backup/restore. Jangan mengklaim data aman selamanya atau bahwa database tidak akan pernah pause: kuota, pause/retensi, kebijakan dan harga layanan harus diverifikasi berdasarkan paket aktual.

### D. Asisten AI: Google Gemini API

Asisten AI mendukung chat/pencarian pintar, rekomendasi buku, dan panduan penggunaan. Model yang ditargetkan adalah Gemini 2.5 Flash melalui API Google AI Studio, dengan status model/kuota/harga diverifikasi sebelum rilis. Backend menjadi perantara; API key disimpan sebagai secret/environment variable. AI tidak menjadi sumber kebenaran stok atau transaksi. Bila AI gagal, katalog, peminjaman, dan pengembalian inti harus tetap berjalan.

### E. QR anggota dan QR buku

QR anggota harus mengidentifikasi anggota yang datanya diimpor dari file (sumber Tata Usaha). Metode token/ID dapat dipilih berdasarkan keamanan dan kemudahan; data pribadi tidak boleh ditulis langsung ke QR dalam bentuk terbuka. QR buku dibuat otomatis oleh aplikasi untuk satu eksemplar, berdasarkan ID unik yang juga dibuat aplikasi. **Lembar/label QR buku wajib menampilkan ID eksemplar yang bisa dibaca manusia** agar orang yang menempel label tahu QR itu untuk buku yang mana. Server tetap memvalidasi status aktual di database.

### F. Penyimpanan aset dan backup

Hugging Face Spaces adalah tempat menjalankan backend, bukan tempat penyimpanan permanen untuk data penting. Data bisnis berada di Supabase PostgreSQL. Cover buku dan aset harus ditempatkan pada penyimpanan persisten yang diputuskan dan diuji, misalnya Supabase Storage jika sesuai batas paket. Backup database dan aset harus terpisah dari penyimpanan utama, dan pemulihan harus pernah diuji. Update atau restart aplikasi tidak boleh menghilangkan data.

### G. Keamanan, sesi tablet, dan pengujian

Cegah peminjaman ganda dengan validasi server/database, lindungi hak akses admin, jaga API key, gunakan HTTPS, dan kelola sesi tablet bersama agar data anggota sebelumnya dibersihkan setelah transaksi atau timeout. Sistem perlu diuji terhadap scan berulang, QR invalid, konflik transaksi, kegagalan jaringan, cold start, kegagalan Gemini, backup/restore, serta tampilan notifikasi keterlambatan setelah backend bangun dari tidur. Tablet yang login sebagai admin dan juga dipakai anggota harus memisahkan mode layanan mandiri dari halaman admin, supaya anggota tidak dapat membuka data admin.

### Catatan realisme biaya dan layanan gratis

Target produk adalah biaya operasional Rp0 jika bisa dicapai. Namun “gratis selamanya”, “data dijaga selamanya”, “bangun seketika”, dan waktu cold start tertentu tidak boleh dianggap jaminan tanpa dukungan ketentuan layanan aktual. AI wajib memeriksa paket gratis terbaru, batas pemakaian, kebijakan pause, kuota database/storage, dan rate limit Gemini. Pekerjaan berkala (misalnya pembersihan anggota tidak aktif) tidak boleh hanya berupa loop background di proses Flask yang dapat tidur; jalankan saat admin membuka aplikasi atau lewat scheduler eksternal yang telah diuji.

---

# 4. Pengguna, Skenario Penggunaan, dan Aturan Layanan

## 4.1 Prinsip operasional: self-service-first

**Aturan wajib:** petugas perpustakaan bukan operator utama untuk transaksi rutin. Aplikasi tidak boleh dirancang dengan asumsi bahwa petugas selalu hadir untuk memulai, memvalidasi secara manual, atau menyelesaikan setiap peminjaman/pengembalian. Dalam kondisi normal, anggota harus dapat menjalankan proses secara mandiri di tablet bersama.

Pekerjaan yang boleh membutuhkan administrator/pengelola berwenang adalah penyiapan awal, impor/pembaruan data anggota, pengelolaan katalog dan eksemplar, konfigurasi kebijakan, audit, backup/pemulihan, koreksi administratif, dan kasus pengecualian yang tidak aman untuk diputuskan otomatis. Peran administratif ini tidak harus menjadi petugas transaksi sehari-hari. Siapa yang secara resmi memegang kewenangan tersebut perlu disepakati dengan sekolah.

Sistem harus menyediakan pesan kesalahan yang bisa dipahami, tombol batal/ulang, pemulihan sesi, dan jalur alternatif yang aman untuk masalah umum. Jika sebuah kasus tidak dapat diputuskan dengan aman tanpa manusia, sistem harus berhenti tanpa mengubah data secara keliru dan mencatat kasus tersebut untuk tindak lanjut. Jangan berpura-pura bahwa transaksi berhasil, jangan membuat data palsu, dan jangan menjadikan petugas sebagai syarat untuk setiap transaksi normal.

## 4.2 Skenario administrator/pengelola

Administrator/pengelola yang berwenang menyiapkan dan memelihara data buku/eksemplar/anggota, meninjau laporan, menjalankan impor/ekspor, memperbaiki kesalahan melalui prosedur yang tercatat, mengelola konfigurasi, serta menangani kasus yang memerlukan keputusan manusia. Tindakan administratif yang mengubah catatan penting sebaiknya mencatat siapa, kapan, apa yang diubah, dan alasannya. Sistem harus tetap dapat melayani transaksi rutin ketika administrator tidak sedang membuka aplikasi, selama layanan dan infrastruktur berjalan normal.

## 4.3 Skenario siswa/anggota

Anggota aktif dapat mencari buku dan melihat informasi katalog yang diizinkan. Pada layanan mandiri, anggota memulai sesi di tablet, memindai QR anggota, lalu memindai QR tiap eksemplar yang hendak dipinjam. Sebelum transaksi selesai, sistem menampilkan daftar eksemplar, aturan terkait, serta ringkasan due date agar pengguna dapat memeriksa transaksi. Transaksi hanya diselesaikan setelah validasi terakhir berhasil.

Alur tersebut adalah target produk; keberadaan tiap langkah di antarmuka aktual harus diperiksa dari kode.

## 4.4 Skenario pengembalian oleh orang lain

Pengembalian tidak harus dilakukan oleh anggota yang meminjam. Orang yang membawa buku dapat melakukan proses pengembalian melalui alur yang disediakan, sementara sistem menentukan pinjaman aktif berdasarkan QR eksemplar yang dipindai. Sistem perlu menampilkan judul/identitas yang cukup untuk konfirmasi, lalu mencatat waktu pengembalian serta kondisi buku.

QR anggota atau sesi yang sebelumnya digunakan untuk peminjaman tidak boleh membuat sistem menolak pengembalian hanya karena orang yang sedang berada di tablet berbeda dari peminjam asli. Pengecekan yang benar adalah memastikan eksemplar tersebut mempunyai pinjaman aktif yang sah dan belum dikembalikan. Jalur ini (jalur A di 4.8) tidak memerlukan kartu anggota. Perpanjangan dan penyelesaian buku hilang/rusak dilakukan lewat sesi anggota (jalur B).

## 4.5 Skenario pengunjung umum

Pengunjung boleh membaca buku di area perpustakaan sesuai kebijakan sekolah, tetapi tidak boleh meminjam melalui sistem. Jangan membangun akun pengunjung untuk meminjam, memberikan QR anggota peminjaman kepada pengunjung, atau mengaktifkan fitur peminjaman umum kecuali pengguna mengubah keputusan DEC-001.

## 4.6 Aturan masa pinjam, perpanjangan, dan notifikasi keterlambatan

- **Masa pinjam awal maksimal 7 hari/168 jam** sejak transaksi berhasil. Sistem menetapkan jatuh tempo otomatis untuk setiap eksemplar.
- Anggota boleh mengembalikan kapan saja sebelum atau sesudah jatuh tempo. Pengembalian lebih awal tidak membutuhkan masa pinjam minimum.
- Setiap eksemplar boleh diperpanjang **satu kali saja selama 7 hari tambahan**. Perpanjangan harus dipilih dan dikonfirmasi oleh anggota. Gunakan QR/perintah perpanjangan yang disediakan sistem; satu QR sesi dapat membawa daftar buku yang dipilih, tetapi setiap eksemplar tetap divalidasi dan diperpanjang satu per satu secara logis.
- Sistem tidak boleh memperpanjang buku otomatis hanya karena buku lain dikembalikan. Saat anggota menyelesaikan sesi pengembalian, sistem menampilkan buku lain yang belum dipindai, terutama buku yang dipinjam dalam rentang 24 jam dari kelompok waktu pengembalian itu, dan bertanya apakah ingin memperpanjangnya.
- Jika buku belum dikembalikan dan tidak diperpanjang, statusnya **Belum dikembalikan**; jika melewati jatuh tempo, status tambahan **Terlambat** berlaku. Setelah lebih dari 7 hari lewat jatuh tempo, tampilkan peringatan keterlambatan serius dan blokir peminjaman baru sampai buku dikembalikan atau penyelesaian kehilangan/kerusakan selesai. Sistem tidak otomatis menetapkan buku hilang.
- **Notifikasi keterlambatan di dalam aplikasi adalah fitur wajib dan dapat dilihat siapa pun yang membuka halaman notifikasi.** WhatsApp tidak digunakan. Tujuannya agar peminjam dan teman yang melihatnya dapat saling mengingatkan (DEC-017).
- Daftar notifikasi dihitung dari data transaksi aktual; tidak membutuhkan nomor telepon, provider pesan, atau scheduler untuk menghitung status.
- Setiap eksemplar memiliki waktu pinjam, jatuh tempo, waktu perpanjangan, dan waktu kembali sendiri. Transaksi multi-buku tidak boleh menyamakan jatuh tempo antar-eksemplar.
- Simpan timestamp secara konsisten dan tampilkan dalam zona waktu sekolah yang dikonfigurasi. Uji tepat 168 jam dan batas keterlambatan lebih dari 7 hari.

Jangan membulatkan durasi tanpa definisi yang jelas. Jangan menyimpan durasi sebagai nilai bebas yang berbeda dari timestamp tanpa mekanisme konsistensi.

## 4.7 Peminjaman beberapa buku

Satu proses peminjaman dapat mencakup beberapa eksemplar. Namun, setiap eksemplar perlu memiliki status dan riwayatnya sendiri sehingga pengembalian sebagian tidak memaksa semua buku dalam transaksi dianggap telah kembali.

Contoh konseptual:

- Anggota meminjam eksemplar A, B, dan C dalam satu proses.
- B dikembalikan lebih dahulu; A dan C masih dipinjam.
- Sistem harus mencatat B sebagai kembali, sedangkan A dan C tetap aktif.
- Riwayat transaksi induk dapat menandai transaksi sebagai sebagian selesai atau status setara, tetapi label final harus mengikuti desain yang diaudit dan ditetapkan.

Pengguna tidak menetapkan batas maksimum jumlah buku dalam satu transaksi. Jangan membuat batas buatan tanpa persetujuan. Judul yang sama boleh dipinjam lebih dari satu kali jika setiap eksemplar memiliki ID eksemplar berbeda.

## 4.8 Jalur pengembalian

Ada dua jalur yang saling melengkapi (penyelarasan v4.2, perlu konfirmasi pengguna):

- **Jalur A, kembalikan buku:** siapa pun memindai QR buku. Server menemukan pinjaman aktif eksemplar itu, menampilkan judul secukupnya untuk konfirmasi, lalu mencatat waktu dan kondisi. Tidak perlu kartu anggota, sehingga teman peminjam juga bisa mengembalikan.
- **Jalur B, sesi anggota:** peminjam asli memakai kartunya untuk mengembalikan banyak buku sekaligus, memperpanjang, atau menyelesaikan buku hilang/rusak. Langkahnya:

1. Anggota masuk ke sesi pengembalian melalui identifikasi QR anggota.
2. Sistem menampilkan daftar eksemplar yang masih tercatat dipinjam oleh anggota tersebut.
3. Anggota memindai QR setiap buku yang benar-benar dikembalikan. Setiap pemindaian memvalidasi eksemplar dan pinjaman aktif; buku yang tidak dipindai tidak dianggap kembali.
4. Saat anggota memilih **Selesaikan Sesi**, sistem menampilkan ringkasan buku yang dikembalikan dan daftar buku yang masih belum dipindai.
5. Untuk setiap buku yang masih dipinjam, anggota dapat memilih perpanjangan satu kali selama 7 hari tambahan jika masih memenuhi syarat, membiarkannya tetap dipinjam, atau membuka alur penyelesaian jika buku hilang/rusak.
6. Buku yang dipinjam dalam rentang 24 jam dapat ditampilkan sebagai kelompok pemeriksaan bersama, tetapi status dan keputusan tetap per eksemplar (definisi acuan waktunya: OPEN-018).
7. Sistem meminta konfirmasi akhir dan menyimpan perubahan secara atomik. Buku yang belum dipindai tetap berstatus belum dikembalikan.
8. Setelah sesi selesai, sistem membersihkan data sesi dari layar bersama dan menampilkan ringkasan hasil.

Pengembalian lewat jalur A tidak harus dilakukan oleh peminjam asli. Jika QR tidak terbaca, jalur alternatif dapat menggunakan ID eksemplar tercetak dan validasi tambahan; tindakan manual harus tercatat. Jika identitas tidak dapat dipastikan, sistem berhenti secara aman.

## 4.9 Kartu anggota digital

Kartu anggota harus dapat dicetak sendiri, bisa dicetak ulang, dan tidak memerlukan bahan kartu plastik. Desain yang dituju sederhana, hemat tinta, mudah dipotong/dipegang, dan hanya menampilkan informasi yang memang diperlukan: nama serta kategori beserta keterangannya (lihat 4.9.1), dan QR. Kelas dan nomor telepon tidak dicantumkan.

QR harus memuat token acak/referensi yang tidak mengungkap data pribadi secara langsung. Jika token dicabut atau kartu diganti, QR lama harus ditolak sesuai rancangan. Kartu yang dicetak ulang tidak boleh membuat dua identitas anggota baru atau menghilangkan riwayat anggota lama.

### 4.9.1 Data anggota yang disimpan (DEC-023)

Data dibuat sederhana agar tidak perlu diperbarui tiap tahun ajaran. Kelas tidak disimpan.

Data inti: **nama**, **status aktif/nonaktif**, dan **kategori** dari tabel referensi. Kategori dikelola sebagai tabel referensi, bukan kolom khusus per jenis anggota, sehingga menambah jurusan atau mata pelajaran tidak mengubah struktur data. Keterangan per jenis anggota (mengikuti arahan pengguna; daftar final mengikuti template impor):

| Jenis anggota | Keterangan pada kategori |
|---|---|
| Murid | jurusan |
| Guru jurusan | program keahlian |
| Guru umum | mata pelajaran yang diajar (misalnya Matematika) |
| Staf dan teknisi | jenis (staf atau teknisi) dan keterangan tugas/bagian bila perlu (perlu konfirmasi) |

Sistem tetap membuat ID anggota unik secara otomatis, karena nama saja tidak unik. Nomor telepon tidak disimpan.

## 4.10 Impor anggota massal

Impor Excel/CSV ditujukan untuk mendaftarkan atau memperbarui banyak anggota dengan lebih efisien, termasuk populasi di atas 1.000 orang. Sumber daftar adalah data anggota yang disediakan Tata Usaha sekolah, disusun mengikuti template dan panduan kolom yang disediakan layanan impor aplikasi. Petugas perpustakaan dapat mengimpor data dan menonaktifkan akun; mereka bukan operator transaksi peminjaman. Proses perlu:

- memeriksa header/kolom wajib dan format data;
- mendeteksi anggota duplikat dengan aturan yang disepakati (OPEN-011), karena nama saja tidak unik;
- hanya menyimpan data minimal (DEC-023); kolom lain seperti kelas atau nomor telepon diabaikan atau ditolak sesuai panduan;
- menampilkan pratinjau dan ringkasan sebelum perubahan;
- memisahkan baris berhasil, dilewati, dan gagal dengan alasan yang bisa dipahami;
- mencegah impor setengah jalan yang merusak integritas, atau memiliki strategi transaksi/rollback yang jelas;
- tidak menghapus riwayat transaksi anggota yang dinonaktifkan;
- data anggota yang tidak muncul dalam file impor tidak otomatis dihapus atau dinonaktifkan kecuali aturan itu disetujui secara eksplisit;
- mendukung status aktif/nonaktif atau padanan status yang disepakati;
- melindungi data anggota dalam file dan log;
- mencatat siapa yang melakukan impor dan kapan, jika sesuai dengan struktur audit.

Jangan mengasumsikan sistem dapat mengambil data langsung dari database resmi sekolah. Format kolom ditentukan oleh template aplikasi; yang masih perlu diputuskan hanya aturan mengenali anggota yang sama saat impor ulang (OPEN-011).

---

# 5. Buku, Eksemplar Fisik, dan Integritas Data

## 5.1 Judul buku berbeda dari eksemplar fisik

Konsep penting: **judul/katalog** menjelaskan karya atau edisi buku, sedangkan **eksemplar** menjelaskan satu benda fisik tertentu yang bisa dipinjam, dikembalikan, hilang, atau rusak.

Contoh: perpustakaan memiliki tiga salinan buku dengan judul yang sama. Sistem perlu membedakan salinan 1, salinan 2, dan salinan 3. Pemindaian QR pada salah satu salinan harus mengarah ke salinan itu saja.

Model konseptual yang disarankan:

- entitas judul/katalog buku;
- entitas eksemplar fisik dengan identifier unik;
- token/metadata QR per eksemplar;
- transaksi peminjaman induk;
- detail item peminjaman untuk tiap eksemplar;
- riwayat pengembalian dan kondisi;
- data anggota serta token QR anggota.

Nama tabel dan struktur aktual **belum boleh dipastikan** sebelum memeriksa repositori dan database. Tabel bernama `eksemplar_buku` pernah diusulkan, tetapi tidak boleh dianggap telah ada.

## 5.1.1 Pembuatan eksemplar otomatis dan penambahan buku (DEC-004, DEC-011, DEC-012, DEC-013)

Nomor registrasi lama sekolah tidak digunakan. Aplikasi membuat ID unik dan QR untuk setiap eksemplar.

- Petugas menambah buku dengan mengisi data katalog (judul dan data pendukung) serta **jumlah eksemplar**. Aplikasi membuat ID unik untuk tiap eksemplar secara otomatis. Petugas tidak mengetik nomor apa pun per eksemplar.
- Penambahan juga dapat dilakukan lewat impor Excel/CSV berisi judul dan jumlah. File lengkap berisi semua buku tidak diwajibkan.
- ID eksemplar dibuat oleh server, unik, stabil, tidak pernah dipakai ulang, dan tidak berubah walau data katalog berubah. ID harus pendek dan mudah dibaca/diketik.
- Tampilkan konfirmasi jumlah sebelum eksemplar dibuat, supaya salah ketik (misalnya 500 bukan 50) tidak langsung menjadi data.
- Pembuatan bersifat atomik: semua eksemplar berhasil dibuat atau tidak sama sekali. Klik ganda atau kirim ulang tidak boleh membuat eksemplar ganda.
- Setelah dibuat, aplikasi menyediakan lembar label QR untuk dicetak (per judul atau per batch), berisi QR dan ID yang terbaca manusia.
- Menambah jumlah untuk judul yang sudah ada membuat eksemplar baru dengan ID baru. Eksemplar lama tidak ditimpa atau digabung.
- Jika judul yang diimpor kemungkinan sudah ada di katalog, tampilkan peringatan di pratinjau. Jangan menggabungkan diam-diam (kunci pencocokan: OPEN-012).
- Mengurangi koleksi dilakukan per eksemplar (penonaktifan atau status hilang/rusak), bukan dengan menurunkan angka jumlah. Riwayat tetap ada.
- Label yang rusak atau hilang dapat dicetak ulang dengan ID dan QR yang sama.
- Buku lama yang sudah ada di rak harus diberi label baru dari aplikasi. Strategi operasionalnya perlu disepakati (OPEN-012).
- Impor menampilkan pratinjau dan ringkasan: judul baru, eksemplar dibuat, baris dilewati atau bermasalah. Baris dengan judul kosong atau jumlah tidak valid ditandai error. Hindari penghapusan massal otomatis.
- Perubahan data katalog tidak boleh menghapus atau menimpa riwayat transaksi.

## 5.2 Status eksemplar

Sistem perlu membedakan status operasional eksemplar, seperti tersedia, sedang dipinjam, sedang dalam penanganan, hilang, rusak, atau dinonaktifkan. **Daftar status final, transisi yang sah, dan nama status teknis harus diselaraskan dengan kode dan keputusan sekolah.** Jangan membuat status baru tanpa memperbarui dokumentasi, aturan transisi, dan tes.

Status harus diturunkan atau diperbarui melalui satu aturan domain yang konsisten. Hindari keadaan seperti:

- satu eksemplar dipinjam dua orang sekaligus;
- buku sudah ditandai kembali namun item pinjamnya masih aktif;
- buku hilang dianggap tersedia;
- eksemplar dinonaktifkan lalu riwayat pinjamannya dihapus;
- pencatatan pengembalian sebagian membuat semua eksemplar dianggap kembali.

## 5.3 Keunikan dan pencegahan pinjam ganda

Server harus memeriksa ketersediaan saat proses akhir diselesaikan, bukan hanya ketika QR pertama dipindai. Jika dua tablet/sesi berusaha meminjam eksemplar yang sama, hanya satu operasi yang boleh berhasil.

Validasi antarmuka tidak cukup. Aturan penting harus ditegakkan di sisi server dan dilindungi oleh transaksi/constraint database yang sesuai dengan teknologi aktual.

## 5.4 Riwayat tidak boleh hilang karena penonaktifan

Menonaktifkan anggota, menonaktifkan eksemplar, mengganti token, atau mengubah katalog tidak boleh menghapus jejak transaksi historis. Anggota yang tidak aktif cukup dinonaktifkan; tidak ada penghapusan otomatis berdasarkan masa tidak aktif (DEC-020, v4.1). Akun nonaktif tidak dapat memulai pinjaman baru, tetapi histori dan kewajiban tetap tersimpan. Penghapusan permanen bukan bagian dari versi pertama dan memerlukan kebijakan retensi serta prosedur terencana.

## 5.5 Waktu transaksi dan jejak audit

Waktu peminjaman dan pengembalian adalah data penting. Penyimpanan dan tampilan waktunya harus konsisten; jangan bergantung pada zona waktu komputer pengguna. Untuk tindakan administratif yang berdampak pada riwayat, simpan audit trail yang memadai jika rancangan dan lingkupnya memungkinkan: pelaku, aksi, waktu, objek, serta alasan/keterangan.

Jika perubahan data historis memang diperlukan untuk koreksi, gunakan proses yang dapat ditinjau dan tercatat, bukan menimpa data secara diam-diam.

---

# 6. QR, Layanan Mandiri, Keamanan, dan Privasi

## 6.1 Tujuan QR

QR bertujuan mempercepat identifikasi anggota dan eksemplar tanpa mengetik nomor secara berulang. QR bukan alat autentikasi yang sempurna dan tidak membuktikan kepemilikan fisik atau kehadiran fisik sebuah buku.

## 6.2 QR anggota

- QR sebaiknya memuat token acak yang cukup sulit ditebak, bukan data personal dalam teks terbuka.
- Token harus dapat dinonaktifkan/dicabut dan diterbitkan ulang.
- Pemindaian token harus divalidasi server.
- Token lama sesudah penggantian tidak boleh terus diterima tanpa batas.
- Tampilan kartu hanya memuat data minimum yang dibutuhkan.
- Pencetakan ulang tidak mengubah identifier internal anggota.
- Jangan menulis token lengkap di log publik, URL yang mudah terekspos, atau pesan kesalahan yang dapat dilihat orang lain.

## 6.3 QR eksemplar buku

QR harus mengidentifikasi eksemplar unik. Label fisik sebaiknya ditempatkan pada area yang masuk akal—misalnya di dalam sampul—agar lebih sulit dipisahkan dari buku secara tidak sengaja. Namun lokasi label hanyalah mitigasi; itu bukan jaminan anti-kecurangan.

QR yang disalin tetap mungkin. Karena itu, sistem harus memvalidasi status, ketersediaan, pinjaman aktif, dan keadaan terbaru sebelum menyelesaikan transaksi.

## 6.4 Alur peminjaman mandiri yang dituju

1. Tablet menunjukkan layar awal dan tidak menampilkan data sesi sebelumnya.
2. Anggota memulai sesi peminjaman.
3. Anggota memindai QR kartu.
4. Server memvalidasi token, status anggota, serta aturan peminjaman yang telah disetujui.
5. Anggota memindai QR tiap eksemplar fisik yang ingin dimasukkan.
6. Tiap scan divalidasi; item invalid, nonaktif, tidak tersedia, atau duplikat diberi penjelasan dan tidak ditambahkan secara keliru.
7. Pengguna melihat daftar final beserta due date/ringkasan yang dibutuhkan dan dapat membatalkan sebelum commit.
8. Saat pengguna menekan selesai, server memvalidasi ulang semua kondisi terkini.
9. Semua perubahan yang tergabung dalam transaksi disimpan secara atomik.
10. Jika sukses, tampilkan konfirmasi/struk ringkas. Jika gagal, jangan tampilkan seolah-olah pinjaman berhasil.
11. Sistem menghapus/menutup sesi dan membersihkan informasi pribadi dari layar.
12. Setelah timeout atau pembatalan, tablet kembali ke keadaan awal tanpa sisa identitas/daftar pinjaman sesi lama.

## 6.5 Alur pengembalian mandiri

Alur pengembalian berpusat pada QR eksemplar dan pinjaman aktif yang ditemukan di server. Proses tidak boleh mengharuskan orang yang sedang mengembalikan adalah peminjam asli. Sesi anggota (jalur B di 4.8) adalah jalur tambahan untuk mengembalikan banyak buku, memperpanjang, atau menyelesaikan buku hilang/rusak, dan tidak menggantikan jalur scan buku. Sistem harus mencegah pengembalian ganda, pengembalian buku yang tidak memiliki pinjaman aktif, dan perubahan status yang tidak sinkron.

Jika buku rusak atau hilang, alur normal perlu diarahkan ke pencatatan kondisi/penanganan yang sesuai, bukan sekadar menutup pinjaman dan langsung menganggap buku tersedia.

## 6.6 Sesi tablet bersama

Tablet digunakan bergantian, sehingga wajib mempertimbangkan:

- timeout otomatis setelah tidak aktif;
- tombol batal/keluar yang jelas;
- reset keadaan klien dan server-side session sesuai desain;
- tidak menyimpan informasi anggota pada browser lokal secara tidak perlu;
- tidak menampilkan data peminjam sebelumnya kepada pengguna berikutnya;
- mencegah tombol Back/refresh atau pengiriman ulang membuat transaksi ganda;
- akses kamera dan penanganan izin perangkat;
- pesan yang dapat dipahami jika kamera gagal;
- mekanisme pemulihan jika tablet atau jaringan terputus saat transaksi.

## 6.7 QR rusak atau tidak terbaca

Jalur manual harus memiliki prosedur eksplisit, bukan cara pintas yang melewati validasi. Minimal:

- minta ID eksemplar yang tercetak di label (dibuat pendek agar mudah diketik) atau informasi pengganti yang disetujui;
- cari satu eksemplar yang cocok dan perlihatkan identitas buku untuk konfirmasi;
- validasi pinjaman/keadaan eksemplar di server;
- catat bahwa metode input manual digunakan;
- terapkan konfirmasi/verifikasi tambahan sesuai kebijakan yang disepakati;
- jika hasilnya ambigu, berhenti dan serahkan kepada petugas, bukan memilih buku secara otomatis;
- jangan membiarkan input manual membuktikan bahwa fisik buku benar-benar ada.

## 6.8 Privasi dan keamanan

- Rahasiakan API key dan kredensial di environment variables/secret manager yang sesuai; jangan commit `.env`, token, password, atau kredensial.
- Terapkan autentikasi dan otorisasi sisi server pada setiap endpoint yang relevan.
- Validasi input di server dan gunakan pola query yang aman melalui lapisan database yang sesuai.
- Lindungi upload file: tipe, ukuran, nama file, lokasi penyimpanan, dan akses.
- Hindari menampilkan data pribadi pada halaman publik, log error, atau output AI. Satu pengecualian sudah diputuskan pengguna: halaman notifikasi keterlambatan (DEC-017) boleh menampilkan nama anggota, judul/ID eksemplar, jatuh tempo, dan lama terlambat. Tidak boleh ada data lain di halaman itu (misalnya kategori/jurusan, ID anggota, atau token QR), dan pembatasan aksesnya perlu diputuskan (OPEN-016).
- Batasi data yang dikirim ke layanan pihak ketiga hanya pada yang diperlukan dan disetujui.
- Gunakan HTTPS untuk deployment publik.
- Jangan mengekspor atau membagikan data nyata kepada AI/chatbot tanpa kewenangan dan sanitasi yang tepat.
- Tambahkan mitigasi untuk CSRF, session handling, rate limiting, injection, path traversal, dan risiko web lain yang relevan menurut framework dan konfigurasi aktual.
- Jangan mengklaim kontrol keamanan sudah ada sampai kode dan konfigurasi diperiksa.

---

# 7. Buku Hilang/Rusak, Kebijakan, dan Pemberitahuan

## 7.1 Buku hilang

Buku yang hilang harus diselesaikan melalui alur QR Penyelesaian Buku, bukan ditandai tersedia atau langsung dihapus dari histori.

1. Anggota masuk ke sesi pengembalian yang sah lalu memindai QR Penyelesaian Buku yang disediakan aplikasi/perpustakaan. QR ini adalah pintu masuk ke alur penyelesaian, bukan bukti pembayaran dan bukan QR yang ditempelkan pada buku.
2. Sistem menampilkan daftar buku yang masih tercatat dipinjam oleh anggota tersebut. Anggota memilih satu atau beberapa buku untuk diselesaikan.
3. Untuk setiap buku, anggota memilih kondisi **Hilang**, **Rusak**, atau **Lainnya**, lalu menambahkan keterangan bila diperlukan.
4. Untuk setiap buku yang dipilih, anggota memilih pengganti **kamus** atau **Al-Qur’an**. Satu sesi boleh menyelesaikan beberapa buku, dan pilihan pengganti dicatat terpisah untuk tiap buku.
5. Sistem menampilkan konfirmasi akhir yang menyebut judul buku asal, kondisi, deskripsi, dan jenis pengganti untuk tiap buku. Anggota harus mengonfirmasi sebelum catatan dibuat.
6. Sistem mencatat kasus sebagai **Menunggu penyelesaian/penerimaan pengganti**. Petugas tidak mengoperasikan transaksi rutin, tetapi penerimaan barang pengganti dapat dikonfirmasi oleh petugas yang berwenang.
7. Setelah pengganti diterima dan dikonfirmasi, sistem menutup kewajiban, menyimpan audit trail, dan memperbarui status eksemplar asal sebagai hilang/rusak sesuai kasus. Riwayat tidak dihapus.

Satu QR Penyelesaian Buku boleh digunakan berulang kali. Satu sesi dapat menyelesaikan beberapa buku, tetapi setiap buku memiliki catatan, kondisi, dan jenis pengganti sendiri. QR tersebut hanya membuka alur; otorisasi tetap berasal dari sesi anggota yang valid.

## 7.2 Buku rusak

Buku rusak mengikuti alur yang sama: anggota memilih eksemplar yang sesuai, memilih kondisi **Rusak**, dan menambahkan keterangan. Jika buku perlu diganti, anggota memilih kamus atau Al-Qur’an sesuai ketentuan penggantian yang tersedia. Sistem tidak boleh menganggap buku rusak tersedia untuk dipinjam kembali sebelum kondisi dan tindak lanjutnya diselesaikan.

## 7.3 Keterlambatan, pemblokiran, dan penyelesaian

Batas masa pinjam awal adalah 168 jam. Setiap eksemplar boleh diperpanjang satu kali selama 7 hari tambahan. Jika buku belum dikembalikan setelah jatuh tempo, sistem menandainya **Terlambat**. Jika keterlambatan melebihi 7 hari, status menjadi peringatan serius dan peminjaman baru diblokir sampai buku dikembalikan atau penyelesaian kehilangan/kerusakan dikonfirmasi.

**Terlambat tidak otomatis berarti hilang.** Sistem tidak boleh mengubah buku menjadi hilang hanya berdasarkan waktu. Anggota harus memilih tindakan yang benar di sesi pengembalian/penyelesaian.

Penggantian berupa kamus atau Al-Qur’an, bukan uang. Setiap buku yang diselesaikan memiliki rekaman kondisi, keterangan, pilihan pengganti, waktu konfirmasi, dan status penerimaan. Peminjaman baru dibuka kembali setelah tidak ada lagi buku belum dikembalikan atau kewajiban penggantian yang masih memblokir akun. Tidak ada sanksi lain untuk keterlambatan selain penandaan dan pemblokiran peminjaman baru; sanksi tambahan tidak boleh ditebak (OPEN-018).

## 7.4 Notifikasi keterlambatan di dalam aplikasi

Notifikasi keterlambatan dalam aplikasi adalah fitur wajib; WhatsApp tidak digunakan (DEC-017). Halaman notifikasi dapat dilihat siapa pun yang membuka halaman tersebut, tanpa login admin khusus, agar notifikasi berfungsi sebagai pengingat sosial.

- Daftar menampilkan pinjaman yang melewati jatuh tempo: nama anggota, judul/ID eksemplar, tanggal jatuh tempo, dan lama keterlambatan secukupnya untuk mengenali pinjaman.
- Daftar dihitung dari data transaksi aktual. Pinjaman yang sudah kembali atau sudah diperpanjang sesuai aturan tidak ditampilkan sebagai terlambat.
- Informasi yang ditampilkan dibatasi pada kebutuhan pengingat; jangan menampilkan data anggota lain yang tidak relevan.
- Notifikasi tetap benar setelah aplikasi tidur, restart, atau deploy ulang karena status dihitung dari timestamp dan transaksi aktual.
- Penanda sudah dilihat/ditindaklanjuti boleh ditambahkan sebagai catatan bantu, tetapi tidak mengubah status pinjaman.
- Tidak ada pengiriman pesan ke pihak luar dan tidak membutuhkan provider pesan.
- Halaman transaksi admin tetap dipisahkan dari mode kiosk layanan mandiri; halaman notifikasi yang dapat dilihat umum tidak memberikan akses ke fungsi admin.


---

# 8. AI Book Assistant / SraX AI

Riwayat proyek pernah menyebut assistant AI berbasis Gemini, dengan nama seperti **AI Book Assistant** atau **SraX AI**, serta variabel lingkungan `GEMINI_API_KEY` dan model `gemini-2.5-flash`. Ini semua perlu diverifikasi dari kode dan konfigurasi terbaru.

## 8.1 Peran yang masuk akal

AI dapat menjadi fitur pendukung, misalnya membantu pengguna menemukan buku berdasarkan minat, menjelaskan tema/isi umum suatu buku berdasarkan data yang tersedia, atau memandu penggunaan katalog. Fungsi tepat yang diinginkan harus diperiksa dari implementasi dan kebutuhan terbaru.

## 8.2 Batas AI

- AI bukan sumber kebenaran untuk status stok, pinjaman aktif, jatuh tempo, atau data anggota. Data transaksi harus diambil dari database melalui logika aplikasi yang tervalidasi.
- AI tidak boleh menyelesaikan atau mengubah transaksi pinjaman/pengembalian tanpa alur server yang eksplisit, validasi, dan otorisasi.
- AI tidak boleh mengarang bahwa sebuah buku tersedia. Jika data tidak ditemukan, nyatakan tidak diketahui.
- Jangan mengirim informasi pribadi anggota, token QR, kredensial, atau isi seluruh database ke API AI tanpa kebutuhan, izin, serta pengamanan yang jelas.
- Tangani timeout, limit, error API, jawaban tidak valid, dan model yang tidak tersedia dengan pesan yang baik.
- Jangan menyimpan API key di source code atau repository.
- Evaluasi biaya dan ketergantungan eksternal. Jika API tidak tersedia, fungsi inti perpustakaan harus tetap dapat bekerja sejauh desain memungkinkan.
- Verifikasi nama model dan endpoint dari dokumentasi terkini sebelum mengubah integrasi, karena informasi tersebut dapat berubah.

## 8.3 Kriteria minimum fitur AI

1. Input pengguna divalidasi dan dibatasi secara wajar.
2. Error API tidak menjatuhkan seluruh aplikasi.
3. Jawaban tidak dipakai sebagai fakta transaksi tanpa verifikasi database.
4. Data pribadi tidak terekspos dalam prompt, jawaban, atau log.
5. Pengguna memahami bahwa jawaban merupakan bantuan AI, bukan catatan resmi perpustakaan.
6. Tes atau pengujian manual mencakup kondisi sukses dan gagal.

---

# 9. Teknologi dan Arsitektur

## 9.1 Arsitektur target dan kondisi implementasi

Arsitektur target yang ditetapkan pengguna adalah:

- Python + Flask sebagai backend;
- Hugging Face Spaces sebagai hosting backend dengan Docker;
- Supabase PostgreSQL sebagai database target;
- HTML, CSS, JavaScript, dan Jinja atau solusi UI yang telah digunakan di repositori sebagai antarmuka;
- Google Gemini API untuk Asisten AI/pencarian pintar;
- Notifikasi keterlambatan dalam aplikasi yang dapat dilihat siapa pun yang membuka halaman notifikasi (tanpa WhatsApp);
- Excel/CSV untuk impor dan ekspor data;
- QR anggota dan QR eksemplar yang dibuat otomatis oleh aplikasi, dengan ID eksemplar tercetak pada label QR buku.

Ini adalah arsitektur target, bukan bukti bahwa seluruh layanan sudah dikonfigurasi. SQLite pernah digunakan untuk pengembangan lokal dan mungkin masih ada dalam repo. Agent harus memeriksa `requirements.txt`, `pyproject.toml`, file konfigurasi, struktur folder, migration scripts, dan keadaan Git sebelum mengubah implementasi. Render/Neon merupakan rencana lama yang telah digantikan dan bukan arsitektur target saat ini.

## 9.2 Arsitektur yang diinginkan secara prinsip

Arsitektur harus memisahkan tanggung jawab sejauh wajar:

- **UI/presentation:** menerima aksi pengguna, menampilkan data dan pesan, tidak menjadi satu-satunya penjaga aturan bisnis.
- **Route/controller:** menghubungkan HTTP request dan response dengan layanan aplikasi.
- **Service/domain logic:** menerapkan aturan peminjaman, pengembalian, QR, impor, kondisi buku, serta otorisasi proses.
- **Repository/data access:** mengelola query dan transaksi database.
- **Database:** menyimpan data transaksional secara konsisten.
- **External integrations:** AI API, penyimpanan media, atau layanan lain—dipisahkan agar kegagalan layanan luar tidak merusak inti transaksi.
- **Tests:** memeriksa aturan domain, data access, endpoint/alur, serta skenario kegagalan penting.

Jika repositori saat ini belum terstruktur seperti ini, jangan langsung menulis ulang semuanya. Audit dulu dan lakukan refactor bertahap jika memberi manfaat terukur.

## 9.3 Migrasi SQLite ke PostgreSQL

SQLite dapat tetap berguna untuk pengembangan lokal, tetapi database SQLite pada filesystem container hosting tidak boleh diasumsikan persisten untuk produksi. Target produksi adalah Supabase PostgreSQL. Migrasi perlu dilakukan hanya setelah audit skema, backup, pemetaan ID buku lama ke ID eksemplar baru, dan pengujian integritas. Ketentuan Supabase harus diverifikasi; jangan menganggap layanan gratis menjamin data tersimpan selamanya tanpa batas.

Sebelum migrasi:

- ambil dan verifikasi backup dari database sumber;
- identifikasi skema dan variasi data nyata;
- ukur/inspeksi data lama, termasuk struktur JSON atau ID fisik yang pernah dilaporkan;
- rancang pemetaan dan migrasi yang dapat diuji;
- jalankan migrasi di salinan/staging terlebih dahulu;
- cocokkan jumlah dan integritas data sebelum/sesudah;
- tes transaksi peminjaman/pengembalian dan constraint;
- lakukan uji restore dari backup;
- sediakan cara rollback yang realistis;
- jangan migrasikan produksi tanpa persetujuan pengguna.

Perbedaan tipe data, constraint, autoincrement, SQL, transaksi, indeks, waktu, dan perilaku konkurensi harus diperhitungkan. Jangan menganggap pemindahan file database sama dengan migrasi database.

## 9.4 Upload cover dan file

Jika cover buku diunggah, lokasi penyimpanannya harus cocok dengan pola deployment. Filesystem hosting mungkin tidak persisten. Sebelum memilih storage, pastikan apakah cover perlu tetap tersedia setelah restart/deploy, bagaimana backup dilakukan, bagaimana akses publik dibatasi, dan bagaimana file lama dipetakan saat migrasi. Jangan sekadar mengubah lokasi upload tanpa mempertahankan referensi dan file yang sudah ada.

## 9.5 Deployment bukan sekadar “aplikasi bisa dibuka”

Kelayakan produksi juga mencakup:

- database persisten;
- HTTPS;
- konfigurasi rahasia di environment variables;
- backup dan uji pemulihan;
- otorisasi serta sesi yang aman;
- penanganan kesalahan tanpa membocorkan rahasia;
- log yang berguna tanpa membocorkan data pribadi;
- migrasi database yang terkontrol;
- media persisten jika diperlukan;
- pemantauan error dan rencana pemulihan;
- biaya aktual dan batas platform;
- persetujuan sekolah sebelum data nyata dipakai.

Sebuah deploy berhasil tidak otomatis berarti siap digunakan sekolah.

---

# 10. Requirement Fungsional dan Kriteria Penerimaan

Bagian ini mendefinisikan apa yang perlu dibuktikan pada produk. Requirement ID dapat dipakai di issue tracker, commit, pull request, test, dan laporan agent.

**Status awal seluruh requirement di bawah:** `BELUM DIVERIFIKASI DALAM DOKUMEN INI`. Status harus diperbarui berdasarkan audit repositori dan bukti tes, bukan perkiraan.

## 10.1 Katalog dan eksemplar

### LIB-CAT-001 — Pencarian dan detail katalog

**Tujuan:** membantu pengguna menemukan buku dengan cepat.

Kriteria penerimaan:
- pengguna dapat melakukan pencarian dengan field yang memang didukung dan didokumentasikan;
- hasil dan detail tidak mengarang status ketersediaan;
- input pencarian kosong/tidak valid ditangani dengan benar;
- tidak ada akses tak sah ke data administratif dari tampilan publik;
- pencarian yang tidak menemukan hasil memberikan umpan balik yang jelas.

### LIB-COPY-001 — Identitas unik eksemplar

**Tujuan:** membedakan benda fisik dari judul buku.

Kriteria penerimaan:
- setiap eksemplar yang dapat dipinjam memiliki ID stabil yang unik, dibuat otomatis oleh aplikasi dan tidak pernah dipakai ulang;
- QR mengarah ke tepat satu eksemplar;
- peminjaman/pengembalian mengubah status eksemplar yang tepat;
- duplikasi identifier ditolak atau ditangani melalui proses koreksi;
- judul/metadata katalog tetap dapat dihubungkan dengan seluruh eksemplar terkait.

### LIB-COPY-002 — Perubahan status eksemplar

Kriteria penerimaan:
- hanya transisi yang sah yang diizinkan;
- buku yang sedang dipinjam atau hilang tidak ditampilkan sebagai tersedia;
- tindakan administratif yang berdampak penting tervalidasi dan terlacak;
- data historis tidak hilang saat sebuah eksemplar dinonaktifkan.

## 10.2 Peminjaman multi-buku

### LIB-LOAN-001 — Transaksi multi-item atomik

**Tujuan:** memungkinkan satu transaksi berisi lebih dari satu eksemplar tanpa inkonsistensi.

Kriteria penerimaan:
- satu transaksi dapat mengandung beberapa item jika anggota dan seluruh item memenuhi aturan;
- tiap item menyimpan kaitan yang benar ke eksemplar dan transaksi;
- item duplikat tidak dimasukkan tanpa sengaja;
- ketersediaan tiap eksemplar divalidasi ulang saat commit;
- jika satu kondisi wajib gagal, aturan commit/batal harus konsisten dan terdokumentasi;
- bila terjadi error database, tidak boleh ada transaksi setengah jadi;
- tidak boleh ada eksemplar dipinjam ganda saat dua permintaan bersamaan;
- due date dihitung dari waktu peminjaman yang berhasil sesuai batas 168 jam;
- tidak ada batas maksimum jumlah item yang ditetapkan oleh pengguna; jangan membuat batas buatan. Tetap pastikan setiap eksemplar fisik berbeda dan valid.

### LIB-LOAN-002 — Riwayat peminjaman per eksemplar

Kriteria penerimaan:
- tiap item dapat ditelusuri dari waktu pinjam sampai kembali/penanganan khusus;
- histori memisahkan item yang sudah kembali dan yang masih dipinjam;
- menonaktifkan anggota atau eksemplar tidak menghapus histori;
- timestamp dan zona waktu tampil konsisten.

## 10.3 Pengembalian

### LIB-RETURN-001 — Pengembalian sebagian dan penuh

Kriteria penerimaan:
- dari transaksi dengan beberapa eksemplar, satu item dapat dikembalikan tanpa menutup item lain;
- item yang sudah kembali tidak dapat dikembalikan ulang sebagai transaksi baru;
- eksemplar tanpa pinjaman aktif tidak boleh ditandai kembali seolah-olah memiliki pinjaman;
- satu item yang dikembalikan berubah status secara konsisten pada riwayat dan data eksemplar;
- error di tengah operasi tidak meninggalkan state yang tidak cocok;
- proses kembali oleh orang lain tetap diizinkan sesuai DEC-006.

### LIB-RETURN-002 — Durasi aktual dan keterlambatan

Kriteria penerimaan:
- durasi aktual dihitung dari timestamp pinjam dan kembali;
- due date memakai aturan 168 jam yang konsisten;
- pengembalian sebelum jatuh tempo tidak dianggap terlambat;
- pengembalian sesudah jatuh tempo dikategorikan sesuai definisi yang disetujui;
- batas waktu, pembulatan, dan zona waktu diuji pada tepi tanggal serta pergantian hari;
- nilai durasi yang ditampilkan konsisten dengan sumber timestamp.

### LIB-RETURN-003 — Kondisi buku saat kembali

Kriteria penerimaan:
- kondisi yang dipilih dicatat sesuai daftar yang disetujui;
- kategori rusak/hilang tidak membuat eksemplar otomatis tersedia;
- bila kebijakan belum jelas, sistem tidak menciptakan sanksi atau denda baru secara diam-diam;
- perubahan kondisi punya kaitan ke transaksi/item yang tepat.

### LIB-RETURN-004 — Perpanjangan satu kali per eksemplar

**Asal:** DEC-005, revisi v4.1. Status: PLANNED.

Kriteria penerimaan:
- setiap eksemplar memiliki masa pinjam awal maksimal 168 jam;
- perpanjangan hanya dapat dilakukan satu kali per eksemplar;
- perpanjangan sebelum jatuh tempo menetapkan jatuh tempo baru = jatuh tempo lama + 7 hari; aturan untuk buku yang sudah lewat jatuh tempo mengikuti OPEN-017 dan tidak boleh ditebak;
- anggota harus memilih dan mengonfirmasi perpanjangan; tidak ada perpanjangan otomatis;
- jika buku lain yang dipinjam dalam rentang 24 jam belum dipindai saat sesi pengembalian, sistem menawarkannya untuk ditinjau, tetapi keputusan tetap per buku;
- sistem menolak perpanjangan kedua dan menjelaskan bahwa buku harus dikembalikan;
- riwayat mencatat waktu perpanjangan dan jatuh tempo baru;
- QR/perintah perpanjangan tidak dapat digunakan ulang untuk memperpanjang eksemplar yang sama lebih dari sekali.

## 10.4 QR dan layanan mandiri

### LIB-QR-001 — Token QR anggota

Kriteria penerimaan:
- QR tidak memuat data pribadi sebagai teks langsung;
- token divalidasi di server;
- token yang dicabut/diganti tidak lagi diterima sesuai aturan;
- pemindaian token salah/tidak dikenal memberikan respons aman;
- isi token tidak bocor melalui log atau pesan publik.

### LIB-QR-002 — QR eksemplar

Kriteria penerimaan:
- QR mengidentifikasi satu eksemplar;
- QR yang tidak valid, eksemplar nonaktif, atau eksemplar dengan status tidak layak dipinjam ditolak dengan jelas;
- status divalidasi ulang saat transaksi diselesaikan;
- scan ulang tidak menambahkan item ganda.

### LIB-QR-003 — Jalur manual untuk QR yang rusak

Kriteria penerimaan:
- input nomor manual tetap harus menemukan eksemplar unik;
- jika lebih dari satu hasil/ambigu, proses dihentikan untuk ditangani petugas;
- validasi aturan transaksi tetap berjalan;
- penggunaan jalur manual ditandai pada catatan/log yang sesuai;
- sistem tidak mengklaim input manual membuktikan keberadaan fisik buku.

### LIB-QR-004 — Label QR buku dan kartu anggota cetak

**Asal:** DEC-008, DEC-011, DEC-023 (direvisi pada v4.0).

Kriteria penerimaan:
- aplikasi menghasilkan lembar label QR untuk eksemplar yang dipilih, per judul atau per batch;
- tiap label menampilkan QR dan ID eksemplar yang terbaca manusia, berdekatan;
- ID tercetak selalu cocok dengan eksemplar yang ditunjuk QR;
- label dapat dicetak ulang dengan ID dan QR yang sama;
- kartu anggota dapat dicetak sendiri, dicetak ulang, dan hemat tinta;
- kartu hanya memuat nama serta kategori beserta keterangannya (DEC-023) serta QR, tanpa kelas dan tanpa nomor telepon;
- pencetakan ulang tidak membuat identitas anggota baru dan tidak menghapus riwayat.

### LIB-OPS-001 — Transaksi rutin tidak bergantung pada operator petugas

Kriteria penerimaan:
- anggota yang memenuhi syarat dapat menyelesaikan peminjaman rutin dari awal sampai konfirmasi tanpa petugas melakukan tindakan pada sistem;
- pengembalian rutin dapat diselesaikan orang yang membawa buku tanpa harus menjadi peminjam asli dan tanpa petugas memproses transaksi;
- transaksi normal tidak membutuhkan persetujuan manual petugas;
- sesi pengguna sebelumnya selalu dibersihkan sebelum sesi baru;
- masalah umum seperti QR tidak terbaca, scan duplikat, anggota tidak aktif, atau buku tidak tersedia memiliki pesan dan jalur pemulihan mandiri yang aman bila keputusan dapat dibuat secara pasti;
- jika keputusan tidak dapat dibuat dengan aman, sistem menolak/menahan transaksi tanpa mengubah status secara keliru dan memberi instruksi tindak lanjut yang jelas;
- aplikasi tidak mengklaim beroperasi mandiri jika server/database/kamera/jaringan yang dibutuhkan sedang tidak tersedia;
- tes penerimaan mencakup simulasi operasional ketika tidak ada petugas yang mengoperasikan aplikasi.

### LIB-KIOSK-001 — Peminjaman mandiri melalui tablet

Kriteria penerimaan:
- alur dimulai dari sesi baru dan memvalidasi anggota;
- pengguna dapat menambahkan beberapa eksemplar;
- pengguna dapat meninjau/membatalkan sebelum commit;
- commit berhasil hanya bila validasi server lulus;
- transaksi gagal tidak ditampilkan sebagai berhasil;
- setelah berhasil, dibatalkan, atau timeout, sesi dibersihkan;
- identitas dan item sesi sebelumnya tidak muncul pada sesi berikutnya;
- pengiriman request ulang tidak membuat pinjaman ganda;
- kamera gagal atau tidak diizinkan menghasilkan petunjuk yang jelas.


## 10.5 Anggota dan impor massal

### LIB-MEMBER-001 — Siklus hidup anggota

Kriteria penerimaan:
- ID anggota unik dibuat otomatis oleh aplikasi (nama tidak dipakai sebagai identitas unik);
- data inti yang disimpan adalah nama, status aktif/nonaktif, dan kategori anggota dari tabel kategori sesuai DEC-023;
- anggota aktif/nonaktif dibedakan;
- petugas perpustakaan dapat menonaktifkan akun;
- status aktif/nonaktif dan penonaktifan anggota diatur oleh LIB-MEMBER-002;
- akun yang dinonaktifkan tidak dapat memulai pinjaman baru;
- histori pinjaman anggota tetap ada;
- token QR dapat dicabut/diganti tanpa menghapus identitas atau histori anggota.

### LIB-MEMBER-002 — Penonaktifan anggota tanpa penghapusan otomatis

**Asal:** DEC-020. Status: PLANNED; keputusan produk ditutup v4.1.

Kriteria penerimaan:
- petugas yang berwenang dapat mengubah status anggota menjadi aktif/nonaktif;
- anggota nonaktif tidak dapat memulai peminjaman baru;
- anggota nonaktif tetap muncul dalam histori transaksi dan laporan yang relevan;
- data anggota dan histori tidak dihapus otomatis setelah 3 tahun atau jangka waktu lain;
- anggota dapat diaktifkan kembali tanpa membuat identitas baru;
- impor ulang tidak membuat anggota ganda secara diam-diam; ikuti aturan OPEN-011;
- tidak ada proses pembersihan otomatis anggota dalam background atau saat aplikasi dibuka.

### LIB-IMPORT-001 — Impor Excel/CSV

Kriteria penerimaan:
- layanan impor menyediakan template dan panduan susunan kolom;
- hanya data minimal (DEC-023) yang disimpan; kolom lain seperti kelas atau nomor telepon diabaikan atau ditolak sesuai panduan;
- data dicek sebelum perubahan dilakukan;
- duplikasi ditandai dengan alasan;
- kesalahan per baris dilaporkan;
- hasil impor menunjukkan jumlah dibuat/diperbarui/dilewati/gagal;
- kegagalan tidak meninggalkan data setengah masuk tanpa strategi pemulihan;
- data pribadi tidak ditampilkan lebih luas daripada kebutuhan admin;
- perilaku untuk data yang belum dikenal atau kolom ekstra jelas.

### LIB-IMPORT-002 — Penambahan buku dari judul dan jumlah (ID dan QR otomatis)

**Asal:** DEC-004, DEC-011, DEC-012, DEC-013 (direvisi pada v4.0).

Kriteria penerimaan:
- petugas dapat menambah buku dengan mengisi judul dan jumlah eksemplar, tanpa mengetik nomor apa pun per eksemplar;
- aplikasi membuat ID unik dan QR untuk setiap eksemplar sebanyak jumlah yang dimasukkan;
- jumlah ditampilkan untuk konfirmasi sebelum eksemplar dibuat;
- pembuatan atomik: semua eksemplar berhasil dibuat atau tidak sama sekali, dan klik ganda atau kirim ulang tidak membuat eksemplar ganda;
- impor Excel/CSV berisi judul dan jumlah menghasilkan hasil yang sama, dan tidak mewajibkan daftar lengkap buku;
- judul yang mungkin sudah ada ditandai di pratinjau dan tidak digabung diam-diam;
- menambah jumlah untuk judul yang sudah ada membuat eksemplar baru dan tidak mengubah eksemplar lama;
- baris dengan judul kosong atau jumlah tidak valid ditandai error;
- perubahan data katalog tidak menghapus atau menimpa riwayat;
- ringkasan menampilkan judul baru, eksemplar dibuat, dan baris dilewati atau bermasalah;
- ID baru langsung dapat dicetak sebagai label (LIB-QR-004).

## 10.6 Administrasi, laporan, dan backup

### LIB-ADMIN-001 — Hak akses server-side

Kriteria penerimaan:
- route administratif dilindungi autentikasi dan otorisasi;
- menyembunyikan tombol di UI saja tidak dianggap kontrol akses;
- pengguna tanpa izin menerima respons aman;
- perubahan kebijakan/hak akses tidak di-hardcode secara tersebar tanpa struktur yang bisa diaudit.

### LIB-REPORT-001 — Riwayat dan ekspor

Kriteria penerimaan:
- laporan yang diekspor cocok dengan sumber database;
- ekspor tidak memasukkan rahasia atau field pribadi yang tidak dibutuhkan;
- filter/periode laporan dijelaskan dan diuji;
- format file yang keluar bisa dibaca dengan aplikasi umum.

### LIB-BACKUP-001 — Backup dan restore

Kriteria penerimaan:
- backup menyertakan komponen data penting yang telah ditentukan;
- file backup dapat dikenali, diberi waktu, dan disimpan dengan akses terbatas;
- prosedur restore terdokumentasi;
- restore benar-benar diuji di lingkungan terpisah;
- setelah restore, data contoh termasuk relasi transaksi tetap konsisten;
- backup tidak sekadar berarti aplikasi memiliki tombol ekspor CSV.

## 10.7 Kondisi khusus dan integrasi

### LIB-LOSS-001 — Pelaporan dan penggantian buku hilang

Kriteria penerimaan final harus mengikuti kebijakan sekolah yang disetujui. Minimal sistem tidak menyamakan “hilang” dengan “tersedia”, mempertahankan histori, serta dapat mencatat tindak lanjut penggantian Al-Qur’an/kamus secara terhubung dan dapat diaudit. Jenis pengganti, pihak penyetuju, dan kondisi penyelesaian harus dikonfirmasi terlebih dahulu.

### LIB-AI-001 — Assistant AI aman

Kriteria penerimaan:
- API key tidak berada di source code;
- kegagalan API tidak merusak operasi inti perpustakaan;
- informasi stok/riwayat diambil dari sumber aplikasi yang tervalidasi, bukan dikarang oleh model;
- data pribadi diminimalkan;
- error dan rate limit ditangani;
- jawaban AI ditandai sebagai bantuan, bukan catatan resmi.

### LIB-NOTIF-001 — Notifikasi keterlambatan di dalam aplikasi (fitur wajib)

**Asal:** DEC-005, DEC-017 (revisi v4.1).

Kriteria penerimaan:
- halaman notifikasi dapat dibuka tanpa login admin khusus;
- menampilkan pinjaman yang melewati jatuh tempo berdasarkan data aktual;
- menampilkan informasi minimum: nama anggota, judul/ID eksemplar, tanggal jatuh tempo, dan lama terlambat;
- pinjaman yang sudah kembali atau diperpanjang sesuai aturan tidak ditampilkan sebagai terlambat;
- notifikasi tetap benar setelah aplikasi tidur/restart;
- halaman notifikasi tidak memberikan akses ke fungsi administrasi atau data pribadi lain;
- batas 168 jam, perpanjangan, zona waktu, dan keterlambatan serius diuji;
- tidak ada pengiriman pesan ke pihak luar.

### LIB-FINE-001 — Penyelesaian buku hilang/rusak dengan pengganti

**Asal:** DEC-024. Status: PLANNED (belum berarti sudah diimplementasikan).

Kriteria penerimaan:
- tidak ada denda uang atau pembayaran online;
- satu QR Penyelesaian Buku membuka alur hanya di dalam sesi anggota yang valid;
- anggota dapat memilih satu atau beberapa buku yang masih tercatat dipinjam;
- untuk setiap buku, kondisi, deskripsi, dan pengganti (kamus atau Al-Qur’an) dicatat secara terpisah;
- sistem menampilkan konfirmasi akhir yang jelas sebelum menyimpan;
- satu sesi dapat menyelesaikan beberapa buku; setiap buku tetap mempunyai rekaman sendiri;
- keterlambatan tidak otomatis menetapkan buku hilang;
- buku belum dikembalikan/terlambat serius memblokir peminjaman baru sampai dikembalikan atau penyelesaian selesai;
- status penyelesaian baru final setelah penerimaan pengganti dikonfirmasi oleh pihak yang berwenang;
- riwayat kehilangan, kerusakan, dan penggantian tidak dihapus.

### LIB-UX-001 — Bahasa Indonesia sangat sederhana

**Asal:** DEC-022. Requirement ini dibuat pada v3.1 karena keputusan tersebut belum memiliki kriteria penerimaan.

Kriteria penerimaan:
- teks antarmuka tablet dan ponsel memakai kalimat pendek dan kata sehari-hari;
- setiap layar memberi satu instruksi utama per langkah;
- pesan error menjelaskan apa yang terjadi dan apa yang harus dilakukan berikutnya;
- istilah teknis tidak muncul tanpa penjelasan;
- panduan petugas dan panduan siswa dipisahkan;
- uji coba dilakukan kepada setidaknya beberapa calon pengguna awam, dan hasilnya dicatat.

---

# 11. Strategi Pengujian dan Standar Verifikasi

## 11.1 Kategori tes

1. **Unit tests:** aturan durasi, due date, status, validasi QR, transisi status, dan perhitungan lain yang terisolasi.
2. **Repository/database tests:** query, relasi, constraint, rollback, keunikan, serta migrasi.
3. **Integration tests:** interaksi route, service, repository, autentikasi, dan database.
4. **End-to-end/manual tests:** alur dari tablet/kamera, peminjaman multi-buku, pengembalian sebagian, serta reset sesi.
5. **Migration tests:** data lama → skema baru, dry-run jika tersedia, validasi jumlah/relasi, serta rollback/restore.
6. **Deployment tests:** konfigurasi environment, HTTPS, storage, koneksi DB, backup, restore, dan restart.
7. **Security/privacy review:** otorisasi, session, upload, secrets, output error, data pribadi, QR, dan integrasi eksternal.

## 11.2 Kasus tepi wajib dipertimbangkan

- anggota tidak aktif mencoba meminjam;
- QR anggota invalid, token telah dicabut, atau QR lama dipindai;
- QR eksemplar tidak valid, rusak, dinonaktifkan, hilang, atau telah dipinjam;
- dua sesi memindai/mencoba meminjam eksemplar yang sama secara hampir bersamaan;
- QR buku yang sama dipindai beberapa kali dalam satu sesi;
- transaksi multi-item gagal di tahap commit;
- pengembalian sebagian lalu pengembalian item lainnya;
- pengembalian ganda;
- pengembalian oleh orang selain peminjam;
- tanggal batas pinjam, tepat 168 jam, sedikit sebelum/sesudah due date, pergantian hari, dan zona waktu server berbeda;
- kamera ditolak, jaringan terputus, refresh, tombol back, double click, timeout;
- impor CSV dengan duplikasi, format salah, baris kosong, nama berisi karakter khusus, identifier hilang, dan file sangat besar;
- pencabutan token dan pencetakan ulang kartu;
- perubahan status anggota menjadi nonaktif saat masih memiliki riwayat/pinjaman aktif;
- file backup dipulihkan ke database kosong dan diuji konsistensinya;
- kegagalan API Gemini jika integrasi ada;
- pembuatan banyak eksemplar sekaligus, klik ganda, dan kegagalan di tengah pembuatan;
- anggota bernama sama saat impor;
- penonaktifan anggota dengan riwayat lama, pinjaman aktif, atau kewajiban penggantian;
- tablet yang login admin dipakai anggota: halaman admin tidak boleh terbuka dari mode layanan mandiri.

## 11.3 Definisi status fitur

Gunakan label berikut secara ketat:

- **PLANNED:** kebutuhan atau ide disepakati untuk dipertimbangkan/dibangun; belum dibuktikan sebagai implementasi.
- **IN PROGRESS:** pengerjaan sedang dilakukan; belum memenuhi seluruh kriteria penerimaan.
- **IMPLEMENTED:** kode fitur telah ditemukan, tetapi belum seluruh kriteria penerimaan diverifikasi.
- **VERIFIED:** kriteria penerimaan yang relevan telah diuji dan ada bukti hasilnya.
- **BLOCKED:** belum dapat dilanjutkan karena ada dependensi/keputusan/akses yang belum tersedia.
- **DEPRECATED:** sengaja dihentikan melalui keputusan yang jelas; tetap simpan sejarah dan alasan.

Pisahkan juga status produksi:

- **LOCAL-VERIFIED:** lolos pemeriksaan di lingkungan lokal yang dijelaskan.
- **STAGING-VERIFIED:** lolos di staging yang representatif.
- **PRODUCTION-READY:** telah melalui review operasional, keamanan, backup/restore, persetujuan yang diperlukan, serta pemeriksaan deployment.

Jangan menyebut fitur production-ready hanya karena tes lokal lulus.

## 11.4 Bukti yang harus dilaporkan AI

Setelah mengerjakan tugas, laporkan:

- branch dan commit yang sedang digunakan jika informasi Git tersedia;
- file yang berubah dan mengapa;
- perilaku yang berubah;
- requirement ID yang dipenuhi;
- perintah tes yang dijalankan dan hasil nyata;
- tes yang belum dijalankan dan sebabnya;
- migrasi/database yang disentuh atau tidak disentuh;
- risiko, batasan, dan pertanyaan terbuka;
- cara manual untuk memverifikasi fitur;
- konfirmasi eksplisit jika deploy produksi atau migrasi produksi **tidak** dilakukan.

Jangan mengklaim tes lulus bila tidak dijalankan. Jangan menampilkan hasil palsu hanya karena kode terlihat benar.

---

# 12. Roadmap dan Prioritas Pengembangan

Roadmap ini adalah urutan kerja yang masuk akal berdasarkan konteks yang ada. Urutan aktual perlu disesuaikan setelah audit repositori dan diskusi prioritas terbaru. Roadmap tidak berarti fitur sudah dibuat.

## P0 — Audit dan fondasi yang dapat dipercaya

Tujuan: mengetahui keadaan sebenarnya sebelum menambah fitur.

Keluaran:
- audit struktur repo, branch, perubahan yang belum di-commit, dependensi, dan entrypoint;
- audit skema database dan migrasi yang tersedia;
- audit test suite dan hasil tes aktual;
- daftar fitur yang benar-benar ada vs belum ada;
- inventaris risiko data dan deployment;
- catatan gap antara kode dan dokumen;
- penetapan status tiap requirement.

Batas: jangan merombak aplikasi saat audit; jangan menjalankan migrasi produksi.

## P1 — Transaksi multi-buku dan pengembalian sebagian

Tujuan: memastikan beberapa eksemplar bisa dipinjam dalam satu transaksi serta kembali secara independen.

Fokus:
- struktur induk-detail atau desain setara;
- relasi eksemplar yang benar;
- timestamp dan jatuh tempo per item;
- validasi pinjam ganda;
- transaksi atomik/rollback;
- migrasi data lama dengan dry-run, backup, validasi, dan rencana rollback;
- tes pinjam beberapa buku, return sebagian/penuh, duplikasi, kondisi gagal, dan konkurensi.

Penting: riwayat menyebut pekerjaan P1 dan tes terkait pernah dilaporkan, tetapi status aktual harus diverifikasi. Jangan menganggap tugas ini harus dibuat ulang atau dijalankan ulang sebelum mengaudit kondisi saat ini.

## P2 — Layanan mandiri berbasis QR

Tujuan: menjadikan tablet bersama sebagai kanal transaksi rutin yang benar-benar mandiri, tanpa petugas perpustakaan menjadi operator utama. Jalur pengecualian harus aman dan tidak boleh merusak data, tetapi tidak boleh menambah persetujuan petugas pada transaksi normal.

Fokus:
- QR anggota ber-token acak;
- ID dan QR unik per eksemplar yang dibuat otomatis dari judul dan jumlah;
- pencetakan kartu anggota dan label QR buku;
- pemindaian via kamera;
- review transaksi sebelum commit;
- validasi ulang dan commit atomik;
- pengembalian oleh orang lain;
- pengembalian sebagian;
- fallback QR rusak yang dapat diaudit;
- timeout dan reset sesi;
- tes kamera/perangkat serta tes kondisi gagal.

## P3 — Kondisi buku, penyelesaian hilang/rusak dengan pengganti, dan tindak lanjutnya

Tujuan: menjaga status stok tetap benar ketika buku tidak kembali dalam keadaan normal.

Fokus:
- status/kategori sesuai kebijakan;
- alur tindak lanjut kehilangan;
- penggantian dengan Al-Qur’an atau kamus berdasarkan kebijakan yang telah disampaikan;
- alur penyelesaian buku hilang/rusak dan penggantian kamus/Al-Qur’an sesuai DEC-024;
- persetujuan petugas yang berwenang;
- histori dan audit trail;
- tidak menandai item tersedia sebelum syaratnya benar-benar terpenuhi.

Dependensi: implementasi alur penyelesaian, penerimaan barang pengganti, dan uji status buku rusak/hilang.

## P4 — Notifikasi keterlambatan di dalam aplikasi (fitur inti wajib)

Tujuan: admin mengetahui pinjaman yang melewati batas maksimal 7 hari tanpa memeriksa riwayat satu per satu dan tanpa mengirim pesan manual di luar aplikasi.

Fokus:
- tombol/halaman notifikasi khusus admin;
- daftar pinjaman terlambat dihitung dari data aktual;
- akses lewat login admin di HP sendiri dan tablet perpustakaan;
- pemisahan mode layanan mandiri dan mode admin di tablet;
- pengujian tepi 168 jam dan zona waktu.

Tidak membutuhkan provider pesan maupun penjadwal. Halaman notifikasi dapat dilihat siapa pun, tetapi tidak membuka fungsi administrasi.

## P5 — Hosting Hugging Face Spaces, Supabase PostgreSQL, backup, dan keamanan produksi

Tujuan: aplikasi dapat diakses secara online dan data tidak hilang ketika service restart/deploy.

Fokus:
- deploy backend Flask melalui Docker di Hugging Face Spaces;
- gunakan Supabase PostgreSQL sebagai database target;
- evaluasi Supabase Storage atau penyimpanan persisten lain untuk cover/aset;
- migrasi dari database pengembangan ke Supabase hanya setelah audit, backup, dan tes;
- storage cover/file yang persisten;
- secrets/env vars;
- HTTPS;
- backup dan restore yang terbukti;
- pekerjaan berkala pembersihan anggota tidak aktif (LIB-MEMBER-002) lewat cara yang tetap berjalan saat aplikasi tidur;
- observabilitas dan penanganan kegagalan;
- pengujian beban dan batas penggunaan yang realistis;
- catatan tertulis persetujuan sekolah (menurut pemilik proyek sudah disetujui) sebelum data nyata digunakan.

**Larangan:** jangan deploy produksi atau migrasi data produksi tanpa persetujuan eksplisit.

## P6 — Dokumentasi dan pelatihan pengguna

Tujuan: siswa dan pengelola dapat menjalankan sistem tanpa bergantung pada pembuat aplikasi. Panduan harus ditulis dalam Bahasa Indonesia yang sangat sederhana, seolah menjelaskan kepada anak kecil atau orang yang sama sekali tidak paham teknologi. Gunakan kalimat pendek, kata sehari-hari, contoh nyata, satu langkah per poin, dan gambar/screenshot bila membantu. Hindari istilah teknis tanpa penjelasan.

Materi yang perlu disiapkan:
- mencari buku;
- membaca detail dan status buku;
- membuat/mencetak kartu anggota;
- menambah buku (judul dan jumlah) dan mencetak label QR;
- impor anggota dari Excel/CSV;
- memulai peminjaman mandiri;
- meminjam beberapa buku;
- pengembalian sebagian dan penuh;
- mengatasi QR rusak;
- membaca notifikasi keterlambatan;
- mencatat dan menyelesaikan buku rusak/hilang dengan pengganti sesuai alur;
- backup, restore, ekspor laporan;
- pemecahan masalah kamera/jaringan/login.

Gunakan bahasa sederhana, gambar/screenshot aktual dari versi aplikasi yang digunakan, dan pisahkan panduan petugas dari panduan siswa.

---

# 13. Kebutuhan Operasional, Biaya, dan Kesiapan Penggunaan Nyata

## 13.1 Prioritas biaya

Target proyek adalah biaya operasional serendah mungkin, idealnya Rp0 jika layak. Pengguna telah memilih Hugging Face Spaces + Docker dan Supabase PostgreSQL sebagai arsitektur target, tetapi paket gratis dapat berubah dan tidak berarti layanan gratis selamanya atau data dijamin tersimpan tanpa batas. Evaluasi harus transparan dan memeriksa ketentuan terkini sebelum rilis. Periksa harga dan ketentuan terkini tentang:

- hosting aplikasi;
- database dan penyimpanan;
- file cover/upload;
- backup;
- domain/HTTPS bila ada biaya tambahan;
- Gemini/API AI;
- egress/kuota trafik/limit request;
- layanan monitoring atau email.

Jika layanan gratis memiliki sleep/cold start, kuota rendah, retensi singkat, atau risiko dihentikan, dokumentasikan dampak ke pengalaman perpustakaan. Gratis secara uang bukan berarti tanpa biaya operasional atau risiko.

## 13.2 Backup bukan hanya ekspor

Tentukan data yang dibackup, frekuensi, lokasi terpisah, akses, retensi, serta cara memulihkan. Backup harus diuji dengan restore berkala. Database dan file cover mungkin harus dicadangkan secara terpisah. Backup yang belum pernah diuji bukan bukti sistem dapat dipulihkan.

Jangan mengunggah backup yang mengandung nama siswa, kontak, token, atau histori nyata ke chatbot publik hanya untuk meminta bantuan teknis. Buat salinan tersanitasi bila dibutuhkan.

## 13.3 Persiapan sebelum data nyata

Sebelum sekolah memasukkan data nyata, setidaknya pastikan:

- struktur data dan akun sudah ditinjau;
- data percobaan telah dipisahkan dari data nyata;
- akses admin dan password awal aman;
- HTTPS aktif pada deployment publik;
- tidak ada secret di repo;
- backup berjalan dan restore terbukti;
- mekanisme ekspor tersedia;
- kebijakan akses data dan siapa penanggung jawab diketahui;
- alur manual untuk kegagalan sistem jelas;
- batas free tier dan biaya diketahui;
- tes inti dan pemeriksaan keamanan relevan lulus;
- persetujuan sekolah atas penggunaan data/sistem dicatat (menurut pemilik proyek sudah disetujui; simpan catatan tertulis).

## 13.4 Portabilitas

Jangan merancang sistem yang hanya dapat hidup di satu penyedia. Dokumentasikan variabel lingkungan, versi dependensi, prosedur instalasi, skema database, migration scripts, storage, dan prosedur ekspor. Gunakan lapisan akses data yang mengurangi ketergantungan yang tidak perlu, tetapi jangan menambah abstraksi rumit tanpa manfaat yang jelas.

---

# 14. Protokol Kerja untuk Semua AI Chatbot dan Coding Agent

Bagian ini adalah instruksi kerja yang dapat dipakai bersama dokumen ini ketika berpindah AI.

## 14.1 Sebelum mulai bekerja

AI harus:

1. Mengulang pemahaman tugas dalam beberapa kalimat: tujuan, lingkup, dan apa yang tidak akan disentuh.
2. Memeriksa keadaan repo yang relevan: struktur, branch, perubahan belum di-commit, dependensi, skema DB, tests, dan dokumentasi.
3. Tidak menimpa perubahan pengguna yang sudah ada.
4. Menentukan requirement ID yang ditargetkan.
5. Menyusun rencana perubahan sesingkat yang masih jelas.
6. Menyatakan informasi yang belum diketahui dan apakah hal itu menghambat pekerjaan.
7. Menghindari penulisan ulang seluruh aplikasi jika perubahan lokal cukup.

Jika repo tidak tersedia, AI boleh merencanakan atau menulis spesifikasi, tetapi tidak boleh mengaku telah mengaudit atau mengubah kode.

## 14.2 Saat menulis kode

- Kerjakan tugas sempit yang diminta.
- Ikuti pola/arsitektur yang benar-benar digunakan repo jika tidak berbahaya; jangan mengimpor pola baru secara berlebihan.
- Jangan memindahkan aturan bisnis penting hanya ke JavaScript/browser.
- Jangan menyentuh data produksi untuk sekadar menguji fitur.
- Jangan menghapus field, kolom, data lama, test, atau file hanya karena tampak tidak terpakai tanpa memeriksa dependensi.
- Saat mengubah schema, pikirkan migrasi data lama, rollback, dan kompatibilitas.
- Saat menangani tanggal/waktu, tetapkan zona waktu dan periksa batas waktu.
- Saat menangani multi-step transaction, pastikan atomisitas dan konsistensi.
- Saat menambah dependensi, jelaskan alasan dan biaya/risiko pemeliharaannya.
- Jangan pernah meletakkan API key, password, token atau data asli ke source code/commit.

## 14.3 Setelah menulis kode

1. Jalankan formatter/linter/type checks yang memang tersedia jika relevan.
2. Jalankan tes target dan tes regresi yang masuk akal.
3. Periksa diff, file yang tidak sengaja berubah, dan data/config rahasia.
4. Jelaskan apa yang benar-benar dilakukan, tidak dilakukan, dan masih berisiko.
5. Berikan cara verifikasi manual yang sesuai.
6. Catat keputusan baru jika pengguna telah mengonfirmasinya.
7. Jangan deploy, migrasikan produksi, atau mengirim pesan sungguhan tanpa persetujuan khusus.

## 14.4 Template handoff untuk berpindah AI

Salin dan isi bagian ini setiap kali pekerjaan dialihkan ke AI lain.

```text
HANDOFF PROYEK — SISTEM PERPUSTAKAAN DIGITAL SEKOLAH
Tanggal:
AI/agent sebelumnya:
Repositori/lokasi kerja:
Branch:
Commit terakhir (jika diketahui):

1. TUJUAN TUGAS SAAT INI
- Requirement ID:
- Masalah yang ingin diselesaikan:
- Kriteria penerimaan:

2. KONDISI AKTUAL YANG SUDAH DIPERIKSA
- File yang diperiksa:
- Struktur/schema relevan:
- Perubahan belum di-commit:
- Fitur yang telah dibuktikan ada:
- Fitur yang belum diverifikasi:

3. PEKERJAAN YANG SUDAH DILAKUKAN
- File diubah:
- Perubahan utama:
- Alasan desain:
- Migrasi/schema berubah? Jelaskan:

4. VERIFIKASI
- Perintah tes yang dijalankan:
- Hasil tes nyata:
- Tes yang tidak dijalankan dan alasannya:
- Cara verifikasi manual:

5. RISIKO / MASALAH TERSISA
- Bug atau kasus tepi:
- Keputusan produk yang belum ada:
- Dampak ke data lama:
- Risiko keamanan/privasi/deployment:

6. BATASAN WAJIB
- Jangan lakukan deploy produksi tanpa izin.
- Jangan menjalankan migrasi produksi tanpa izin.
- Jangan mengubah kebijakan peminjaman/denda/penggantian tanpa izin.
- Jangan menganggap laporan AI lama sebagai bukti kode saat ini.

7. LANGKAH BERIKUTNYA YANG DISARANKAN
- Tugas kecil berikutnya:
- File/area yang boleh disentuh:
- Tes yang wajib dijalankan:
```

## 14.5 Prompt awal untuk AI baru

Gunakan prompt berikut ketika memberikan dokumen ini kepada chatbot/AI coding agent lain. Sesuaikan akses repo sesuai kemampuan tool yang dipakai.

```text
Baca seluruh dokumen “DOKUMENTASI INDUK PROYEK — SISTEM PERPUSTAKAAN DIGITAL SEKOLAH” sebelum menjawab atau mengubah apa pun.

Anggap dokumen tersebut sebagai konteks produk dan batas keputusan, bukan bukti bahwa fitur sudah diimplementasikan. Bedakan keputusan terkonfirmasi, rencana, laporan historis, kondisi kode aktual, dan pertanyaan terbuka. Jangan mengubah keputusan produk secara diam-diam.

Jika tugas menyangkut kode, mulai dengan mengaudit repositori, branch, perubahan belum di-commit, struktur aplikasi, schema/database, dan tests. Jangan mengarang file/tabel/hasil tes. Pertahankan perubahan pengguna. Buat perubahan sekecil yang menyelesaikan kebutuhan. Tambahkan/perbarui tes dan jalankan tes yang relevan. Laporkan file yang diubah, bukti pengujian, keterbatasan, dan risiko.

Jangan menjalankan migrasi/deploy produksi, menghapus data, mengirim pesan nyata, atau mengubah kebijakan resmi tanpa izin eksplisit. Jangan menganggap QR 100% anti-kecurangan. Ingat bahwa pengunjung umum hanya boleh membaca di tempat; masa pinjam maksimal adalah 7 hari/168 jam dan notifikasi keterlambatan di dalam aplikasi yang dapat dilihat siapa pun yang membuka halaman notifikasi wajib (WhatsApp tidak digunakan); pengembalian dapat dilakukan oleh orang selain peminjam; transaksi dapat memuat jumlah buku tanpa batas yang ditetapkan pengguna dan judul yang sama boleh muncul lebih dari sekali selama eksemplarnya berbeda; ID eksemplar dan QR dibuat otomatis oleh aplikasi (nomor registrasi sekolah tidak dipakai) dan label QR buku harus menampilkan ID tersebut; data anggota minimal (nama, status, jurusan/program keahlian/mata pelajaran, tanpa kelas) diimpor dari file sesuai template aplikasi; penyelesaian buku hilang/rusak melalui alur QR dengan pengganti kamus/Al-Qur’an per buku (bukan uang); anggota tidak aktif cukup dinonaktifkan; tidak ada penghapusan otomatis dan riwayat tetap tersimpan; backend target adalah Hugging Face Spaces + Docker; database target adalah Supabase PostgreSQL; Gemini API dan notifikasi dalam aplikasi adalah fitur wajib; biaya Rp0 adalah target bukan jaminan gratis selamanya; dan self-service adalah prinsip mutlak.

Sebelum mulai, ringkas pemahaman tugas, requirement ID yang relevan, hasil audit yang telah dilakukan, risiko, serta hal yang masih belum diketahui. Jika repo tidak tersedia, jelaskan batasan tersebut dan jangan mengaku telah mengauditnya.
```

## 14.6 Format laporan tugas AI

```text
LAPORAN PEKERJAAN

Tujuan:
Requirement ID:
Status awal:
Status akhir: PLANNED / IN PROGRESS / IMPLEMENTED / VERIFIED / BLOCKED

Temuan audit:
- ...

Perubahan:
- file — perubahan — alasan

Verifikasi:
- perintah tes:
- hasil:
- tes belum dijalankan:

Dampak data/migrasi:
- ...

Risiko dan batasan:
- ...

Yang sengaja tidak dilakukan:
- deploy produksi / migrasi produksi / perubahan kebijakan / lainnya

Langkah berikutnya:
- ...
```

---

# 15. Daftar Keputusan yang Wajib Dilindungi dari Perubahan Tidak Sengaja

- Pengunjung umum hanya membaca di tempat; tidak boleh meminjam (DEC-001).
- Satu tablet bersama dengan kamera menjadi titik layanan mandiri (DEC-002).
- Pencarian buku dapat dilakukan dari HP; transaksi mandiri dilakukan di tablet (DEC-003).
- ID unik eksemplar dibuat otomatis oleh aplikasi; nomor registrasi sekolah tidak digunakan (DEC-004).
- Masa pinjam awal maksimal 7 hari/168 jam; setiap eksemplar boleh diperpanjang satu kali selama 7 hari tambahan setelah tindakan/konfirmasi anggota (DEC-005).
- Pengembalian dapat dilakukan oleh orang selain peminjam (DEC-006).
- Transaksi multi-buku dan pengembalian sebagian wajib didukung; pengguna tidak menetapkan batas jumlah buku, dan judul sama boleh dipinjam jika ID eksemplarnya berbeda (DEC-007, DEC-019).
- Kartu anggota dapat dicetak sendiri (DEC-008).
- Data anggota sederhana (nama, status aktif/nonaktif, dan kategori dari tabel kategori; tanpa kelas sebagai data inti), diimpor dari file sesuai template aplikasi (DEC-009, DEC-023).
- QR anggota harus mengidentifikasi anggota dengan aman; format teknisnya boleh dipilih sesuai kebutuhan, tanpa mengekspos data pribadi (DEC-010).
- QR buku dibuat otomatis oleh aplikasi dan label menampilkan ID eksemplar (DEC-011).
- Buku ditambah dengan judul dan jumlah; aplikasi membuat ID dan QR otomatis; eksemplar tidak pernah digabung atau ditimpa karena judul sama (DEC-012, DEC-013).
- Backend target: Hugging Face Spaces menggunakan Docker (DEC-014).
- Database target: Supabase PostgreSQL (DEC-015).
- Asisten AI target: Google Gemini API, direncanakan Gemini 2.5 Flash (DEC-016).
- Notifikasi keterlambatan dalam aplikasi dapat dilihat siapa pun yang membuka halaman notifikasi; WhatsApp tidak digunakan (DEC-017).
- Self-service adalah prinsip mutlak; petugas bukan operator transaksi peminjaman rutin (DEC-018).
- Tidak ada batas maksimum jumlah buku yang ditetapkan; jangan menambahkan batas buatan (DEC-019).
- Anggota tidak aktif dinonaktifkan, bukan dihapus otomatis; histori transaksi tetap tersimpan dan akun dapat diaktifkan kembali (DEC-020).
- Biaya Rp0 adalah target, bukan jaminan layanan gratis selamanya (DEC-021).
- UI dan panduan harus memakai Bahasa Indonesia sangat sederhana (DEC-022).
- Penyelesaian buku hilang/rusak memakai alur QR dalam sesi anggota, dengan pilihan pengganti kamus atau Al-Qur’an per buku; keterlambatan tidak otomatis berarti hilang (DEC-024).

Jika perubahan tampak membutuhkan perubahan salah satu keputusan ini, jangan menyelipkannya sebagai refactor teknis. Jelaskan konflik, alternatif, konsekuensi, dan minta persetujuan pengguna.

---

# 16. Glosarium

- **Katalog/judul buku:** data bibliografis yang menjelaskan judul/karya/edisi.
- **Eksemplar fisik:** satu salinan fisik yang dapat dipinjam secara individual.
- **QR anggota:** kode berisi token/referensi acak untuk mengidentifikasi anggota lewat server.
- **QR eksemplar:** kode yang mengidentifikasi satu eksemplar fisik tertentu dan label cetaknya wajib menampilkan ID eksemplar.
- **ID eksemplar:** ID unik yang dibuat otomatis oleh aplikasi untuk membedakan eksemplar fisik. Nomor registrasi lama sekolah tidak dipakai.
- **Cold start:** waktu tunggu saat layanan yang tidur harus aktif kembali setelah menerima akses.
- **Hugging Face Spaces:** platform target untuk menjalankan backend Flask dalam Docker.
- **Supabase PostgreSQL:** database target untuk data perpustakaan yang persisten.
- **Notifikasi dalam aplikasi:** daftar pinjaman terlambat yang dihitung dari data jatuh tempo dan dapat dilihat siapa pun yang membuka halaman notifikasi, sebagai pengingat sosial (DEC-017).
- **Penggantian berupa buku:** kamus atau Al-Qur’an sebagai penyelesaian buku hilang/rusak, bukan uang (DEC-024).
- **QR Penyelesaian Buku:** pintu masuk ke alur penyelesaian buku hilang/rusak di dalam sesi anggota yang sah; bukan QR yang ditempel pada buku dan bukan bukti penyelesaian.
- **Perpanjangan:** tambahan 7 hari satu kali per eksemplar, dipilih dan dikonfirmasi anggota (DEC-005).
- **Transaksi induk:** catatan yang menyatukan satu proses peminjaman dengan banyak item, jika desain data memakai model induk-detail.
- **Item/detail pinjaman:** catatan tiap eksemplar dalam transaksi; dapat kembali pada waktu yang berbeda.
- **Peminjaman aktif:** item yang belum tercatat kembali sesuai status bisnis yang disepakati.
- **Due date/jatuh tempo:** batas waktu pengembalian berdasarkan aturan peminjaman.
- **Durasi aktual:** interval waktu dari pinjam sampai pengembalian, dihitung dari timestamp.
- **Transaksi atomik:** beberapa perubahan terkait berhasil seluruhnya atau gagal seluruhnya.
- **Token dicabut:** token tidak lagi sah untuk digunakan.
- **Dry-run:** simulasi pemeriksaan migrasi/operasi tanpa menerapkan perubahan permanen.
- **Backup:** salinan yang dibuat untuk pemulihan; harus disertai prosedur restore dan pengujian.
- **Restore:** proses memulihkan sistem/data dari backup.
- **Staging:** lingkungan uji yang mewakili produksi tanpa menggunakan data nyata yang tidak semestinya.
- **Production:** sistem aktif yang digunakan untuk operasional nyata.
- **Acceptance criteria/kriteria penerimaan:** kondisi terukur yang harus dipenuhi agar fitur dapat dinyatakan selesai/terverifikasi.
- **Audit trail:** catatan aktivitas penting, pelaku, waktu, objek, dan alasan bila diperlukan.
- **Source of truth:** sumber yang menjadi acuan untuk jenis kebenaran tertentu; kondisi kode untuk implementasi, dokumen keputusan untuk maksud produk, tes untuk bukti verifikasi.

---

# 17. Cara Memperbarui Dokumen Ini

Dokumen ini harus berkembang mengikuti keputusan pengguna dan kondisi repositori, bukan menjadi teks statis yang akhirnya berbeda dari proyek.

Setiap pembaruan bermakna sebaiknya mencatat:

- tanggal;
- bagian/requirement yang berubah;
- isi lama dan isi baru atau ringkasan perubahan;
- alasan perubahan;
- siapa yang mengonfirmasi keputusan produk;
- bukti teknis jika perubahan berbicara tentang implementasi;
- apakah keputusan lama dibatalkan atau tetap berlaku untuk data historis.

Jangan menulis “sudah selesai” hanya karena agent telah menghasilkan kode. Perbarui status menjadi `IMPLEMENTED` setelah keberadaan kode diperiksa, dan `VERIFIED` setelah kriteria penerimaan diuji dengan bukti. Untuk deployment, tuliskan status lokal, staging, dan produksi secara terpisah.

## Riwayat dokumen

| Versi | Tanggal | Perubahan |
|---|---|---|
| 2.0 | 16 Oktober 2026 | Konsolidasi konteks proyek, keputusan produk, alur QR, aturan peminjaman/pengembalian, batas keamanan, kebutuhan, roadmap, dan protokol kerja AI berdasarkan riwayat percakapan. Status repositori aktual belum diaudit sebagai bagian dari dokumen ini. |
| 3.0 | 16 Oktober 2026 | Memperbarui arsitektur target ke Hugging Face Spaces + Docker, Supabase PostgreSQL, Gemini API, serta menegaskan WhatsApp sebagai fitur wajib; memperjelas self-service mutlak, batas pinjam 7 hari, QR dengan nomor registrasi, impor buku berbasis nomor registrasi, sumber data anggota dari TU, dan bahasa panduan untuk anak kecil/orang awam. |
| 3.1 | 16 Oktober 2026 | Finalisasi: menghapus butir ganda di 4.10; memperbaiki level heading 3.5; merapikan urutan LIB-QR-003; menyelaraskan langkah pengembalian 4.8 dengan DEC-018; merapikan kata “tepat maksimal” pada DEC-005; menambah contoh risiko layanan gratis pada OPEN-004; menambah catatan urutan P4/P5; menambah requirement turunan LIB-QR-004, LIB-IMPORT-002, dan LIB-UX-001 untuk DEC-008/011/012/013/022. Tidak ada keputusan produk atau arsitektur yang diubah. |
| 4.0 | 16 Oktober 2026 | Revisi keputusan atas ketetapan pengguna: ID eksemplar dan QR dibuat otomatis (DEC-004, DEC-011, DEC-012, DEC-013 direvisi atau digantikan); nomor registrasi tidak dipakai; data anggota minimal tanpa kelas (DEC-009, DEC-023); WhatsApp dibatalkan dan diganti notifikasi dalam aplikasi untuk admin (DEC-005, DEC-017); anggota tidak aktif 3 tahun dihapus otomatis (DEC-020); denda berupa buku kamus/Al-Qur’an (DEC-024). OPEN-001 sampai OPEN-010 diperbarui atau ditutup, OPEN-011 sampai OPEN-015 ditambahkan. Requirement baru: LIB-MEMBER-002, LIB-NOTIF-001, LIB-FINE-001; LIB-WA-001 dihapus; LIB-QR-004 dan LIB-IMPORT-002 direvisi. Rincian di 3.1.1. |
| 4.1 | 17 Oktober 2026 | Menetapkan notifikasi keterlambatan yang dapat dilihat siapa pun di halaman notifikasi; menyederhanakan data anggota menjadi nama/status/kategori; mengganti penghapusan otomatis anggota dengan penonaktifan tanpa penghapusan; menetapkan perpanjangan satu kali selama 7 hari per eksemplar; menetapkan alur pengembalian parsial, QR Penyelesaian Buku yang dapat dipakai berulang kali, penyelesaian beberapa buku per sesi, dan penggantian kamus/Al-Qur’an per buku; buku terlambat lebih dari 7 hari tidak otomatis dianggap hilang tetapi memblokir peminjaman baru sampai diselesaikan. Menutup OPEN-005, OPEN-006, OPEN-011 sampai OPEN-015 sebagai keputusan produk/aturan implementasi; menambahkan LIB-RETURN-004 dan memperbarui LIB-MEMBER-002, LIB-NOTIF-001, LIB-FINE-001, Bagian 4, 7, 10, 12, dan 15. |
| 4.2 | 17 Oktober 2026 | Perapian atas v4.1 tanpa mengubah keputusan: menyelaraskan glosarium, judul P3, dan butir roadmap; menyelaraskan 4.9.1 dengan DEC-023; menyatukan 4.4, 4.8, dan 6.5 menjadi dua jalur pengembalian (perlu konfirmasi); menulis pengecualian privasi notifikasi publik di 6.8; menjernihkan aturan perpanjangan dan menambah OPEN-016, OPEN-017, OPEN-018; memindahkan LIB-RETURN-004 setelah LIB-RETURN-003; memperbaiki urutan riwayat. |
---

# 18. Penutup: Makna Proyek Ini bagi AI Berikutnya

Jangan memperlakukan proyek ini sebagai sekadar aplikasi katalog yang perlu terus ditambah tombol. Prinsip self-service-first (DEC-018) adalah persyaratan inti: jangan menambahkan ketergantungan pada petugas untuk transaksi rutin atau persetujuan manual setiap kali anggota meminjam/mengembalikan buku. Ini adalah sistem operasional yang harus mempertahankan hubungan antara buku fisik, anggota, transaksi, waktu, kondisi, dan riwayat. Peminjaman mandiri hanya berguna jika status stok tetap benar; AI hanya berguna jika tidak mengarang keadaan database; hosting hanya berguna jika data bertahan dan bisa dipulihkan; dan fitur dianggap selesai hanya jika kebutuhan serta hasilnya dapat dibuktikan.

Tugas AI adalah membantu pengguna mewujudkan kebutuhan tersebut secara bertahap, dengan menghormati keputusan yang sudah ditetapkan, menunjukkan hal yang belum diketahui, memeriksa kondisi aktual, menguji perubahan, dan melaporkan hasil dengan jujur.

**Dokumen ini adalah konteks induk dan kontrak kerja, bukan pengganti audit repositori, persetujuan kebijakan sekolah, tinjauan keamanan, atau pengujian sebelum penggunaan data nyata.**
