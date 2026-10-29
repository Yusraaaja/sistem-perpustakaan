# -*- coding: utf-8 -*-
"""
Paket Data Access Layer (Repository Layer) Skema v2.
Memenuhi Sub-Fase 2A, DEC-004, DEC-013, DEC-020, DEC-023, DEC-024.

Prinsip Utama:
1. Connection-Passing: Setiap fungsi menerima parameter `conn: sqlite3.Connection`.
2. No Implicit Commit: Repositori TIDAK melakukan `commit()` atau `rollback()`.
   Batas transaksi dipegang oleh pemanggil (Service Layer atau test case).
3. Parameterized Queries: Semua query menggunakan placeholder `?`.
4. Return DTO/Dict: Mengembalikan Python `dict` murni atau `list[dict]`.
5. Two-Layer ID Collision Retry: Kombinasi lookup cache set lokal + lookup database.
"""

from .catalog_repo import (
    exists_by_id as title_exists_by_id,
    create_title,
    get_title_by_id,
    get_title_by_legacy_id,
    list_titles,
    update_title,
    get_title_availability,
    list_all_titles_for_duplicate_check,
    escape_like_pattern,
    search_catalog_titles_with_availability,
    count_search_catalog_titles,
    get_catalog_metrics_v2,
)
from .copy_repo import (
    exists_by_id as copy_exists_by_id,
    create_copy,
    create_copies_batch,
    get_copy_by_id,
    list_copies_by_title,
    update_copy_status,
    update_copy_location,
    get_copy_availability,
    get_copy_by_legacy_ref,
    map_legacy_copy,
    get_copies_for_labels,
    get_unlabeled_candidate_copies,
)
from .member_repo import (
    exists_by_id as member_exists_by_id,
    category_exists,
    create_category,
    get_category_by_id,
    list_categories,
    seed_default_categories,
    create_member,
    get_member_by_id,
    list_members,
    count_members,
    get_member_summary_metrics,
    update_member_status,
    increment_qr_version,
)
from .loan_repo import (
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
)
from .audit_repo import (
    exists_by_id as audit_exists_by_id,
    record as record_audit,
    get_by_id as get_audit_by_id,
    list_by_object as list_audit_by_object,
    list_recent as list_recent_audits,
)

__all__ = [
    # Catalog
    "title_exists_by_id",
    "create_title",
    "get_title_by_id",
    "get_title_by_legacy_id",
    "list_titles",
    "update_title",
    "get_title_availability",
    # Copy
    "copy_exists_by_id",
    "create_copy",
    "create_copies_batch",
    "get_copy_by_id",
    "list_copies_by_title",
    "update_copy_status",
    "update_copy_location",
    "get_copy_availability",
    "get_copy_by_legacy_ref",
    "map_legacy_copy",
    "get_copies_for_labels",
    "get_unlabeled_candidate_copies",
    # Member
    "member_exists_by_id",
    "category_exists",
    "create_category",
    "get_category_by_id",
    "list_categories",
    "seed_default_categories",
    "create_member",
    "get_member_by_id",
    "list_members",
    "count_members",
    "get_member_summary_metrics",
    "update_member_status",
    "increment_qr_version",
    # Loan
    "loan_exists_by_id",
    "item_exists_by_id",
    "create_loan",
    "add_loan_item",
    "get_loan_by_id",
    "get_loan_items",
    "get_loan_with_items",
    "get_loan_item_by_id",
    "get_active_loan_by_copy",
    "return_loan_item",
    "extend_loan_item",
    "list_loans",
    "list_active_loan_items",
    "get_legacy_extra",
    "save_legacy_extra",
    # Audit
    "audit_exists_by_id",
    "record_audit",
    "get_audit_by_id",
    "list_audit_by_object",
    "list_recent_audits",
]

