# -*- coding: utf-8 -*-
"""
Uji Unit Terisolasi Lapisan Repository (Sub-Fase 2A).
Memenuhi Requirement: LIB-COPY-001, LIB-COPY-002, LIB-MEMBER-001, LIB-LOAN-002,
DEC-004, DEC-005, DEC-013, DEC-020, DEC-023, DEC-024, R2, R4, R12.

Cakupan Pengujian:
1. CRUD Judul Katalog & View Ketersediaan (v_title_availability)
2. CRUD Eksemplar Fisik & View Ketersediaan (v_copy_availability)
3. Pembuatan Eksemplar Batch & Dua Lapis Collision Retry
4. Anggota & Kategori Anggota (DEC-020, DEC-023: tanpa kolom kelas & telepon)
5. Peminjaman Multi-Item dalam Satu Transaksi Atomik
6. Penolakan Indeks Parsial Unik (idx_loan_items_active_copy)
7. Pengembalian Parsial & Transisi Ketersediaan Eksemplar
8. Perpanjangan Peminjaman (extend_loan_item)
9. Penolakan Operasi DELETE oleh Database Trigger (R12)
10. Pencatatan Audit Log dalam Transaksi
11. Simulasi Rollback Atomik jika Terjadi Kegagalan
12. Kompatibilitas Data Lama (member_id = NULL, legacy_extra)
13. Pelacakan Nomor Registrasi Lama (legacy_copy_map)
14. Penonaktifan Status Buku Pengganti DELETE (P2-02)
"""
import os
import shutil
import sqlite3
import unittest
import uuid
from typing import Set

import db
import timeutil
import id_generator
from repositories import (
    title_exists_by_id,
    create_title,
    get_title_by_id,
    list_titles,
    update_title,
    get_title_availability,
    copy_exists_by_id,
    create_copy,
    create_copies_batch,
    get_copy_by_id,
    list_copies_by_title,
    update_copy_status,
    update_copy_location,
    get_copy_availability,
    get_copy_by_legacy_ref,
    map_legacy_copy,
    member_exists_by_id,
    category_exists,
    create_category,
    get_category_by_id,
    list_categories,
    create_member,
    get_member_by_id,
    list_members,
    update_member_status,
    increment_qr_version,
    loan_exists_by_id,
    item_exists_by_id,
    create_loan,
    add_loan_item,
    get_loan_by_id,
    get_loan_items,
    get_loan_with_items,
    get_loan_item_by_id,
    get_active_loan_by_copy,
    return_loan_item,
    extend_loan_item,
    list_loans,
    list_active_loan_items,
    get_legacy_extra,
    save_legacy_extra,
    audit_exists_by_id,
    record_audit,
    get_audit_by_id,
    list_audit_by_object,
    list_recent_audits,
)


