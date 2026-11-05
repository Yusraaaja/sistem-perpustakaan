# -*- coding: utf-8 -*-
# Patch script for Task 5-02: add kiosk routes before DATABASE INITIALIZATION section

kiosk_routes = [
    "",
    "# ==============================================================================",
    "# FASE 5 - KIOSK TABLET (NAMESPACE /kiosk) - Task 5-02",
    "# Route /kiosk/* menggunakan sesi terpisah (kiosk_session, Path=/kiosk).",
    "# Kiosk bersifat publik (tanpa autentikasi admin).",
    "# Fitur pemindaian QR dan alur peminjaman akan diimplementasikan pada Task 5-03 s.d. 5-10.",
    "# ==============================================================================",
    "",
    "",
    "@app.route('/kiosk/')",
    "@app.route('/kiosk')",
    "def kiosk_index():",
    "    'Halaman utama kiosk layanan mandiri anggota perpustakaan (Task 5-02).'",
    "    return render_template('kiosk_index.html')",
    "",
    "",
]

def main():
    app_path = 'app.py'
    with open(app_path, 'rb') as f:
        content = f.read().decode('utf-8')

    code_to_insert = '\r\n'.join(kiosk_routes) + '\r\n'

    # Insert just before DATABASE INITIALIZATION section
    marker = '\r\n# ==========================================\r\n# DATABASE INITIALIZATION & APPLICATION RUNNER\r\n# ==========================================\r\n'
    if marker not in content:
        print('ERROR: DATABASE INITIALIZATION marker not found!')
        idx = content.find('DATABASE INITIALIZATION')
        print(f'Found at: {idx}')
        print(repr(content[idx-30:idx+80]))
        return

    content = content.replace(marker, '\r\n' + code_to_insert + marker.lstrip('\r\n'), 1)
    with open(app_path, 'wb') as f:
        f.write(content.encode('utf-8'))

    lines = content.count('\n')
    print(f'OK: kiosk routes inserted. Total lines: {lines}')

    if '@app.route(\'/kiosk/\')' in content:
        print('OK: /kiosk/ route found')
    if 'def kiosk_index()' in content:
        print('OK: kiosk_index function found')

if __name__ == '__main__':
    main()

