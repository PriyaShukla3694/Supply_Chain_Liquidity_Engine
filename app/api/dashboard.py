
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.invoice import Invoice
from app.models.buyer import Buyer

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    today = date.today()

    eligible_query = db.query(Invoice).filter(
        Invoice.invoice_status == "open",
        Invoice.disputed.is_(False),
        Invoice.invoice_amount >= 50000,
        Invoice.due_date >= today,
    )

    eligible_invoices = [
        invoice
        for invoice in eligible_query.all()
        if (invoice.due_date - today).days >= 10
        and not (
            invoice.buyer
            and (
                invoice.buyer.blacklisted
                or invoice.buyer.tier == "C"
            )
        )
    ]

    eligible_value = sum(
        (Decimal(str(invoice.invoice_amount)) for invoice in eligible_invoices),
        Decimal("0.00"),
    )

    settled_count = db.query(Invoice).filter(
        Invoice.invoice_status == "settled"
    ).count()

    late_count = db.query(Invoice).filter(
        Invoice.invoice_status == "settled",
        Invoice.is_late.is_(True),
    ).count()

    buyers_query = db.query(Buyer)
    total_buyers = buyers_query.count()

    tier_counts = {
        tier: buyers_query.filter(Buyer.tier == tier).count()
        for tier in ("A", "B", "C")
    }

    budget = (
        min(max(eligible_value * Decimal("0.015"), Decimal("30000")), Decimal("100000"))
        if eligible_value > 0
        else Decimal("0.00")
    )

    return {
        "eligible_invoice_value": str(eligible_value),
        "eligible_invoice_count": len(eligible_invoices),
        "historical_late_rate": round(
            late_count / settled_count * 100, 2
        ) if settled_count else 0.0,
        "weekly_discount_budget": str(budget),
        "total_buyers": total_buyers,
        "buyer_tiers": {
            tier: {
                "count": count,
                "percentage": round(count / total_buyers * 100, 2)
                if total_buyers else 0.0,
            }
            for tier, count in tier_counts.items()
        },
        "currency": "INR",
    }


@router.get("/invoices")
def dashboard_invoices(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    today = date.today()

    invoices = (
        db.query(Invoice)
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []

    for invoice in invoices:
        days_until_due = (invoice.due_date - today).days
        buyer = invoice.buyer

        if invoice.invoice_status == "settled":
            eligibility_status = "Settled"
        elif invoice.disputed:
            eligibility_status = "Disputed"
        elif (
            invoice.invoice_amount < 50000
            or days_until_due < 10
            or (buyer and (buyer.blacklisted or buyer.tier == "C"))
        ):
            eligibility_status = "Ineligible"
        else:
            eligibility_status = "Eligible"

        amount = Decimal(str(invoice.invoice_amount))

        results.append({
            "invoice_id": invoice.invoice_id,
            "buyer_id": invoice.buyer_id,
            "invoice_amount": str(amount),
            "formatted_amount": f"₹{amount:,.2f}",
            "invoice_date": invoice.invoice_date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "days_until_due": days_until_due,
            "tier": buyer.tier if buyer else None,
            "invoice_status": invoice.invoice_status,
            "disputed": invoice.disputed,
            "eligibility_status": eligibility_status,
        })

    return results
