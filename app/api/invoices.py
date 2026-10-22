
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.core.clock import business_today
from app.models.audit_log import AuditLog
from app.models.buyer import Buyer
from app.models.invoice import Invoice
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.invoice import (
    BuyerSummary,
    InvoiceCreate,
    InvoiceDetailRead,
    InvoiceRead,
    InvoiceSettle,
    InvoiceSummary,
    InvoiceUpdate,
    MetricSummary,
    PaymentRead,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _enrich_invoice_read(
    invoice: Invoice,
    today: Optional[date] = None,
) -> InvoiceRead:
    """Computes days_until_due and overdue_days according to business rules."""
    if today is None:
        today = business_today()

    if invoice.invoice_status == "settled":
        days_until_due = None
        overdue_days = 0
    else:
        days_until_due = (invoice.due_date - today).days
        overdue_days = max(0, (today - invoice.due_date).days)

    read_model = InvoiceRead.model_validate(invoice)
    read_model.days_until_due = days_until_due
    read_model.overdue_days = overdue_days

    return read_model


def _enrich_invoice_detail(
    invoice: Invoice,
    today: Optional[date] = None,
) -> InvoiceDetailRead:
    """Computes maturity metrics and attaches buyer and payment details."""
    if today is None:
        today = business_today()

    if invoice.invoice_status == "settled":
        days_until_due = None
        overdue_days = 0
    else:
        days_until_due = (invoice.due_date - today).days
        overdue_days = max(0, (today - invoice.due_date).days)

    detail_model = InvoiceDetailRead.model_validate(invoice)
    detail_model.days_until_due = days_until_due
    detail_model.overdue_days = overdue_days

    if invoice.buyer:
        detail_model.buyer = BuyerSummary.model_validate(invoice.buyer)

    if invoice.payments:
        detail_model.payments = [
            PaymentRead.model_validate(payment)
            for payment in invoice.payments
        ]

    return detail_model


def _log_audit(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_id: str,
    payload: dict,
) -> None:
    """Writes an immutable audit log row for tracking state changes."""
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type="invoice",
        entity_id=str(entity_id),
        payload=payload,
    )
    db.add(audit)
    db.commit()


@router.get(
    "/summary",
    response_model=InvoiceSummary,
    summary="Get Invoices Summary",
    description=(
        "Returns aggregate counts and ₹ totals for open, overdue, settled, "
        "and disputed invoices scoped to the current user's company."
    ),
)
def get_invoices_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = business_today()

    stats = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.invoice_status == "open", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("open_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Invoice.invoice_status == "open",
                            Invoice.invoice_amount,
                        ),
                        else_=Decimal("0.00"),
                    )
                ),
                Decimal("0.00"),
            ).label("open_total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Invoice.invoice_status == "open")
                            & (Invoice.due_date < today),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("overdue_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (Invoice.invoice_status == "open")
                            & (Invoice.due_date < today),
                            Invoice.invoice_amount,
                        ),
                        else_=Decimal("0.00"),
                    )
                ),
                Decimal("0.00"),
            ).label("overdue_total"),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.invoice_status == "settled", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("settled_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Invoice.invoice_status == "settled",
                            Invoice.invoice_amount,
                        ),
                        else_=Decimal("0.00"),
                    )
                ),
                Decimal("0.00"),
            ).label("settled_total"),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.disputed.is_(True), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("disputed_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Invoice.disputed.is_(True),
                            Invoice.invoice_amount,
                        ),
                        else_=Decimal("0.00"),
                    )
                ),
                Decimal("0.00"),
            ).label("disputed_total"),
        )
        .select_from(Invoice)
        .join(
            Supplier,
            Invoice.supplier_id == Supplier.supplier_id,
        )
        .filter(Supplier.company_id == current_user.company_id)
        .first()
    )

    open_count = int(stats.open_count or 0)
    open_total = round(
        Decimal(str(stats.open_total or 0)),
        2,
    )

    overdue_count = int(stats.overdue_count or 0)
    overdue_total = round(
        Decimal(str(stats.overdue_total or 0)),
        2,
    )

    settled_count = int(stats.settled_count or 0)
    settled_total = round(
        Decimal(str(stats.settled_total or 0)),
        2,
    )

    disputed_count = int(stats.disputed_count or 0)
    disputed_total = round(
        Decimal(str(stats.disputed_total or 0)),
        2,
    )

    return InvoiceSummary(
        open=MetricSummary(
            count=open_count,
            total_amount=open_total,
        ),
        overdue=MetricSummary(
            count=overdue_count,
            total_amount=overdue_total,
        ),
        settled=MetricSummary(
            count=settled_count,
            total_amount=settled_total,
        ),
        disputed=MetricSummary(
            count=disputed_count,
            total_amount=disputed_total,
        ),
        open_count=open_count,
        open_total=open_total,
        overdue_count=overdue_count,
        overdue_total=overdue_total,
        settled_count=settled_count,
        settled_total=settled_total,
        disputed_count=disputed_count,
        disputed_total=disputed_total,
    )


