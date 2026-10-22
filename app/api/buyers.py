
from datetime import date
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
from app.schemas.buyer import (
    BuyerCreate,
    BuyerDetailRead,
    BuyerRead,
    BuyerUpdate,
)
from app.schemas.common import PaginatedResponse, PaginationParams
from app.services.buyer_scoring import (
    preview_buyer_score,
    calculate_and_persist_buyer_score,
)

router = APIRouter(prefix="/buyers", tags=["Buyers"])


def _compute_buyer_financials(
    db: Session, buyer_id: str
) -> tuple[int, Decimal]:
    """Compute invoice count and open exposure for a buyer."""
    invoice_count = (
        db.query(func.count(Invoice.invoice_id))
        .filter(Invoice.buyer_id == buyer_id)
        .scalar()
        or 0
    )

    open_exposure = (
        db.query(
            func.coalesce(
                func.sum(Invoice.invoice_amount),
                Decimal("0.00"),
            )
        )
        .filter(
            Invoice.buyer_id == buyer_id,
            Invoice.invoice_status == "open",
        )
        .scalar()
        or Decimal("0.00")
    )

    return invoice_count, round(Decimal(str(open_exposure)), 2)


def _get_company_buyer(
    db: Session,
    buyer_id: str,
    company_id: int,
) -> Optional[Buyer]:
    """Return a buyer only if its primary supplier belongs to the company."""
    return (
        db.query(Buyer)
        .join(Supplier, Buyer.primary_supplier_id == Supplier.supplier_id)
        .filter(
            Buyer.buyer_id == buyer_id,
            Supplier.company_id == company_id,
        )
        .first()
    )


@router.get(
    "",
    response_model=PaginatedResponse[BuyerRead],
    summary="List Buyers",
    description="List buyers scoped to the user's company with pagination and filters.",
)
def list_buyers(
    tier: Optional[str] = Query(None),
    behavioural_segment: Optional[str] = Query(None),
    blacklisted: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
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
                detail="Invalid tier filter. Must be 'A', 'B', or 'C'.",
            )
        query = query.filter(Buyer.tier == tier_clean)

    if behavioural_segment:
        query = query.filter(
            Buyer.behavioural_segment == behavioural_segment.strip()
        )

    if blacklisted is not None:
        query = query.filter(Buyer.blacklisted == blacklisted)

    if search:
        query = query.filter(
            Buyer.buyer_id.ilike(f"%{search.strip()}%")
        )

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
)
def get_buyer(
    buyer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    buyer = _get_company_buyer(
        db, buyer_id, current_user.company_id
    )

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Buyer '{buyer_id}' not found.",
        )

    invoice_count, open_exposure = _compute_buyer_financials(
        db, buyer_id
    )

    buyer_detail = BuyerDetailRead.model_validate(buyer)
    buyer_detail.invoice_count = invoice_count
    buyer_detail.open_exposure = open_exposure

    return buyer_detail


@router.get(
    "/{buyer_id}/score",
    summary="Get Buyer Score Preview",
    description="Return a read-only scoring preview.",
)
def get_buyer_score(
    buyer_id: str,
    as_of_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    buyer = _get_company_buyer(
        db, buyer_id, current_user.company_id
    )

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Buyer not found.",
        )

    try:
        return preview_buyer_score(
            db=db,
            buyer_id=buyer_id,
            as_of_date=as_of_date,
        )
    except ValueError as exc:
        if str(exc).startswith("Buyer not found:"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer not found.",
            ) from exc
        raise


@router.post(
    "/{buyer_id}/score",
    summary="Calculate and Persist Buyer Score",
    description="Persist one buyer's score. Requires admin or finance_manager.",
)
def calculate_and_persist_buyer_score_endpoint(
    buyer_id: str,
    as_of_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager")
    ),
):
    buyer = _get_company_buyer(
        db, buyer_id, current_user.company_id
    )

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Buyer not found.",
        )

    try:
        return calculate_and_persist_buyer_score(
            db=db,
            buyer_id=buyer_id,
            as_of_date=as_of_date,
        )
    except ValueError as exc:
        if str(exc).startswith("Buyer not found:"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer not found.",
            ) from exc
        raise


@router.post(
    "/scores/bulk",
    summary="Bulk Calculate Buyer Scores",
    description=(
        "Preview all company buyers by default. "
        "Persistence requires dry_run=false and an authorized role."
    ),
)
def bulk_calculate_buyer_scores(
    as_of_date: Optional[date] = Query(default=None),
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager")
    ),
):
    buyers = (
        db.query(Buyer)
        .join(Supplier, Buyer.primary_supplier_id == Supplier.supplier_id)
        .filter(Supplier.company_id == current_user.company_id)
        .order_by(Buyer.buyer_id)
        .all()
    )

    results = []
    previewed = 0
    processed = 0
    failed = 0

    for buyer in buyers:
        try:
            if dry_run:
                result = preview_buyer_score(
                    db=db,
                    buyer_id=buyer.buyer_id,
                    as_of_date=as_of_date,
                )
                previewed += 1
                item_status = "previewed"
            else:
                result = calculate_and_persist_buyer_score(
                    db=db,
                    buyer_id=buyer.buyer_id,
                    as_of_date=as_of_date,
                )
                processed += 1
                item_status = "processed"

            results.append({
                "buyer_id": buyer.buyer_id,
                "status": item_status,
                "result": result,
            })

        except Exception as exc:
            failed += 1

            # In write mode, avoid leaving the current failed transaction open.
            if not dry_run:
                db.rollback()

            results.append({
                "buyer_id": buyer.buyer_id,
                "status": "failed",
                "message": str(exc),
            })

    return {
        "dry_run": dry_run,
        "total": len(buyers),
        "previewed": previewed,
        "processed": processed,
        "failed": failed,
        "results": results,
    }


@router.post(
    "",
    response_model=BuyerDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Buyer",
    description="Create a buyer. Requires admin or finance_manager.",
)
def create_buyer(
    buyer_in: BuyerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager")
    ),
):
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
            detail=(
                f"Primary supplier '{buyer_in.primary_supplier_id}' "
                "not found in your company."
            ),
        )

    existing = (
        db.query(Buyer)
        .filter(Buyer.buyer_id == buyer_in.buyer_id)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Buyer '{buyer_in.buyer_id}' already exists.",
        )

    buyer = Buyer(**buyer_in.model_dump())
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
    description="Update a buyer. Requires admin or finance_manager.",
)
def update_buyer(
    buyer_id: str,
    buyer_in: BuyerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager")
    ),
):
    buyer = _get_company_buyer(
        db, buyer_id, current_user.company_id
    )

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Buyer '{buyer_id}' not found.",
        )

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
                detail=(
                    f"Primary supplier '{buyer_in.primary_supplier_id}' "
                    "not found in your company."
                ),
            )

    update_data = buyer_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(buyer, field, value)

    db.commit()
    db.refresh(buyer)

    invoice_count, open_exposure = _compute_buyer_financials(
        db, buyer_id
    )

    buyer_detail = BuyerDetailRead.model_validate(buyer)
    buyer_detail.invoice_count = invoice_count
    buyer_detail.open_exposure = open_exposure

    return buyer_detail


@router.delete(
    "/{buyer_id}",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    summary="Delete Buyer (Forbidden)",
    description="Hard delete is disabled to preserve financial and audit integrity.",
)
def delete_buyer(
    buyer_id: str,
    current_user: User = Depends(require_roles("admin")),
):
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=(
            "Hard deletion is not permitted. "
            "Use PATCH to set blacklisted=true instead."
        ),
    )
