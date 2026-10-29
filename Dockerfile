# ==============================================================================
# DOCKERFILE - SISTEM PERPUSTAKAAN DIGITAL SEKOLAH
# ==============================================================================
# Base image Python 3.11 Slim Debian Bookworm untuk kestabilan, kompatibilitas
# paket komputasi (pandas, numpy, openpyxl), dan ukuran image yang ringkas.
FROM python:3.11-slim

# Pasang paket sistem minimum yang dibutuhkan SQLite dan health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Salin requirements dan install dependensi Python dengan caching layer efisien
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh kode sumber aplikasi
COPY . .

# Buat folder penyimpanan persisten untuk database dan cover buku yang diunggah
RUN mkdir -p /app/data /app/static/covers

# Environment variables default runtime container
ENV PYTHONUNBUFFERED=1 \
    PORT=5000 \
    DATABASE_NAME=/app/data/perpustakaan.db

EXPOSE 5000

# Menjalankan aplikasi dengan Gunicorn WSGI Server:
# - workers 1 + threads 8: Menghindari race condition multi-proses SQLite sambil melayani multi-user konkruen.
# - timeout 60: Memberikan batas waktu wajar untuk proses ekspor laporan Excel dan pemanggilan Gemini API.
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 60 app:app

