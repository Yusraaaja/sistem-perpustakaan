# -*- coding: utf-8 -*-
"""
Paket Business Service Layer Sistem Perpustakaan Digital Skema v2.
Memenuhi Sub-Fase 2B, DEC-004, DEC-005, DEC-006, DEC-007, DEC-019, DEC-020, DEC-023, DEC-024.
"""

from .exceptions import (
    ServiceError,
    ValidationError,
    MemberNotFoundError,
    MemberInactiveError,
    CopyNotFoundError,
    CopyNotAvailableError,
    LoanNotFoundError,
    LoanItemNotFoundError,
    LoanItemAlreadyReturnedError,
    LoanExtensionLimitReachedError,
    InvalidOperationError,
)
from .transaction import transaction_scope
from .member_service import (
    validate_member_for_borrowing,
    register_member,
    deactivate_member,
    reactivate_member,
)
from .catalog_service import (
    create_title_with_copies,
    add_copies_to_title,
    deactivate_copy,
    get_title_with_details,
)
from .loan_service import (
    borrow_copies,
    return_copies,
    extend_loan,
    resolve_lost_or_damaged,
)

__all__ = [
    # Exceptions
    "ServiceError",
    "ValidationError",
    "MemberNotFoundError",
    "MemberInactiveError",
    "CopyNotFoundError",
    "CopyNotAvailableError",
    "LoanNotFoundError",
    "LoanItemNotFoundError",
    "LoanItemAlreadyReturnedError",
    "LoanExtensionLimitReachedError",
    "InvalidOperationError",
    # Transaction
    "transaction_scope",
    # Member Service
    "validate_member_for_borrowing",
    "register_member",
    "deactivate_member",
    "reactivate_member",
    # Catalog Service
    "create_title_with_copies",
    "add_copies_to_title",
    "deactivate_copy",
    "get_title_with_details",
    # Loan Service
    "borrow_copies",
    "return_copies",
    "extend_loan",
    "resolve_lost_or_damaged",
]

