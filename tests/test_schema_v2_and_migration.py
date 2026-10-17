# -*- coding: utf-8 -*-
"""
Uji Unit Skema Database v2, Migrator, Integritas Relasi, dan Batasan Keamanan (Fase 1B).
Memenuhi Requirement: LIB-COPY-001, LIB-COPY-002, LIB-MEMBER-001, LIB-LOAN-002,
R1 - R12, DEC-004, DEC-013, DEC-020, DEC-023, DEC-024.
"""
import json
import os
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from db import get_connection, detect_schema_version
from scripts.migrate_legacy_to_v2 import (
    migrate_database,
    check_production_guardrail,
    detect_registration_duplicates_across_books
)
from timeutil import now_utc, format_iso_utc


class SchemaV2AndMigrationUnitTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "scratch_test_dbs")
        os.makedirs(self.test_dir, exist_ok=True)
        self.cleanups = []

    def tearDown(self):
        for path in self.cleanups:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def _create_temp_db(self, name: str) -> str:
        path = os.path.join(self.test_dir, name)
        self.cleanups.append(path)
        return path

    def test_01_reject_v1_database(self):
        """R1: Migrator menolak database berskema v1 dengan pesan instruksi yang jelas."""
        db_path = self._create_temp_db("legacy_v1.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY, judul TEXT, stok INTEGER);")
        conn.execute("CREATE TABLE peminjaman (id INTEGER PRIMARY KEY, id_buku INTEGER, id_anggota TEXT);")
        conn.commit()
        conn.close()

        with self.assertRaises(RuntimeError) as ctx:
            migrate_database(db_path, dry_run=True)
        self.assertIn("Skema database terdeteksi v1", str(ctx.exception))
        self.assertIn("jalankan migrate_p1_multibook.py", str(ctx.exception))

    def test_02_reject_production_db_path(self):
        """R1: Migrator menolak tegas jika path mengarah ke perpustakaan.db produksi (nama maupun realpath)."""
        self.assertTrue(check_production_guardrail("perpustakaan.db"))
        self.assertTrue(check_production_guardrail("./perpustakaan.db"))
        self.assertTrue(check_production_guardrail(os.path.abspath("perpustakaan.db")))

        with self.assertRaises(RuntimeError) as ctx:
            migrate_database("perpustakaan.db", dry_run=True)
        self.assertIn("database produksi 'perpustakaan.db' DILARANG KERAS", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            migrate_database("./perpustakaan.db", dry_run=False)
        self.assertIn("database produksi 'perpustakaan.db' DILARANG KERAS", str(ctx.exception))

    def test_03_foreign_keys_enforced(self):
        """R3: Memastikan PRAGMA foreign_keys = ON aktif di get_connection dan insert FK invalid ditolak."""
        db_path = self._create_temp_db("fk_test.db")
        # Buat skema v2
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)
        migrate_database(db_path, dry_run=False)

        conn = get_connection(db_path)
        # Coba insert ke copies dengan title_id fiktif
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO copies (id, title_id, status, created_at)
                VALUES ('C-FIKTIF', 'T-NONEXISTENT', 'aktif', '2026-10-17T08:00:00Z')
                """
            )
        conn.close()

    def test_04_partial_unique_index_prevents_double_active_loan(self):
        """R2 & LIB-LOAN-002: Constraint parsial menolak dua loan_item aktif untuk satu copy_id."""
        db_path = self._create_temp_db("partial_unique_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)
        migrate_database(db_path, dry_run=False)

        conn = get_connection(db_path)
        # Ambil satu copy yang sedang tersedia
        row = conn.execute("SELECT copy_id FROM v_copy_availability WHERE availability_status = 'tersedia' LIMIT 1").fetchone()
        copy_id = row["copy_id"]
        loan_id = conn.execute("SELECT id FROM loans LIMIT 1").fetchone()["id"]

        # Insert pinjaman aktif pertama (returned_at IS NULL) -> Berhasil
        conn.execute(
            """
            INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at, returned_at)
            VALUES ('LI-TEST-ACT-1', ?, ?, '2026-10-17T08:00:00Z', '2026-10-24T08:00:00Z', NULL)
            """,
            (loan_id, copy_id)
        )
        conn.commit()

        # Insert pinjaman aktif kedua untuk copy yang SAMA -> Wajib Ditolak IntegrityError
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at, returned_at)
                VALUES ('LI-TEST-ACT-2', ?, ?, '2026-10-17T09:00:00Z', '2026-10-24T09:00:00Z', NULL)
                """,
                (loan_id, copy_id)
            )

        # Setelah item pertama dikembalikan (returned_at terisi), item baru bisa dipinjam
        conn.execute(
            "UPDATE loan_items SET returned_at = '2026-10-18T10:00:00Z' WHERE id = 'LI-TEST-ACT-1'"
        )
        conn.commit()

        # Sekarang insert aktif kedua harus berhasil
        conn.execute(
            """
            INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at, returned_at)
            VALUES ('LI-TEST-ACT-2', ?, ?, '2026-10-18T11:00:00Z', '2026-10-25T11:00:00Z', NULL)
            """,
            (loan_id, copy_id)
        )
        conn.commit()
        conn.close()

    def test_05_prevent_delete_copies_and_loan_items(self):
        """R12: Trigger menolak operasi DELETE pada tabel copies dan loan_items."""
        db_path = self._create_temp_db("delete_guard_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)
        migrate_database(db_path, dry_run=False)

        conn = get_connection(db_path)
        with self.assertRaises(sqlite3.IntegrityError) as ctx1:
            conn.execute("DELETE FROM copies")
        self.assertIn("DELETE pada tabel copies dilarang", str(ctx1.exception))

        with self.assertRaises(sqlite3.IntegrityError) as ctx2:
            conn.execute("DELETE FROM loan_items")
        self.assertIn("DELETE pada tabel loan_items dilarang", str(ctx2.exception))
        conn.close()

    def test_06_dry_run_does_not_modify_db(self):
        """R1 & R12: Mode default --dry-run tidak menulis apa pun ke database."""
        db_path = self._create_temp_db("dry_run_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        res = migrate_database(db_path, dry_run=True)
        self.assertEqual(res["mode"], "DRY-RUN")

        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()

        self.assertNotIn("catalog_titles", tables)
        self.assertNotIn("copies", tables)
        self.assertNotIn("loans", tables)
        self.assertNotIn("loan_items", tables)

    def test_07_migration_apply_on_copy_db(self):
        """R1-R11: Migrasi data salinan 15 buku & 3 transaksi berhasil dengan rekonsiliasi generik."""
        db_path = self._create_temp_db("apply_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        res = migrate_database(db_path, dry_run=False)
        self.assertEqual(res["mode"], "APPLY")
        self.assertEqual(res["status"], "SUCCESS")

        conn = get_connection(db_path)

        # 1. Rekonsiliasi jumlah judul katalog (15 judul)
        buku_lama = conn.execute("SELECT COUNT(*) FROM buku").fetchone()[0]
        titles_v2 = conn.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        self.assertEqual(titles_v2, buku_lama)
        self.assertEqual(titles_v2, 15)

        # 2. Rekonsiliasi eksemplar fisik (28 eksemplar: 27 di rak + 1 aktif dipinjam)
        copies_v2 = conn.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        legacy_map_count = conn.execute("SELECT COUNT(*) FROM legacy_copy_map").fetchone()[0]
        self.assertEqual(copies_v2, 28)
        self.assertEqual(legacy_map_count, 28)

        # 3. Rekonsiliasi transaksi peminjaman (3 transaksi)
        loans_v2 = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        self.assertEqual(loans_v2, 3)

        # 4. Rekonsiliasi item peminjaman (3 detail item: 1 aktif, 2 selesai)
        items_v2 = conn.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0]
        active_items = conn.execute("SELECT COUNT(*) FROM loan_items WHERE returned_at IS NULL").fetchone()[0]
        completed_items = conn.execute("SELECT COUNT(*) FROM loan_items WHERE returned_at IS NOT NULL").fetchone()[0]
        self.assertEqual(items_v2, 3)
        self.assertEqual(active_items, 1)
        self.assertEqual(completed_items, 2)

        # 5. R4: legacy_loan_item_extra menyimpan rincian denda lama
        extra_count = conn.execute("SELECT COUNT(*) FROM legacy_loan_item_extra").fetchone()[0]
        self.assertEqual(extra_count, 3)

        # 6. R7: Format waktu ISO8601 UTC seragam YYYY-MM-DDTHH:MM:SSZ
        for r in conn.execute("SELECT borrowed_at, due_at, returned_at FROM loan_items").fetchall():
            self.assertTrue(r["borrowed_at"].endswith("Z"))
            self.assertIn("T", r["borrowed_at"])
            self.assertTrue(r["due_at"].endswith("Z"))
            if r["returned_at"]:
                self.assertTrue(r["returned_at"].endswith("Z"))

        # 7. R7 & Catatan Data: Notes data uji untuk nama peminjam TEST
        test_items = conn.execute(
            """
            SELECT li.notes FROM loan_items li
            JOIN loans l ON li.loan_id = l.id
            WHERE l.legacy_nama_peminjam LIKE '%TEST%'
            """
        ).fetchall()
        for ti in test_items:
            self.assertIn("data_uji", ti["notes"])
            self.assertIn("waktu_lama_perkiraan", ti["notes"])

        # 8. R10: View v_title_availability
        title_summary = conn.execute(
            "SELECT SUM(total_semua), SUM(total_aktif), SUM(available_copies), SUM(borrowed_copies) FROM v_title_availability"
        ).fetchone()
        self.assertEqual(title_summary[0], 28)  # total semua eksemplar
        self.assertEqual(title_summary[1], 28)  # total aktif
        self.assertEqual(title_summary[2], 27)  # tersedia di rak
        self.assertEqual(title_summary[3], 1)   # sedang dipinjam

        conn.close()

    def test_08_migration_idempotent(self):
        """R5: Menjalankan --apply dua kali pada salinan tidak menambah baris baru."""
        db_path = self._create_temp_db("idempotent_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        # Jalankan apply pertama
        migrate_database(db_path, dry_run=False)

        conn = get_connection(db_path)
        c1 = conn.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        cp1 = conn.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        l1 = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        li1 = conn.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0]
        conn.close()

        # Jalankan apply kedua pada DB yang sama
        migrate_database(db_path, dry_run=False)

        conn2 = get_connection(db_path)
        c2 = conn2.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        cp2 = conn2.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        l2 = conn2.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        li2 = conn2.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0]
        conn2.close()

        self.assertEqual(c1, c2)
        self.assertEqual(cp1, cp2)
        self.assertEqual(l1, l2)
        self.assertEqual(li1, li2)

    def test_09_migration_atomic_rollback_on_failure(self):
        """R12: Simulasi kegagalan di tengah jalan me-rollback seluruh transaksi secara aman."""
        db_path = self._create_temp_db("rollback_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        # Inject error saat proses peminjaman
        with patch("scripts.migrate_legacy_to_v2.generate_loan_id", side_effect=ValueError("Simulasi error tak terduga")):
            with self.assertRaises(RuntimeError) as ctx:
                migrate_database(db_path, dry_run=False)
            self.assertIn("telah di-rollback secara aman", str(ctx.exception))

        conn = sqlite3.connect(db_path)
        # Pastikan tidak ada data yang tersimpan separuh (partial write)
        has_loans = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='loans'").fetchone()[0]
        if has_loans:
            loans_count = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
            self.assertEqual(loans_count, 0)
        conn.close()

    def test_10_duplicate_registration_across_books_rejected(self):
        """R6: Jika ada nomor registrasi duplikat antar-buku, migrasi berhenti dan melapor."""
        db_path = self._create_temp_db("dup_reg_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        # Rekayasa nomor duplikat: tambahkan '00000101' (milik buku 1) ke buku 2
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        buku2_regs = json.loads(cur.execute("SELECT id_buku_fisik FROM buku WHERE id = 2").fetchone()[0])
        buku2_regs.append("00000101")
        cur.execute("UPDATE buku SET id_buku_fisik = ? WHERE id = 2", (json.dumps(buku2_regs),))
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx:
            migrate_database(db_path, dry_run=True)
        self.assertIn("Ditemukan duplikasi nomor registrasi antar-buku", str(ctx.exception))
        self.assertIn("00000101", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

