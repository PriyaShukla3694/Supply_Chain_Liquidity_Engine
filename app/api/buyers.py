from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.models.buyer import Buyer
from app.models.invoice import Invoice
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.buyer import BuyerCreate, BuyerDetailRead, BuyerRead, BuyerUpdate
from app.schemas.common import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/buyers", tags=["Buyers"])


def _compute_buyer_financials(db: Session, buyer_id: str) -> tuple[int, Decimal]:
    """Computes invoice_count and open_exposure (sum of open invoices) for a given buyer."""
    invoice_count = (
        db.query(func.count(Invoice.invoice_id))
        .filter(Invoice.buyer_id == buyer_id)
        .scalar()
        or 0
    )
    open_exposure = (
        db.query(func.coalesce(func.sum(Invoice.invoice_amount), Decimal("0.00")))
        .filter(Invoice.buyer_id == buyer_id, Invoice.invoice_status == "open")
        .scalar()
        or Decimal("0.00")
    )
    return invoice_count, round(Decimal(str(open_exposure)), 2)


@router.get(
    "",
    response_model=PaginatedResponse[BuyerRead],
    summary="List Buyers",
    description="Lists buyers scoped to the user's company (via primary supplier) with pagination and filters.",
)
def list_buyers(
    tier: Optional[str] = Query(None, description="Filter by risk tier ('A', 'B', 'C')"),
    behavioural_segment: Optional[str] = Query(None, description="Filter by behavioural segment"),
    blacklisted: Optional[bool] = Query(None, description="Filter by blacklisted status"),
    search: Optional[str] = Query(None, description="Search by buyer ID"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Buyer)
        .join(Supplier, Buyer.primary_supplier_id == Supplier.supplier_id)
        .filter(Supplier.company_id == current_user.company_id)
    )

    if tier is not None:
        tier_clean = tier.strip().upper()
        if tier_clean not in ("A", "B", "C"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid tier filter. Must be 'A', 'B', or 'C'",
            )
        query = query.filter(Buyer.tier == tier_clean)

    if behavioural_segment:
        query = query.filter(Buyer.behavioural_segment == behavioural_segment.strip())

    if blacklisted is not None:
        query = query.filter(Buyer.blacklisted == blacklisted)

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(Buyer.buyer_id.ilike(search_pattern))

    total = query.count()
    items = (
        query.order_by(Buyer.buyer_id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return PaginatedResponse[BuyerRead](
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{buyer_id}",
    response_model=BuyerDetailRead,
    summary="Get Buyer Details",
    description="Retrieves buyer details including live computed invoice_count and open_exposure.",
)
def get_buyer(
    buyer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    buyer = (
        db.query(Buyer)
        .join(Supplier, Buyer.primary_supplier_id == Supplier.supplier_id)
        .filter(
            Buyer.buyer_id == buyer_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Buyer '{buyer_id}' not found",
        )

    invoice_count, open_exposure = _compute_buyer_financials(db, buyer_id)
    buyer_detail = BuyerDetailRead.model_validate(buyer)
    buyer_detail.invoice_count = invoice_count
    buyer_detail.open_exposure = open_exposure
    return buyer_detail


@router.post(
    "",
    response_model=BuyerDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Buyer",
    description="Creates a new buyer attached to a supplier in the current user's company. Requires 'admin' or 'finance_manager' role.",
)
def create_buyer(
    buyer_in: BuyerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    # Verify primary supplier exists and belongs to current user's company
    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_id == buyer_in.primary_supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Primary supplier '{buyer_in.primary_supplier_id}' not found in your company",
        )

    # Check for duplicate buyer_id
    existing = db.query(Buyer).filter(Buyer.buyer_id == buyer_in.buyer_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Buyer with ID '{buyer_in.buyer_id}' already exists",
        )

    buyer_data = buyer_in.model_dump()
    buyer = Buyer(**buyer_data)
    db.add(buyer)
    db.commit()
    db.refresh(buyer)

    buyer_detail = BuyerDetailRead.model_validate(buyer)
    buyer_detail.invoice_count = 0
    buyer_detail.open_exposure = Decimal("0.00")
    return buyer_detail


@router.patch(
    "/{buyer_id}",
    response_model=BuyerDetailRead,
    summary="Update Buyer",
    description="Partially updates an existing buyer. Requires 'admin' or 'finance_manager' role.",
)
def update_buyer(
    buyer_id: str,
    buyer_in: BuyerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    buyer = (
        db.query(Buyer)
        .join(Supplier, Buyer.primary_supplier_id == Supplier.supplier_id)
        .filter(
            Buyer.buyer_id == buyer_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Buyer '{buyer_id}' not found",
        )

    # If updating primary_supplier_id, ensure the target supplier belongs to user's company
    if buyer_in.primary_supplier_id is not None:
        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.supplier_id == buyer_in.primary_supplier_id,
                Supplier.company_id == current_user.company_id,
            )
            .first()
        )
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Primary supplier '{buyer_in.primary_supplier_id}' not found in your company",
            )

    update_data = buyer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(buyer, field, value)

    db.commit()
    db.refresh(buyer)

    invoice_count, open_exposure = _compute_buyer_financials(db, buyer_id)
    buyer_detail = BuyerDetailRead.model_validate(buyer)
    buyer_detail.invoice_count = invoice_count
    buyer_detail.open_exposure = open_exposure
    return buyer_detail


@router.delete(
    "/{buyer_id}",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Delete Buyer (Forbidden)",
    description="Hard delete is disabled to preserve financial and audit trail integrity. Use PATCH with blacklisted=true instead.",
)
def delete_buyer(
    buyer_id: str,
    current_user: User = Depends(require_roles("admin")),
):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Hard deletion of buyers is not permitted. Use PATCH to set blacklisted=true instead.",
    )
