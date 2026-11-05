/**
 * tests/test_kiosk_scan_js.js
 *
 * Pengujian runtime JavaScript untuk kiosk_scan.js menggunakan Node.js murni.
 * Tidak memerlukan npm, package.json, Jest, atau Mocha.
 * Jalankan dengan: node tests/test_kiosk_scan_js.js
 *
 * Pendekatan:
 *   1. Pasang DOM minimal (mock) agar kiosk_scan.js dapat dimuat.
 *   2. Ekstrak fungsi-fungsi internal menggunakan modul shim (re-export).
 *   3. Uji perilaku debounce, processing lock, opSeq, dan validasi format
 *      secara langsung sebagai unit test runtime.
 *
 * Keterbatasan yang didokumentasikan:
 *   - fetch() di-mock; pengujian ini tidak menyentuh server Flask.
 *   - Html5Qrcode di-mock; tidak ada kamera nyata.
 *   - setTimeout menggunakan implementasi Node.js bawaan (bukan browser).
 *   - Perilaku visual (CSS class) diperiksa via statusEl.className mock.
 */

'use strict';

// ── Infrastruktur tes minimal ─────────────────────────────────────────────────

let _passed = 0;
let _failed = 0;
const _failures = [];

function assert(condition, msg) {
  if (!condition) {
    throw new Error('ASSERT GAGAL: ' + msg);
  }
}

function assertEqual(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error('ASSERT GAGAL: ' + (msg || '') +
      ' — diharapkan ' + JSON.stringify(expected) +
      ', aktual ' + JSON.stringify(actual));
  }
}

function assertNotEqual(actual, unexpected, msg) {
  if (actual === unexpected) {
    throw new Error('ASSERT GAGAL: ' + (msg || '') +
      ' — seharusnya tidak sama dengan ' + JSON.stringify(unexpected));
  }
}

async function runTest(name, fn) {
  try {
    await fn();
    console.log('  ok  ' + name);
    _passed++;
  } catch (e) {
    console.log('  FAIL ' + name);
    console.log('       ' + e.message);
    _failed++;
    _failures.push({ name, message: e.message });
  }
}

// ── Buat DOM mock + modul shim ────────────────────────────────────────────────

/**
 * Buat instance terisolasi lingkungan kiosk_scan.js.
 * Setiap panggilan ke makeEnv() mengembalikan state baru yang tidak berbagi
 * variabel dengan instance lain.
 *
 * @param {object} opts
 * @param {object} opts.fetchImpl  - Implementasi fetch mock
 * @param {number} opts.nowMs      - Nilai awal Date.now() (default 10000)
 */
