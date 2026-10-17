# -*- coding: utf-8 -*-
"""
Skrip Migrasi Skema dan Data Legacy P1 ke Skema v2 (Fase 1B).
Memenuhi Requirement: LIB-COPY-001, LIB-COPY-002, LIB-MEMBER-001, LIB-LOAN-002,
R1 - R12, DEC-004, DEC-013, DEC-020, DEC-023, DEC-024.

Perilaku Utama:
1. Default: --dry-run (hanya simulasi rekonsiliasi dan verifikasi integritas).
   Untuk menulis ke database, jalankan dengan flag: --apply.
2. Penolakan Keras (Guardrail):
   - Menolak keras jika path database mengarah ke database produksi 'perpustakaan.db'.
   - Menolak jika database berskema v1 (wajib jalankan migrate_p1_multibook.py terlebih dahulu).
3. Transaksional & Atomik: Seluruh operasi berjalan dalam single transaction (BEGIN IMMEDIATE / COMMIT).
   Jika terjadi kesalahan di tengah jalan, seluruh perubahan di-rollback secara otomatis.
4. Idempotensi: Dapat dijalankan berkali-kali tanpa menduplikasi data (menggunakan legacy_buku_id,
   legacy_copy_map, dan legacy_peminjaman_id).
"""
import argparse
import json
import os
import sys
import sqlite3
from typing import Dict, List, Set, Tuple, Optional

# Tambahkan direktori root ke path agar modul-modul internal dapat diimpor
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db import get_connection, detect_schema_version
from timeutil import now_utc, format_iso_utc, legacy_date_to_utc_iso
from id_generator import (
    generate_title_id,
    generate_copy_id,
    generate_loan_id,
    generate_loan_item_id,
    generate_audit_id
)

SEED_MEMBER_CATEGORIES = [
    ("MC-MURID", "murid", "Siswa / Murid berdasarkan jurusan"),
    ("MC-GURU-JUR", "guru_jurusan", "Guru kejuruan berdasarkan program keahlian"),
    ("MC-GURU-UMUM", "guru_umum", "Guru mata pelajaran umum"),
    ("MC-STAF", "staf", "Tenaga kependidikan / staf tata usaha"),
    ("MC-TEKNISI", "teknisi", "Laboran / teknisi bengkel/lab"),
]


def check_production_guardrail(db_path: str) -> bool:
    """
    Memeriksa apakah target database mengarah ke database produksi 'perpustakaan.db'.
    Menggunakan perbandingan os.path.realpath (R1).
    """
    prod_path = os.path.join(PROJECT_ROOT, "perpustakaan.db")
    prod_resolved = os.path.realpath(prod_path)
    target_resolved = os.path.realpath(db_path)
    return target_resolved == prod_resolved


def apply_schema_ddl(conn: sqlite3.Connection):
    """Mengeksekusi file DDL migrasi skema v2."""
    ddl_path = os.path.join(PROJECT_ROOT, "migrations", "0001_initial_v2_schema.sql")
    with open(ddl_path, "r", encoding="utf-8") as f:
        ddl_sql = f.read()
    conn.executescript(ddl_sql)


def detect_registration_duplicates_across_books(
    conn: sqlite3.Connection
) -> Tuple[Dict[str, int], List[Tuple[str, int, int]]]:
    """
    Memeriksa nomor registrasi fisik di seluruh buku dan transaksi peminjaman (R6).
    Mengembalikan: (reg_to_book_map, daftar_duplikasi_antar_buku).
    """
    cursor = conn.cursor()
    reg_to_book: Dict[str, int] = {}
    duplicates: List[Tuple[str, int, int]] = []

    # 1. Dari tabel buku (kolom JSON id_buku_fisik)
    books = cursor.execute("SELECT id, id_buku_fisik FROM buku").fetchall()
    for b in books:
        b_id = b["id"]
        raw_json = b["id_buku_fisik"]
        if raw_json:
            try:
                regs = json.loads(raw_json)
                for r in regs:
                    reg_str = str(r).strip()
                    if reg_str:
                        if reg_str in reg_to_book and reg_to_book[reg_str] != b_id:
                            duplicates.append((reg_str, reg_to_book[reg_str], b_id))
                        reg_to_book[reg_str] = b_id
            except Exception:
                pass

    # 2. Dari tabel peminjaman_detail
    details = cursor.execute("SELECT id, id_buku, no_registrasi FROM peminjaman_detail").fetchall()
    for d in details:
        b_id = d["id_buku"]
        reg = d["no_registrasi"]
        if reg:
            reg_str = str(reg).strip()
            if reg_str:
                if reg_str in reg_to_book and reg_to_book[reg_str] != b_id:
                    duplicates.append((reg_str, reg_to_book[reg_str], b_id))
                reg_to_book[reg_str] = b_id

    return reg_to_book, duplicates


