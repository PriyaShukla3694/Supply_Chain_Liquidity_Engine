
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.core.business_rules import (
    get_business_rule,
    is_invoice_discount_eligible,
    calculate_discount_amounts,
    is_human_approval_required,
)
from app.core.clock import business_today
from app.models.buyer import Buyer
from app.models.discount_offer import DiscountOffer
from app.models.forecast import Forecast
from app.models.invoice import Invoice
from app.models.supplier import Supplier


ACTIVE_BUDGET_STATUSES = ("recommended", "offered", "accepted")
CENT = Decimal("0.01")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _week_bounds(today: date) -> tuple[date, date]:
    week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)


def _get_company_urgency(
    db: Session,
    company_id: int,
    today: date,
) -> bool:
    """Use the latest forecast available on or before the business date."""
    forecast = (
        db.query(Forecast)
        .filter(
            Forecast.company_id == company_id,
            Forecast.forecast_date <= today,
        )
        .order_by(Forecast.forecast_date.desc(), Forecast.id.desc())
        .first()
    )

    return bool(forecast and forecast.status == "URGENT")


def _get_tier_cap(
    tier: str,
    urgent: bool,
    tier_rules: dict,
) -> Decimal:
    normalized_tier = (tier or "").strip().upper()

    if normalized_tier == "A":
        value = tier_rules.get("A", 0.015)
    elif normalized_tier == "B":
        value = tier_rules.get("B", 0.01)
    elif normalized_tier == "C":
        value = (
            tier_rules.get("C_urgent_max", 0.01)
            if urgent
            else tier_rules.get("C", 0.005)
        )
    else:
        value = 0

    return _decimal(value)


def _get_cooldown_buyers(
    db: Session,
    company_id: int,
    today: date,
    cooldown_days: int,
) -> set[str]:
    cutoff = today - timedelta(days=cooldown_days)

    rows = (
        db.query(DiscountOffer.buyer_id)
        .join(Invoice, DiscountOffer.invoice_id == Invoice.invoice_id)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
        .filter(
            Supplier.company_id == company_id,
            DiscountOffer.offer_date >= cutoff,
            DiscountOffer.offer_date <= today,
            DiscountOffer.status.in_(ACTIVE_BUDGET_STATUSES),
        )
        .distinct()
        .all()
    )

    return {row[0] for row in rows}


def _get_existing_weekly_allocation(
    db: Session,
    company_id: int,
    week_start: date,
    week_end: date,
) -> Decimal:
    total = (
        db.query(DiscountOffer.discount_amount)
        .join(Invoice, DiscountOffer.invoice_id == Invoice.invoice_id)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
        .filter(
            Supplier.company_id == company_id,
            DiscountOffer.offer_date >= week_start,
            DiscountOffer.offer_date <= week_end,
            DiscountOffer.status.in_(ACTIVE_BUDGET_STATUSES),
        )
        .all()
    )

    return sum((_decimal(row[0]) for row in total), Decimal("0.00"))


