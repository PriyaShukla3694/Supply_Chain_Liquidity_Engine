from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.business_rule import BusinessRule


DEFAULT_BUSINESS_RULES: Dict[str, Any] = {
    "discount_eligibility": {
        "min_invoice_amount": 50000.0,
        "min_days_to_due": 10,
        "excluded_buyer_statuses": ["blacklisted"],
    },
    "tier_max_discounts": {
        "A": 0.015,
        "B": 0.01,
        "C": 0.005,
        "C_urgent_max": 0.01,
    },
    "human_approval_thresholds": {
        "max_discount_amount": 1000.0,
        "max_invoice_amount": 100000.0,
    },
    "weekly_budget_formula": {
        "pct_of_eligible_invoice_value": 0.015,
        "min_budget": 30000.0,
        "max_budget": 100000.0,
    },
    "buyer_offer_cooldown_days": 14,
}


def get_business_rule(db: "Session", rule_key: str) -> Any:
    """
    Reads dynamic business rule configuration from the database.
    Falls back to default rule values if the rule is not yet seeded.
    """
    from app.models.business_rule import BusinessRule

    rule_record = db.query(BusinessRule).filter(
        BusinessRule.rule_key == rule_key
    ).first()

    if rule_record is not None:
        return rule_record.rule_value

    return DEFAULT_BUSINESS_RULES.get(rule_key)


def set_business_rule(
    db: "Session",
    rule_key: str,
    rule_value: Any,
    updated_by: str = "system",
    description: str | None = None,
) -> "BusinessRule":
    """
    Upserts a business rule record in the database.
    """
    from app.models.business_rule import BusinessRule

    rule_record = db.query(BusinessRule).filter(
        BusinessRule.rule_key == rule_key
    ).first()

    if rule_record:
        rule_record.rule_value = rule_value
        rule_record.updated_by = updated_by

        if description:
            rule_record.description = description
    else:
        rule_record = BusinessRule(
            rule_key=rule_key,
            rule_value=rule_value,
            updated_by=updated_by,
            description=description,
        )
        db.add(rule_record)

    db.commit()
    db.refresh(rule_record)

    return rule_record


def seed_default_business_rules(
    db: "Session",
    updated_by: str = "system",
) -> None:
    """
    Seeds initial default business rules into the database if missing.
    """
    from app.models.business_rule import BusinessRule

    for key, val in DEFAULT_BUSINESS_RULES.items():
        existing = db.query(BusinessRule).filter(
            BusinessRule.rule_key == key
        ).first()

        if not existing:
            db.add(
                BusinessRule(
                    rule_key=key,
                    rule_value=val,
                    updated_by=updated_by,
                )
            )

    db.commit()


def is_invoice_discount_eligible(
    invoice_amount_inr: Any,
    days_until_due: int,
    is_disputed: bool,
    invoice_status: str,
    buyer_tier: str = "Tier-B",
    is_urgent: bool = False,
    min_amount_thresh: Any = None,
) -> Tuple[bool, List[str]]:
    """Evaluates whether an invoice qualifies for a discount offer strictly in INR.

    Conditions from business rules:
    1. invoice_status == 'open'
    2. days_until_due >= 10
    3. is_disputed is False
    4. invoice_amount_inr >= 50,000 INR
    5. Buyer tier allows discounts: Tier A and Tier B eligible;
       Tier C excluded unless is_urgent is True.
    """
    reasons: List[str] = []

    if invoice_status.strip().lower() != "open":
        reasons.append("invoice_not_open")

    if days_until_due < 10:
        reasons.append("days_until_due_less_than_10")

    if is_disputed:
        reasons.append("invoice_disputed")

    threshold = (
        Decimal(str(min_amount_thresh))
        if min_amount_thresh is not None
        else Decimal(str(DEFAULT_BUSINESS_RULES["discount_eligibility"]["min_invoice_amount"]))
    )
    amt = Decimal(str(invoice_amount_inr))
    if amt < threshold:
        reasons.append("amount_below_minimum_threshold")

    norm_tier = buyer_tier.strip()
    if norm_tier in ("Tier-C", "C") and not is_urgent:
        reasons.append("tier_c_ineligible_without_urgency")

    return len(reasons) == 0, reasons


def calculate_discount_amounts(
    invoice_amount_inr: Any,
    discount_rate: Any,
) -> Dict[str, Decimal]:
    """Calculates discount_amount and net_payable_if_accepted strictly in INR.

    discount_amount = invoice_amount_inr * discount_rate
    net_payable = invoice_amount_inr - discount_amount
    """
    amt = Decimal(str(invoice_amount_inr))
    rate = Decimal(str(discount_rate))
    disc = (amt * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = (amt - disc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "invoice_amount": amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "discount_amount": disc,
        "net_payable_if_accepted": net,
        "offered_rate_pct": rate,
    }


def is_human_approval_required(
    invoice_amount_inr: Any,
    discount_amount_inr: Any,
    max_discount_thresh: Any = None,
    max_invoice_thresh: Any = None,
) -> bool:
    """Checks human approval governance in INR:

    Requires approval when:
    discount_amount > ₹1,000 OR invoice_amount > ₹100,000
    """
    disc_thresh = (
        Decimal(str(max_discount_thresh))
        if max_discount_thresh is not None
        else Decimal(str(DEFAULT_BUSINESS_RULES["human_approval_thresholds"]["max_discount_amount"]))
    )
    inv_thresh = (
        Decimal(str(max_invoice_thresh))
        if max_invoice_thresh is not None
        else Decimal(str(DEFAULT_BUSINESS_RULES["human_approval_thresholds"]["max_invoice_amount"]))
    )
    amt = Decimal(str(invoice_amount_inr))
    disc = Decimal(str(discount_amount_inr))
    return bool(disc > disc_thresh or amt > inv_thresh)
