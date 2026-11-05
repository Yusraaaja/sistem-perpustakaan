# -*- coding: utf-8 -*-
# Patch script for Task 5-02: insert KioskIsolatedSessionInterface into app.py

import os

kiosk_lines = [
    "",
    "# ==============================================================================",
    "# ISOLASI SESI KIOSK (TASK 5-02, DEC-002, DEC-018)",
    "# Antarmuka sesi kustom yang memisahkan sesi kiosk dari sesi admin secara ketat.",
    "# Kiosk: cookie 'kiosk_session' Path=/kiosk; Admin: cookie 'session' Path=/.",
    "# Kiosk sessions TIDAK PERNAH memuat kunci admin (logged_in, user_role, admin_username).",
    "# ==============================================================================",
    "",
    "from flask.sessions import SecureCookieSessionInterface",
    "from itsdangerous import BadSignature",
    "",
    "",
    "def _is_kiosk_request(path: str) -> bool:",
    "    'True jika path request mengarah ke namespace kiosk (/kiosk atau /kiosk/*).'",
    "    return path == '/kiosk' or path.startswith('/kiosk/')",
    "",
    "",
    "class KioskIsolatedSessionInterface(SecureCookieSessionInterface):",
    "    'Antarmuka sesi kustom Flask: pisahkan sesi kiosk dari sesi admin secara ketat.'",
    "",
    "    def open_session(self, app, request):",
    "        s = self.get_signing_serializer(app)",
    "        if s is None:",
    "            return None",
    "",
    "        if _is_kiosk_request(request.path):",
    "            # Baca cookie kiosk saja, abaikan cookie admin",
    "            val = request.cookies.get(KIOSK_SESSION_COOKIE_NAME)",
    "            if not val:",
    "                return self.session_class({'_is_kiosk': True})",
    "            try:",
    "                data = s.loads(val, max_age=KIOSK_SESSION_LIFETIME_SECONDS)",
    "                # Hapus paksa kunci admin — mencegah eskalasi privilege",
    "                for key in KIOSK_FORBIDDEN_SESSION_KEYS:",
    "                    data.pop(key, None)",
    "                data['_is_kiosk'] = True",
    "                return self.session_class(data)",
    "            except BadSignature:",
    "                return self.session_class({'_is_kiosk': True})",
    "        else:",
    "            # Baca cookie admin standar Flask",
    "            cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')",
    "            val = request.cookies.get(cookie_name)",
    "            if not val:",
    "                return self.session_class()",
    "            max_age = int(app.permanent_session_lifetime.total_seconds())",
    "            try:",
    "                data = s.loads(val, max_age=max_age)",
    "                # Hapus marker kiosk jika ada di cookie admin (defensive)",
    "                data.pop('_is_kiosk', None)",
    "                return self.session_class(data)",
    "            except BadSignature:",
    "                return self.session_class()",
    "",
    "    def save_session(self, app, session, response):",
    "        from flask import request as _current_request",
    "        s = self.get_signing_serializer(app)",
    "        if s is None:",
    "            return",
    "",
    "        domain = self.get_cookie_domain(app)",
    "        secure = self.get_cookie_secure(app)",
    "        samesite = self.get_cookie_samesite(app)",
    "        httponly = self.get_cookie_httponly(app)",
    "",
    "        if session.accessed:",
    "            response.vary.add('Cookie')",
    "",
    "        if _is_kiosk_request(_current_request.path):",
    "            name = KIOSK_SESSION_COOKIE_NAME",
    "            path = KIOSK_COOKIE_PATH",
    "            expires = None  # Session cookie tanpa expiry tetap untuk kiosk",
    "        else:",
    "            name = app.config.get('SESSION_COOKIE_NAME', 'session')",
    "            path = app.config.get('SESSION_COOKIE_PATH', '/')",
    "            expires = self.get_expiration_time(app, session)",
    "",
    "        if not session:",
    "            if session.modified:",
    "                response.delete_cookie(name, domain=domain, path=path,",
    "                                       secure=secure, samesite=samesite, httponly=httponly)",
    "                response.vary.add('Cookie')",
    "            return",
    "",
    "        if not self.should_set_cookie(app, session):",
    "            return",
    "",
    "        val = s.dumps(dict(session))",
    "        response.set_cookie(name, val, expires=expires, httponly=httponly,",
    "                            domain=domain, path=path, secure=secure, samesite=samesite)",
    "        response.vary.add('Cookie')",
    "",
    "",
    "# Pasang session interface kustom kiosk SETELAH konfigurasi app selesai",
    "app.session_interface = KioskIsolatedSessionInterface()",
    "",
]

def main():
    app_path = 'app.py'
    with open(app_path, 'rb') as f:
        content = f.read().decode('utf-8')

    # Build insert block with CRLF (matching app.py line endings)
    code_to_insert = '\r\n'.join(kiosk_lines) + '\r\n'

    # Insertion marker: just before the BRUTE FORCE section
    marker = ('# ========================================================='
              '=====================\r\n# BRUTE FORCE & LOGIN RATE LIMITING ENGINE (In-Memory Thread-Safe)\r\n')
    if marker not in content:
        print('ERROR: Insertion marker not found! Searching...')
        # Try to find close match
        idx = content.find('# BRUTE FORCE')
        print(f'BRUTE FORCE found at index: {idx}')
        print('Context:', repr(content[idx-100:idx+50]))
        return

    content = content.replace(marker, code_to_insert + marker, 1)
    with open(app_path, 'wb') as f:
        f.write(content.encode('utf-8'))

    lines = content.count('\n')
    print(f'OK: KioskIsolatedSessionInterface inserted. Total lines: {lines}')

    checks = [
        'KioskIsolatedSessionInterface',
        '_is_kiosk_request',
        'app.session_interface = KioskIsolatedSessionInterface()',
        'KIOSK_SESSION_COOKIE_NAME',
        'KIOSK_FORBIDDEN_SESSION_KEYS',
    ]
    for chk in checks:
        if chk in content:
            print(f'OK: {chk!r} found in app.py')
        else:
            print(f'MISSING: {chk!r} NOT found in app.py')

if __name__ == '__main__':
    main()
