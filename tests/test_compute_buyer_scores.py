from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base
from app.models.buyer import Buyer
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.risk_score import RiskScore
from app.models.supplier import Supplier
from app.services.buyer_scoring import (
    assign_tier,
    calculate_financial_score,
    calculate_liquidity_score,
    calculate_overall_score,
    calculate_reliability_score,
    get_business_as_of_date,
    preview_buyer_score,
)
from scripts.compute_buyer_scores import compute_all_buyer_scores


@pytest.fixture
def scoring_db():
    """Isolated SQLite database for scoring tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    company = Company(id=1, name="Test Company", industry="Manufacturing")
    session.add(company)
    session.commit()

    supplier = Supplier(
        supplier_id="SUPP-TEST",
        name="Primary Supplier",
        company_id=1,
        is_active=True,
    )
    session.add(supplier)
    session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.mark.unit
def test_scores_always_within_0_to_100():
    """All individual and overall scores must be bounded strictly between 0 and 100."""
    reliability_test_cases = [
        (0.0, 0, 0.0),
        (1.0, 100, 1.0),
        (0.5, 7.5, 0.5),
        (0.2, 3, 0.2),
        (0.0, 50, 1.0),
        (1.0, 0, 0.0),
    ]

    for late_rate, avg_days, late_last5 in reliability_test_cases:
        rel = calculate_reliability_score(late_rate, avg_days, late_last5)
        assert 0.0 <= rel <= 100.0, f"Reliability score {rel} out of bounds [0, 100]"

    financial_inputs = [
        (0, 100000),
        (50000, 100000),
        (100000, 100000),
        (200000, 100000),  # open exposure exceeds credit limit
    ]
    for exposure, limit in financial_inputs:
        fin = calculate_financial_score(exposure, limit)
        assert 0.0 <= fin <= 100.0, f"Financial score {fin} out of bounds [0, 100]"

    liquidity_inputs = [
        (0, 0),
        (0, 50000),
        (25000, 50000),
        (50000, 50000),
    ]
    for overdue, exposure in liquidity_inputs:
        liq = calculate_liquidity_score(overdue, exposure)
        assert 0.0 <= liq <= 100.0, f"Liquidity score {liq} out of bounds [0, 100]"

    for r in [0.0, 25.0, 50.0, 80.0, 100.0]:
        for f in [0.0, 25.0, 50.0, 80.0, 100.0]:
            for l in [0.0, 25.0, 50.0, 80.0, 100.0]:
                ovr = calculate_overall_score(r, f, l)
                assert 0.0 <= ovr <= 100.0, f"Overall score {ovr} out of bounds [0, 100]"


@pytest.mark.unit
def test_tier_boundaries_at_80_and_50():
    """Tier boundaries must be exactly at 80 (A vs B) and 50 (B vs C)."""
    assert assign_tier(100.0) == "A"
    assert assign_tier(80.0001) == "A"
    assert assign_tier(80.0) == "A"
    assert assign_tier(79.9999) == "B"
    assert assign_tier(79.9) == "B"
    assert assign_tier(50.0001) == "B"
    assert assign_tier(50.0) == "B"
    assert assign_tier(49.9999) == "C"
    assert assign_tier(49.9) == "C"
    assert assign_tier(0.0) == "C"


@pytest.mark.unit
def test_cold_start_never_gives_tier_a(scoring_db):
    """Buyers with fewer than 5 resolved invoices must receive Tier B (cold_start), never Tier A."""
    buyer = Buyer(
        buyer_id="BUYER-COLD-START",
        primary_supplier_id="SUPP-TEST",
        credit_limit=Decimal("500000.00"),
        tier=None,
        tier_basis=None,
    )
    scoring_db.add(buyer)

    # 4 perfect settled invoices (0 days late, on time)
    for i in range(4):
        inv = Invoice(
            invoice_id=2000 + i,
            supplier_id="SUPP-TEST",
            buyer_id="BUYER-COLD-START",
            invoice_amount=Decimal("1000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 20),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        )
        scoring_db.add(inv)
    scoring_db.commit()

    score = preview_buyer_score(scoring_db, "BUYER-COLD-START", as_of_date=date(2025, 2, 1))

    assert score["tier"] == "B"
    assert score["tier_basis"] == "cold_start"
    assert score["tier"] != "A"
    assert score["status"] == "provisional"


@pytest.mark.unit
def test_blocked_case_credit_limit_null_or_zero(scoring_db):
    """Credit limit NULL or <= 0 must set tier=None, tier_basis='scoring_blocked'."""
    buyer_null = Buyer(
        buyer_id="BUYER-NULL-LIMIT",
        primary_supplier_id="SUPP-TEST",
        credit_limit=None,
    )
    buyer_zero = Buyer(
        buyer_id="BUYER-ZERO-LIMIT",
        primary_supplier_id="SUPP-TEST",
        credit_limit=Decimal("0.00"),
    )
    scoring_db.add_all([buyer_null, buyer_zero])

    # Add 10 resolved invoices for each
    for idx, b_id in enumerate(["BUYER-NULL-LIMIT", "BUYER-ZERO-LIMIT"]):
        for i in range(10):
            inv = Invoice(
                invoice_id=3000 + idx * 20 + i,
                supplier_id="SUPP-TEST",
                buyer_id=b_id,
                invoice_amount=Decimal("500.00"),
                invoice_date=date(2025, 1, 1),
                due_date=date(2025, 1, 30),
                settled_date=date(2025, 1, 25),
                invoice_status="settled",
                is_late=0,
                days_late=0,
            )
            scoring_db.add(inv)
    scoring_db.commit()

    res_null = preview_buyer_score(scoring_db, "BUYER-NULL-LIMIT", as_of_date=date(2025, 2, 1))
    assert res_null["tier"] is None
    assert res_null["tier_basis"] == "scoring_blocked"
    assert res_null["status"] == "credit_limit_decision_required"

    res_zero = preview_buyer_score(scoring_db, "BUYER-ZERO-LIMIT", as_of_date=date(2025, 2, 1))
    assert res_zero["tier"] is None
    assert res_zero["tier_basis"] == "scoring_blocked"
    assert res_zero["status"] == "credit_limit_decision_required"


@pytest.mark.unit
def test_script_run_twice_gives_same_risk_scores_row_count(scoring_db):
    """Running compute_all_buyer_scores twice must be idempotent with identical row count."""
    # Create 3 buyers: 1 scored, 1 cold-start, 1 blocked
    b_scored = Buyer(
        buyer_id="B-SCORED",
        primary_supplier_id="SUPP-TEST",
        credit_limit=Decimal("100000.00"),
    )
    b_cold = Buyer(
        buyer_id="B-COLD",
        primary_supplier_id="SUPP-TEST",
        credit_limit=Decimal("100000.00"),
    )
    b_blocked = Buyer(
        buyer_id="B-BLOCKED",
        primary_supplier_id="SUPP-TEST",
        credit_limit=Decimal("0.00"),
    )
    scoring_db.add_all([b_scored, b_cold, b_blocked])

    # 6 settled invoices for b_scored
    for i in range(6):
        scoring_db.add(
            Invoice(
                invoice_id=4000 + i,
                supplier_id="SUPP-TEST",
                buyer_id="B-SCORED",
                invoice_amount=Decimal("1000.00"),
                invoice_date=date(2025, 1, 1),
                due_date=date(2025, 1, 30),
                settled_date=date(2025, 1, 25),
                invoice_status="settled",
                is_late=0,
                days_late=0,
            )
        )
    # 2 settled invoices for b_cold
    for i in range(2):
        scoring_db.add(
            Invoice(
                invoice_id=4100 + i,
                supplier_id="SUPP-TEST",
                buyer_id="B-COLD",
                invoice_amount=Decimal("1000.00"),
                invoice_date=date(2025, 1, 1),
                due_date=date(2025, 1, 30),
                settled_date=date(2025, 1, 25),
                invoice_status="settled",
                is_late=0,
                days_late=0,
            )
        )
    scoring_db.commit()

    # First run
    summary1 = compute_all_buyer_scores(scoring_db, as_of_date=date(2025, 2, 1), dry_run=False)
    count1 = (
        scoring_db.query(RiskScore)
        .filter(RiskScore.model_version == "rules_v1")
        .count()
    )
    assert count1 == 1  # Only B-SCORED has status == 'calculated'
    assert summary1["buyers_scored"] == 1
    assert summary1["cold_start"] == 1
    assert summary1["blocked"] == 1

    # Second run
    summary2 = compute_all_buyer_scores(scoring_db, as_of_date=date(2025, 2, 1), dry_run=False)
    count2 = (
        scoring_db.query(RiskScore)
        .filter(RiskScore.model_version == "rules_v1")
        .count()
    )
    assert count2 == count1
    assert summary2["buyers_scored"] == summary1["buyers_scored"]
    assert summary2["cold_start"] == summary1["cold_start"]
    assert summary2["blocked"] == summary1["blocked"]


@pytest.mark.unit
def test_as_of_date_helper_uses_latest_invoice_and_not_today(scoring_db, monkeypatch):
    """The as-of date helper must return the latest invoice_date and NEVER default to today's date."""
    monkeypatch.setattr(settings, "BUSINESS_AS_OF_DATE", None)

    historical_latest_date = date(2015, 4, 15)
    today = date.today()
    assert historical_latest_date != today

    scoring_db.add(
        Invoice(
            invoice_id=5001,
            supplier_id="SUPP-TEST",
            buyer_id="B-DATE-TEST",
            invoice_amount=Decimal("100.00"),
            invoice_date=date(2015, 1, 10),
            due_date=date(2015, 2, 10),
            invoice_status="settled",
        )
    )
    scoring_db.add(
        Invoice(
            invoice_id=5002,
            supplier_id="SUPP-TEST",
            buyer_id="B-DATE-TEST",
            invoice_amount=Decimal("100.00"),
            invoice_date=historical_latest_date,
            due_date=date(2015, 5, 15),
            invoice_status="open",
        )
    )
    scoring_db.commit()

    resolved_date = get_business_as_of_date(scoring_db)
    assert resolved_date == historical_latest_date
    assert resolved_date != today

    # Verify that when BUSINESS_AS_OF_DATE setting is explicitly provided, it takes precedence
    custom_date = date(2023, 6, 30)
    monkeypatch.setattr(settings, "BUSINESS_AS_OF_DATE", custom_date)
    assert get_business_as_of_date(scoring_db) == custom_date