@router.get(
    "",
    response_model=PaginatedResponse[InvoiceRead],
    summary="List Invoices",
    description=(
        "Lists invoices scoped to the current user's company with rich "
        "filtering, computed maturity dates, and pagination."
    ),
)
def list_invoices(
    buyer_id: Optional[str] = Query(None, description="Filter by buyer ID"),
    supplier_id: Optional[str] = Query(None, description="Filter by supplier ID"),
    invoice_status: Optional[str] = Query(
        None,
        description="Filter by status ('open' or 'settled')",
    ),
    is_late: Optional[bool] = Query(
        None,
        description="Filter by late settlement status",
    ),
    disputed: Optional[bool] = Query(
        None,
        description="Filter by dispute flag",
    ),
    invoice_date_from: Optional[date] = Query(
        None,
        description="Earliest invoice issue date",
    ),
    invoice_date_to: Optional[date] = Query(
        None,
        description="Latest invoice issue date",
    ),
    due_date_from: Optional[date] = Query(
        None,
        description="Earliest due date",
    ),
    due_date_to: Optional[date] = Query(
        None,
        description="Latest due date",
    ),
    min_amount: Optional[Decimal] = Query(
        None,
        description="Minimum invoice amount in INR",
    ),
    max_amount: Optional[Decimal] = Query(
        None,
        description="Maximum invoice amount in INR",
    ),
    sort_by: Optional[str] = Query(
        "invoice_date",
        description="Field to sort by: invoice_date, due_date, invoice_amount",
    ),
    order: Optional[str] = Query(
        "desc",
        description="Sort order: asc, desc",
    ),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Invoice)
        .join(
            Supplier,
            Invoice.supplier_id == Supplier.supplier_id,
        )
        .filter(Supplier.company_id == current_user.company_id)
    )

    if buyer_id:
        query = query.filter(Invoice.buyer_id == buyer_id.strip())

    if supplier_id:
        query = query.filter(Invoice.supplier_id == supplier_id.strip())

    if invoice_status is not None:
        clean_status = invoice_status.strip().lower()

        if clean_status not in ("open", "settled"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid invoice_status. Must be 'open' or 'settled'",
            )

        query = query.filter(Invoice.invoice_status == clean_status)

    if is_late is not None:
        query = query.filter(Invoice.is_late == is_late)

    if disputed is not None:
        query = query.filter(Invoice.disputed == disputed)

    if invoice_date_from is not None:
        query = query.filter(Invoice.invoice_date >= invoice_date_from)

    if invoice_date_to is not None:
        query = query.filter(Invoice.invoice_date <= invoice_date_to)

    if due_date_from is not None:
        query = query.filter(Invoice.due_date >= due_date_from)

    if due_date_to is not None:
        query = query.filter(Invoice.due_date <= due_date_to)

    if min_amount is not None:
        query = query.filter(Invoice.invoice_amount >= min_amount)

    if max_amount is not None:
        query = query.filter(Invoice.invoice_amount <= max_amount)

    allowed_sort = {
        "invoice_date": Invoice.invoice_date,
        "due_date": Invoice.due_date,
        "invoice_amount": Invoice.invoice_amount,
    }

    if sort_by not in allowed_sort:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid sort_by. Allowed values: "
                f"{', '.join(allowed_sort.keys())}"
            ),
        )

    clean_order = order.strip().lower() if order else "desc"

    if clean_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid order. Must be 'asc' or 'desc'",
        )

    sort_col = allowed_sort[sort_by]

    if clean_order == "desc":
        query = query.order_by(
            sort_col.desc(),
            Invoice.invoice_id.desc(),
        )
    else:
        query = query.order_by(
            sort_col.asc(),
            Invoice.invoice_id.asc(),
        )

    total = query.count()
    items = query.offset(pagination.offset).limit(pagination.limit).all()

    today = business_today()
    enriched_items = [
        _enrich_invoice_read(invoice, today)
        for invoice in items
    ]

    return PaginatedResponse[InvoiceRead](
        items=enriched_items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{invoice_id}",
    response_model=InvoiceDetailRead,
    summary="Get Invoice Detail",
    description=(
        "Retrieves invoice details including buyer summary, payments list, "
        "and computed maturity metrics."
    ),
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = (
        db.query(Invoice)
        .join(
            Supplier,
            Invoice.supplier_id == Supplier.supplier_id,
        )
        .filter(
            Invoice.invoice_id == invoice_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' not found",
        )

    return _enrich_invoice_detail(invoice)


@router.post(
    "",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Invoice",
    description=(
        "Creates a new invoice in 'open' status. Requires 'admin' or "
        "'finance_manager' role. Logs action in audit_logs."
    ),
)
def create_invoice(
    invoice_in: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    buyer = (
        db.query(Buyer)
        .filter(Buyer.buyer_id == invoice_in.buyer_id)
        .first()
    )

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Buyer '{invoice_in.buyer_id}' does not exist",
        )

    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_id == invoice_in.supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Supplier '{invoice_in.supplier_id}' "
                "does not exist in your company"
            ),
        )

    if invoice_in.invoice_id is not None:
        existing = (
            db.query(Invoice)
            .filter(Invoice.invoice_id == invoice_in.invoice_id)
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Invoice with ID {invoice_in.invoice_id} already exists",
            )

        new_id = invoice_in.invoice_id
    else:
        max_id = db.query(func.max(Invoice.invoice_id)).scalar() or 0
        new_id = max_id + 1

    invoice = Invoice(
        invoice_id=new_id,
        buyer_id=invoice_in.buyer_id,
        supplier_id=invoice_in.supplier_id,
        invoice_date=invoice_in.invoice_date,
        due_date=invoice_in.due_date,
        payment_terms_days=invoice_in.payment_terms_days,
        invoice_amount=invoice_in.invoice_amount,
        currency=invoice_in.currency,
        disputed=invoice_in.disputed,
        invoice_status="open",
        settled_date=None,
        days_late=None,
        is_late=None,
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="create",
        entity_id=str(invoice.invoice_id),
        payload={
            "buyer_id": invoice.buyer_id,
            "supplier_id": invoice.supplier_id,
            "invoice_amount": str(invoice.invoice_amount),
            "due_date": invoice.due_date.isoformat(),
            "payment_terms_days": invoice.payment_terms_days,
        },
    )

    return _enrich_invoice_read(invoice)


