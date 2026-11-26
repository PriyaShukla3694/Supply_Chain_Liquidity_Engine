from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.user import User
from app.schemas.discount import DiscountRecommendationsResponse
from app.schemas.discount_offer import DiscountOfferCreate, DiscountOfferResponse
from app.services.discount_optimizer import generate_discount_recommendations
from app.services.discount_offer_service import create_discount_offer, approve_discount_offer, reject_discount_offer

router = APIRouter(prefix="/discounts", tags=["Discounts"])


@router.get(
    "/recommendations",
    response_model=DiscountRecommendationsResponse,
    summary="Generate Discount Recommendations",
    description=(
        "Generate read-only, company-scoped discount recommendations. "
        "Does not create or persist discount offers."
    ),
)
def get_discount_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager")
    ),
):
    if current_user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a company.",
        )

    return generate_discount_recommendations(
        db=db,
        company_id=current_user.company_id,
    )


@router.post(
    "/offers",
    response_model=DiscountOfferResponse,
    summary="Create Discount Offer",
    description="Create and persist a discount offer after reΓÇævalidating eligibility and budget constraints.",
)
def create_offer(
    payload: DiscountOfferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager")
    ),
):
    if current_user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a company.",
        )
    try:
        offer = create_discount_offer(
            db=db,
            company_id=current_user.company_id,
            invoice_id=payload.invoice_id,
            buyer_id=payload.buyer_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return offer

@router.put(
    "/offers/{offer_id}/approve",
    response_model=DiscountOfferResponse,
    summary="Approve Discount Offer",
    description="Approve a recommended discount offer. Only admin and finance_manager roles may perform this action.",
)
def approve_offer(
    offer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    if current_user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a company.",
        )
    try:
        offer = approve_discount_offer(
            db=db,
            company_id=current_user.company_id,
            offer_id=offer_id,
            approver_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return offer

@router.put(
    "/offers/{offer_id}/reject",
    response_model=DiscountOfferResponse,
    summary="Reject Discount Offer",
    description="Reject a recommended discount offer. Only admin and finance_manager roles may perform this action.",
)
def reject_offer(
    offer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "finance_manager")),
):
    if current_user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a company.",
        )
    try:
        offer = reject_discount_offer(
            db=db,
            company_id=current_user.company_id,
            offer_id=offer_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return offer
