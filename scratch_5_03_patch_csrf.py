"""
Patch: tambahkan exemption kiosk ke verify_csrf (Task 5-03).
Kiosk POST /kiosk/validate_qr adalah publik (tanpa sesi admin),
tidak memerlukan CSRF token berbasis sesi admin.
"""
import pathlib, sys

app_path = pathlib.Path(__file__).parent / 'app.py'
content = app_path.read_bytes()

# Cari baris di dalam verify_csrf yang memeriksa CSRF token
# Tambahkan early return untuk kiosk SETELAH method check, SEBELUM token check

OLD = (
    b"@app.before_request\r\n"
    b"def verify_csrf():\r\n"
    b"    \"\"\"Verifikasi token CSRF pada seluruh permintaan yang memutasi state (POST, PUT, DELETE, PATCH).\"\"\"\r\n"
    b"    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):\r\n"
    b"        session_token = session.get('_csrf_token')\r\n"
)

NEW = (
    b"@app.before_request\r\n"
    b"def verify_csrf():\r\n"
    b"    \"\"\"Verifikasi token CSRF pada seluruh permintaan yang memutasi state (POST, PUT, DELETE, PATCH).\"\"\"\r\n"
    b"    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):\r\n"
    b"        # Kiosk API endpoint (Task 5-03+) adalah publik dan tidak memiliki sesi admin.\r\n"
    b"        # CSRF berbasis sesi tidak relevan untuk kiosk JSON POST.\r\n"
    b"        if _is_kiosk_request(request.path) and request.is_json:\r\n"
    b"            return  # Kiosk JSON POST dikecualikan dari CSRF sesi admin\r\n"
    b"        session_token = session.get('_csrf_token')\r\n"
)

if OLD not in content:
    print("ERROR: target CSRF tidak ditemukan", file=sys.stderr)
    sys.exit(1)

new_content = content.replace(OLD, NEW, 1)
if new_content == content:
    print("ERROR: penggantian gagal", file=sys.stderr)
    sys.exit(1)

app_path.write_bytes(new_content)
print("OK: kiosk CSRF exemption ditambahkan ke verify_csrf")