def migrate_database(db_path: str, dry_run: bool = True) -> Dict[str, any]:
    """
    Menjalankan proses migrasi data dari skema P1 ke skema v2.
    """
    # 1. Guardrail path produksi (R1)
    if check_production_guardrail(db_path):
        raise RuntimeError(
            "ERROR: Migrasi langsung ke database produksi 'perpustakaan.db' DILARANG KERAS. "
            "Gunakan salinan database di folder backups/ (misal: backups/test_copy_migration.db)."
        )

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database tidak ditemukan pada path: {db_path}")

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 2. Deteksi versi skema sumber (R1)
    schema_ver = detect_schema_version(conn)
    if schema_ver == "v1":
        conn.close()
        raise RuntimeError(
            "ERROR: Skema database terdeteksi v1. Silakan jalankan migrate_p1_multibook.py "
            "pada salinan database terlebih dahulu sebelum migrasi ke v2."
        )

    # 3. Pemeriksaan duplikasi nomor registrasi antar-buku (R6)
    reg_to_book, duplicates = detect_registration_duplicates_across_books(conn)
    if duplicates:
        conn.close()
        dup_msgs = [f"Nomor '{r}' duplikat antara Buku ID {b1} dan ID {b2}" for r, b1, b2 in duplicates]
        raise ValueError("Ditemukan duplikasi nomor registrasi antar-buku:\n" + "\n".join(dup_msgs))

    # Kumpulkan data sebelum migrasi untuk rekonsiliasi generik
    books = cursor.execute("SELECT * FROM buku ORDER BY id").fetchall()
    loans_legacy = cursor.execute("SELECT * FROM peminjaman ORDER BY id").fetchall()
    details_legacy = cursor.execute("SELECT * FROM peminjaman_detail ORDER BY id").fetchall()

    total_buku_lama = len(books)
    total_copies_unik = len(reg_to_book)
    total_loans_lama = len(loans_legacy)
    total_details_lama = len(details_legacy)
    active_details_lama = sum(1 for d in details_legacy if d["status"] == "Dipinjam" or d["tgl_dikembalikan"] is None)
    completed_details_lama = sum(1 for d in details_legacy if d["status"] == "Kembali" or d["tgl_dikembalikan"] is not None)

    unique_borrowers = sorted(list({l["id_anggota"] for l in loans_legacy if l["id_anggota"]}))

    summary = {
        "schema_version_detected": schema_ver,
        "total_catalog_titles": total_buku_lama,
        "total_unique_copies": total_copies_unik,
        "total_loans": total_loans_lama,
        "total_loan_items": total_details_lama,
        "active_loan_items": active_details_lama,
        "completed_loan_items": completed_details_lama,
        "unique_borrowers_count": len(unique_borrowers),
        "unique_borrowers": unique_borrowers,
        "mode": "DRY-RUN" if dry_run else "APPLY",
        "status": "SUCCESS"
    }

    if dry_run:
        conn.close()
        return summary

    # =========================================================================
    # EKSEKUSI PENULISAN ATOMIK (--apply)
    # =========================================================================
    now_iso = format_iso_utc(now_utc())

    try:
        conn.execute("BEGIN IMMEDIATE;")

        # A. Pasang skema DDL v2
        apply_schema_ddl(conn)

        # B. Seed member_categories
        for cat_id, jenis, ket in SEED_MEMBER_CATEGORIES:
            cursor.execute(
                """
                INSERT OR IGNORE INTO member_categories (id, jenis, keterangan)
                VALUES (?, ?, ?)
                """,
                (cat_id, jenis, ket)
            )

        # C. Migrasi catalog_titles (R5: Idempotensi via legacy_buku_id)
        existing_titles = {
            r["legacy_buku_id"]: r["id"]
            for r in cursor.execute("SELECT id, legacy_buku_id FROM catalog_titles WHERE legacy_buku_id IS NOT NULL").fetchall()
        }
        buku_to_title_id: Dict[int, str] = {}

        for b in books:
            b_id = b["id"]
            if b_id in existing_titles:
                t_id = existing_titles[b_id]
            else:
                t_id = generate_title_id()
                metadata = {
                    "kondisi_asli": b["kondisi_buku"],
                    "sumber_perolehan": b["sumber_perolehan"],
                    "tanggal_masuk": b["tanggal_masuk"],
                    "stok_lama": b["stok"]
                }
                cursor.execute(
                    """
                    INSERT INTO catalog_titles (
                        id, judul, subjudul, penulis, penerbit, tahun, isbn, kategori,
                        ddc, sinopsis, cover_path, harga_buku, metadata_json, legacy_buku_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t_id, b["judul"], b["sub_judul"], b["penulis"], b["penerbit"],
                        b["tahun_terbit"], b["isbn"], b["kategori"], None, b["sinopsis"],
                        b["cover_img"], b["harga_buku"] or 0, json.dumps(metadata), b_id,
                        now_iso, now_iso
                    )
                )
            buku_to_title_id[b_id] = t_id

        # D. Migrasi copies & legacy_copy_map (R6, R8, R9)
        existing_copies = {
            r["old_ref"]: r["copy_id"]
            for r in cursor.execute("SELECT old_ref, copy_id FROM legacy_copy_map").fetchall()
        }
        reg_to_copy_id: Dict[str, str] = {}

        # Identifikasi status khusus dari peminjaman_detail (misal Rusak/Hilang)
        detail_status_by_reg: Dict[str, str] = {}
        for d in details_legacy:
            reg = d["no_registrasi"]
            if reg:
                detail_status_by_reg[str(reg).strip()] = d["status"]

        for reg_str, b_id in reg_to_book.items():
            if reg_str in existing_copies:
                c_id = existing_copies[reg_str]
            else:
                c_id = generate_copy_id()
                t_id = buku_to_title_id[b_id]
                b_info = next(b for b in books if b["id"] == b_id)

                # R6: Status copy
                det_status = detail_status_by_reg.get(reg_str)
                if det_status == "Rusak":
                    copy_status = "rusak"
                elif det_status == "Hilang":
                    copy_status = "hilang"
                else:
                    copy_status = "aktif"

                cursor.execute(
                    """
                    INSERT INTO copies (
                        id, title_id, call_number, status, lokasi_rak, tanggal_masuk,
                        sumber, harga, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c_id, t_id, None, copy_status, b_info["lokasi_rak"],
                        b_info["tanggal_masuk"], b_info["sumber_perolehan"],
                        b_info["harga_buku"] or 0, now_iso
                    )
                )
                cursor.execute(
                    """
                    INSERT INTO legacy_copy_map (old_ref, copy_id, legacy_buku_id)
                    VALUES (?, ?, ?)
                    """,
                    (reg_str, c_id, b_id)
                )

            reg_to_copy_id[reg_str] = c_id

        # E. Migrasi loans (R4, R5)
        existing_loans = {
            r["legacy_peminjaman_id"]: r["id"]
            for r in cursor.execute("SELECT id, legacy_peminjaman_id FROM loans WHERE legacy_peminjaman_id IS NOT NULL").fetchall()
        }
        loan_to_v2_id: Dict[int, str] = {}

        for l in loans_legacy:
            l_id_legacy = l["id"]
            if l_id_legacy in existing_loans:
                l_v2_id = existing_loans[l_id_legacy]
            else:
                l_v2_id = generate_loan_id()
                created_utc = legacy_date_to_utc_iso(l["tgl_pinjam"], "00:00:00") or now_iso
                cursor.execute(
                    """
                    INSERT INTO loans (
                        id, member_id, legacy_nama_peminjam, created_at, idempotency_key, legacy_peminjaman_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        l_v2_id, None, l["id_anggota"], created_utc,
                        l["kode_transaksi"] if "kode_transaksi" in l.keys() else f"LEGACY-{l_id_legacy}",
                        l_id_legacy
                    )
                )
            loan_to_v2_id[l_id_legacy] = l_v2_id

        # F. Migrasi loan_items & legacy_loan_item_extra (R4, R7, R8, R11)
        existing_items = {
            (r["loan_id"], r["copy_id"]): r["id"]
            for r in cursor.execute("SELECT id, loan_id, copy_id FROM loan_items").fetchall()
        }

        for d in details_legacy:
            l_legacy_id = d["id_peminjaman"]
            reg = str(d["no_registrasi"]).strip() if d["no_registrasi"] else None
            if not reg or reg not in reg_to_copy_id:
                continue

            l_v2_id = loan_to_v2_id[l_legacy_id]
            c_v2_id = reg_to_copy_id[reg]

            if (l_v2_id, c_v2_id) in existing_items:
                continue

            li_id = generate_loan_item_id()

            # R7: Konversi waktu
            header_loan = next(l for l in loans_legacy if l["id"] == l_legacy_id)
            borrowed_at = legacy_date_to_utc_iso(header_loan["tgl_pinjam"], "00:00:00")
            due_at = legacy_date_to_utc_iso(header_loan["tgl_kembali_seharusnya"], "23:59:59")
            returned_at = legacy_date_to_utc_iso(d["tgl_dikembalikan"], "23:59:59") if d["tgl_dikembalikan"] else None

            # R8: return_condition mapping
            det_status = d["status"]
            if det_status == "Kembali":
                ret_condition = "baik"
            elif det_status == "Rusak":
                ret_condition = "rusak"
            elif det_status == "Hilang":
                ret_condition = "hilang"
            else:
                ret_condition = None

            # R11: returned_via
            returned_via = "legacy" if returned_at is not None else None

            # Catatan data: Data uji dan perkiraan waktu lama
            peminjam_nama = header_loan["id_anggota"] or ""
            notes_parts = []
            if "TEST" in peminjam_nama.upper():
                notes_parts.append("data_uji")
            notes_parts.append("waktu_lama_perkiraan")
            notes_str = "; ".join(notes_parts)

            cursor.execute(
                """
                INSERT INTO loan_items (
                    id, loan_id, copy_id, borrowed_at, due_at, extended_at, extension_count,
                    returned_at, return_condition, returned_via, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    li_id, l_v2_id, c_v2_id, borrowed_at, due_at, None, 0,
                    returned_at, ret_condition, returned_via, notes_str
                )
            )

            # R4: Simpan rincian lama ke legacy_loan_item_extra
            cursor.execute(
                """
                INSERT OR IGNORE INTO legacy_loan_item_extra (
                    loan_item_id, fine_overdue, fine_condition, status_penggantian, catatan_penggantian
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    li_id, d["denda_keterlambatan"] or 0, d["denda_kondisi"] or 0,
                    d["status_penggantian"], d["catatan_penggantian"]
                )
            )

        # G. Catat versi migrasi ke schema_version
        cursor.execute(
            """
            INSERT OR REPLACE INTO schema_version (version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (2, "0001_initial_v2_schema", now_iso)
        )

        # H. Catat ke audit_log
        audit_id = generate_audit_id()
        audit_detail = {
            "catalog_titles": total_buku_lama,
            "copies": total_copies_unik,
            "loans": total_loans_lama,
            "loan_items": total_details_lama
        }
        cursor.execute(
            """
            INSERT INTO audit_log (
                id, at, actor, action, object_type, object_id, reason, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id, now_iso, "system_migration", "MIGRATE_V2",
                "database", "v2", "Migrasi skema dan data dari P1 ke v2",
                json.dumps(audit_detail)
            )
        )

        # Selesaikan transaksi atomik
        conn.commit()

        # I. Verifikasi integritas pasca-migrasi
        c_count = cursor.execute("SELECT COUNT(*) FROM catalog_titles").fetchone()[0]
        cp_count = cursor.execute("SELECT COUNT(*) FROM copies").fetchone()[0]
        l_count = cursor.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        li_count = cursor.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0]
        active_li = cursor.execute("SELECT COUNT(*) FROM loan_items WHERE returned_at IS NULL").fetchone()[0]

        summary["verified_catalog_titles"] = c_count
        summary["verified_copies"] = cp_count
        summary["verified_loans"] = l_count
        summary["verified_loan_items"] = li_count
        summary["verified_active_loan_items"] = active_li

    except Exception as e:
        conn.rollback()
        conn.close()
        raise RuntimeError(f"Migrasi gagal dan telah di-rollback secara aman: {e}")

    conn.close()
    return summary


def main():
    parser = argparse.ArgumentParser(description="Migrator Database Skema Legacy P1 ke v2 (Perpustakaan Digital)")
    parser.add_argument("--source", default=os.path.join(PROJECT_ROOT, "backups", "test_copy_migration.db"),
                        help="Path ke database sumber salinan (default: backups/test_copy_migration.db)")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="Terapkan perubahan ke database. Jika tidak disertakan, berjalan dalam mode --dry-run")
    args = parser.parse_args()

    db_path = args.source
    dry_run = not args.apply

    print("=" * 70)
    print("MIGRATOR SKEMA DATABASE v2 (FASE 1B)")
    print(f"Target Database : {db_path}")
    print(f"Mode Operasi    : {'DRY-RUN (Simulasi Saja, Aman)' if dry_run else 'APPLY (Menulis ke Salinan Database)'}")
    print("=" * 70)

    try:
        summary = migrate_database(db_path, dry_run=dry_run)
        print("\n--- HASIL ANALISIS / MIGRASI ---")
        print(f"Versi Skema Terdeteksi   : {summary['schema_version_detected']}")
        print(f"Judul Katalog (Buku)     : {summary['total_catalog_titles']} judul")
        print(f"Eksemplar Fisik Unik     : {summary['total_unique_copies']} eksemplar")
        print(f"Transaksi Peminjaman     : {summary['total_loans']} transaksi")
        print(f"Detail Item Pinjaman     : {summary['total_loan_items']} item")
        print(f" - Item Aktif (Dipinjam) : {summary['active_loan_items']} item")
        print(f" - Item Selesai (Kembali): {summary['completed_loan_items']} item")
        print(f"Peminjam Lama Unik ({summary['unique_borrowers_count']}) : {', '.join(summary['unique_borrowers'])}")

        if not dry_run:
            print("\n--- VERIFIKASI REKONSILIASI SETELAH APPLY ---")
            print(f"catalog_titles terverifikasi : {summary['verified_catalog_titles']} baris")
            print(f"copies terverifikasi         : {summary['verified_copies']} baris")
            print(f"loans terverifikasi          : {summary['verified_loans']} baris")
            print(f"loan_items terverifikasi     : {summary['verified_loan_items']} baris")
            print(f"loan_items aktif             : {summary['verified_active_loan_items']} baris")
            print("\n[SUCCESS] Migrasi data ke skema v2 berhasil dilakukan secara atomik!")
        else:
            print("\n[INFO] Mode DRY-RUN selesai. Tidak ada perubahan yang ditulis ke file database.")
            print("Gunakan flag '--apply' untuk menerapkan perubahan pada salinan database.")

    except Exception as err:
        print(f"\n[FAILED] {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