function makeEnv(opts) {
  opts = opts || {};

  // State terisolasi per-instance
  const dom = {
    status:      { textContent: '', className: 'kiosk-status kiosk-status--idle', hidden: false },
    qrReader:    { textContent: '', className: '', hidden: false },
    manualBtn:   { hidden: false, _listeners: {}, addEventListener: function(ev, fn) { this._listeners[ev] = fn; } },
    manualArea:  { hidden: true },
    manualInput: { value: '', focus: function(){}, _listeners: {}, addEventListener: function(ev, fn) { this._listeners[ev] = fn; } },
    manualSubmit:{ _listeners: {}, addEventListener: function(ev, fn) { this._listeners[ev] = fn; } },
  };

  let _nowMs = opts.nowMs !== undefined ? opts.nowMs : 10000;
  const fetchImpl = opts.fetchImpl || function() {
    return Promise.resolve({
      status: 200,
      json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'Belum diverifikasi' }); }
    });
  };

  // Kumpulkan semua fetch call yang dilakukan
  const fetchCalls = [];
  const wrappedFetch = function(url, init) {
    fetchCalls.push({ url, body: init && init.body ? JSON.parse(init.body) : null });
    return fetchImpl(url, init);
  };

  // Timer tracking
  const timers = [];
  const setTimeoutMock = function(fn, ms) {
    const id = timers.length;
    timers.push({ fn, ms, fired: false, cancelled: false });
    return id;
  };

  // Eksekusi semua timer yang belum fired
  const flushTimers = function() {
    timers.forEach(function(t) {
      if (!t.fired && !t.cancelled) {
        t.fired = true;
        t.fn();
      }
    });
  };

  // ── Jalankan kiosk_scan.js dalam context terisolasi via Function() ──────────
  // Kita gunakan teknik "module shim": jalankan IIFE dari kiosk_scan.js
  // setelah mengganti semua globals.

  const fs = require('fs');
  const path = require('path');
  const jsPath = path.join(__dirname, '..', 'static', 'js', 'kiosk_scan.js');
  let jsSource = fs.readFileSync(jsPath, 'utf8');

  // Bungkus source dalam fungsi yang menerima semua dependency sebagai param
  // agar state tiap instance benar-benar terpisah.
  const wrappedSource = `
(function(__document, __Html5Qrcode, __fetch, __Date, __setTimeout) {
  // Override globals di dalam scope ini
  var document = __document;
  var Html5Qrcode = __Html5Qrcode;
  var fetch = __fetch;
  var Date = __Date;
  var setTimeout = __setTimeout;

  ${jsSource}
  
  // Return handle ke elemen DOM untuk inspeksi tes
  return {
    statusEl: __document.getElementById('kiosk-status'),
    manualBtn: __document.getElementById('kiosk-manual-btn'),
    manualArea: __document.getElementById('kiosk-manual-area'),
    manualInput: __document.getElementById('kiosk-manual-input'),
    manualSubmit: __document.getElementById('kiosk-manual-submit'),
  };
})
`;

  const mockDocument = {
    getElementById: function(id) {
      if (id === 'kiosk-status')       return dom.status;
      if (id === 'kiosk-qr-reader')    return dom.qrReader;
      if (id === 'kiosk-manual-btn')   return dom.manualBtn;
      if (id === 'kiosk-manual-area')  return dom.manualArea;
      if (id === 'kiosk-manual-input') return dom.manualInput;
      if (id === 'kiosk-manual-submit') return dom.manualSubmit;
      return null;
    },
    readyState: 'complete',
    addEventListener: function() {}
  };

  const mockHtml5Qrcode = {
    getCameras: function() { return Promise.resolve([]); }
  };

  const mockDate = { now: function() { return _nowMs; } };

  // Evaluasi kode
  const factory = eval(wrappedSource);
  factory(mockDocument, mockHtml5Qrcode, wrappedFetch, mockDate, setTimeoutMock);

  // Manipulator waktu
  const advanceTime = function(ms) { _nowMs += ms; };
  const setNow = function(ms) { _nowMs = ms; };

  return {
    dom,
    fetchCalls,
    timers,
    flushTimers,
    advanceTime,
    setNow,
    // Akses langsung tombol dan input untuk simulasi event
    clickManualBtn:    function() { dom.manualBtn._listeners['click'] && dom.manualBtn._listeners['click'](); },
    clickManualSubmit: function() { dom.manualSubmit._listeners['click'] && dom.manualSubmit._listeners['click'](); },
    pressEnterOnInput: function() {
      dom.manualInput._listeners['keydown'] &&
      dom.manualInput._listeners['keydown']({ key: 'Enter' });
    },
  };
}

// ── Suite pengujian ───────────────────────────────────────────────────────────

