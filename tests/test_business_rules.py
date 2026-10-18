
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.business_rule import BusinessRule
from app.core.business_rules import (
    get_business_rule,
    set_business_rule,
    seed_default_business_rules,
    DEFAULT_BUSINESS_RULES,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.mark.unit
def test_fallback_to_default_business_rules(db_session):
    rule = get_business_rule(db_session, "discount_eligibility")

    assert rule["min_invoice_amount"] == 50000.0
    assert rule["min_days_to_due"] == 10
    assert rule["excluded_buyer_statuses"] == ["blacklisted"]


@pytest.mark.unit
def test_seed_default_business_rules(db_session):
    seed_default_business_rules(db_session)

    rules_in_db = db_session.query(BusinessRule).all()

    assert len(rules_in_db) == len(DEFAULT_BUSINESS_RULES)


@pytest.mark.unit
def test_set_and_get_business_rule_override(db_session):
    new_threshold = {
        "min_invoice_amount": 50000.0,
        "min_days_to_due": 7,
    }

    set_business_rule(
        db_session,
        "discount_eligibility",
        new_threshold,
        updated_by="admin",
    )

    updated_rule = get_business_rule(db_session, "discount_eligibility")

    assert updated_rule["min_invoice_amount"] == 50000.0
    assert updated_rule["min_days_to_due"] == 7


@pytest.mark.unit
def test_business_rules_financial_thresholds_in_inr():
    """Verify financial thresholds are expressed in INR."""
    eligibility = DEFAULT_BUSINESS_RULES["discount_eligibility"]
    assert eligibility["min_invoice_amount"] == 50000.0

    approval = DEFAULT_BUSINESS_RULES["human_approval_thresholds"]
    assert approval["max_discount_amount"] == 1000.0
    assert approval["max_invoice_amount"] == 100000.0

    budget = DEFAULT_BUSINESS_RULES["weekly_budget_formula"]
    assert budget["pct_of_eligible_invoice_value"] == 0.015
    assert budget["min_budget"] == 30000.0
    assert budget["max_budget"] == 100000.0


@pytest.mark.unit
def test_tier_max_discounts_keys_standardised():
    discounts = DEFAULT_BUSINESS_RULES["tier_max_discounts"]

    assert "A" in discounts
    assert "B" in discounts
    assert "C" in discounts
    assert "C_urgent_max" in discounts

    assert discounts["A"] == 0.015
    assert discounts["B"] == 0.01
    assert discounts["C"] == 0.005
    assert discounts["C_urgent_max"] == 0.01
