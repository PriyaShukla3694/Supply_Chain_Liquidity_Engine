
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.buyer import Buyer
from app.services.buyer_scoring import preview_buyer_score

router = APIRouter(
    prefix="/buyers",
    tags=["Buyers"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_buyers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return buyer records for the directory. Read-only."""
    buyers = (
        db.query(Buyer)
        .order_by(Buyer.buyer_id.asc())
        .all()
    )

    return [
        {
            "buyer_id": buyer.buyer_id,
            "tier": buyer.tier,
            "credit_limit": (
                float(buyer.credit_limit)
                if buyer.credit_limit is not None
                else None
            ),
        }
        for buyer in buyers
    ]


@router.get("/{buyer_id}/score")
def get_buyer_score(
    buyer_id: str,
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a read-only buyer scoring preview."""
    try:
        return preview_buyer_score(
            db=db,
            buyer_id=buyer_id,
            as_of_date=as_of_date,
        )
    except ValueError as exc:
        if str(exc).startswith("Buyer not found:"):
            raise HTTPException(
                status_code=404,
                detail="Buyer not found",
            ) from exc
        raise
