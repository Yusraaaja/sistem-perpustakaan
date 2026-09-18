@echo off
title [PORTABLE-DEBUG] Sistem Perpustakaan Digital - Auto Setup & Run
cls

:: 1. PINDAH KE DIREKTORI DI MANA FILE BAT INI DIKLIK
cd /d "%~dp0"

echo ===================================================================
echo     AUTO-INITIALIZATION SYSTEM - DIGITAL LIBRARY BY AGAM
echo ===================================================================
echo.

:: 2. CEK APAKAH PYTHON SUDAH TERINSTAL
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python BELUM terinstal di komputer ini.
    echo [!] Memulai instalasi Python otomatis via Winget...
    echo [!] Mohon tunggu, proses ini memerlukan koneksi internet...
    
    winget install --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements
    
    if %errorlevel% neq 0 (
        echo.
        echo [EROR] Gagal menginstal Python otomatis via Winget.
        echo [!] Pastikan komputer terkoneksi internet atau instal Python manual.
        goto CRASH_GUARD
    )
    
    echo [/] Python sukses terinstal!
    echo [!] Memperbarui Environment PATH sistem secara sementara...
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\;%LOCALAPPDATA%\Programs\Python\Python311\Scripts\;%PATH%"
) else (
    echo [/] Python terdeteksi aman pada sistem.
)

:: 3. VALIDASI & INTEGRITAS VIRTUAL ENVIRONMENT (ANTI-CRASH GUARD)
echo [!] Memeriksa integritas Virtual Environment...
if not exist venv (
    echo [!] Folder venv tidak ditemukan. Membuat Virtual Environment baru...
    python -m venv venv
    goto RUN_WITH_VENV
)

:: Proteksi jika folder venv rusak atau bawaan dari OS lain
if not exist venv\Scripts\activate.bat (
    echo [PERINGATAN] Folder venv terdeteksi rusak/bukan milik Windows!
    echo [!] Melompati venv dan beralih menggunakan instalasi Python Global...
    goto RUN_WITH_GLOBAL
)

:RUN_WITH_VENV
echo [!] Mengaktifkan Virtual Environment...
:: Gunakan CMD /C agar jika script aktivasi bawaan venv crash, file .bat ini tidak ikut mati
cmd /c "venv\Scripts\activate.bat && pip install flask pandas openpyxl --quiet"
if %errorlevel% neq 0 (
    echo [PERINGATAN] Gagal mengaktifkan venv secara bersih.
    goto RUN_WITH_GLOBAL
)

:: Jalankan browser dan aplikasi via lingkungan venv
echo [!] Menyiapkan pemicu otomatisasi Google Chrome / Edge...
start "" http://127.0.0.1:5000
echo [SUKSES] Menjalankan server perpustakaan via VENV...
venv\Scripts\python.exe app.py
goto END_SCRIPT

:RUN_WITH_GLOBAL
echo [!] Memeriksa dependensi pada Python Global...
pip install flask pandas openpyxl --quiet
echo [!] Menyiapkan pemicu otomatisasi Google Chrome / Edge...
start "" http://127.0.0.1:5000
echo [SUKSES] Menjalankan server perpustakaan via PYTHON GLOBAL...
python app.py
goto END_SCRIPT

:CRASH_GUARD
echo.
echo ===================================================================
echo [SISTEM BERHENTI] Terjadi kesalahan kritis sebelum program berjalan.
echo ===================================================================
echo Silakan periksa pesan eror di atas.

:END_SCRIPT
echo.
echo [INFO] Sesi terminal ditahan agar tidak menutup otomatis.
pause