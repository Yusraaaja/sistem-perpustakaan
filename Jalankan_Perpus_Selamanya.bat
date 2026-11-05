@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sistem Perpustakaan Digital
cls

cd /d "%~dp0"

echo ===================================================================
echo     SISTEM PERPUSTAKAAN DIGITAL - MULAI OTOMATIS
echo ===================================================================
echo.
echo Folder aplikasi: %CD%
echo Jangan tutup jendela ini selama sistem digunakan.
echo.

if not exist "app.py" (
    echo [ERROR] File app.py tidak ditemukan di folder ini.
    echo Pastikan pintasan mengarah ke folder aplikasi yang benar.
    goto CRASH_GUARD
)

if not exist "requirements.txt" (
    echo [ERROR] File requirements.txt tidak ditemukan.
    echo Instalasi pustaka tidak dapat dilanjutkan.
    goto CRASH_GUARD
)

if not exist ".env" (
    echo [PERINGATAN] File pengaturan .env tidak ditemukan.
    echo Fitur AI Book Assistant mungkin tidak aktif.
    echo Sistem perpustakaan tetap dapat digunakan tanpa AI.
    echo.
)

echo [1/5] Memeriksa Python...
set "PYEXE="
call :FIND_PYTHON

if not defined PYEXE (
    echo Python belum tersedia. Memasang Python 3.11 melalui winget...
    echo Proses ini memerlukan internet dan dapat memakan beberapa menit.
    echo.
    call :INSTALL_PYTHON
    call :INJECT_PYTHON_PATH
    set "PYEXE="
    call :FIND_PYTHON
)

if not defined PYEXE (
    echo [ERROR] Python tidak ditemukan setelah pemeriksaan dan instalasi.
    echo Instal Python 3.11 secara manual, lalu jalankan file ini lagi.
    echo Jangan mengandalkan jendela lama: buka file ini sekali lagi setelah instalasi.
    goto CRASH_GUARD
)

echo Python siap digunakan.
"%PYEXE%" --version
if errorlevel 1 (
    echo [ERROR] Python terdeteksi tetapi tidak dapat dijalankan.
    goto CRASH_GUARD
)
echo.

echo [2/5] Menyiapkan lingkungan virtual ^(venv^)...
if not exist "venv\Scripts\python.exe" (
    echo Lingkungan virtual belum siap. Membuat venv...
    "%PYEXE%" -m venv venv
    if errorlevel 1 (
        echo [ERROR] Gagal membuat lingkungan virtual.
        echo Sistem tidak akan memakai Python global sebagai cadangan.
        goto CRASH_GUARD
    )
)

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv\Scripts\python.exe tidak ditemukan.
    echo Lingkungan virtual gagal disiapkan. Startup dihentikan.
    echo Sistem tidak akan memakai Python global sebagai cadangan.
    goto CRASH_GUARD
)

echo Lingkungan virtual siap.
echo.

echo [3/5] Memasang pustaka dari requirements.txt...
"venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Gagal memasang pustaka aplikasi.
    echo Periksa koneksi internet, lalu jalankan file ini lagi.
    echo Sistem tidak dijalankan karena pustaka belum lengkap.
    goto CRASH_GUARD
)
echo Pustaka aplikasi siap.
echo.

echo [4/5] Memeriksa apakah sistem sudah berjalan...
call :PORT_LISTENING
if not errorlevel 1 (
    echo [INFO] Port 5000 sudah digunakan.
    echo Sistem mungkin sudah berjalan. Server baru tidak akan dimulai.
    echo Membuka halaman perpustakaan di browser...
    start "" "http://127.0.0.1:5000"
    echo.
    echo Jika halaman tidak muncul, pastikan aplikasi yang memakai port 5000
    echo adalah Sistem Perpustakaan Digital, lalu buka:
    echo   http://127.0.0.1:5000
    echo.
    echo Jendela ini dapat ditutup.
    pause
    exit /b 0
)
echo Port 5000 masih kosong. Server akan dimulai.
echo.

