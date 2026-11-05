"""
Patch script: tambahkan route /kiosk/validate_qr ke app.py (Task 5-03).
Dijalankan sekali; tidak memodifikasi database.
"""
import pathlib, sys

app_path = pathlib.Path(__file__).parent / 'app.py'
content = app_path.read_bytes()

MARKER = (
    b"# ==========================================\r\n"
    b"# DATABASE INITIALIZATION & APPLICATION RUNNER\r\n"
    b"# ==========================================\r\n"
)

if MARKER not in content:
    print("ERROR: marker tidak ditemukan — periksa app.py", file=sys.stderr)
    sys.exit(1)

INSERTION = (
    b"\r\n"
    b"# ------------------------------------------------------------------------------\r\n"
    b"# FASE 5 \xe2\x80\x94 KIOSK: /kiosk/validate_qr (Task 5-03)\r\n"
    b"# Endpoint format-check untuk komponen scan QR kiosk.\r\n"
    b"#\r\n"
    b"# Kontrak:\r\n"
    b"#   - Menerima JSON { \"code\": \"<string>\" }.\r\n"
    b"#   - Hanya memeriksa FORMAT kode (panjang, karakter yang diizinkan).\r\n"
    b"#   - TIDAK mengakses database, TIDAK memverifikasi identitas anggota/buku.\r\n"
    b"#   - Kode yang lolos dinyatakan sebagai \"format_ok\", bukan \"verified\".\r\n"
    b"#   - Logika peminjaman dan verifikasi identitas adalah bagian Task 5-04.\r\n"
    b"#   - Isolasi sesi kiosk (KioskIsolatedSessionInterface) berlaku otomatis.\r\n"
    b"# ------------------------------------------------------------------------------\r\n"
    b"_KIOSK_QR_VALID_RE = re.compile(r'^[A-Za-z0-9:\\-]{1,200}$')\r\n"
    b"_KIOSK_QR_MAX_CODE_LEN = 200\r\n"
    b"\r\n"
    b"\r\n"
    b"@app.route('/kiosk/validate_qr', methods=['POST'])\r\n"
    b"def kiosk_validate_qr():\r\n"
    b"    \"\"\"\r\n"
    b"    Periksa format kode QR dari kiosk scanner (Task 5-03).\r\n"
    b"\r\n"
    b"    Hanya memvalidasi format -- belum memverifikasi keanggotaan atau ketersediaan buku.\r\n"
    b"    Respons 200 berarti kode lolos pemeriksaan format, bukan bahwa kode valid sebagai\r\n"
    b"    anggota atau buku yang sah. Logika tersebut ada di Task 5-04.\r\n"
    b"    \"\"\"\r\n"
    b"    # Periksa Content-Type JSON\r\n"
    b"    if not request.is_json:\r\n"
    b"        return jsonify({\r\n"
    b"            'status': 'error',\r\n"
    b"            'error': 'Content-Type harus application/json'\r\n"
    b"        }), 400\r\n"
    b"\r\n"
    b"    data = request.get_json(silent=True)\r\n"
    b"    if data is None:\r\n"
    b"        return jsonify({\r\n"
    b"            'status': 'error',\r\n"
    b"            'error': 'Body JSON tidak valid atau kosong'\r\n"
    b"        }), 400\r\n"
    b"\r\n"
    b"    # Periksa keberadaan dan tipe field 'code'\r\n"
    b"    code = data.get('code')\r\n"
    b"    if not isinstance(code, str):\r\n"
    b"        return jsonify({\r\n"
    b"            'status': 'error',\r\n"
    b"            'error': 'Field \"code\" wajib ada dan bertipe string'\r\n"
    b"        }), 400\r\n"
    b"\r\n"
    b"    code = code.strip()\r\n"
    b"\r\n"
    b"    # Periksa panjang\r\n"
    b"    if len(code) == 0:\r\n"
    b"        return jsonify({\r\n"
    b"            'status': 'error',\r\n"
    b"            'error': 'Kode tidak boleh kosong'\r\n"
    b"        }), 400\r\n"
    b"\r\n"
    b"    if len(code) > _KIOSK_QR_MAX_CODE_LEN:\r\n"
    b"        return jsonify({\r\n"
    b"            'status': 'error',\r\n"
    b"            'error': 'Kode terlalu panjang (maksimum {} karakter)'.format(_KIOSK_QR_MAX_CODE_LEN)\r\n"
    b"        }), 400\r\n"
    b"\r\n"
    b"    # Periksa format karakter\r\n"
    b"    if not _KIOSK_QR_VALID_RE.match(code):\r\n"
    b"        return jsonify({\r\n"
    b"            'status': 'error',\r\n"
    b"            'error': 'Format kode tidak dikenali (hanya huruf, angka, tanda \"-\" dan \":\" diizinkan)'\r\n"
    b"        }), 400\r\n"
    b"\r\n"
    b"    # Format lolos -- kembalikan kode untuk konfirmasi UI\r\n"
    b"    # CATATAN: ini bukan verifikasi identitas atau keabsahan kode sebagai anggota/buku.\r\n"
    b"    display_code = code[:12] + ('...' if len(code) > 12 else '')\r\n"
    b"    return jsonify({\r\n"
    b"        'status': 'format_ok',\r\n"
    b"        'display_code': display_code,\r\n"
    b"        'note': 'Kode lolos pemeriksaan format. Belum diverifikasi sebagai anggota atau buku.'\r\n"
    b"    }), 200\r\n"
    b"\r\n"
    b"\r\n"
)

new_content = content.replace(MARKER, INSERTION + MARKER, 1)

if new_content == content:
    print("ERROR: penggantian tidak berhasil", file=sys.stderr)
    sys.exit(1)

app_path.write_bytes(new_content)
print("OK: /kiosk/validate_qr route berhasil ditambahkan ke app.py")

