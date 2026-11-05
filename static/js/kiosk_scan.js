/**
 * kiosk_scan.js — QR scan debounce, UI feedback & borrow flow state machine
 *                 (Task 5-03 + Task 5-04)
 *
 * Kontrak perilaku (Task 5-03 — tidak berubah):
 *   - Debounce: QR yang sama diabaikan selama DEBOUNCE_MS setelah terdeteksi.
 *   - Processing lock: hanya satu request berjalan pada satu waktu.
 *     Callback scanner tambahan (kamera atau manual) saat lock aktif diabaikan.
 *   - Operation counter: timer status menggunakan nomor urut sehingga
 *     timer lama tidak dapat menimpa status yang dihasilkan operasi baru.
 *   - Lock selalu dilepas di blok finally — baik respons OK, error HTTP,
 *     maupun exception jaringan.
 *   - Kegagalan inisialisasi kamera (getCameras, start) dibedakan dari
 *     kegagalan menemukan QR dalam frame (onScanFailure biasa).
 *   - Input manual mengikuti validasi dan lock yang sama dengan kamera.
 *   - Tidak ada CDN; library dimuat dari static/vendor/html5-qrcode/.
 *
 * Tambahan Task 5-04 — State machine alur pinjam:
 *   - State IDLE → scan kartu → MEMBER_ACTIVE → scan buku* → MEMBER_ACTIVE
 *   - submitCode() merutekan request ke endpoint yang sesuai berdasarkan
 *     prefix kode (M- → scan_member, C- + memberActive → scan_copy,
 *     selain itu → validate_qr).
 *   - Nama anggota ditampilkan setelah scan kartu berhasil (K.03).
 *   - Daftar keranjang diperbarui setelah setiap scan buku berhasil.
 *   - Tombol Batal muncul setelah scan kartu berhasil; konfirmasi hanya
 *     ditampilkan jika keranjang tidak kosong (K.04).
 *   - Pembatalan memanggil POST /kiosk/cancel dan mereset UI ke IDLE.
 */