echo [5/5] Menjalankan server...
echo Mohon tunggu hingga server siap sebelum browser dibuka.
start /b "" "venv\Scripts\python.exe" app.py

set "WAITED=0"
:WAIT_SERVER
call :PORT_LISTENING
if not errorlevel 1 goto SERVER_READY
set /a WAITED+=1
if !WAITED! GEQ 60 goto SERVER_TIMEOUT
timeout /t 1 /nobreak >nul
goto WAIT_SERVER

:SERVER_READY
echo.
echo [SUKSES] Server siap di http://127.0.0.1:5000
echo Membuka browser...
start "" "http://127.0.0.1:5000"
echo.
echo ------------------------------------------------------------------
echo Sistem sedang berjalan.
echo Jangan tutup jendela ini selama petugas memakai aplikasi.
echo Tutup jendela ini hanya jika ingin mematikan sistem.
echo ------------------------------------------------------------------
echo.

:KEEP_RUNNING
timeout /t 3 /nobreak >nul
call :PORT_LISTENING
if not errorlevel 1 goto KEEP_RUNNING

echo.
echo [INFO] Server sudah berhenti.
echo Jika ini tidak disengaja, jalankan file ini lagi.
pause
exit /b 0

:SERVER_TIMEOUT
echo.
echo [ERROR] Server tidak siap di port 5000 dalam waktu yang wajar.
echo Periksa pesan di atas. Database tidak diubah oleh launcher ini.
goto CRASH_GUARD

:INSTALL_PYTHON
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Perintah winget tidak tersedia di komputer ini.
    echo Instal Python 3.11 secara manual, lalu jalankan file ini lagi.
    goto CRASH_GUARD
)
winget install --id Python.Python.3.11 --scope user --silent --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo [PERINGATAN] winget selesai dengan status tidak sukses.
    echo Launcher akan memeriksa lagi apakah Python sudah dapat dipakai.
)
exit /b 0

:INJECT_PYTHON_PATH
rem PATH jendela ini tidak otomatis terbarui setelah instalasi.
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%PATH%"
exit /b 0

:FIND_PYTHON
set "PYEXE="

for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
    if exist "%%I" (
        echo %%I | findstr /I /C:"WindowsApps" >nul
        if errorlevel 1 (
            set "PYEXE=%%I"
            exit /b 0
        )
    )
)

for /f "delims=" %%I in ('where python 2^>nul') do (
    echo %%I | findstr /I /C:"WindowsApps" >nul
    if errorlevel 1 (
        if exist "%%I" (
            "%%I" -c "import sys" >nul 2>&1
            if not errorlevel 1 (
                set "PYEXE=%%I"
                exit /b 0
            )
        )
    )
)

call :TRY_PYTHON "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" && exit /b 0
call :TRY_PYTHON "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" && exit /b 0
call :TRY_PYTHON "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" && exit /b 0
call :TRY_PYTHON "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" && exit /b 0
call :TRY_PYTHON "%ProgramFiles%\Python311\python.exe" && exit /b 0
call :TRY_PYTHON "%ProgramFiles%\Python312\python.exe" && exit /b 0
call :TRY_PYTHON "C:\Python311\python.exe" && exit /b 0
call :TRY_PYTHON "C:\Python314\python.exe" && exit /b 0
exit /b 1

:TRY_PYTHON
if exist "%~1" (
    "%~1" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PYEXE=%~1"
        exit /b 0
    )
)
exit /b 1

:PORT_LISTENING
netstat -ano 2>nul | findstr /C:":5000 " | findstr /I /C:"LISTENING" >nul
exit /b %errorlevel%

:CRASH_GUARD
echo.
echo ===================================================================
echo SISTEM BERHENTI - terjadi kesalahan sebelum aplikasi siap.
echo Jendela ini dibiarkan terbuka agar pesan di atas dapat dibaca.
echo Database perpustakaan tidak dihapus dan tidak dibuat ulang oleh launcher.
echo ===================================================================
echo.
pause
endlocal
exit 1
