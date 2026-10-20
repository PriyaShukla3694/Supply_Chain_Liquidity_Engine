from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.payment import (
    PaymentCreate,
    PaymentRead,
    PaymentUpdate,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


def _log_audit(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
) -> None:
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
    )
    db.add(audit)


@router.get(
    "",
    response_model=PaginatedResponse[PaymentRead],
    summary="List Payments",
    description="Retrieve paginated list of payments with optional filtering by invoice_id, status, and payment_date range.",
)
def list_payments(
    invoice_id: Optional[int] = Query(None, description="Filter by invoice ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (completed, pending, failed, refunded)"),
    from_date: Optional[date] = Query(None, description="Filter payments on or after date"),
    to_date: Optional[date] = Query(None, description="Filter payments on or before date"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.invoice_id)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
    )

    if current_user.company_id:
        query = query.filter(Supplier.company_id == current_user.company_id)

    if invoice_id is not None:
        query = query.filter(Payment.invoice_id == invoice_id)

    if status_filter:
        query = query.filter(Payment.status == status_filter.strip().lower())

    if from_date is not None:
        query = query.filter(Payment.payment_date >= from_date)

    if to_date is not None:
        query = query.filter(Payment.payment_date <= to_date)

    total = query.count()
    items = (
        query.order_by(Payment.payment_date.desc(), Payment.payment_id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return PaginatedResponse(
        items=[PaymentRead.model_validate(p) for p in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    summary="Get Single Payment",
    description="Retrieve payment details by payment ID scoped to user company.",
)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.invoice_id)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
    )
    if current_user.company_id:
        query = query.filter(Supplier.company_id == current_user.company_id)

    payment = query.filter(Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found",
        )

    return PaymentRead.model_validate(payment)


@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record Payment",
    description="Record a new payment for an open or settled invoice. If completed payment equals invoice amount, triggers settlement.",
)
def create_payment(
    payment_in: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    # Validate invoice exists and belongs to company
    invoice_query = (
        db.query(Invoice)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
        .filter(Invoice.invoice_id == payment_in.invoice_id)
    )
    if current_user.company_id:
        invoice_query = invoice_query.filter(Supplier.company_id == current_user.company_id)

    invoice = invoice_query.first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{payment_in.invoice_id}' not found",
        )

    # Validate invoice status
    if invoice.invoice_status not in ("open", "settled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot record payment for invoice with status '{invoice.invoice_status}'. Invoice must be open or settled.",
        )

    # Validate payment date
    if payment_in.payment_date < invoice.invoice_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payment_date cannot be earlier than invoice_date",
        )

    # Settlement trigger check
    settlement_triggered = False
    if payment_in.status == "completed" and invoice.invoice_status == "open":
        if payment_in.payment_amount == invoice.invoice_amount:
            days_diff = (payment_in.payment_date - invoice.due_date).days
            days_late = max(0, days_diff)
            is_late = days_diff > 0

            invoice.invoice_status = "settled"
            invoice.settled_date = payment_in.payment_date
            invoice.days_late = days_late
            invoice.is_late = is_late
            settlement_triggered = True

            _log_audit(
                db=db,
                user_id=current_user.id,
                action="settle",
                entity_type="invoice",
                entity_id=str(invoice.invoice_id),
                payload={
                    "settled_date": payment_in.payment_date.isoformat(),
                    "days_late": days_late,
                    "is_late": is_late,
                    "trigger": "payment_recording",
                },
            )

    payment = Payment(
        invoice_id=payment_in.invoice_id,
        payment_date=payment_in.payment_date,
        payment_amount=payment_in.payment_amount,
        payment_method=payment_in.payment_method,
        reference_number=payment_in.reference_number,
        status=payment_in.status,
        discount_applied=payment_in.discount_applied,
    )
    db.add(payment)
    db.flush()

    # Automatically generate transaction record for audit and tracking
    txn = Transaction(
        payment_id=payment.payment_id,
        transaction_type="credit",
        amount=payment.payment_amount,
        transaction_date=datetime.now(timezone.utc),
        currency="INR",
        description=f"Payment for invoice #{invoice.invoice_id}",
        status="settled" if payment.status == "completed" else "pending" if payment.status == "pending" else "failed",
    )
    db.add(txn)

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="create",
        entity_type="payment",
        entity_id=str(payment.payment_id),
        payload={
            "invoice_id": payment.invoice_id,
            "payment_amount": str(payment.payment_amount),
            "payment_date": payment.payment_date.isoformat(),
            "status": payment.status,
            "settlement_triggered": settlement_triggered,
        },
    )

    db.commit()
    db.refresh(payment)
    return PaymentRead.model_validate(payment)


@router.patch(
    "/{payment_id}",
    response_model=PaymentRead,
    summary="Update Payment Status",
    description="Update status and details of an existing payment. If status updated to completed and equals invoice amount, triggers invoice settlement.",
)
def update_payment(
    payment_id: int,
    payment_update: PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    query = (
        db.query(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.invoice_id)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
    )
    if current_user.company_id:
        query = query.filter(Supplier.company_id == current_user.company_id)

    payment = query.filter(Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found",
        )

    invoice = payment.invoice
    old_values = {
        "status": payment.status,
        "payment_method": payment.payment_method,
        "reference_number": payment.reference_number,
        "discount_applied": str(payment.discount_applied),
    }

    new_values = {}
    settlement_triggered = False

    if payment_update.status is not None:
        new_status = payment_update.status
        # If status changes to completed, check for invoice settlement trigger
        if new_status == "completed" and payment.status != "completed" and invoice.invoice_status == "open":
            if payment.payment_amount == invoice.invoice_amount:
                days_diff = (payment.payment_date - invoice.due_date).days
                days_late = max(0, days_diff)
                is_late = days_diff > 0

                invoice.invoice_status = "settled"
                invoice.settled_date = payment.payment_date
                invoice.days_late = days_late
                invoice.is_late = is_late
                settlement_triggered = True

                _log_audit(
                    db=db,
                    user_id=current_user.id,
                    action="settle",
                    entity_type="invoice",
                    entity_id=str(invoice.invoice_id),
                    payload={
                        "settled_date": payment.payment_date.isoformat(),
                        "days_late": days_late,
                        "is_late": is_late,
                        "trigger": "payment_status_update",
                        "payment_id": str(payment.payment_id),
                    },
                )
        payment.status = new_status
        new_values["status"] = new_status

    if payment_update.payment_method is not None:
        payment.payment_method = payment_update.payment_method
        new_values["payment_method"] = payment_update.payment_method

    if payment_update.reference_number is not None:
        payment.reference_number = payment_update.reference_number
        new_values["reference_number"] = payment_update.reference_number

    if payment_update.discount_applied is not None:
        payment.discount_applied = payment_update.discount_applied
        new_values["discount_applied"] = str(payment_update.discount_applied)

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="update",
        entity_type="payment",
        entity_id=str(payment.payment_id),
        payload={
            "previous": old_values,
            "changes": new_values,
            "settlement_triggered": settlement_triggered,
        },
    )

    db.commit()
    db.refresh(payment)
    return PaymentRead.model_validate(payment)


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Delete Payment (Forbidden)",
    description="Hard deletion of payments is prohibited for financial compliance and audit trail integrity.",
)
def delete_payment(
    payment_id: int,
    current_user: User = Depends(require_roles("admin")),
):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Hard deletion of payments is not permitted.",
    )
