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
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.unit
def test_fallback_to_default_business_rules(db_session):
    rule = get_business_rule(db_session, "discount_eligibility")
    assert rule["min_invoice_amount"] == 50000.0
    assert rule["min_days_to_due"] == 10


@pytest.mark.unit
def test_seed_default_business_rules(db_session):
    seed_default_business_rules(db_session)
    rules_in_db = db_session.query(BusinessRule).all()
    assert len(rules_in_db) == len(DEFAULT_BUSINESS_RULES)


@pytest.mark.unit
def test_set_and_get_business_rule_override(db_session):
    new_threshold = {"min_invoice_amount": 50000.0, "min_days_to_due": 7}
    set_business_rule(db_session, "discount_eligibility", new_threshold, updated_by="admin")

    updated_rule = get_business_rule(db_session, "discount_eligibility")
    assert updated_rule["min_invoice_amount"] == 50000.0
    assert updated_rule["min_days_to_due"] == 7
