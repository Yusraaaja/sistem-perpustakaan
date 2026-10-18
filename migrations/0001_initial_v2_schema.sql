-- ==============================================================================
-- Migrasi Skema Database Perpustakaan Digital v2 (Fase 1B)
-- Memenuhi Requirement: LIB-COPY-001, LIB-COPY-002, LIB-MEMBER-001, LIB-LOAN-002,
-- R1 - R12, DEC-004, DEC-013, DEC-020, DEC-023, DEC-024.
-- ==============================================================================

-- 0. Tabel Pelacak Versi Skema
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- 1. Kategori Anggota (Seed Awal)
CREATE TABLE IF NOT EXISTS member_categories (
    id TEXT PRIMARY KEY,
    jenis TEXT NOT NULL UNIQUE,
    keterangan TEXT
);

-- 2. Anggota Perpustakaan (Tanpa kelas dan tanpa telepon)
CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,                       -- Format M-xxxx (Base32 Crockford)
    nama TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'nonaktif')),
    category_id TEXT NOT NULL REFERENCES member_categories(id),
    qr_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,                  -- ISO8601 UTC seragam
    updated_at TEXT NOT NULL                   -- ISO8601 UTC seragam
);

-- 3. Judul Katalog (Dipetakan dari buku, memiliki tracking legacy_buku_id unik)
CREATE TABLE IF NOT EXISTS catalog_titles (
    id TEXT PRIMARY KEY,                       -- Format T-xxxx (Base32 Crockford)
    judul TEXT NOT NULL,
    subjudul TEXT,
    penulis TEXT,
    penerbit TEXT,
    tahun TEXT,
    isbn TEXT,
    kategori TEXT,
    ddc TEXT,
    sinopsis TEXT,
    cover_path TEXT,
    harga_buku INTEGER DEFAULT 0,
    metadata_json TEXT,
    legacy_buku_id INTEGER UNIQUE,             -- Idempotensi migrasi (R5)
    created_at TEXT NOT NULL,                  -- ISO8601 UTC seragam
    updated_at TEXT NOT NULL                   -- ISO8601 UTC seragam
);

-- 4. Eksemplar Fisik Buku (Tanpa kondisi, barcode_id, atau no_induk per R8 & R9)
CREATE TABLE IF NOT EXISTS copies (
    id TEXT PRIMARY KEY,                       -- Format C-xxxx (Base32 Crockford)
    title_id TEXT NOT NULL REFERENCES catalog_titles(id),
    call_number TEXT,
    status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'nonaktif', 'hilang', 'rusak', 'dalam_penanganan')),
    lokasi_rak TEXT,
    tanggal_masuk TEXT,
    sumber TEXT,
    harga INTEGER DEFAULT 0,
    created_at TEXT NOT NULL                   -- ISO8601 UTC seragam
);

-- 5. Transaksi Peminjaman (Header, tanpa kelas/jurusan per R4, tracking legacy_peminjaman_id)
CREATE TABLE IF NOT EXISTS loans (
    id TEXT PRIMARY KEY,                       -- Format L-xxxx (Base32 Crockford)
    member_id TEXT REFERENCES members(id),     -- NULL untuk transaksi lama (R4 & catatan data)
    legacy_nama_peminjam TEXT,                 -- Teks asli peminjam lama
    created_at TEXT NOT NULL,                  -- ISO8601 UTC seragam
    idempotency_key TEXT UNIQUE,
    legacy_peminjaman_id INTEGER UNIQUE        -- Idempotensi migrasi (R5)
);