(function () {
  'use strict';

  /* ── Konstanta ─────────────────────────────────────────────────── */
  var DEBOUNCE_MS    = 2000;   // abaikan QR yang sama selama 2 s
  var IDLE_DELAY_MS  = 1500;   // tunda kembali ke idle setelah status sukses/gagal
  var MAX_CODE_LEN   = 200;    // panjang maksimum kode yang dikirim ke server
  /** Format yang diterima: alfanumerik + '-' + ':' (sesuai format token HMAC proyek) */
  var VALID_CODE_RE  = /^[A-Za-z0-9:\-]{1,200}$/;

  /* Endpoint URLs */
  var VALIDATE_URL     = '/kiosk/validate_qr';
  var SCAN_MEMBER_URL  = '/kiosk/scan_member';
  var SCAN_COPY_URL    = '/kiosk/scan_copy';
  var CANCEL_URL       = '/kiosk/cancel';

  /* ── Status scanner ─────────────────────────────────────────────── */
  /** Kode QR terakhir yang DIKIRIM ke server, beserta timestamp pengiriman. */
  var lastSent = { code: null, timestamp: 0 };

  /** true jika ada request yang sedang berjalan. */
  var processing = false;

  /**
   * Nomor urut operasi. Setiap kali submitCode() dipanggil, opSeq naik.
   * Timer yang dibuat oleh operasi N hanya mengubah status jika opSeq
   * masih N saat timer meletus. Ini mencegah timer lama menimpa status baru.
   */
  var opSeq = 0;

  /** Apakah kamera berhasil diinisialisasi. */
  var cameraActive = false;

  /* ── State Task 5-04 ─────────────────────────────────────────────── */
  /** true setelah scan_member berhasil divalidasi server. */
  var memberActive = false;

  /** Jumlah item di keranjang (disinkronkan dari respons server). */
  var cartCount = 0;

  /* ── Elemen DOM ─────────────────────────────────────────────────── */
  var statusEl      = document.getElementById('kiosk-status');
  var qrReaderEl    = document.getElementById('kiosk-qr-reader');
  var manualBtn     = document.getElementById('kiosk-manual-btn');
  var manualArea    = document.getElementById('kiosk-manual-area');
  var manualInput   = document.getElementById('kiosk-manual-input');
  var manualSubmit  = document.getElementById('kiosk-manual-submit');
  var memberInfoEl  = document.getElementById('kiosk-member-info');
  var memberNameEl  = document.getElementById('kiosk-member-name');
  var cartAreaEl    = document.getElementById('kiosk-cart-area');
  var cartListEl    = document.getElementById('kiosk-cart-list');
  var cartCountEl   = document.getElementById('kiosk-cart-count');
  var cancelBtn     = document.getElementById('kiosk-cancel-btn');

  /* ── Pembaruan status UI ─────────────────────────────────────────── */
  /**
   * Ubah status bar.
   * @param {string} msg  - Pesan yang ditampilkan.
   * @param {string} type - 'idle' | 'processing' | 'format_ok' | 'format_bad'
   *                        | 'server_error' | 'camera_error'
   *                        | 'member_ok' | 'copy_ok'  (Task 5-04)
   */
  function setStatus(msg, type) {
    statusEl.textContent = msg;
    statusEl.className = 'kiosk-status kiosk-status--' + type;
  }

  /**
   * Jadwalkan kembali ke idle setelah IDLE_DELAY_MS.
   * seq harus cocok dengan opSeq saat timer meletus; jika tidak, abaikan.
   */
  function scheduleIdle(seq) {
    setTimeout(function () {
      if (opSeq === seq) {
        if (memberActive) {
          setStatus('Arahkan QR label buku ke kamera, atau Batal untuk keluar.', 'idle');
        } else {
          setStatus('Siapkan kartu atau buku, arahkan QR ke kamera.', 'idle');
        }
      }
    }, IDLE_DELAY_MS);
  }

  /* ── Validasi kode ──────────────────────────────────────────────── */
  function isValidFormat(code) {
    return typeof code === 'string' &&
           code.length > 0 &&
           code.length <= MAX_CODE_LEN &&
           VALID_CODE_RE.test(code);
  }

  /* ── UI Task 5-04 ────────────────────────────────────────────────── */

  /**
   * Tampilkan info anggota dan tombol Batal, sembunyikan petunjuk format-only.
   */
  function showMemberSession(memberName) {
    if (memberNameEl) { memberNameEl.textContent = memberName; }
    if (memberInfoEl) { memberInfoEl.hidden = false; }
    if (cartAreaEl)   { cartAreaEl.hidden = false; }
    if (cancelBtn)    { cancelBtn.hidden = false; }
  }

  /**
   * Tambah satu item ke daftar keranjang di UI.
   */
  function appendCartItem(copyId, title) {
    if (!cartListEl) { return; }
    var li = document.createElement('li');
    li.textContent = title || copyId;
    cartListEl.appendChild(li);
  }

  /**
   * Perbarui label jumlah keranjang.
   */
  function updateCartCount(count) {
    cartCount = count;
    if (cartCountEl) {
      cartCountEl.textContent = count + ' buku' + (count === 1 ? '' : ' ') + ' dipilih';
    }
  }

  /**
   * Reset seluruh UI ke state IDLE awal.
   */
  function resetToIdle() {
    memberActive = false;
    cartCount    = 0;
    if (memberInfoEl) { memberInfoEl.hidden = true; }
    if (memberNameEl) { memberNameEl.textContent = ''; }
    if (cartAreaEl)   { cartAreaEl.hidden = true; }
    if (cartListEl)   { cartListEl.innerHTML = ''; }
    if (cartCountEl)  { cartCountEl.textContent = ''; }
    if (cancelBtn)    { cancelBtn.hidden = true; }
    setStatus('Siapkan kartu atau buku, arahkan QR ke kamera.', 'idle');
  }

  /* ── Tombol Batal ────────────────────────────────────────────────── */
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      /* K.04: Dialog konfirmasi hanya jika keranjang tidak kosong. */
      if (cartCount > 0) {
        if (!confirm(
          'Batalkan sesi pinjam?\n' +
          cartCount + ' buku yang dipindai akan dihapus dari keranjang.'
        )) {
          return;
        }
      }

      fetch(CANCEL_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: '{}'
      })
      .then(function () {
        resetToIdle();
      })
      .catch(function () {
        /* Bahkan jika fetch gagal, reset UI agar tidak terjebak */
        resetToIdle();
      });
    });
  }

  /* ── Routing URL berdasarkan state & prefix kode ─────────────────── */
  /**
   * Tentukan endpoint target berdasarkan kode dan state saat ini.
   * @param {string} code
   * @returns {string} URL endpoint
   */
  function resolveUrl(code) {
    var upper = code.toUpperCase();
    if (upper.indexOf('M-') === 0) {
      /* Prefix kartu anggota → selalu ke scan_member */
      return SCAN_MEMBER_URL;
    }
    if (upper.indexOf('C-') === 0 && memberActive) {
      /* Prefix eksemplar + sesi anggota aktif → scan_copy */
      return SCAN_COPY_URL;
    }
    /* Fallback: format check saja */
    return VALIDATE_URL;
  }

  /* ── Handler respons per endpoint ────────────────────────────────── */

  function handleScanMemberOk(data, mySeq) {
    memberActive = true;
    cartCount    = 0;
    showMemberSession(data.member_name);
    if (cartListEl) { cartListEl.innerHTML = ''; }
    updateCartCount(0);
    setStatus('Selamat datang, ' + data.member_name + '! Scan buku yang ingin dipinjam.', 'member_ok');
    scheduleIdle(mySeq);
  }

  function handleScanCopyOk(data, mySeq) {
    appendCartItem(data.copy_id, data.title);
    updateCartCount(data.cart_count);
    setStatus(
      '\u2705 "' + (data.title || data.copy_id) + '" ditambahkan. ' +
      'Total: ' + data.cart_count + ' buku.',
      'copy_ok'
    );
    scheduleIdle(mySeq);
  }

  function handleValidateOk(data, mySeq) {
    setStatus(
      'Format kode diterima (' + data.display_code + '). ' +
      'Scan kartu anggota terlebih dahulu.',
      'format_ok'
    );
    scheduleIdle(mySeq);
  }

  function handleErrorResponse(httpStatus, data, mySeq) {
    var msg;
    var errorCode = data && data.error_code;
    var errorMsg  = data && data.error;

    if (httpStatus === 409 && errorCode === 'SESSION_ACTIVE') {
      msg = 'Sesi anggota masih aktif. Tekan Batal untuk memulai sesi baru.';
    } else if (httpStatus === 409 && errorCode === 'DUPLICATE_COPY') {
      msg = 'Buku ini sudah ada di keranjang.';
    } else if (httpStatus === 422 && errorCode === 'MEMBER_INACTIVE') {
      msg = 'Anggota tidak aktif. Hubungi petugas perpustakaan.';
    } else if (httpStatus === 422 && errorCode === 'MEMBER_NOT_FOUND') {
      msg = 'Kartu anggota tidak dikenali. Coba lagi atau hubungi petugas.';
    } else if (httpStatus === 422 && errorCode === 'INVALID_TOKEN') {
      msg = 'Kartu anggota tidak valid atau sudah kedaluwarsa.';
    } else if (httpStatus === 422 && errorCode === 'TOKEN_REVOKED') {
      msg = 'QR kartu sudah tidak aktif. Minta QR baru dari petugas.';
    } else if (httpStatus === 404 && errorCode === 'COPY_NOT_FOUND') {
      msg = 'Buku tidak ditemukan dalam sistem.';
    } else if (httpStatus === 422 && errorCode === 'COPY_NOT_ACTIVE') {
      msg = 'Buku tidak dapat dipinjam (nonaktif/hilang).';
    } else if (httpStatus === 422 && errorCode === 'COPY_NOT_AVAILABLE') {
      msg = 'Buku sedang dipinjam oleh anggota lain.';
    } else if (httpStatus === 422 && errorCode === 'CART_FULL') {
      msg = 'Keranjang penuh (maksimum 10 buku). Selesaikan atau batalkan sesi.';
    } else if (httpStatus === 403 && errorCode === 'SESSION_REQUIRED') {
      msg = 'Scan kartu anggota terlebih dahulu.';
    } else if (httpStatus === 400) {
      msg = 'Format kode tidak valid: ' + (errorMsg || 'tidak dikenali') + '.';
    } else {
      msg = 'Respons tidak dikenali dari server (' + httpStatus + '). Coba lagi.';
    }

    var statusType = (httpStatus >= 500) ? 'server_error' : 'format_bad';
    setStatus(msg, statusType);
    scheduleIdle(mySeq);
  }

  /* ── Pengiriman kode ke server ──────────────────────────────────── */
  /**
   * Kirim kode ke endpoint yang sesuai.
   * Menerapkan debounce, lock pemrosesan, dan operation counter.
   * @param {string} code
   */
  function submitCode(code) {
    /* --- Validasi format lokal ------------------------------------ */
    if (!isValidFormat(code)) {
      setStatus('Format kode tidak dikenali. Coba lagi.', 'format_bad');
      scheduleIdle(opSeq);
      return;
    }

    var now = Date.now();

    /* --- Debounce: kode sama dalam DEBOUNCE_MS -------------------- */
    if (code === lastSent.code && (now - lastSent.timestamp) < DEBOUNCE_MS) {
      /* Duplikasi dalam interval debounce — abaikan sepenuhnya */
      return;
    }

    /* --- Lock: request sebelumnya masih berjalan ------------------ */
    if (processing) {
      /* QR berbeda pun diabaikan selama request aktif */
      return;
    }

    /* --- Mulai pemrosesan ----------------------------------------- */
    processing = true;
    lastSent = { code: code, timestamp: now };
    opSeq += 1;
    var mySeq = opSeq;

    var url = resolveUrl(code);
    var isMember = (url === SCAN_MEMBER_URL);
    var isCopy   = (url === SCAN_COPY_URL);

    setStatus('Memproses…', 'processing');

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ code: code })
    })
    .then(function (resp) {
      return resp.json().then(function (data) {
        return { httpStatus: resp.status, data: data };
      });
    })
    .then(function (result) {
      if (opSeq !== mySeq) { return; } /* operasi lebih baru sudah berjalan */

      if (result.httpStatus === 200) {
        var status = result.data && result.data.status;
        if (isMember && status === 'member_ok') {
          handleScanMemberOk(result.data, mySeq);
        } else if (isCopy && status === 'copy_ok') {
          handleScanCopyOk(result.data, mySeq);
        } else if (status === 'format_ok') {
          handleValidateOk(result.data, mySeq);
        } else if (status === 'cancelled') {
          resetToIdle();
        } else {
          setStatus('Respons tidak dikenali dari server. Coba lagi.', 'server_error');
          scheduleIdle(mySeq);
        }
      } else {
        handleErrorResponse(result.httpStatus, result.data, mySeq);
      }
    })
    .catch(function () {
      if (opSeq !== mySeq) { return; }
      setStatus('Tidak dapat menghubungi server. Periksa koneksi jaringan.', 'server_error');
      scheduleIdle(mySeq);
    })
    .finally(function () {
      /* Lock dilepas setelah respons maupun exception. */
      processing = false;
    });
  }

  /* ── Input manual ───────────────────────────────────────────────── */
  function showManualInput() {
    manualArea.hidden = false;
    manualBtn.hidden  = true;
    if (manualInput) { manualInput.focus(); }
  }

  function hideManualInput() {
    manualArea.hidden = true;
    manualBtn.hidden  = false;
    if (manualInput) { manualInput.value = ''; }
  }

  if (manualBtn) {
    manualBtn.addEventListener('click', function () { showManualInput(); });
  }

  if (manualSubmit) {
    manualSubmit.addEventListener('click', function () {
      var code = manualInput ? manualInput.value.trim() : '';
      if (!code) {
        setStatus('Kode tidak boleh kosong.', 'format_bad');
        return;
      }
      hideManualInput();
      submitCode(code);
    });
  }

  if (manualInput) {
    manualInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var code = manualInput.value.trim();
        if (!code) {
          setStatus('Kode tidak boleh kosong.', 'format_bad');
          return;
        }
        hideManualInput();
        submitCode(code);
      }
    });
  }

  /* ── Inisialisasi kamera ────────────────────────────────────────── */
  /**
   * Tampilkan pesan kamera gagal dan tawarkan input manual.
   * Hanya dipanggil untuk kegagalan inisialisasi / akses — bukan
   * untuk kegagalan menemukan QR dalam frame.
   */
  function handleCameraFailure(reason) {
    cameraActive = false;
    var msg = 'Kamera tidak dapat digunakan';
    if (reason) { msg += ': ' + reason; }
    msg += '. Gunakan input manual.';
    setStatus(msg, 'camera_error');
    if (manualBtn) { manualBtn.hidden = false; }
  }

  /**
   * Callback scanner: dipanggil setiap kali QR berhasil dibaca dari frame.
   * Bukan kegagalan kamera — hanya kegagalan menemukan QR di frame ini.
   */
  function onScanSuccess(decodedText) {
    submitCode(decodedText);
  }

  /**
   * Callback kegagalan pemindaian per-frame (tidak ada QR ditemukan).
   * Ini normal; tidak perlu ditampilkan ke pengguna.
   */
  function onScanFailure(/* errorMessage */) {
    /* Tidak ada tindakan — kegagalan per-frame adalah perilaku normal scanner. */
  }

  function initScanner() {
    /* Pastikan library tersedia */
    if (typeof Html5Qrcode === 'undefined') {
      handleCameraFailure('library Html5Qrcode tidak termuat');
      return;
    }

    Html5Qrcode.getCameras()
      .then(function (cameras) {
        if (!cameras || cameras.length === 0) {
          handleCameraFailure('tidak ada perangkat kamera yang terdeteksi');
          return;
        }

        var cameraId = cameras[0].id;
        var html5QrCode = new Html5Qrcode('kiosk-qr-reader');

        html5QrCode.start(
          cameraId,
          { fps: 10, qrbox: { width: 250, height: 250 } },
          onScanSuccess,
          onScanFailure
        )
        .then(function () {
          cameraActive = true;
          setStatus('Siapkan kartu atau buku, arahkan QR ke kamera.', 'idle');
        })
        .catch(function (err) {
          handleCameraFailure(
            typeof err === 'string' ? err : (err && err.message ? err.message : 'tidak dapat memulai kamera')
          );
        });
      })
      .catch(function (err) {
        handleCameraFailure(
          typeof err === 'string' ? err : (err && err.message ? err.message : 'izin kamera ditolak atau tidak tersedia')
        );
      });
  }

  /* ── Mulai ─────────────────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScanner);
  } else {
    initScanner();
  }

})();
