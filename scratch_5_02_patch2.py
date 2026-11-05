# -*- coding: utf-8 -*-
# Patch script for Task 5-02: add kiosk guard to enforce_session_idle_timeout

def main():
    app_path = 'app.py'
    with open(app_path, 'rb') as f:
        content = f.read().decode('utf-8')

    old = (
        'def enforce_session_idle_timeout():\r\n'
        '    """\r\n'
        '    Penegakan batas ketidakaktifan (idle timeout) pada sesi terautentikasi (Task 3-01).\r\n'
        '    Sesi admin yang tidak aktif melampaui ADMIN_IDLE_TIMEOUT_MINUTES akan dibersihkan secara fail-closed.\r\n'
        '    """\r\n'
        "    if session.get('logged_in'):\r\n"
    )
    new = (
        'def enforce_session_idle_timeout():\r\n'
        '    """\r\n'
        '    Penegakan batas ketidakaktifan (idle timeout) pada sesi terautentikasi (Task 3-01).\r\n'
        '    Sesi admin yang tidak aktif melampaui ADMIN_IDLE_TIMEOUT_MINUTES akan dibersihkan secara fail-closed.\r\n'
        '    Sesi kiosk (/kiosk/*) dikecualikan; timeout kiosk ditangani terpisah pada Task 5-08.\r\n'
        '    """\r\n'
        '    if _is_kiosk_request(request.path):\r\n'
        '        return  # Kiosk session timeout ditangani terpisah (Task 5-08)\r\n'
        "    if session.get('logged_in'):\r\n"
    )

    if old not in content:
        print('ERROR: Pattern not found!')
        idx = content.find('def enforce_session_idle_timeout')
        print('Function at:', idx)
        print('Context:', repr(content[idx:idx+400]))
        return

    content = content.replace(old, new, 1)
    with open(app_path, 'wb') as f:
        f.write(content.encode('utf-8'))
    print('OK: enforce_session_idle_timeout patched with kiosk guard')

if __name__ == '__main__':
    main()