-- 6. Detail Item Peminjaman (Tanpa denda atau replacement_status per R4)
CREATE TABLE IF NOT EXISTS loan_items (
    id TEXT PRIMARY KEY,                       -- Format LI-xxxxxxxx (Base32 Crockford)
    loan_id TEXT NOT NULL REFERENCES loans(id),
    copy_id TEXT NOT NULL REFERENCES copies(id),
    borrowed_at TEXT NOT NULL,                 -- ISO8601 UTC seragam
    due_at TEXT NOT NULL,                      -- ISO8601 UTC seragam
    extended_at TEXT,                          -- ISO8601 UTC seragam
    extension_count INTEGER NOT NULL DEFAULT 0,
    returned_at TEXT,                          -- ISO8601 UTC seragam (NULL = sedang dipinjam)
    return_condition TEXT CHECK (return_condition IS NULL OR return_condition IN ('baik', 'rusak', 'lainnya', 'hilang')),
    returned_via TEXT CHECK (returned_via IS NULL OR returned_via IN ('jalur_a', 'jalur_b', 'manual', 'penyelesaian', 'legacy')),
    notes TEXT
);

-- CONSTRAINT KRITIS (LIB-LOAN-002 & R2): Satu copy hanya boleh memiliki 1 peminjaman aktif
CREATE UNIQUE INDEX IF NOT EXISTS idx_loan_items_active_copy 
ON loan_items(copy_id) 
WHERE returned_at IS NULL;

-- 7. Data Historis Denda & Penggantian Lama (Tabel Baca-Saja, R4, DEC-024)
CREATE TABLE IF NOT EXISTS legacy_loan_item_extra (
    loan_item_id TEXT PRIMARY KEY REFERENCES loan_items(id),
    fine_overdue INTEGER DEFAULT 0,
    fine_condition INTEGER DEFAULT 0,
    status_penggantian TEXT,
    catatan_penggantian TEXT
);

-- 8. Peta Jejak Balik Nomor Registrasi Lama ke Copy ID Baru (R9)
CREATE TABLE IF NOT EXISTS legacy_copy_map (
    old_ref TEXT PRIMARY KEY,
    copy_id TEXT NOT NULL REFERENCES copies(id),
    legacy_buku_id INTEGER
);

-- 9. Catatan Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,                       -- Format AUD-xxxxxxxx (Base32 Crockford)
    at TEXT NOT NULL,                          -- ISO8601 UTC seragam
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    reason TEXT,
    detail_json TEXT
);

-- 10. Triggers Pencegahan Penghapusan Data (R12 - Integritas Riwayat)
CREATE TRIGGER IF NOT EXISTS trg_prevent_delete_copies
BEFORE DELETE ON copies
BEGIN
    SELECT RAISE(ABORT, 'DELETE pada tabel copies dilarang demi integritas riwayat perpustakaan');
END;

CREATE TRIGGER IF NOT EXISTS trg_prevent_delete_loan_items
BEFORE DELETE ON loan_items
BEGIN
    SELECT RAISE(ABORT, 'DELETE pada tabel loan_items dilarang demi integritas riwayat perpustakaan');
END;

-- 11. View Ketersediaan Eksemplar
CREATE VIEW IF NOT EXISTS v_copy_availability AS
SELECT 
    c.id AS copy_id,
    c.title_id,
    c.status AS copy_status,
    CASE 
        WHEN c.status != 'aktif' THEN c.status
        WHEN li.id IS NOT NULL THEN 'dipinjam'
        ELSE 'tersedia'
    END AS availability_status,
    li.loan_id AS active_loan_id,
    li.borrowed_at,
    li.due_at
FROM copies c
LEFT JOIN loan_items li ON c.id = li.copy_id AND li.returned_at IS NULL;

-- 12. View Ketersediaan Judul Katalog (R10)
CREATE VIEW IF NOT EXISTS v_title_availability AS
SELECT 
    t.id AS title_id,
    t.judul,
    COUNT(c.id) AS total_semua,
    COUNT(CASE WHEN c.status = 'aktif' THEN 1 END) AS total_aktif,
    COUNT(CASE WHEN c.status = 'aktif' AND li.id IS NULL THEN 1 END) AS available_copies,
    COUNT(CASE WHEN li.id IS NOT NULL THEN 1 END) AS borrowed_copies
FROM catalog_titles t
LEFT JOIN copies c ON t.id = c.title_id
LEFT JOIN loan_items li ON c.id = li.copy_id AND li.returned_at IS NULL
GROUP BY t.id;