class RepositoryLayerUnitTests(unittest.TestCase):
    def setUp(self):
        # Gunakan scratch database terisolasi di folder tests/scratch_test_dbs/
        self.test_dir = os.path.join(os.path.dirname(__file__), "scratch_test_dbs")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, f"test_repo_{uuid.uuid4().hex[:8]}.db")

        # Buat skema v2 baru dari file migrasi DDL resmi
        migration_file = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "0001_initial_v2_schema.sql"
        )
        with open(migration_file, "r", encoding="utf-8") as f:
            ddl_script = f.read()

        conn_init = db.get_connection(self.db_path)
        conn_init.executescript(ddl_script)
        conn_init.close()

        # Buka koneksi aktif dengan PRAGMA foreign_keys = ON
        self.conn = db.get_connection(self.db_path)

        # Seed kategori anggota standar
        self._seed_categories()

    def tearDown(self):
        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        if hasattr(self, "db_path") and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    def _seed_categories(self):
        categories = [
            ("MC-MURID", "murid", "Siswa / Murid berdasarkan jurusan"),
            ("MC-GURU-JUR", "guru_jurusan", "Guru kejuruan berdasarkan program keahlian"),
            ("MC-GURU-UMUM", "guru_umum", "Guru mata pelajaran umum"),
            ("MC-STAF", "staf", "Tenaga kependidikan / staf tata usaha"),
            ("MC-TEKNISI", "teknisi", "Laboran / teknisi bengkel/lab"),
        ]
        with self.conn:
            for cat_id, jenis, ket in categories:
                create_category(self.conn, cat_id, jenis, ket)

    def test_01_catalog_crud_and_availability_views(self):
        """Memverifikasi operasi CRUD catalog_titles dan agregasi v_title_availability."""
        # 1. Validasi field wajib
        with self.assertRaises(ValueError):
            create_title(self.conn, {"judul": ""})

        # 2. Pembuatan judul katalog
        with self.conn:
            title_id = create_title(
                self.conn,
                {
                    "judul": "Pemrograman Python Terapan",
                    "penulis": "Tim Pengembang",
                    "penerbit": "SMK Penerbit",
                    "tahun": "2026",
                    "isbn": "978-602-1234-56-7",
                    "kategori": "Teknologi",
                    "harga_buku": 85000,
                },
            )

        self.assertTrue(title_id.startswith("T-"))
        self.assertTrue(title_exists_by_id(self.conn, title_id))

        # 3. Pembacaan data judul
        title = get_title_by_id(self.conn, title_id)
        self.assertIsNotNone(title)
        self.assertEqual(title["judul"], "Pemrograman Python Terapan")
        self.assertEqual(title["harga_buku"], 85000)

        # 4. Pembaruan data judul
        with self.conn:
            updated = update_title(
                self.conn,
                title_id,
                {"harga_buku": 90000, "penulis": "Tim Ahli Python"},
            )
        self.assertTrue(updated)
        title_after = get_title_by_id(self.conn, title_id)
        self.assertEqual(title_after["harga_buku"], 90000)
        self.assertEqual(title_after["penulis"], "Tim Ahli Python")

        # 5. Pencarian judul
        results = list_titles(self.conn, search="Python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], title_id)

        # 6. Agregasi awal ketersediaan judul (belum ada eksemplar)
        avail = get_title_availability(self.conn, title_id)
        self.assertEqual(len(avail), 1)
        self.assertEqual(avail[0]["total_semua"], 0)
        self.assertEqual(avail[0]["available_copies"], 0)
        self.assertEqual(avail[0]["borrowed_copies"], 0)

    def test_02_copy_crud_and_availability_views(self):
        """Memverifikasi pembuatan eksemplar, penegakan FK, dan view ketersediaan (v_copy_availability)."""
        # Buat judul katalog
        with self.conn:
            t_id = create_title(self.conn, {"judul": "Jaringan Komputer"})

        # Foreign Key: membuat eksemplar dengan title_id palsu wajib ditolak FK
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                create_copy(self.conn, {"title_id": "T-NONEXISTENT"})

        # Validasi status tidak valid
        with self.assertRaises(ValueError):
            create_copy(self.conn, {"title_id": t_id, "status": "status_ngawur"})

        # Buat eksemplar sah
        with self.conn:
            c_id = create_copy(
                self.conn,
                {
                    "title_id": t_id,
                    "call_number": "004.6 TIM j.1",
                    "lokasi_rak": "Rak TKJ-01",
                    "status": "aktif",
                },
            )

        self.assertTrue(c_id.startswith("C-"))
        self.assertTrue(copy_exists_by_id(self.conn, c_id))

        # Baca eksemplar dengan join judul
        copy_obj = get_copy_by_id(self.conn, c_id)
        self.assertIsNotNone(copy_obj)
        self.assertEqual(copy_obj["title_judul"], "Jaringan Komputer")
        self.assertEqual(copy_obj["lokasi_rak"], "Rak TKJ-01")

        # Cek view ketersediaan eksemplar
        c_avail = get_copy_availability(self.conn, copy_id=c_id)
        self.assertEqual(len(c_avail), 1)
        self.assertEqual(c_avail[0]["copy_status"], "aktif")
        self.assertEqual(c_avail[0]["availability_status"], "tersedia")
        self.assertIsNone(c_avail[0]["active_loan_id"])

        # Cek view ketersediaan judul
        t_avail = get_title_availability(self.conn, title_id=t_id)
        self.assertEqual(t_avail[0]["total_semua"], 1)
        self.assertEqual(t_avail[0]["total_aktif"], 1)
        self.assertEqual(t_avail[0]["available_copies"], 1)
        self.assertEqual(t_avail[0]["borrowed_copies"], 0)

    def test_03_batch_copies_and_two_layer_collision_retry(self):
        """Memverifikasi pembuatan batch eksemplar dengan dua lapis collision check (P2-01)."""
        with self.conn:
            t_id = create_title(self.conn, {"judul": "Basis Data Relasional"})

        seen_cache: Set[str] = set()
        with self.conn:
            batch_ids = create_copies_batch(
                self.conn,
                title_id=t_id,
                count=5,
                base_data={"lokasi_rak": "Rak RPL-A"},
                seen_ids=seen_cache,
            )

        self.assertEqual(len(batch_ids), 5)
        self.assertEqual(len(set(batch_ids)), 5)  # Semua ID unik
        self.assertEqual(len(seen_cache), 5)     # Dicatat ke cache seen_ids

        # Verifikasi seluruhnya tersimpan di database
        copies = list_copies_by_title(self.conn, t_id)
        self.assertEqual(len(copies), 5)

        # Verifikasi view judul mencatat 5 eksemplar tersedia
        t_avail = get_title_availability(self.conn, title_id=t_id)
        self.assertEqual(t_avail[0]["available_copies"], 5)

        # Uji eksplisit verifikasi collision retry dua lapis:
        # Lapis 1: ID sudah ada di tabel copies database (exists_by_id)
        # Lapis 2: ID sudah ada di cache lokal seen_ids (batch check)
        from unittest.mock import patch

        candidate_in_db = batch_ids[0]      # ada di database
        candidate_in_seen = "C-INSEENCACHE"  # ada di seen_ids
        candidate_fresh = "C-UNIQUENOW"     # unik / belum terpakai
        test_seen_set = {candidate_in_seen}

        def mock_generate_with_retry(is_taken=None):
            candidates = [candidate_in_db, candidate_in_seen, candidate_fresh]
            for c in candidates:
                if is_taken and is_taken(c):
                    continue
                return c
            raise RuntimeError("Semua kandidat tabrakan.")

        with patch("id_generator.generate_copy_id", side_effect=mock_generate_with_retry):
            with self.conn:
                new_c_id = create_copy(
                    self.conn,
                    {"title_id": t_id, "status": "aktif"},
                    seen_ids=test_seen_set,
                )

        self.assertEqual(new_c_id, candidate_fresh)
        self.assertIn(candidate_fresh, test_seen_set)
        self.assertTrue(copy_exists_by_id(self.conn, candidate_fresh))

    def test_04_member_repository_and_decisions(self):
        """Memverifikasi manajemen anggota: DEC-020 (status aktif/nonaktif) dan DEC-023 (tanpa kelas/telepon)."""
        # 1. Kategori sudah ter-seed
        self.assertTrue(category_exists(self.conn, "MC-MURID"))
        cats = list_categories(self.conn)
        self.assertEqual(len(cats), 5)

        # 2. Buat anggota baru
        with self.conn:
            m_id = create_member(
                self.conn,
                {
                    "nama": "Ahmad Dani",
                    "category_id": "MC-MURID",
                    "status": "aktif",
                },
            )

        self.assertTrue(m_id.startswith("M-"))
        self.assertTrue(member_exists_by_id(self.conn, m_id))

        member = get_member_by_id(self.conn, m_id)
        self.assertIsNotNone(member)
        self.assertEqual(member["nama"], "Ahmad Dani")
        self.assertEqual(member["category_jenis"], "murid")
        self.assertEqual(member["status"], "aktif")
        self.assertEqual(member["qr_version"], 1)

        # Pastikan TIDAK ADA kolom kelas atau telepon di tabel members (DEC-023)
        self.assertNotIn("kelas", member)
        self.assertNotIn("telepon", member)

        # 3. Penonaktifan anggota (DEC-020)
        with self.conn:
            ok = update_member_status(self.conn, m_id, "nonaktif")
        self.assertTrue(ok)
        member_updated = get_member_by_id(self.conn, m_id)
        self.assertEqual(member_updated["status"], "nonaktif")

        # 4. Increment QR Version
        with self.conn:
            new_ver = increment_qr_version(self.conn, m_id)
        self.assertEqual(new_ver, 2)
        self.assertEqual(get_member_by_id(self.conn, m_id)["qr_version"], 2)

    def test_05_multi_item_loan_creation_in_single_transaction(self):
        """Memverifikasi peminjaman multi-item dalam satu transaksi atomik & pembaruan view ketersediaan."""
        with self.conn:
            m_id = create_member(self.conn, {"nama": "Budi Santoso", "category_id": "MC-MURID"})
            t_id = create_title(self.conn, {"judul": "Koleksi Ensiklopedia"})
            c_ids = create_copies_batch(self.conn, t_id, 3)

        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        due_iso = timeutil.format_iso_utc(timeutil.calculate_due_datetime(now_iso, hours=168))

        # Peminjaman 3 item sekaligus dalam satu transaksi
        with self.conn:
            loan_id = create_loan(self.conn, {"member_id": m_id})
            for copy_id in c_ids:
                add_loan_item(
                    self.conn,
                    {
                        "loan_id": loan_id,
                        "copy_id": copy_id,
                        "borrowed_at": now_iso,
                        "due_at": due_iso,
                    },
                )

        # Verifikasi loan_repo
        loan = get_loan_with_items(self.conn, loan_id)
        self.assertIsNotNone(loan)
        self.assertEqual(loan["member_nama"], "Budi Santoso")
        self.assertEqual(len(loan["items"]), 3)

        # Verifikasi view ketersediaan judul: 0 tersedia, 3 dipinjam
        t_avail = get_title_availability(self.conn, title_id=t_id)
        self.assertEqual(t_avail[0]["available_copies"], 0)
        self.assertEqual(t_avail[0]["borrowed_copies"], 3)

        # Verifikasi view ketersediaan eksemplar: semua dipinjam
        for copy_id in c_ids:
            c_avail = get_copy_availability(self.conn, copy_id=copy_id)[0]
            self.assertEqual(c_avail["availability_status"], "dipinjam")
            self.assertEqual(c_avail["active_loan_id"], loan_id)

    def test_06_partial_unique_index_rejects_duplicate_active_borrowing(self):
        """LIB-LOAN-002: Indeks parsial unik idx_loan_items_active_copy menolak peminjaman ganda untuk copy yang sama."""
        with self.conn:
            m1 = create_member(self.conn, {"nama": "Peminjam Pertama", "category_id": "MC-MURID"})
            m2 = create_member(self.conn, {"nama": "Peminjam Kedua", "category_id": "MC-MURID"})
            t = create_title(self.conn, {"judul": "Buku Langka"})
            c = create_copy(self.conn, {"title_id": t})

        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        due_iso = timeutil.format_iso_utc(timeutil.calculate_due_datetime(now_iso))

        # Peminjaman pertama aktif
        with self.conn:
            l1 = create_loan(self.conn, {"member_id": m1})
            add_loan_item(self.conn, {"loan_id": l1, "copy_id": c, "borrowed_at": now_iso, "due_at": due_iso})

        # Coba pinjam copy yang sama untuk peminjam kedua -> Wajib melempar sqlite3.IntegrityError
        l2 = create_loan(self.conn, {"member_id": m2})
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                add_loan_item(
                    self.conn,
                    {"loan_id": l2, "copy_id": c, "borrowed_at": now_iso, "due_at": due_iso},
                )

        # Verifikasi active loan peminjam pertama tetap utuh
        active_loan = get_active_loan_by_copy(self.conn, c)
        self.assertIsNotNone(active_loan)
        self.assertEqual(active_loan["member_id"], m1)

    def test_07_partial_return_and_copy_status_transitions(self):
        """DEC-007: Pengembalian parsial per eksemplar mengembalikan status eksemplar tanpa mempengaruhi eksemplar lain."""
        with self.conn:
            m = create_member(self.conn, {"nama": "Peminjam Mandiri", "category_id": "MC-MURID"})
            t = create_title(self.conn, {"judul": "Paket Buku UN"})
            c1 = create_copy(self.conn, {"title_id": t})
            c2 = create_copy(self.conn, {"title_id": t})

        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        due_iso = timeutil.format_iso_utc(timeutil.calculate_due_datetime(now_iso))

        with self.conn:
            loan_id = create_loan(self.conn, {"member_id": m})
            item_id_1 = add_loan_item(self.conn, {"loan_id": loan_id, "copy_id": c1, "borrowed_at": now_iso, "due_at": due_iso})
            item_id_2 = add_loan_item(self.conn, {"loan_id": loan_id, "copy_id": c2, "borrowed_at": now_iso, "due_at": due_iso})

        # Kembalikan eksemplar c1 saja
        ret_time = timeutil.format_iso_utc(timeutil.now_utc())
        with self.conn:
            returned = return_loan_item(
                self.conn,
                item_id=item_id_1,
                return_condition="baik",
                returned_via="manual",
                returned_at=ret_time,
            )
        self.assertTrue(returned)

        # Verifikasi item 1 berstatus selesai, item 2 masih dipinjam
        item1 = get_loan_item_by_id(self.conn, item_id_1)
        item2 = get_loan_item_by_id(self.conn, item_id_2)
        self.assertEqual(item1["returned_at"], ret_time)
        self.assertEqual(item1["return_condition"], "baik")
        self.assertIsNone(item2["returned_at"])

        # Verifikasi c1 kembali berstatus 'tersedia', c2 masih 'dipinjam'
        avail_c1 = get_copy_availability(self.conn, copy_id=c1)[0]
        avail_c2 = get_copy_availability(self.conn, copy_id=c2)[0]
        self.assertEqual(avail_c1["availability_status"], "tersedia")
        self.assertEqual(avail_c2["availability_status"], "dipinjam")

        # Verifikasi agregasi judul: 1 tersedia, 1 dipinjam
        t_avail = get_title_availability(self.conn, title_id=t)[0]
        self.assertEqual(t_avail["available_copies"], 1)
        self.assertEqual(t_avail["borrowed_copies"], 1)

        # Sekarang c1 dapat dipinjam kembali oleh orang lain secara sah
        with self.conn:
            m2 = create_member(self.conn, {"nama": "Peminjam Baru", "category_id": "MC-MURID"})
            loan_id_2 = create_loan(self.conn, {"member_id": m2})
            new_item_id = add_loan_item(self.conn, {"loan_id": loan_id_2, "copy_id": c1, "borrowed_at": ret_time, "due_at": due_iso})
        self.assertTrue(new_item_id.startswith("LI-"))

    def test_08_loan_extension(self):
        """Memverifikasi perpanjangan batas waktu peminjaman (extend_loan_item)."""
        with self.conn:
            m = create_member(self.conn, {"nama": "Siswa Rajin", "category_id": "MC-MURID"})
            t = create_title(self.conn, {"judul": "Matematika Diskrit"})
            c = create_copy(self.conn, {"title_id": t})

        now_iso = timeutil.format_iso_utc(timeutil.now_utc())
        initial_due = timeutil.format_iso_utc(timeutil.calculate_due_datetime(now_iso, hours=168))
        extended_due = timeutil.format_iso_utc(timeutil.calculate_due_datetime(initial_due, hours=168))

        with self.conn:
            l_id = create_loan(self.conn, {"member_id": m})
            li_id = add_loan_item(self.conn, {"loan_id": l_id, "copy_id": c, "borrowed_at": now_iso, "due_at": initial_due})

        # Eksekusi perpanjangan
        with self.conn:
            ok = extend_loan_item(self.conn, li_id, new_due_at=extended_due)
        self.assertTrue(ok)

        item = get_loan_item_by_id(self.conn, li_id)
        self.assertEqual(item["due_at"], extended_due)
        self.assertEqual(item["extension_count"], 1)
        self.assertIsNotNone(item["extended_at"])

    def test_09_prevent_delete_triggers_on_copies_and_loan_items(self):
        """R12: Triggers trg_prevent_delete_copies dan trg_prevent_delete_loan_items menolak operasi DELETE."""
        with self.conn:
            m = create_member(self.conn, {"nama": "Testing Trigger", "category_id": "MC-MURID"})
            t = create_title(self.conn, {"judul": "Integritas Data"})
            c = create_copy(self.conn, {"title_id": t})
            l = create_loan(self.conn, {"member_id": m})
            li = add_loan_item(
                self.conn,
                {
                    "loan_id": l,
                    "copy_id": c,
                    "borrowed_at": "2026-10-17T08:00:00Z",
                    "due_at": "2026-10-24T08:00:00Z",
                },
            )

        # 1. Coba DELETE dari copies
        with self.assertRaises(sqlite3.DatabaseError) as ctx:
            self.conn.execute("DELETE FROM copies WHERE id = ?;", (c,))
        self.assertIn("DELETE pada tabel copies dilarang", str(ctx.exception))

        # 2. Coba DELETE dari loan_items
        with self.assertRaises(sqlite3.DatabaseError) as ctx:
            self.conn.execute("DELETE FROM loan_items WHERE id = ?;", (li,))
        self.assertIn("DELETE pada tabel loan_items dilarang", str(ctx.exception))

    def test_10_audit_logging_in_same_transaction(self):
        """Memverifikasi pencatatan audit log dalam transaksi yang sama dan format timestamp UTC ISO8601."""
        with self.conn:
            t = create_title(self.conn, {"judul": "Audit Trail Test"})
            audit_id = record_audit(
                self.conn,
                actor="admin_perpustakaan",
                action="TITLE_CREATE",
                object_type="catalog_titles",
                object_id=t,
                reason="Pendaftaran buku baru kurikulum merdeka",
                detail_json={"judul": "Audit Trail Test"},
            )

        self.assertTrue(audit_id.startswith("AUD-"))
        self.assertTrue(audit_exists_by_id(self.conn, audit_id))

        audit = get_audit_by_id(self.conn, audit_id)
        self.assertIsNotNone(audit)
        self.assertEqual(audit["actor"], "admin_perpustakaan")
        self.assertEqual(audit["action"], "TITLE_CREATE")
        self.assertIn("T", audit["at"])  # Format ISO8601
        self.assertTrue(audit["at"].endswith("Z"))

        # Cek list by object
        logs = list_audit_by_object(self.conn, "catalog_titles", t)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["id"], audit_id)

    def test_11_atomic_rollback_on_failure(self):
        """Memverifikasi kepatuhan transaksi atomik: kegagalan di tengah jalan me-rollback seluruh operasi."""
        with self.conn:
            m = create_member(self.conn, {"nama": "Tes Rollback", "category_id": "MC-MURID"})
            t = create_title(self.conn, {"judul": "Simulasi Kegagalan"})
            c = create_copy(self.conn, {"title_id": t})

        loan_id_candidate = "L-ROLLBACKTEST"
        item_id_candidate = "LI-ROLLBACKTEST"
        audit_id_candidate = "AUD-ROLLBACKTEST"

        try:
            with self.conn:
                # 1. Buat header loan
                create_loan(self.conn, {"id": loan_id_candidate, "member_id": m})
                # 2. Tambah item pertama
                add_loan_item(
                    self.conn,
                    {
                        "id": item_id_candidate,
                        "loan_id": loan_id_candidate,
                        "copy_id": c,
                        "borrowed_at": "2026-10-17T08:00:00Z",
                        "due_at": "2026-10-24T08:00:00Z",
                    },
                )
                # 3. Catat audit log dalam transaksi yang sama
                # Simulasikan ID teralokasi
                conn_raw = self.conn
                conn_raw.execute(
                    """
                    INSERT INTO audit_log (id, at, actor, action, object_type, object_id, reason)
                    VALUES (?, '2026-10-17T08:00:00Z', 'admin_test', 'LOAN_CREATE', 'loans', ?, 'Tes Rollback');
                    """,
                    (audit_id_candidate, loan_id_candidate),
                )
                # 4. Simulasikan error tak terduga sebelum blok commit selesai
                raise RuntimeError("Kegagalan koneksi internal / simulasi crash!")
        except RuntimeError:
            pass

        # Verifikasi bahwa seluruh mutasi (loan, item, dan audit_log) DIBATALKAN
        self.assertFalse(loan_exists_by_id(self.conn, loan_id_candidate))
        self.assertFalse(item_exists_by_id(self.conn, item_id_candidate))
        self.assertFalse(audit_exists_by_id(self.conn, audit_id_candidate))

        # Eksemplar tetap berstatus 'tersedia'
        avail = get_copy_availability(self.conn, copy_id=c)[0]
        self.assertEqual(avail["availability_status"], "tersedia")

    def test_12_legacy_loan_and_notes_compatibility(self):
        """R4 & DEC-024: Kompatibilitas transaksi legacy (member_id = NULL) dan pencatatan legacy_extra."""
        with self.conn:
            t = create_title(self.conn, {"judul": "Buku Arsip Lama", "legacy_buku_id": 999})
            c = create_copy(self.conn, {"title_id": t})

            # Buat loan tanpa member_id, hanya dengan legacy_nama_peminjam
            l_id = create_loan(
                self.conn,
                {
                    "member_id": None,
                    "legacy_nama_peminjam": "Bambang (Alumni 2024)",
                    "legacy_peminjaman_id": 888,
                },
            )
            li_id = add_loan_item(
                self.conn,
                {
                    "loan_id": l_id,
                    "copy_id": c,
                    "borrowed_at": "2026-09-01T08:00:00Z",
                    "due_at": "2026-09-08T08:00:00Z",
                    "notes": "data_uji; waktu_lama_perkiraan",
                },
            )

            # Simpan data denda arsip lama
            save_legacy_extra(
                self.conn,
                item_id=li_id,
                fine_overdue=3000,
                fine_condition=0,
                status_penggantian="tidak_ada",
            )

        # Verifikasi get loan
        loan = get_loan_by_id(self.conn, l_id)
        self.assertIsNone(loan["member_id"])
        self.assertEqual(loan["legacy_nama_peminjam"], "Bambang (Alumni 2024)")

        # Verifikasi list loans menampilkan display name
        loans = list_loans(self.conn)
        found = next((item for item in loans if item["id"] == l_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["peminjam_display_name"], "Bambang (Alumni 2024)")

        # Verifikasi legacy extra
        extra = get_legacy_extra(self.conn, li_id)
        self.assertIsNotNone(extra)
        self.assertEqual(extra["fine_overdue"], 3000)

    def test_13_legacy_copy_map(self):
        """R9: Pemetaan nomor registrasi lama ke eksemplar v2 melalui legacy_copy_map."""
        with self.conn:
            t = create_title(self.conn, {"judul": "Kamus Bahasa Indonesia"})
            c = create_copy(self.conn, {"title_id": t})
            map_legacy_copy(self.conn, old_ref="B-0012-REG", copy_id=c, legacy_buku_id=12)

        resolved = get_copy_by_legacy_ref(self.conn, "B-0012-REG")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["id"], c)
        self.assertEqual(resolved["old_ref"], "B-0012-REG")
        self.assertEqual(resolved["legacy_buku_id"], 12)

    def test_14_copy_deactivation_instead_of_delete(self):
        """P2-02: Penonaktifan eksemplar buku sebagai pengganti operasi DELETE."""
        with self.conn:
            t = create_title(self.conn, {"judul": "Ensiklopedia Sains"})
            c = create_copy(self.conn, {"title_id": t, "status": "aktif"})

        # Cek ketersediaan awal
        self.assertEqual(get_title_availability(self.conn, t)[0]["available_copies"], 1)

        # Ubah status eksemplar menjadi 'nonaktif'
        with self.conn:
            ok = update_copy_status(self.conn, c, "nonaktif")
        self.assertTrue(ok)

        # Eksemplar tidak lagi dihitung sebagai copy aktif atau tersedia
        c_avail = get_copy_availability(self.conn, copy_id=c)[0]
        self.assertEqual(c_avail["copy_status"], "nonaktif")
        self.assertEqual(c_avail["availability_status"], "nonaktif")

        t_avail = get_title_availability(self.conn, title_id=t)[0]
        self.assertEqual(t_avail["total_semua"], 1)
        self.assertEqual(t_avail["total_aktif"], 0)
        self.assertEqual(t_avail["available_copies"], 0)
        self.assertEqual(t_avail["borrowed_copies"], 0)


if __name__ == "__main__":
    unittest.main()

