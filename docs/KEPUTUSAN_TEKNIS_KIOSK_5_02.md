

---

# Keputusan Teknis: Isolasi Sesi Kiosk (Task 5-02)

**ID Keputusan:** DEC-KSI-001 (Task 5-02, DEC-002, DEC-018)
**Tanggal:** 1 November 2026
**Status:** Ditetapkan

---

## 1. Masalah

Flask menggunakan satu antarmuka sesi tunggal (`SecureCookieSessionInterface`) dengan satu nama cookie (`session`) dan `Path=/` untuk seluruh aplikasi. Ini berarti browser akan mengirim cookie admin ke URL `/kiosk/` karena `Path=/` mencakup semua sub-path. Jika kiosk membaca cookie `session` yang sama, seorang admin yang juga membuka halaman kiosk secara tidak sengaja akan dikenali sebagai pengguna terautentikasi di kiosk — ini adalah kebocoran hak akses silang yang tidak disengaja.

---

## 2. Keputusan: Custom Session Interface

Sistem mengimplementasikan `KioskIsolatedSessionInterface` — subclass `SecureCookieSessionInterface` — yang menggantikan `app.session_interface` default Flask.

### Prinsip Isolasi

| Aspek | Sesi Admin | Sesi Kiosk |
|---|---|---|
| Nama Cookie | `session` | `kiosk_session` |
| Path Cookie | `/` | `/kiosk` |
| Lifetime | 8 jam (ADMIN_SESSION_LIFETIME_HOURS) | 1 jam (KIOSK_SESSION_LIFETIME_SECONDS) |
| Kunci terlarang | — | `logged_in`, `user_role`, `admin_username` |
| Akses admin | Ya (via `is_admin_session()`) | Tidak pernah |

### Mekanisme open_session

Saat request masuk:
1. Jika path adalah `/kiosk` atau `/kiosk/*` (`_is_kiosk_request()`):
   - Baca cookie `kiosk_session`, **abaikan** cookie `session` admin.
   - Hapus paksa semua kunci admin dari data sesi (defense-in-depth).
   - Tandai sesi dengan `_is_kiosk = True`.
2. Jika path adalah selain kiosk:
   - Baca cookie `session` admin, **abaikan** cookie `kiosk_session`.
   - Hapus marker `_is_kiosk` jika ada.

### Mekanisme save_session

Saat response dikirim:
- Kiosk: tulis `kiosk_session` dengan `Path=/kiosk`.
- Admin: tulis `session` dengan `Path=/`.

### Mengapa Cookie Path Saja Tidak Cukup

Browser mengirim cookie berdasarkan **request path**, bukan berdasarkan cookie path. Cookie admin dengan `Path=/` dikirim ke SEMUA sub-path termasuk `/kiosk/`. Oleh karena itu, isolasi harus dilakukan di **sisi server** (server-side) dengan cara menolak membaca cookie admin saat melayani request kiosk.

---

## 3. Alur Pencegahan Eskalasi Privilege

**Skenario: Penyerang membuat `kiosk_session` dengan kunci admin**

1. Penyerang membuat cookie `kiosk_session` bertanda tangan dengan `logged_in=True, user_role='admin'`.
2. `open_session` mendeteksi `/kiosk/` → baca `kiosk_session`.
3. `KIOSK_FORBIDDEN_SESSION_KEYS` = `{'logged_in', 'user_role', 'admin_username'}` → kunci dihapus.
4. Sesi yang tersisa tidak mengandung `logged_in=True` atau `user_role='admin'`.
5. `is_admin_session()` mengembalikan `False` → akses `/admin` ditolak.

**Skenario: Admin login, lalu akses `/kiosk/`**

1. Admin punya cookie `session` dengan `logged_in=True, user_role='admin'`.
2. Request `/kiosk/` → `open_session` membaca `kiosk_session` (tidak ada / kosong), **abaikan** cookie `session`.
3. Sesi kiosk kosong — tidak punya `logged_in` atau `user_role`.
4. Kiosk berjalan sebagai pengguna publik anonim.

---

## 4. Dampak pada Fitur yang Ada

- `is_admin_session()`, `reject_unauthorized_admin()`: **tidak berubah**.
- `enforce_session_idle_timeout()`: dikecualikan untuk path kiosk (guard `_is_kiosk_request`); timeout kiosk ditangani di Task 5-08.
- CSRF: token CSRF disimpan di sesi kiosk secara terpisah; `verify_csrf()` berfungsi normal.
- Seluruh route admin (`/admin/*`): tidak terpengaruh.

---

## 5. File yang Diubah

- `policy.py`: tambah `KIOSK_SESSION_COOKIE_NAME`, `KIOSK_COOKIE_PATH`, `KIOSK_SESSION_LIFETIME_SECONDS`, `KIOSK_FORBIDDEN_SESSION_KEYS`.
- `app.py`: tambah `_is_kiosk_request()`, `KioskIsolatedSessionInterface`, `app.session_interface = KioskIsolatedSessionInterface()`, route `/kiosk/` dan `/kiosk`, guard kiosk pada `enforce_session_idle_timeout`.
- `templates/kiosk_index.html`: halaman placeholder kiosk (tanpa navbar admin).
- `tests/test_kiosk_session.py`: 34 tes isolasi sesi kiosk.