@router.patch(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="Update Invoice",
    description=(
        "Partially updates an invoice (disputed and amount only). Open "
        "invoices can be updated by admin/finance_manager. Settled invoices "
        "are immutable except by admin. Logs action in audit_logs."
    ),
)
def update_invoice(
    invoice_id: int,
    invoice_in: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    invoice = (
        db.query(Invoice)
        .join(
            Supplier,
            Invoice.supplier_id == Supplier.supplier_id,
        )
        .filter(
            Invoice.invoice_id == invoice_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' not found",
        )

    if (
        invoice.invoice_status == "settled"
        and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Settled invoices are immutable and can only be modified "
                "by an administrator"
            ),
        )

    update_data = invoice_in.model_dump(exclude_unset=True)

    if not update_data:
        return _enrich_invoice_read(invoice)

    old_values = {}
    new_values = {}

    for key, val in update_data.items():
        curr_val = getattr(invoice, key)
        old_values[key] = (
            str(curr_val) if isinstance(curr_val, Decimal) else curr_val
        )

        setattr(invoice, key, val)

        new_values[key] = (
            str(val) if isinstance(val, Decimal) else val
        )

    db.commit()
    db.refresh(invoice)

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="update",
        entity_id=str(invoice.invoice_id),
        payload={
            "previous": old_values,
            "changes": new_values,
        },
    )

    return _enrich_invoice_read(invoice)


@router.post(
    "/{invoice_id}/settle",
    response_model=InvoiceRead,
    summary="Mark Invoice Settled",
    description=(
        "Marks an open invoice as settled and computes days_late and "
        "is_late relative to due_date. Requires 'admin' or "
        "'finance_manager'. Logs action in audit_logs."
    ),
)
def settle_invoice(
    invoice_id: int,
    settle_in: InvoiceSettle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    invoice = (
        db.query(Invoice)
        .join(
            Supplier,
            Invoice.supplier_id == Supplier.supplier_id,
        )
        .filter(
            Invoice.invoice_id == invoice_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' not found",
        )

    if invoice.invoice_status == "settled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice '{invoice_id}' is already settled",
        )

    if settle_in.settled_date < invoice.invoice_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="settled_date cannot be earlier than invoice_date",
        )

    # Keep actual settlement date logic unchanged.
    days_diff = (settle_in.settled_date - invoice.due_date).days
    days_late = max(0, days_diff)
    is_late = days_diff > 0

    invoice.invoice_status = "settled"
    invoice.settled_date = settle_in.settled_date
    invoice.days_late = days_late
    invoice.is_late = is_late

    db.commit()
    db.refresh(invoice)

    _log_audit(
        db=db,
        user_id=current_user.id,
        action="settle",
        entity_id=str(invoice.invoice_id),
        payload={
            "settled_date": settle_in.settled_date.isoformat(),
            "days_late": days_late,
            "is_late": is_late,
        },
    )

    return _enrich_invoice_read(invoice)


@router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Delete Invoice (Forbidden)",
    description=(
        "Hard deletion of invoices is prohibited for regulatory compliance "
        "and audit trail integrity."
    ),
)
def delete_invoice(
    invoice_id: int,
    current_user: User = Depends(require_roles("admin")),
):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Hard deletion of invoices is not permitted.",
    )