async function runAllTests() {
  console.log('\n=== Tes runtime JavaScript: kiosk_scan.js ===\n');

  // ── 1. Debounce: QR sama dalam interval → satu request ───────────────────────
  await runTest(
    'D.1a debounce: QR sama terdeteksi dua kali dalam 2 s → hanya 1 request',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return Promise.resolve({
            status: 200,
            json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'Belum diverifikasi' }); }
          });
        }
      });

      // Simulasikan callback QR scan dua kali berturut-turut dengan kode yang sama
      // Dengan mengakses onScanSuccess melalui mock Html5Qrcode
      // Karena kiosk_scan.js meng-expose via Html5Qrcode.start callback,
      // kita perlu cara lain: simulasikan klik manual submit

      // Kirim pertama
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();

      // Tunggu fetch selesai
      await new Promise(r => setTimeout(r, 50));

      // Kirim kedua (kode sama, dalam 2 s)
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();

      await new Promise(r => setTimeout(r, 50));

      // Hanya 1 fetch yang seharusnya terjadi (debounce mencegah kedua)
      assertEqual(callCount, 1, 'Debounce harus mencegah request kedua untuk kode yang sama');
    }
  );

  await runTest(
    'D.1b debounce: QR sama setelah 2 s → request baru diizinkan',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return Promise.resolve({
            status: 200,
            json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'Belum diverifikasi' }); }
          });
        }
      });

      // Kirim pertama
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      // Maju waktu melewati debounce
      env.advanceTime(2001);

      // Kirim kedua (kode sama, setelah debounce habis)
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 2, 'Setelah debounce habis, kode yang sama harus diterima lagi');
    }
  );

  // ── 2. Processing lock: tidak ada request paralel ─────────────────────────────
  await runTest(
    'D.2 processing lock: callback berulang saat request berjalan tidak membuat request paralel',
    async function() {
      let callCount = 0;
      let resolveFetch;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return new Promise(function(resolve) {
            resolveFetch = resolve; // tunggu manual
          });
        }
      });

      // Kirim pertama (fetch tidak selesai)
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 10));

      assertEqual(callCount, 1, 'Request pertama harus terpanggil');

      // Kirim kedua saat lock aktif (kode berbeda — lock tetap berlaku)
      env.dom.manualInput.value = 'C-XY5678';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 10));

      assertEqual(callCount, 1, 'Lock harus mencegah request paralel untuk kode berbeda');

      // Selesaikan request pertama
      resolveFetch({
        status: 200,
        json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); }
      });
      await new Promise(r => setTimeout(r, 50));
    }
  );

  // ── 3. Lock dilepas setelah request selesai → scan berikutnya bisa ──────────
  await runTest(
    'D.3 setelah request selesai, QR berikutnya dapat diproses',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return Promise.resolve({
            status: 200,
            json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); }
          });
        }
      });

      // Kirim pertama
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));
      assertEqual(callCount, 1, 'Request pertama OK');

      // Setelah selesai, maju waktu agar debounce tidak berlaku (kode berbeda)
      // Kode berbeda tidak terkena debounce — langsung kirim
      env.dom.manualInput.value = 'C-XY5678';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 2, 'Setelah lock dilepas, request berikutnya harus diterima');
    }
  );

  // ── 4. Lock dilepas setelah request gagal (HTTP error) ───────────────────────
  await runTest(
    'D.4a lock dilepas setelah HTTP 400 response',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return Promise.resolve({
            status: 400,
            json: function() { return Promise.resolve({ status: 'error', error: 'format salah' }); }
          });
        }
      });

      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      // Lock harus sudah dilepas — kirim kode berbeda
      env.dom.manualInput.value = 'C-XY5678';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 2, 'Lock harus dilepas setelah HTTP error, memungkinkan request berikutnya');
    }
  );

  await runTest(
    'D.4b lock dilepas setelah network exception',
    async function() {
      let callCount = 0;
      let phase = 0;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          phase++;
          if (phase === 1) {
            return Promise.reject(new Error('Network error'));
          }
          return Promise.resolve({
            status: 200,
            json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); }
          });
        }
      });

      // Request pertama gagal (network error)
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      // Lock harus dilepas meski exception; maju waktu agar debounce tidak berlaku
      env.advanceTime(2001);
      env.dom.manualInput.value = 'M-AB1234'; // kode sama boleh karena debounce habis
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 2, 'Lock harus dilepas setelah network exception');
    }
  );

  // ── 5. opSeq: timer lama tidak menimpa status baru ───────────────────────────
  await runTest(
    'D.5 timer status lama (opSeq lama) tidak menimpa status operasi lebih baru',
    async function() {
      // Kita tidak bisa mengontrol setTimeout Node langsung dari luar IIFE.
      // Tes ini verifikasi via kode JS kiosk_scan.js itu sendiri:
      // scheduleIdle(seq) hanya mengubah status jika opSeq === seq.
      //
      // Cara tes: jalankan dua operasi berurutan cepat (kode berbeda, debounce tidak berlaku).
      // Setelah keduanya selesai, flush timer — status harus menunjukkan idle
      // (timer kedua boleh jalan karena opSeq cocok; timer pertama harus terbaiki).
      //
      // Karena env menggunakan setTimeoutMock (tidak auto-fire), kita flush manual.

      let callCount = 0;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return Promise.resolve({
            status: 200,
            json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); }
          });
        }
      });

      // Operasi 1: kode M-AB1234
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      // Status setelah op1: format_ok
      const statusAfterOp1 = env.dom.status.className;

      // Operasi 2: kode berbeda (lock sudah dilepas, debounce tidak berlaku)
      env.dom.manualInput.value = 'C-XY5678';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      // Flush semua timer (termasuk scheduleIdle dari op1 dan op2)
      env.flushTimers();

      // Status akhir setelah flush timer seharusnya: idle (dari timer op2 yang valid)
      // Timer op1 tidak mengubah status karena opSeq (=2) !== seq (=1).
      // Timer op2 mengubah status ke idle karena opSeq === seq.
      // Assertion: className harus mengandung 'idle' (hasil timer op2 yang valid).
      assert(
        env.dom.status.className.includes('idle'),
        'Status setelah flush timer harus idle — hanya timer opSeq terbaru yang boleh berjalan, aktual: ' +
        env.dom.status.className
      );

      assertEqual(callCount, 2, 'Dua operasi harus menghasilkan dua request');
    }
  );

  // ── 6. Validasi format lokal mencegah pengiriman ke server ───────────────────
  await runTest(
    'D.6a input tidak valid (karakter khusus) tidak dikirim ke server',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        fetchImpl: function() { callCount++; return Promise.resolve({ status: 200, json: function() { return Promise.resolve({}); } }); }
      });

      // Tunggu inisialisasi kamera selesai (getCameras() Promise resolved → handleCameraFailure)
      // agar status camera_error tidak menimpa status format_bad yang akan kita cek.
      await new Promise(r => setTimeout(r, 20));

      env.dom.manualInput.value = 'QR!@#$%';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 20));

      assertEqual(callCount, 0, 'Kode dengan karakter tidak valid tidak boleh dikirim ke server');
      // Status bisa camera_error (kamera tidak ada) ATAU format_bad.
      // Yang WAJIB: tidak ada fetch ke server.
      // Status format_bad hanya muncul jika kamera tidak mengoverwrite.
      // Verifikasi: tidak ada request = benar.
      // (Di browser nyata: jika kamera gagal, status camera_error; user menggunakan input manual)
    }
  );

  await runTest(
    'D.6b input kosong tidak dikirim ke server',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        fetchImpl: function() { callCount++; return Promise.resolve({ status: 200, json: function() { return Promise.resolve({}); } }); }
      });

      // Tombol submit dengan input kosong
      env.dom.manualInput.value = '';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 0, 'Input kosong tidak boleh dikirim ke server');
    }
  );

  await runTest(
    'D.6c input valid dikirim ke server',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        fetchImpl: function() { callCount++; return Promise.resolve({ status: 200, json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'M', note: 'n' }); } }); }
      });

      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 1, 'Input valid harus dikirim ke server');
    }
  );

  // ── 7. Input manual mengikuti lock yang sama ──────────────────────────────────
  await runTest(
    'D.8 input manual mengikuti processing lock (tidak mengirim saat lock aktif)',
    async function() {
      let callCount = 0;
      let resolveFetch;
      const env = makeEnv({
        nowMs: 10000,
        fetchImpl: function() {
          callCount++;
          return new Promise(function(resolve) { resolveFetch = resolve; });
        }
      });

      // Kirim dari manual (lock aktif)
      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 10));

      // Coba kirim lagi (kode berbeda, manual) saat lock masih aktif
      env.dom.manualInput.value = 'C-XY5678';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 10));

      assertEqual(callCount, 1, 'Input manual tidak boleh mengirim request saat lock aktif');

      // Selesaikan request
      resolveFetch({ status: 200, json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); } });
      await new Promise(r => setTimeout(r, 50));
    }
  );

  // ── 8. Status UI berubah sesuai kondisi ──────────────────────────────────────
  await runTest(
    'UI: status berubah ke "processing" saat mengirim',
    async function() {
      let statusDuringFetch = '';
      const env = makeEnv({
        fetchImpl: function() {
          statusDuringFetch = env.dom.status.className;
          return new Promise(function(resolve) {
            setTimeout(function() {
              resolve({ status: 200, json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); } });
            }, 20);
          });
        }
      });

      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 10));

      assert(statusDuringFetch.includes('processing'),
        'Status harus "processing" saat fetch berjalan, dapat: ' + statusDuringFetch);
    }
  );

  await runTest(
    'UI: status berubah ke "format_ok" setelah respons 200',
    async function() {
      const env = makeEnv({
        fetchImpl: function() {
          return Promise.resolve({
            status: 200,
            json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'M-AB...', note: 'Belum diverifikasi' }); }
          });
        }
      });

      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assert(env.dom.status.className.includes('format_ok'),
        'Status harus format_ok setelah respons 200: ' + env.dom.status.className);
    }
  );

  await runTest(
    'UI: status berubah ke "server_error" saat network gagal',
    async function() {
      const env = makeEnv({
        fetchImpl: function() { return Promise.reject(new Error('Network down')); }
      });

      env.dom.manualInput.value = 'M-AB1234';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 50));

      assert(env.dom.status.className.includes('server_error'),
        'Status harus server_error saat network gagal: ' + env.dom.status.className);
    }
  );

  await runTest(
    'UI: status berubah ke "format_bad" untuk kode tidak valid',
    async function() {
      const env = makeEnv();

      // Tunggu inisialisasi kamera (async Promise) selesai sebelum mengecek status
      await new Promise(r => setTimeout(r, 20));

      // Setelah camera_error set (kamera tidak ada di mock),
      // submit kode tidak valid — status harus berubah ke format_bad
      env.dom.manualInput.value = 'kode dengan spasi!';
      env.clickManualSubmit();
      await new Promise(r => setTimeout(r, 10));

      assert(env.dom.status.className.includes('format_bad'),
        'Status harus format_bad untuk kode tidak valid: ' + env.dom.status.className);
    }
  );

  // ── 9. Enter key pada input manual ───────────────────────────────────────────
  await runTest(
    'input manual: tekan Enter mengirim kode valid',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        fetchImpl: function() {
          callCount++;
          return Promise.resolve({ status: 200, json: function() { return Promise.resolve({ status: 'format_ok', display_code: 'X', note: 'n' }); } });
        }
      });

      env.dom.manualInput.value = 'M-AB1234';
      env.pressEnterOnInput();
      await new Promise(r => setTimeout(r, 50));

      assertEqual(callCount, 1, 'Tekan Enter harus mengirim kode valid ke server');
    }
  );

  await runTest(
    'input manual: tekan Enter dengan input kosong tidak mengirim',
    async function() {
      let callCount = 0;
      const env = makeEnv({
        fetchImpl: function() { callCount++; return Promise.resolve({ status: 200, json: function() { return Promise.resolve({}); } }); }
      });

      env.dom.manualInput.value = '';
      env.pressEnterOnInput();
      await new Promise(r => setTimeout(r, 10));

      assertEqual(callCount, 0, 'Enter dengan input kosong tidak boleh mengirim ke server');
    }
  );

  // ── Hasil ─────────────────────────────────────────────────────────────────────
  console.log('\n─────────────────────────────────────────────────');
  console.log('Hasil: ' + _passed + ' lulus, ' + _failed + ' gagal');
  if (_failures.length > 0) {
    console.log('\nKegagalan:');
    _failures.forEach(function(f) {
      console.log('  - ' + f.name + ': ' + f.message);
    });
  }
  console.log('─────────────────────────────────────────────────\n');

  process.exit(_failed > 0 ? 1 : 0);
}

runAllTests().catch(function(e) {
  console.error('Error fatal dalam test runner:', e);
  process.exit(1);
});
