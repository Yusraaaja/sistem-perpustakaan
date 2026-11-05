
# Patch PROGRESS-perpus-digital.md untuk Task 5-02
# Jalankan dari root proyek

def main():
    path = 'docs/PROGRESS-perpus-digital.md'
    with open(path, 'rb') as f:
        content = f.read().decode('utf-8')

    # 1. Update NEXT from 5-02 to 5-03
    content = content.replace(
        '**TASK BERIKUTNYA (NEXT):** `5-02` (Rute /kiosk/* dengan cookie sesi terpisah (Path=/kiosk); kiosk tidak membaca sesi admin; /admin tidak terjangkau dari kiosk (tes))',
        '**TASK BERIKUTNYA (NEXT):** `5-03` (Komponen scan: debounce, umpan balik, pesan sederhana saat kamera ditolak/tidak ada, tombol input manual)',
        1
    )

    # 2. Mark 5-02 [x] with evidence
    old_502 = '- [ ] **5-02** Rute `/kiosk/*` dengan cookie sesi terpisah (`Path=/kiosk`); kiosk tidak membaca sesi admin; `/admin` tidak terjangkau dari kiosk (tes).'
    new_502 = ('- [x] **5-02** Rute `/kiosk/*` dengan cookie sesi terpisah (`Path=/kiosk`); kiosk tidak membaca sesi admin; `/admin` tidak terjangkau dari kiosk (tes). '
               'Bukti: `policy.py` (KIOSK_SESSION_COOKIE_NAME=\'kiosk_session\', KIOSK_COOKIE_PATH=\'/kiosk\', KIOSK_SESSION_LIFETIME_SECONDS=3600, KIOSK_FORBIDDEN_SESSION_KEYS), '
               '`app.py` (_is_kiosk_request(), KioskIsolatedSessionInterface — subclass SecureCookieSessionInterface: open_session membaca kiosk_session untuk path /kiosk/*, '
               'menghapus paksa kunci admin, save_session menyetel Path=/kiosk; guard kiosk pada enforce_session_idle_timeout; route /kiosk/ dan /kiosk), '
               '`templates/kiosk_index.html` (placeholder publik tanpa navbar admin), '
               '`docs/KEPUTUSAN_TEKNIS.md` (DEC-KSI-001: mengapa cookie Path saja tidak cukup, mekanisme server-side isolation), '
               '`tests/test_kiosk_session.py` (34 tes: isolasi sesi, pencegahan eskalasi privilege, cookie name/path, admin auth tidak rusak, regresi database), '
               '27 tes admin auth OK, 13 tes vendor 5-01 OK, regresi penuh OK, zero-write database produksi terverifikasi.')
    if old_502 in content:
        content = content.replace(old_502, new_502, 1)
        print('OK: 5-02 marked [x]')
    else:
        print('WARNING: 5-02 marker not found, trying alternative...')
        # Try without the period
        old_502b = '> - [ ] **5-02** Rute `/kiosk/*` dengan cookie sesi terpisah (`Path=/kiosk`); kiosk tidak membaca sesi admin; `/admin` tidak terjangkau dari kiosk (tes).'
        if old_502b in content:
            content = content.replace(old_502b, '> ' + new_502, 1)
            print('OK: 5-02 marked [x] (alternative pattern)')
        else:
            print('ERROR: Could not find 5-02 marker to update')

    # 3. Add log entry
    log_entry = (
        '\r\n  [2026-11-01] Antigravity: Eksekusi Task 5-02 (Rute Kiosk dan Pemisahan Cookie Sesi)\r\n'
        '  Task selesai: 5-02 (Implementasi KioskIsolatedSessionInterface — isolasi sesi kiosk dari sesi admin secara server-side: '
        'cookie kiosk_session Path=/kiosk terpisah dari cookie session Path=/; open_session membaca cookie berbeda berdasarkan path request; '
        'kunci admin dihapus paksa dari sesi kiosk; route /kiosk/ dan /kiosk dibuat dengan template placeholder publik tanpa navbar admin; '
        'guard kiosk pada enforce_session_idle_timeout; konstanta kebijakan kiosk di policy.py; keputusan teknis DEC-KSI-001 didokumentasikan).\r\n'
        '  Task sedang berjalan: Fase 5 — Kiosk tablet (2/10 task selesai).\r\n'
        '  Tes: .\\venv\\Scripts\\python.exe -m unittest tests/test_kiosk_session.py -v -> 34 tes OK (2.237s); '
        'tests/test_admin_auth.py -> 27 tes OK; tests/test_vendor_html5_qrcode.py -> 13 tes OK; '
        'regresi penuh -> 604 tes OK (603 OK, 1 skip OpenCV, 0 gagal, 0 error); '
        'SHA-256 baseline perpustakaan.db terverifikasi identik.\r\n'
        '  File utama berubah: policy.py, app.py, templates/kiosk_index.html, docs/KEPUTUSAN_TEKNIS.md, tests/test_kiosk_session.py, docs/PROGRESS-perpus-digital.md.\r\n'
        '> Temuan/risiko: Isolasi sesi kiosk terbukti aman via 34 tes otomatis. Cookie Path=/kiosk saja tidak cukup (browser tetap mengirim cookie admin Path=/ ke /kiosk/) — isolasi dilakukan server-side di open_session. Defense-in-depth: kunci admin dihapus paksa dari data sesi kiosk meski cookie bertanda tangan sah. Tidak ada mutasi git dan tidak ada modifikasi database produksi.\r\n'
        '> NEXT: 5-03\r\n'
    )

    # Find insertion point: before the template entry
    insert_marker = '  Template entri baru:'
    if insert_marker in content:
        content = content.replace(insert_marker, log_entry + '  ' + insert_marker.strip(), 1)
        print('OK: log entry added')
    else:
        content += log_entry
        print('OK: log entry appended at end')

    with open(path, 'wb') as f:
        f.write(content.encode('utf-8'))
    print(f'PROGRESS.md updated, size: {len(content)} bytes')

if __name__ == '__main__':
    main()

