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

    def test_03b_centralized_connection_configuration_and_pragma(self):
        """1B-03: Memastikan get_connection() memuat konfigurasi terpusat dan PRAGMA foreign_keys = 1."""
        db_path = self._create_temp_db("central_conn_test.db")
        old_env = os.environ.get("DATABASE_NAME")
        try:
            os.environ["DATABASE_NAME"] = db_path
            # Tes 1: get_connection() tanpa argumen menggunakan env DATABASE_NAME
            conn = get_connection()
            fk_on = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            self.assertEqual(fk_on, 1)

            # Tes 2: get_db_connection() wrapper dari app.py mendelegasikan ke konfigurasi terpusat
            import app as library_app
            app_conn = library_app.get_db_connection()
            app_fk_on = app_conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            self.assertEqual(app_fk_on, 1)

            # Tes 3: Foreign Key enforcement menolak referensi tidak valid
            conn.execute("CREATE TABLE parent (id TEXT PRIMARY KEY);")
            conn.execute("CREATE TABLE child (id TEXT PRIMARY KEY, parent_id TEXT REFERENCES parent(id));")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO child VALUES ('c1', 'nonexistent');")

            conn.close()
            app_conn.close()
        finally:
            if old_env is not None:
                os.environ["DATABASE_NAME"] = old_env
            else:
                os.environ.pop("DATABASE_NAME", None)

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

        # 9. Verifikasi Integritas Foreign Key (PRAGMA foreign_key_check)
        fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
        self.assertEqual(len(fk_violations), 0, f"Ditemukan pelanggaran Foreign Key: {fk_violations}")

        # 10. Verifikasi Pemetaan Spesifik: 1 aktif (Yusra / 00001501) dan 2 kembali (baik / legacy)
        active_item = conn.execute(
            """
            SELECT li.*, l.legacy_nama_peminjam, lcm.old_ref
            FROM loan_items li
            JOIN loans l ON li.loan_id = l.id
            JOIN legacy_copy_map lcm ON li.copy_id = lcm.copy_id
            WHERE li.returned_at IS NULL
            """
        ).fetchone()
        self.assertIsNotNone(active_item)
        self.assertEqual(active_item["legacy_nama_peminjam"], "Yusra")
        self.assertEqual(active_item["old_ref"], "00001501")
        self.assertIsNone(active_item["return_condition"])
        self.assertIsNone(active_item["returned_via"])

        completed_items = conn.execute(
            """
            SELECT li.*, l.legacy_nama_peminjam, lcm.old_ref
            FROM loan_items li
            JOIN loans l ON li.loan_id = l.id
            JOIN legacy_copy_map lcm ON li.copy_id = lcm.copy_id
            WHERE li.returned_at IS NOT NULL
            ORDER BY li.id
            """
        ).fetchall()
        self.assertEqual(len(completed_items), 2)
        for ci in completed_items:
            self.assertEqual(ci["return_condition"], "baik")
            self.assertEqual(ci["returned_via"], "legacy")

        # 11. Verifikasi schema_version dan audit_log
        ver_row = conn.execute("SELECT version, name FROM schema_version").fetchone()
        self.assertEqual(ver_row["version"], 2)
        self.assertEqual(ver_row["name"], "0001_initial_v2_schema")

        audit_row = conn.execute("SELECT action, object_type, object_id FROM audit_log WHERE action = 'MIGRATE_V2'").fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["action"], "MIGRATE_V2")
        self.assertEqual(audit_row["object_type"], "database")
        self.assertEqual(audit_row["object_id"], "v2")

        conn.close()

    def test_08_migration_idempotent(self):
        """R5: Menjalankan --apply dua kali pada salinan tidak menambah baris baru atau mengubah pemetaan ID."""
        db_path = self._create_temp_db("idempotent_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        # Jalankan apply pertama
        res1 = migrate_database(db_path, dry_run=False)
        self.assertEqual(res1["mode"], "APPLY")
        self.assertEqual(res1["status"], "SUCCESS")

        conn = get_connection(db_path)
        c1 = conn.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        cp1 = conn.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        l1 = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        li1 = conn.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0]
        lcm1 = conn.execute("SELECT COUNT(*) FROM legacy_copy_map").fetchone()[0]
        extra1 = conn.execute("SELECT COUNT(*) FROM legacy_loan_item_extra").fetchone()[0]
        mc1 = conn.execute("SELECT COUNT(*) FROM member_categories").fetchone()[0]

        titles_before = sorted(r["id"] for r in conn.execute("SELECT id FROM catalog_titles").fetchall())
        copies_before = sorted(r["id"] for r in conn.execute("SELECT id FROM copies").fetchall())
        loans_before = sorted(r["id"] for r in conn.execute("SELECT id FROM loans").fetchall())
        items_before = sorted(r["id"] for r in conn.execute("SELECT id FROM loan_items").fetchall())

        fk_check_1 = conn.execute("PRAGMA foreign_key_check;").fetchall()
        self.assertEqual(len(fk_check_1), 0)
        conn.close()

        # Jalankan apply kedua pada DB yang sama
        res2 = migrate_database(db_path, dry_run=False)
        self.assertEqual(res2["mode"], "APPLY")
        self.assertEqual(res2["status"], "SUCCESS")

        conn2 = get_connection(db_path)
        c2 = conn2.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        cp2 = conn2.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        l2 = conn2.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        li2 = conn2.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0]
        lcm2 = conn2.execute("SELECT COUNT(*) FROM legacy_copy_map").fetchone()[0]
        extra2 = conn2.execute("SELECT COUNT(*) FROM legacy_loan_item_extra").fetchone()[0]
        mc2 = conn2.execute("SELECT COUNT(*) FROM member_categories").fetchone()[0]

        titles_after = sorted(r["id"] for r in conn2.execute("SELECT id FROM catalog_titles").fetchall())
        copies_after = sorted(r["id"] for r in conn2.execute("SELECT id FROM copies").fetchall())
        loans_after = sorted(r["id"] for r in conn2.execute("SELECT id FROM loans").fetchall())
        items_after = sorted(r["id"] for r in conn2.execute("SELECT id FROM loan_items").fetchall())

        fk_check_2 = conn2.execute("PRAGMA foreign_key_check;").fetchall()
        self.assertEqual(len(fk_check_2), 0)
        conn2.close()

        # Verifikasi konsistensi jumlah baris
        self.assertEqual(c1, c2)
        self.assertEqual(cp1, cp2)
        self.assertEqual(l1, l2)
        self.assertEqual(li1, li2)
        self.assertEqual(lcm1, lcm2)
        self.assertEqual(extra1, extra2)
        self.assertEqual(mc1, mc2)

        # Verifikasi kekekalan identitas Primary Key (tidak ada ID yang dibuat ulang atau ditimpa)
        self.assertEqual(titles_before, titles_after)
        self.assertEqual(copies_before, copies_after)
        self.assertEqual(loans_before, loans_after)
        self.assertEqual(items_before, items_after)

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

    def test_11_schema_v2_ddl_and_version_detection(self):
        """1B-05: Verifikasi DDL skema v2, ketiadaan kolom terlarang, CHECK constraints, dan deteksi versi."""
        db_path = self._create_temp_db("ddl_v2_test.db")
        conn = get_connection(db_path)

        # 1. Terapkan DDL skema v2 secara langsung pada database kosong
        ddl_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "0001_initial_v2_schema.sql")
        with open(ddl_path, "r", encoding="utf-8") as f:
            ddl_sql = f.read()
        conn.executescript(ddl_sql)

        # 2. Verifikasi seluruh tabel v2 wajib telah terdefinisi
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        required_tables = {
            "schema_version",
            "member_categories",
            "members",
            "catalog_titles",
            "copies",
            "loans",
            "loan_items",
            "legacy_loan_item_extra",
            "legacy_copy_map",
            "audit_log",
        }
        for tbl in required_tables:
            self.assertIn(tbl, tables, f"Tabel wajib '{tbl}' tidak ditemukan di DDL skema v2")

        # 3. Verifikasi ketiadaan kolom yang dilarang (DEC-020, DEC-023, R4, R8, R9)
        def get_columns(table_name):
            return [col["name"] for col in conn.execute(f"PRAGMA table_info({table_name});").fetchall()]

        members_cols = get_columns("members")
        self.assertNotIn("kelas", members_cols, "Kolom 'kelas' dilarang pada tabel members (DEC-023)")
        self.assertNotIn("telepon", members_cols, "Kolom 'telepon' dilarang pada tabel members (DEC-023)")

        copies_cols = get_columns("copies")
        self.assertNotIn("barcode_id", copies_cols, "Kolom 'barcode_id' dilarang pada tabel copies (R8)")
        self.assertNotIn("no_induk", copies_cols, "Kolom 'no_induk' dilarang pada tabel copies (R9)")
        self.assertNotIn("kondisi", copies_cols, "Kolom 'kondisi' dilarang pada tabel copies (R8)")

        loans_cols = get_columns("loans")
        self.assertNotIn("kelas", loans_cols, "Kolom 'kelas' dilarang pada tabel loans (R4)")
        self.assertNotIn("jurusan", loans_cols, "Kolom 'jurusan' dilarang pada tabel loans (R4)")

        # 4. Verifikasi CHECK constraints menolak nilai di luar whitelist
        # Seed satu kategori valid terlebih dahulu
        conn.execute("INSERT INTO member_categories (id, jenis, keterangan) VALUES ('MC-MURID', 'murid', 'Siswa');")

        # members.status harus 'aktif' atau 'nonaktif'
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO members (id, nama, status, category_id, created_at, updated_at) "
                "VALUES ('M-TEST01', 'Udin', 'pending', 'MC-MURID', '2026-10-18T00:00:00Z', '2026-10-18T00:00:00Z');"
            )

        # Seed satu judul katalog valid
        conn.execute(
            "INSERT INTO catalog_titles (id, judul, created_at, updated_at) "
            "VALUES ('T-TEST01', 'Buku Fisika', '2026-10-18T00:00:00Z', '2026-10-18T00:00:00Z');"
        )

        # copies.status harus dalam whitelist status
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO copies (id, title_id, status, created_at) "
                "VALUES ('C-TEST01', 'T-TEST01', 'terbakar', '2026-10-18T00:00:00Z');"
            )

        # Seed copy valid & loan valid
        conn.execute(
            "INSERT INTO copies (id, title_id, status, created_at) "
            "VALUES ('C-TEST01', 'T-TEST01', 'aktif', '2026-10-18T00:00:00Z');"
        )
        conn.execute(
            "INSERT INTO loans (id, created_at) "
            "VALUES ('L-TEST01', '2026-10-18T00:00:00Z');"
        )

        # loan_items.return_condition invalid ditolak
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at, return_condition) "
                "VALUES ('LI-TST01', 'L-TEST01', 'C-TEST01', '2026-10-18T00:00:00Z', '2026-10-25T00:00:00Z', 'ancur');"
            )

        # loan_items.returned_via invalid ditolak
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at, returned_via) "
                "VALUES ('LI-TST02', 'L-TEST01', 'C-TEST01', '2026-10-18T00:00:00Z', '2026-10-25T00:00:00Z', 'pos');"
            )

        # 5. Verifikasi deteksi versi skema (detect_schema_version)
        # Pada koneksi ini yang sudah memuat catalog_titles, copies, loan_items -> terdeteksi 'v2'
        self.assertEqual(detect_schema_version(conn), "v2")

        # Database kosong -> terdeteksi 'v1'
        db_empty = self._create_temp_db("detect_v1.db")
        conn_empty = get_connection(db_empty)
        self.assertEqual(detect_schema_version(conn_empty), "v1")
        conn_empty.close()

        # Database dengan peminjaman_detail tanpa v2 -> terdeteksi 'P1'
        db_p1 = self._create_temp_db("detect_p1.db")
        conn_p1 = get_connection(db_p1)
        conn_p1.execute("CREATE TABLE buku (id INTEGER PRIMARY KEY);")
        conn_p1.execute("CREATE TABLE peminjaman (id INTEGER PRIMARY KEY);")
        conn_p1.execute("CREATE TABLE peminjaman_detail (id INTEGER PRIMARY KEY, id_peminjaman INTEGER);")
        self.assertEqual(detect_schema_version(conn_p1), "P1")
        conn_p1.close()

        conn.close()

    def test_12_availability_views_copy_and_title_contracts(self):
        """1B-06: Verifikasi kepatuhan kontrak view ketersediaan (v_copy_availability & v_title_availability)."""
        db_path = self._create_temp_db("avail_views_test.db")
        conn = get_connection(db_path)

        ddl_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "0001_initial_v2_schema.sql")
        with open(ddl_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        # 1. Judul tanpa eksemplar sama sekali (t_empty)
        conn.execute(
            "INSERT INTO catalog_titles (id, judul, created_at, updated_at) "
            "VALUES ('T-EMPTY', 'Buku Tanpa Eksemplar', '2026-10-18T00:00:00Z', '2026-10-18T00:00:00Z');"
        )
        empty_row = conn.execute("SELECT * FROM v_title_availability WHERE title_id = 'T-EMPTY';").fetchone()
        self.assertIsNotNone(empty_row)
        self.assertEqual(empty_row["total_semua"], 0)
        self.assertEqual(empty_row["total_aktif"], 0)
        self.assertEqual(empty_row["available_copies"], 0)
        self.assertEqual(empty_row["borrowed_copies"], 0)

        # 2. Judul dengan multi-eksemplar beraneka status (aktif, rusak, hilang, nonaktif, dalam_penanganan)
        conn.execute(
            "INSERT INTO catalog_titles (id, judul, created_at, updated_at) "
            "VALUES ('T-MULTI', 'Buku Ragam Eksemplar', '2026-10-18T00:00:00Z', '2026-10-18T00:00:00Z');"
        )
        copies_data = [
            ("C-AKT1", "T-MULTI", "aktif"),
            ("C-AKT2", "T-MULTI", "aktif"),
            ("C-RUS1", "T-MULTI", "rusak"),
            ("C-HIL1", "T-MULTI", "hilang"),
            ("C-NON1", "T-MULTI", "nonaktif"),
            ("C-TNG1", "T-MULTI", "dalam_penanganan"),
        ]
        for cid, tid, st in copies_data:
            conn.execute(
                "INSERT INTO copies (id, title_id, status, created_at) VALUES (?, ?, ?, '2026-10-18T00:00:00Z');",
                (cid, tid, st),
            )

        # Periksa v_copy_availability awal
        c_rows = {
            r["copy_id"]: r
            for r in conn.execute("SELECT * FROM v_copy_availability WHERE title_id = 'T-MULTI';").fetchall()
        }
        self.assertEqual(len(c_rows), 6)
        # Eksemplar aktif belum dipinjam -> status 'tersedia', active_loan_id None
        self.assertEqual(c_rows["C-AKT1"]["availability_status"], "tersedia")
        self.assertEqual(c_rows["C-AKT1"]["copy_status"], "aktif")
        self.assertIsNone(c_rows["C-AKT1"]["active_loan_id"])

        self.assertEqual(c_rows["C-AKT2"]["availability_status"], "tersedia")
        self.assertIsNone(c_rows["C-AKT2"]["active_loan_id"])

        # Eksemplar non-aktif / rusak / hilang / dalam_penanganan -> availability_status mengikuti copy_status
        self.assertEqual(c_rows["C-RUS1"]["availability_status"], "rusak")
        self.assertEqual(c_rows["C-HIL1"]["availability_status"], "hilang")
        self.assertEqual(c_rows["C-NON1"]["availability_status"], "nonaktif")
        self.assertEqual(c_rows["C-TNG1"]["availability_status"], "dalam_penanganan")

        # Periksa v_title_availability sebelum peminjaman:
        # total_semua=6, total_aktif=2, available_copies=2, borrowed_copies=0
        t_row = conn.execute("SELECT * FROM v_title_availability WHERE title_id = 'T-MULTI';").fetchone()
        self.assertEqual(t_row["total_semua"], 6)
        self.assertEqual(t_row["total_aktif"], 2)
        self.assertEqual(t_row["available_copies"], 2)
        self.assertEqual(t_row["borrowed_copies"], 0)

        # 3. Transisi Peminjaman: C-AKT1 dipinjam (loan_items.returned_at IS NULL)
        conn.execute("INSERT INTO loans (id, created_at) VALUES ('L-TRX01', '2026-10-18T08:00:00Z');")
        conn.execute(
            "INSERT INTO loan_items (id, loan_id, copy_id, borrowed_at, due_at, returned_at) "
            "VALUES ('LI-TRX01', 'L-TRX01', 'C-AKT1', '2026-10-18T08:00:00Z', '2026-10-25T08:00:00Z', NULL);"
        )

        c1_borrowed = conn.execute("SELECT * FROM v_copy_availability WHERE copy_id = 'C-AKT1';").fetchone()
        self.assertEqual(c1_borrowed["availability_status"], "dipinjam")
        self.assertEqual(c1_borrowed["active_loan_id"], "L-TRX01")
        self.assertEqual(c1_borrowed["borrowed_at"], "2026-10-18T08:00:00Z")
        self.assertEqual(c1_borrowed["due_at"], "2026-10-25T08:00:00Z")

        # C-AKT2 tetap tersedia
        c2_avail = conn.execute("SELECT * FROM v_copy_availability WHERE copy_id = 'C-AKT2';").fetchone()
        self.assertEqual(c2_avail["availability_status"], "tersedia")
        self.assertIsNone(c2_avail["active_loan_id"])

        # v_title_availability setelah peminjaman: available_copies berkurang jadi 1, borrowed_copies jadi 1
        t_row_borrowed = conn.execute("SELECT * FROM v_title_availability WHERE title_id = 'T-MULTI';").fetchone()
        self.assertEqual(t_row_borrowed["total_semua"], 6)
        self.assertEqual(t_row_borrowed["total_aktif"], 2)
        self.assertEqual(t_row_borrowed["available_copies"], 1)
        self.assertEqual(t_row_borrowed["borrowed_copies"], 1)

        # 4. Transisi Pengembalian: C-AKT1 dikembalikan (loan_items.returned_at terisi)
        conn.execute(
            "UPDATE loan_items SET returned_at = '2026-10-19T10:00:00Z', return_condition = 'baik', returned_via = 'jalur_a' "
            "WHERE id = 'LI-TRX01';"
        )

        c1_returned = conn.execute("SELECT * FROM v_copy_availability WHERE copy_id = 'C-AKT1';").fetchone()
        self.assertEqual(c1_returned["availability_status"], "tersedia")
        self.assertIsNone(c1_returned["active_loan_id"])

        t_row_returned = conn.execute("SELECT * FROM v_title_availability WHERE title_id = 'T-MULTI';").fetchone()
        self.assertEqual(t_row_returned["available_copies"], 2)
        self.assertEqual(t_row_returned["borrowed_copies"], 0)

        conn.close()

    def test_13_migrator_safety_and_dryrun_contracts(self):
        """1B-07: Memastikan kontrak keselamatan migrator: SHA256 byte-identical saat dry-run, deteksi duplikat detail, dan default CLI."""
        import hashlib
        from scripts.migrate_legacy_to_v2 import main as migrator_main

        # 1. Byte-level integrity check on dry-run: SHA-256 harus 100% identik sebelum dan sesudah dry-run
        db_path = self._create_temp_db("dry_run_hash_test.db")
        source_p1 = os.path.join(os.path.dirname(__file__), "..", "backups", "test_copy_migration.db")
        shutil.copy(source_p1, db_path)

        with open(db_path, "rb") as f:
            hash_before = hashlib.sha256(f.read()).hexdigest()

        summary = migrate_database(db_path, dry_run=True)

        with open(db_path, "rb") as f:
            hash_after = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(hash_before, hash_after, "File database termutasi saat dry-run!")
        self.assertEqual(summary["mode"], "DRY-RUN")
        self.assertEqual(summary["status"], "SUCCESS")
        self.assertIn("schema_version_detected", summary)
        self.assertIn("total_catalog_titles", summary)
        self.assertIn("total_unique_copies", summary)
        self.assertIn("total_loans", summary)
        self.assertIn("total_loan_items", summary)
        self.assertIn("active_loan_items", summary)
        self.assertIn("completed_loan_items", summary)
        self.assertIn("unique_borrowers_count", summary)

        # 2. Verifikasi deteksi duplikasi nomor registrasi yang bersumber dari peminjaman_detail
        db_dup_detail = self._create_temp_db("dup_detail_test.db")
        shutil.copy(source_p1, db_dup_detail)

        conn = sqlite3.connect(db_dup_detail)
        # Masukkan detail peminjaman yang mengaitkan nomor registrasi '00000101' (milik buku 1) ke id_buku = 2
        conn.execute(
            """
            INSERT INTO peminjaman_detail (id_peminjaman, id_buku, no_registrasi, status)
            VALUES (1, 2, '00000101', 'Dipinjam')
            """
        )
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx:
            migrate_database(db_dup_detail, dry_run=True)
        self.assertIn("Ditemukan duplikasi nomor registrasi antar-buku", str(ctx.exception))
        self.assertIn("00000101", str(ctx.exception))

        # 3. CLI default invocation behavior: tanpa argumen --apply, CLI berjalan dalam mode dry-run
        with patch("sys.argv", ["migrate_legacy_to_v2.py", "--source", db_path]):
            with patch("scripts.migrate_legacy_to_v2.migrate_database") as mock_migrate:
                mock_migrate.return_value = summary
                migrator_main()
                mock_migrate.assert_called_once_with(db_path, dry_run=True)

        # 4. CLI dengan --apply meneruskan dry_run=False
        apply_summary = dict(summary)
        apply_summary.update({
            "mode": "APPLY",
            "verified_catalog_titles": 15,
            "verified_copies": 28,
            "verified_loans": 3,
            "verified_loan_items": 3,
            "verified_active_loan_items": 1,
        })
        with patch("sys.argv", ["migrate_legacy_to_v2.py", "--source", db_path, "--apply"]):
            with patch("scripts.migrate_legacy_to_v2.migrate_database") as mock_migrate:
                mock_migrate.return_value = apply_summary
                migrator_main()
                mock_migrate.assert_called_once_with(db_path, dry_run=False)


if __name__ == "__main__":
    unittest.main()

