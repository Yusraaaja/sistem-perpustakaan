# -*- coding: utf-8 -*-
"""
Uji Unit Terisolasi Lapisan Business Service (Sub-Fase 2B).
Memenuhi Kriteria Pengujian Sub-Fase 2B:
- Peminjaman multi-item berhasil.
- Anggota atau eksemplar yang tidak memenuhi syarat ditolak.
- Eksemplar yang sama tidak dapat dipinjam aktif dua kali.
- Pengembalian parsial dan penuh.
- Perpanjangan sesuai aturan DEC-005 (maksimal 1 kali).
- Audit log ikut di-rollback jika transaksi gagal.
- Kegagalan salah satu item membatalkan seluruh peminjaman (atomisitas penuh).
- Penonaktifan eksemplar tanpa DELETE (P2-02).
- Penyelesaian buku hilang/rusak dengan penggantian fisik (DEC-024).
"""
import os
import shutil
import sqlite3
import unittest
import uuid

import db
import timeutil
from repositories import (
    loan_repo,
    copy_repo,
    catalog_repo,
    member_repo,
    audit_repo,
)
from services import (
    borrow_copies,
    return_copies,
    extend_loan,
    resolve_lost_or_damaged,
    register_member,
    deactivate_member,
    reactivate_member,
    create_title_with_copies,
    add_copies_to_title,
    deactivate_copy,
    transaction_scope,
    MemberNotFoundError,
    MemberInactiveError,
    CopyNotFoundError,
    CopyNotAvailableError,
    LoanItemNotFoundError,
    LoanItemAlreadyReturnedError,
    LoanExtensionLimitReachedError,
    InvalidOperationError,
    ValidationError,
)


class BusinessServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "scratch_test_dbs")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, f"test_svc_{uuid.uuid4().hex[:8]}.db")

        # Inisialisasi skema v2 baru dari file DDL
        migration_file = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "0001_initial_v2_schema.sql"
        )
        with open(migration_file, "r", encoding="utf-8") as f:
            ddl_script = f.read()

        conn_init = db.get_connection(self.db_path)
        conn_init.executescript(ddl_script)
        conn_init.close()

        self.conn = db.get_connection(self.db_path)
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
                member_repo.create_category(self.conn, cat_id, jenis, ket)

    def test_01_borrow_copies_success(self):
        """Memverifikasi peminjaman multi-item berhasil, view terupdate, dan audit log tercatat."""
        member = register_member(self.conn, nama="Siti Rahma", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn,
            title_data={"judul": "Fisika Terapan SMK"},
            initial_copies=3,
        )
        copy_ids = title["copy_ids"]

        # Peminjaman 3 eksemplar
        loan = borrow_copies(
            self.conn,
            member_id=member["id"],
            copy_ids=copy_ids,
            actor="kiosk_tablet_01",
        )

        self.assertIsNotNone(loan)
        self.assertEqual(len(loan["items"]), 3)
        self.assertEqual(loan["member_id"], member["id"])

        # Verifikasi view ketersediaan
        t_avail = catalog_repo.get_title_availability(self.conn, title["id"])[0]
        self.assertEqual(t_avail["available_copies"], 0)
        self.assertEqual(t_avail["borrowed_copies"], 3)

        # Verifikasi audit log tercatat
        audits = audit_repo.list_by_object(self.conn, "loans", loan["id"])
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["action"], "LOAN_CREATE")
        self.assertEqual(audits[0]["actor"], "kiosk_tablet_01")

    def test_02_borrow_rejected_for_inactive_or_nonexistent_member(self):
        """DEC-020: Anggota nonaktif atau tidak terdaftar ditolak untuk meminjam buku."""
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Kimia Industri"}, initial_copies=1
        )
        copy_id = title["copy_ids"][0]

        # 1. Anggota tidak ada
        with self.assertRaises(MemberNotFoundError):
            borrow_copies(self.conn, member_id="M-TIDAKADA", copy_ids=[copy_id])

        # 2. Anggota dinonaktifkan
        member = register_member(self.conn, nama="Budi Nonaktif", category_id="MC-MURID")
        deactivate_member(self.conn, member_id=member["id"], reason="Lulus sekolah")

        with self.assertRaises(MemberInactiveError) as ctx:
            borrow_copies(self.conn, member_id=member["id"], copy_ids=[copy_id])
        self.assertIn("berstatus nonaktif", str(ctx.exception))

        # Eksemplar tetap berstatus tersedia
        avail = copy_repo.get_copy_availability(self.conn, copy_id=copy_id)[0]
        self.assertEqual(avail["availability_status"], "tersedia")

    def test_03_borrow_rejected_for_unavailable_or_nonexistent_copy(self):
        """Memverifikasi penolakan peminjaman bila eksemplar tidak ada atau berstatus nonaktif."""
        member = register_member(self.conn, nama="Dewi Sartika", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Biologi Dasar"}, initial_copies=1
        )
        copy_id = title["copy_ids"][0]

        # 1. Eksemplar palsu
        with self.assertRaises(CopyNotFoundError):
            borrow_copies(self.conn, member_id=member["id"], copy_ids=["C-PALSU999"])

        # 2. Eksemplar dinonaktifkan
        deactivate_copy(self.conn, copy_id=copy_id, reason="Buku robek parah")
        with self.assertRaises(CopyNotAvailableError) as ctx:
            borrow_copies(self.conn, member_id=member["id"], copy_ids=[copy_id])
        self.assertIn("tidak dapat dipinjam", str(ctx.exception))

    def test_04_borrow_duplicate_active_copy_rejected(self):
        """LIB-LOAN-002: Eksemplar yang sedang dipinjam aktif tidak dapat dipinjam kembali."""
        m1 = register_member(self.conn, nama="Peminjam Pertama", category_id="MC-MURID")
        m2 = register_member(self.conn, nama="Peminjam Kedua", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Algoritma Pemrograman"}, initial_copies=1
        )
        c_id = title["copy_ids"][0]

        # Peminjaman pertama sah
        borrow_copies(self.conn, member_id=m1["id"], copy_ids=[c_id])

        # Peminjaman kedua atas copy yang sama ditolak
        with self.assertRaises(CopyNotAvailableError) as ctx:
            borrow_copies(self.conn, member_id=m2["id"], copy_ids=[c_id])
        self.assertIn("tidak dapat dipinjam", str(ctx.exception))

    def test_05_multi_item_borrow_atomic_rollback_on_single_item_failure(self):
        """Batas Transaksi: Kegagalan pada salah satu item membatalkan seluruh peminjaman dan audit log."""
        member = register_member(self.conn, nama="Uji Atomik", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Paket Buku UN"}, initial_copies=2
        )
        c1, c2 = title["copy_ids"]
        c3_invalid = "C-NONEXISTENT99"

        # Coba pinjam c1, c2, dan c3_invalid
        with self.assertRaises(CopyNotFoundError):
            borrow_copies(self.conn, member_id=member["id"], copy_ids=[c1, c2, c3_invalid])

        # Verifikasi ROLLBACK PENUH:
        # 1. c1 dan c2 tetap berstatus tersedia (tidak terpinjam)
        avail_c1 = copy_repo.get_copy_availability(self.conn, copy_id=c1)[0]
        avail_c2 = copy_repo.get_copy_availability(self.conn, copy_id=c2)[0]
        self.assertEqual(avail_c1["availability_status"], "tersedia")
        self.assertEqual(avail_c2["availability_status"], "tersedia")

        # 2. Tidak ada header peminjaman yang tersimpan untuk anggota ini
        loans = loan_repo.list_loans(self.conn, member_id=member["id"])
        self.assertEqual(len(loans), 0)

        # 3. Tidak ada audit log LOAN_CREATE yang tersisa
        audits = audit_repo.list_recent_audits(self.conn)
        loan_audits = [a for a in audits if a["action"] == "LOAN_CREATE"]
        self.assertEqual(len(loan_audits), 0)

    def test_06_return_copies_full_and_partial(self):
        """DEC-006 & DEC-007: Pengembalian parsial dan penuh, update status eksemplar rusak."""
        member = register_member(self.conn, nama="Peminjam Setia", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Kamus Bahasa Indonesia"}, initial_copies=2
        )
        c1, c2 = title["copy_ids"]

        borrow_copies(self.conn, member_id=member["id"], copy_ids=[c1, c2])

        # 1. Pengembalian parsial: kembalikan c1 dengan kondisi baik
        ret1 = return_copies(self.conn, copy_ids=[c1], return_condition="baik")
        self.assertEqual(len(ret1), 1)
        self.assertEqual(ret1[0]["return_condition"], "baik")

        avail_c1 = copy_repo.get_copy_availability(self.conn, copy_id=c1)[0]
        avail_c2 = copy_repo.get_copy_availability(self.conn, copy_id=c2)[0]
        self.assertEqual(avail_c1["availability_status"], "tersedia")
        self.assertEqual(avail_c2["availability_status"], "dipinjam")

        # 2. Pengembalian c2 dengan kondisi rusak
        ret2 = return_copies(self.conn, copy_ids=[c2], return_condition="rusak")
        self.assertEqual(len(ret2), 1)
        self.assertEqual(ret2[0]["return_condition"], "rusak")

        # Status eksemplar c2 menjadi 'rusak'
        copy_c2 = copy_repo.get_copy_by_id(self.conn, c2)
        self.assertEqual(copy_c2["status"], "rusak")

    def test_07_return_unborrowed_copy_rejected(self):
        """Memverifikasi pengembalian eksemplar yang tidak sedang dipinjam ditolak."""
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Statistika Dasar"}, initial_copies=1
        )
        c_id = title["copy_ids"][0]

        with self.assertRaises(CopyNotAvailableError):
            return_copies(self.conn, copy_ids=[c_id])

    def test_08_extend_loan_success_and_limit(self):
        """DEC-005: Perpanjangan berhasil 1x (+168 jam), perpanjangan kedua ditolak."""
        member = register_member(self.conn, nama="Siswa Teladan", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Kalkulus Lanjut"}, initial_copies=1
        )
        c_id = title["copy_ids"][0]

        loan = borrow_copies(self.conn, member_id=member["id"], copy_ids=[c_id])
        item_id = loan["items"][0]["id"]
        initial_due = loan["items"][0]["due_at"]

        # Perpanjangan pertama: berhasil
        extended_item = extend_loan(self.conn, item_id=item_id, extension_hours=168)
        self.assertEqual(extended_item["extension_count"], 1)
        self.assertNotEqual(extended_item["due_at"], initial_due)

        # Perpanjangan kedua: wajib ditolak (DEC-005)
        with self.assertRaises(LoanExtensionLimitReachedError) as ctx:
            extend_loan(self.conn, item_id=item_id)
        self.assertIn("Batas perpanjangan maksimal 1 kali telah tercapai", str(ctx.exception))

    def test_09_extend_already_returned_item_rejected(self):
        """Memverifikasi perpanjangan ditolak jika buku sudah dikembalikan."""
        member = register_member(self.conn, nama="Siswa Cepat", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Filsafat Ilmu"}, initial_copies=1
        )
        c_id = title["copy_ids"][0]

        loan = borrow_copies(self.conn, member_id=member["id"], copy_ids=[c_id])
        item_id = loan["items"][0]["id"]

        return_copies(self.conn, copy_ids=[c_id])

        with self.assertRaises(LoanItemAlreadyReturnedError):
            extend_loan(self.conn, item_id=item_id)

    def test_10_resolve_lost_or_damaged_book(self):
        """DEC-024: Penyelesaian buku hilang/rusak dengan penggantian kamus/Al-Qur'an tanpa denda uang."""
        member = register_member(self.conn, nama="Peminjam Sial", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Atlas Dunia Modern"}, initial_copies=1
        )
        c_id = title["copy_ids"][0]

        loan = borrow_copies(self.conn, member_id=member["id"], copy_ids=[c_id])
        item_id = loan["items"][0]["id"]

        # Selesaikan penggantian
        resolved = resolve_lost_or_damaged(
            self.conn,
            item_id=item_id,
            replacement_type="Al-Qur'an Standar Kemenag",
            notes="Buku basah kehujanan, diganti Al-Qur'an sesuai kesepakatan",
        )

        self.assertEqual(resolved["return_condition"], "rusak")
        self.assertEqual(resolved["returned_via"], "penyelesaian")

        # Cek catatan extra
        extra = loan_repo.get_legacy_extra(self.conn, item_id)
        self.assertIsNotNone(extra)
        self.assertEqual(extra["fine_overdue"], 0)
        self.assertEqual(extra["fine_condition"], 0)
        self.assertEqual(extra["status_penggantian"], "selesai")

        # Cek audit log
        audits = audit_repo.list_by_object(self.conn, "loan_items", item_id)
        resolve_audits = [a for a in audits if a["action"] == "RESOLVE_LOST_OR_DAMAGED"]
        self.assertEqual(len(resolve_audits), 1)

    def test_11_catalog_service_create_title_and_copies(self):
        """Memverifikasi pembuatan katalog dan penonaktifan eksemplar (P2-02)."""
        title = create_title_with_copies(
            self.conn,
            title_data={"judul": "Pemrograman Web Lanjut"},
            initial_copies=2,
            copy_base_data={"lokasi_rak": "Rak RPL-3"},
        )
        self.assertEqual(len(title["copy_ids"]), 2)

        # Tambah 2 eksemplar lagi
        new_ids = add_copies_to_title(self.conn, title_id=title["id"], count=2)
        self.assertEqual(len(new_ids), 2)

        # Cek total eksemplar tersedia = 4
        t_avail = catalog_repo.get_title_availability(self.conn, title["id"])[0]
        self.assertEqual(t_avail["available_copies"], 4)

        # Nonaktifkan 1 eksemplar
        ok = deactivate_copy(self.conn, copy_id=new_ids[0], reason="Halaman sobek")
        self.assertTrue(ok)

        t_avail_after = catalog_repo.get_title_availability(self.conn, title["id"])[0]
        self.assertEqual(t_avail_after["available_copies"], 3)
        self.assertEqual(t_avail_after["total_aktif"], 3)
        self.assertEqual(t_avail_after["total_semua"], 4)

    def test_12_deactivate_borrowed_copy_rejected(self):
        """Memverifikasi eksemplar yang sedang dipinjam aktif tidak dapat dinonaktifkan."""
        member = register_member(self.conn, nama="Peminjam Uji", category_id="MC-MURID")
        title = create_title_with_copies(
            self.conn, title_data={"judul": "Kamus Jepang-Indonesia"}, initial_copies=1
        )
        c_id = title["copy_ids"][0]

        borrow_copies(self.conn, member_id=member["id"], copy_ids=[c_id])

        with self.assertRaises(InvalidOperationError) as ctx:
            deactivate_copy(self.conn, copy_id=c_id, reason="Penarikan buku")
        self.assertIn("sedang dipinjam", str(ctx.exception))

    def test_13_member_service_deactivate_and_reactivate(self):
        """Memverifikasi penonaktifan dan pengaktifan kembali anggota (DEC-020)."""
        member = register_member(self.conn, nama="Joko Susilo", category_id="MC-MURID")
        m_id = member["id"]

        # Nonaktifkan
        deactivate_member(self.conn, member_id=m_id, reason="Cuti 1 semester")
        self.assertEqual(member_repo.get_member_by_id(self.conn, m_id)["status"], "nonaktif")

        # Aktifkan kembali
        reactivate_member(self.conn, member_id=m_id, reason="Selesai cuti")
        self.assertEqual(member_repo.get_member_by_id(self.conn, m_id)["status"], "aktif")

    def test_14_audit_log_rollback_when_service_transaction_fails(self):
        """Memverifikasi audit log yang dicatat dalam scope transaksi ikut ter-rollback jika terjadi error."""
        member = register_member(self.conn, nama="Tes Rollback Audit", category_id="MC-MURID")

        try:
            with transaction_scope(self.conn):
                audit_repo.record_audit(
                    self.conn,
                    actor="test_admin",
                    action="TRANSIENT_ACTION",
                    object_type="members",
                    object_id=member["id"],
                    reason="Aksi sementara yang akan gagal",
                )
                # Simulasikan kegagalan
                raise RuntimeError("Kegagalan yang disengaja dalam blok transaksi!")
        except RuntimeError:
            pass

        # Pastikan audit log untuk TRANSIENT_ACTION tidak pernah tersimpan di database
        audits = audit_repo.list_by_object(self.conn, "members", member["id"])
        transient_audits = [a for a in audits if a["action"] == "TRANSIENT_ACTION"]
        self.assertEqual(len(transient_audits), 0)


if __name__ == "__main__":
    unittest.main()

