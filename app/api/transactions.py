from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.transaction import TransactionRead

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get(
    "",
    response_model=PaginatedResponse[TransactionRead],
    summary="List Transactions (Read-Only)",
    description="Retrieve paginated list of transactions with optional filtering by payment_id, transaction_type, status, and date range.",
)
def list_transactions(
    payment_id: Optional[int] = Query(None, description="Filter by payment ID"),
    transaction_type: Optional[str] = Query(None, description="Filter by type (credit, debit)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (settled, pending, failed)"),
    from_date: Optional[datetime] = Query(None, description="Filter transactions on or after datetime"),
    to_date: Optional[datetime] = Query(None, description="Filter transactions on or before datetime"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Transaction)

    if current_user.company_id:
        query = (
            query.outerjoin(Payment, Transaction.payment_id == Payment.payment_id)
            .outerjoin(Invoice, Payment.invoice_id == Invoice.invoice_id)
            .outerjoin(Supplier, Invoice.supplier_id == Supplier.supplier_id)
            .filter(
                (Supplier.company_id == current_user.company_id)
                | (Transaction.payment_id.is_(None))
            )
        )

    if payment_id is not None:
        query = query.filter(Transaction.payment_id == payment_id)

    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type.strip().lower())

    if status_filter:
        query = query.filter(Transaction.status == status_filter.strip().lower())

    if from_date is not None:
        query = query.filter(Transaction.transaction_date >= from_date)

    if to_date is not None:
        query = query.filter(Transaction.transaction_date <= to_date)

    total = query.count()
    items = (
        query.order_by(Transaction.transaction_date.desc(), Transaction.transaction_id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return PaginatedResponse(
        items=[TransactionRead.model_validate(t) for t in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionRead,
    summary="Get Single Transaction (Read-Only)",
    description="Retrieve a single transaction record by ID.",
)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Transaction)
    if current_user.company_id:
        query = (
            query.outerjoin(Payment, Transaction.payment_id == Payment.payment_id)
            .outerjoin(Invoice, Payment.invoice_id == Invoice.invoice_id)
            .outerjoin(Supplier, Invoice.supplier_id == Supplier.supplier_id)
            .filter(
                (Supplier.company_id == current_user.company_id)
                | (Transaction.payment_id.is_(None))
            )
        )

    txn = query.filter(Transaction.transaction_id == transaction_id).first()
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found",
        )

    return TransactionRead.model_validate(txn)


@router.post(
    "",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Create Transaction (Forbidden)",
    description="Transactions are read-only ledger entries automatically generated from payments.",
)
def create_transaction_disallowed():
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Transactions are read-only.",
    )


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Delete Transaction (Forbidden)",
    description="Hard deletion of transactions is prohibited.",
)
def delete_transaction_disallowed(transaction_id: int):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Transactions are read-only.",
    )
