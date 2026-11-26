from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.business_rules import (
    get_business_rule,
    is_invoice_discount_eligible,
    calculate_discount_amounts,
    is_human_approval_required,
)
from app.core.clock import business_today
from app.models.discount_offer import DiscountOffer
from app.models.invoice import Invoice
from app.models.buyer import Buyer
from app.models.supplier import Supplier
from app.services.discount_optimizer import (
    _decimal,
    _week_bounds,
    _get_company_urgency,
    _get_tier_cap,
    _get_cooldown_buyers,
    _get_existing_weekly_allocation,
)

ACTIVE_BUDGET_STATUSES = ("recommended", "offered", "accepted")
CENT = Decimal("0.01")

def _generate_offer_id(invoice_id: int) -> str:
    """Deterministic offer id ΓÇô can be replaced with UUID later."""
    today = business_today()
    return f"OFF-{today:%Y%m%d}-{invoice_id}"

def create_discount_offer(db: Session, company_id: int, invoice_id: int, buyer_id: str) -> DiscountOffer:
    """Create and persist a DiscountOffer with full businessΓÇærule validation.

    Raises ``ValueError`` with a descriptive message on any rule violation; the FastAPI
    layer should convert this to an appropriate ``HTTPException``.
    """
    # 1. Load objects and verify company ownership
    invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")

    buyer = db.query(Buyer).filter(Buyer.buyer_id == buyer_id).first()
    if not buyer:
        raise ValueError(f"Buyer {buyer_id} not found")

    supplier = db.query(Supplier).filter(Supplier.supplier_id == invoice.supplier_id).first()
    if not supplier or supplier.company_id != company_id:
        raise ValueError("Invoice does not belong to the user's company")

    # 2. ReΓÇæevaluate eligibility (same rules as optimizer)
    today = business_today()
    days_until_due = (invoice.due_date - today).days

    eligibility_rules = get_business_rule(db, "discount_eligibility") or {}
    tier_rules = get_business_rule(db, "tier_max_discounts") or {}
    approval_rules = get_business_rule(db, "human_approval_thresholds") or {}
    budget_rules = get_business_rule(db, "weekly_budget_formula") or {}
    cooldown_days = int(get_business_rule(db, "buyer_offer_cooldown_days") or 14)

    urgent = _get_company_urgency(db, company_id, today)

    eligible, reasons = is_invoice_discount_eligible(
        invoice_amount_inr=invoice.invoice_amount,
        days_until_due=days_until_due,
        is_disputed=invoice.disputed or getattr(buyer, "disputed_flag", False),
        invoice_status=invoice.invoice_status,
        buyer_tier=buyer.tier or "",
        is_urgent=urgent,
        min_amount_thresh=_decimal(eligibility_rules.get("min_invoice_amount", 50000)),
    )

    if buyer.blacklisted:
        eligible = False
        reasons.append("buyer_blacklisted")
    if days_until_due < int(eligibility_rules.get("min_days_to_due", 10)):
        eligible = False
        if "days_until_due_less_than_10" not in reasons:
            reasons.append("days_until_due_less_than_10")

    # Cooldown check
    cooldown_buyers = _get_cooldown_buyers(db, company_id, today, cooldown_days)
    if buyer.buyer_id in cooldown_buyers:
        eligible = False
        reasons.append("buyer_cooldown_active")

    if not eligible:
        raise ValueError(f"Invoice {invoice_id} not eligible: {', '.join(reasons)}")

    # 3. Tier cap & discount rate (0.5ΓÇ»% increments)
    tier_cap = _get_tier_cap(buyer.tier or "", urgent, tier_rules)
    if tier_cap <= 0:
        raise ValueError("Buyer tier does not allow discounts")

    rate = (tier_cap / Decimal("0.005")).to_integral_value(rounding=ROUND_HALF_UP) * Decimal("0.005")
    rate = min(rate, tier_cap)

    amounts = calculate_discount_amounts(invoice_amount_inr=invoice.invoice_amount, discount_rate=rate)
    discount_amount = amounts["discount_amount"]

    # 4. Weekly budget validation
    week_start, week_end = _week_bounds(today)
    existing_allocation = _get_existing_weekly_allocation(db, company_id, week_start, week_end)
    budget_pct = _decimal(budget_rules.get("pct_of_eligible_invoice_value", 0.015))
    min_budget = _decimal(budget_rules.get("min_budget", 30000))
    max_budget = _decimal(budget_rules.get("max_budget", 100000))
    calculated_budget = (amounts["invoice_amount"] * budget_pct).quantize(CENT, rounding=ROUND_HALF_UP)
    weekly_budget = min(max(calculated_budget, min_budget), max_budget)
    remaining_budget = max(Decimal("0.00"), weekly_budget - existing_allocation)
    if discount_amount > remaining_budget:
        raise ValueError("Insufficient weekly budget for this offer")

    # 5. Prevent duplicate active offers for the same invoice
    duplicate = (
        db.query(DiscountOffer)
        .filter(
            DiscountOffer.invoice_id == invoice_id,
            DiscountOffer.status.in_(ACTIVE_BUDGET_STATUSES),
        )
        .first()
    )
    if duplicate:
        raise ValueError("An active discount offer already exists for this invoice")

    # 6. HumanΓÇæapproval flag
    requires_approval = is_human_approval_required(
        invoice_amount_inr=invoice.invoice_amount,
        discount_amount_inr=discount_amount,
        max_discount_thresh=approval_rules.get("max_discount_amount"),
        max_invoice_thresh=approval_rules.get("max_invoice_amount"),
    )

    # 7. Persist the offer
    offer = DiscountOffer(
        offer_id=_generate_offer_id(invoice_id),
        invoice_id=invoice_id,
        buyer_id=buyer_id,
        offer_date=today,
        deadline_date=today + timedelta(days=7),
        invoice_amount=amounts["invoice_amount"],
        offered_rate_pct=rate,
        discount_amount=discount_amount,
        net_payable_if_accepted=amounts["net_payable_if_accepted"],
        days_accelerated=0,
        status="offered" if not requires_approval else "recommended",
        recommended_by="optimizer",
        requires_approval=requires_approval,
        recommendation_payload={
            "invoice_id": invoice_id,
            "buyer_id": buyer_id,
            "offered_rate_pct": str(rate),
            "discount_amount": str(discount_amount),
            "net_payable_if_accepted": str(amounts["net_payable_if_accepted"]),
            "requires_approval": requires_approval,
        },
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer
def approve_discount_offer(db: Session, company_id: int, offer_id: str, approver_id: int) -> DiscountOffer:
    """Approve a recommended DiscountOffer.

    - Validates ownership via invoice ΓåÆ supplier ΓåÆ company.
    - Checks that the offer is in 'recommended' status, requires_approval is true, and not expired.
    - ReΓÇæevaluates eligibility and budget constraints to ensure the offer is still valid.
    - Updates status to 'offered', records approver and timestamp.
    """
    # Load offer with related invoice & supplier
    offer = (
        db.query(DiscountOffer)
        .filter(DiscountOffer.offer_id == offer_id)
        .first()
    )
    if not offer:
        raise ValueError("Discount offer not found")

    # Verify company ownership via supplier
    invoice = db.query(Invoice).filter(Invoice.invoice_id == offer.invoice_id).first()
    if not invoice:
        raise ValueError("Associated invoice not found")
    supplier = db.query(Supplier).filter(Supplier.supplier_id == invoice.supplier_id).first()
    if not supplier or supplier.company_id != company_id:
        raise ValueError("Offer does not belong to the user's company")

    # Status checks
    if offer.status != "recommended":
        raise ValueError("Only offers in 'recommended' status can be approved")
    if not offer.requires_approval:
        raise ValueError("Offer does not require approval")
    if offer.deadline_date < business_today():
        raise ValueError("Offer has expired and cannot be approved")

    # ReΓÇævalidate eligibility ΓÇô similar to creation logic
    buyer = db.query(Buyer).filter(Buyer.buyer_id == offer.buyer_id).first()
    if not buyer:
        raise ValueError("Buyer not found for offer")
    days_until_due = (invoice.due_date - business_today()).days
    eligibility_rules = get_business_rule(db, "discount_eligibility") or {}
    tier_rules = get_business_rule(db, "tier_max_discounts") or {}
    urgent = _get_company_urgency(db, company_id, business_today())
    eligible, _ = is_invoice_discount_eligible(
        invoice_amount_inr=invoice.invoice_amount,
        days_until_due=days_until_due,
        is_disputed=invoice.disputed or getattr(buyer, "disputed_flag", False),
        invoice_status=invoice.invoice_status,
        buyer_tier=buyer.tier or "",
        is_urgent=urgent,
        min_amount_thresh=_decimal(eligibility_rules.get("min_invoice_amount", 50000)),
    )
    if not eligible:
        raise ValueError("Offer no longer meets eligibility criteria")

    # Budget reΓÇæcheck (use same logic as creation)
    amounts = calculate_discount_amounts(invoice_amount_inr=invoice.invoice_amount, discount_rate=offer.offered_rate_pct)
    discount_amount = amounts["discount_amount"]
    budget_rules = get_business_rule(db, "weekly_budget_formula") or {}
    week_start, week_end = _week_bounds(business_today())
    existing_allocation = _get_existing_weekly_allocation(db, company_id, week_start, week_end)
    budget_pct = _decimal(budget_rules.get("pct_of_eligible_invoice_value", 0.015))
    min_budget = _decimal(budget_rules.get("min_budget", 30000))
    max_budget = _decimal(budget_rules.get("max_budget", 100000))
    calculated_budget = (amounts["invoice_amount"] * budget_pct).quantize(CENT, rounding=ROUND_HALF_UP)
    weekly_budget = min(max(calculated_budget, min_budget), max_budget)
    remaining_budget = max(Decimal("0.00"), weekly_budget - existing_allocation)
    if discount_amount > remaining_budget:
        raise ValueError("Insufficient weekly budget for this offer")

    # All checks passed ΓÇô update fields
    offer.status = "offered"
    offer.approved_by = approver_id
    offer.approved_at = datetime.utcnow()
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer

def reject_discount_offer(db: Session, company_id: int, offer_id: str) -> DiscountOffer:
    """Reject a recommended DiscountOffer.

    - Validates ownership.
    - Allows rejection when status is 'recommended' and not expired.
    - Updates status to 'rejected'.
    """
    offer = (
        db.query(DiscountOffer)
        .filter(DiscountOffer.offer_id == offer_id)
        .first()
    )
    if not offer:
        raise ValueError("Discount offer not found")

    invoice = db.query(Invoice).filter(Invoice.invoice_id == offer.invoice_id).first()
    if not invoice:
        raise ValueError("Associated invoice not found")
    supplier = db.query(Supplier).filter(Supplier.supplier_id == invoice.supplier_id).first()
    if not supplier or supplier.company_id != company_id:
        raise ValueError("Offer does not belong to the user's company")

    if offer.status != "recommended":
        raise ValueError("Only offers in 'recommended' status can be rejected")
    if offer.deadline_date < business_today():
        raise ValueError("Offer has expired and cannot be rejected")

    # No rejection reason field exists; simply change status
    offer.status = "rejected"
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer
