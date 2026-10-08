from typing import Any, Dict
from sqlalchemy.orm import Session
from app.models.business_rule import BusinessRule


DEFAULT_BUSINESS_RULES: Dict[str, Any] = {
    "discount_eligibility": {
        "min_invoice_amount": 50000.0,
        "min_days_to_due": 10,
        "excluded_buyer_statuses": ["blacklisted", "disputed"],
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


def get_business_rule(db: Session, rule_key: str) -> Any:
    """
    Reads dynamic business rule configuration from the database.
    Falls back to default rule values if the rule is not yet seeded.
    """
    rule_record = db.query(BusinessRule).filter(
        BusinessRule.rule_key == rule_key
    ).first()

    if rule_record is not None:
        return rule_record.rule_value

    return DEFAULT_BUSINESS_RULES.get(rule_key)


def set_business_rule(
    db: Session,
    rule_key: str,
    rule_value: Any,
    updated_by: str = "system",
    description: str | None = None,
) -> BusinessRule:
    """
    Upserts a business rule record in the database.
    """
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
    db: Session,
    updated_by: str = "system",
) -> None:
    """
    Seeds initial default business rules into the database if missing.
    """
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