def generate_discount_recommendations(
    db: Session,
    company_id: int,
) -> dict:
    """
    Generate company-scoped discount recommendations without persisting offers.
    """

    today = business_today()
    week_start, week_end = _week_bounds(today)

    eligibility_rules = get_business_rule(db, "discount_eligibility") or {}
    tier_rules = get_business_rule(db, "tier_max_discounts") or {}
    approval_rules = get_business_rule(db, "human_approval_thresholds") or {}
    budget_rules = get_business_rule(db, "weekly_budget_formula") or {}
    cooldown_days = int(
        get_business_rule(db, "buyer_offer_cooldown_days") or 14
    )

    urgent = _get_company_urgency(db, company_id, today)

    invoices = (
        db.query(Invoice, Buyer)
        .join(Buyer, Invoice.buyer_id == Buyer.buyer_id)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
        .filter(
            Supplier.company_id == company_id,
            Invoice.invoice_status == "open",
        )
        .all()
    )

    cooldown_buyers = _get_cooldown_buyers(
        db, company_id, today, cooldown_days
    )

    candidates = []
    eligible_invoice_total = Decimal("0.00")
    excluded = []

    min_amount = _decimal(
        eligibility_rules.get("min_invoice_amount", 50000)
    )
    min_days = int(eligibility_rules.get("min_days_to_due", 10))

    for invoice, buyer in invoices:
        days_until_due = (invoice.due_date - today).days

        eligible, reasons = is_invoice_discount_eligible(
            invoice_amount_inr=invoice.invoice_amount,
            days_until_due=days_until_due,
            is_disputed=invoice.disputed or buyer.disputed_flag,
            invoice_status=invoice.invoice_status,
            buyer_tier=buyer.tier or "",
            is_urgent=urgent,
            min_amount_thresh=min_amount,
        )

        if buyer.blacklisted:
            reasons.append("buyer_blacklisted")
            eligible = False

        if days_until_due < min_days:
            eligible = False
            if "days_until_due_less_than_10" not in reasons:
                reasons.append("days_until_due_less_than_10")

        if buyer.buyer_id in cooldown_buyers:
            reasons.append("buyer_cooldown_active")
            eligible = False

        if not eligible:
            excluded.append({
                "invoice_id": invoice.invoice_id,
                "buyer_id": buyer.buyer_id,
                "reasons": reasons,
            })
            continue

        tier_cap = _get_tier_cap(buyer.tier or "", urgent, tier_rules)

        if tier_cap <= 0:
            excluded.append({
                "invoice_id": invoice.invoice_id,
                "buyer_id": buyer.buyer_id,
                "reasons": ["invalid_or_missing_buyer_tier"],
            })
            continue

        eligible_invoice_total += _decimal(invoice.invoice_amount)

        candidates.append({
            "invoice": invoice,
            "buyer": buyer,
            "days_until_due": days_until_due,
            "tier_cap": tier_cap,
        })

    budget_pct = _decimal(
        budget_rules.get("pct_of_eligible_invoice_value", 0.015)
    )
    min_budget = _decimal(budget_rules.get("min_budget", 30000))
    max_budget = _decimal(budget_rules.get("max_budget", 100000))

    calculated_budget = (
        eligible_invoice_total * budget_pct
    ).quantize(CENT, rounding=ROUND_HALF_UP)

    weekly_budget = min(max(calculated_budget, min_budget), max_budget)

    existing_allocation = _get_existing_weekly_allocation(
        db, company_id, week_start, week_end
    )

    remaining_budget = max(
        Decimal("0.00"),
        weekly_budget - existing_allocation,
    )

    # Earlier due dates first; responsiveness is a tie-breaker.
    candidates.sort(
        key=lambda item: (
            item["days_until_due"],
            -float(item["buyer"].discount_responsiveness or 0),
            item["invoice"].invoice_id,
        )
    )

    recommendations = []

    for item in candidates:
        invoice = item["invoice"]
        buyer = item["buyer"]
        tier_cap = item["tier_cap"]

        # Rates are selected in 0.5 percentage-point increments.
        rate = (
            (tier_cap / Decimal("0.005")).to_integral_value(
                rounding=ROUND_HALF_UP
            ) * Decimal("0.005")
        )

        rate = min(rate, tier_cap)

        amounts = calculate_discount_amounts(
            invoice_amount_inr=invoice.invoice_amount,
            discount_rate=rate,
        )

        discount_amount = amounts["discount_amount"]

        if discount_amount > remaining_budget:
            excluded.append({
                "invoice_id": invoice.invoice_id,
                "buyer_id": buyer.buyer_id,
                "reasons": ["weekly_budget_exhausted"],
            })
            continue

        requires_approval = is_human_approval_required(
            invoice_amount_inr=invoice.invoice_amount,
            discount_amount_inr=discount_amount,
            max_discount_thresh=approval_rules.get("max_discount_amount"),
            max_invoice_thresh=approval_rules.get("max_invoice_amount"),
        )

        recommendations.append({
            "invoice_id": invoice.invoice_id,
            "buyer_id": buyer.buyer_id,
            "invoice_amount": amounts["invoice_amount"],
            "days_until_due": item["days_until_due"],
            "buyer_tier": buyer.tier,
            "offered_rate_pct": rate,
            "discount_amount": discount_amount,
            "net_payable_if_accepted": amounts[
                "net_payable_if_accepted"
            ],
            "requires_approval": requires_approval,
            "status": "recommended",
        })

        remaining_budget -= discount_amount

    return {
        "business_date": today,
        "week_start": week_start,
        "week_end": week_end,
        "is_urgent": urgent,
        "eligible_invoice_value": eligible_invoice_total,
        "weekly_budget": weekly_budget,
        "existing_allocation": existing_allocation,
        "new_recommendation_total": sum(
            (item["discount_amount"] for item in recommendations),
            Decimal("0.00"),
        ),
        "remaining_budget": remaining_budget,
        "recommendations": recommendations,
        "excluded_invoices": excluded,
    }
