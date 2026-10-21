from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, get_password_hash
from app.db.session import Base, get_db
from app.main import app
from app.models.buyer import Buyer
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.risk_score import RiskScore
from app.models.supplier import Supplier
from app.models.user import User
from app.services.buyer_scoring import (
    calculate_and_persist_buyer_score,
    preview_buyer_score,
)


@pytest.fixture
def isolated_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    company = Company(id=1, name="Test Co", industry="Tech")
    session.add(company)
    session.commit()

    supplier = Supplier(supplier_id="SUPP-1", name="Test Supplier", company_id=1, is_active=True)
    session.add(supplier)
    session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.mark.unit
def test_preview_buyer_score_is_read_only(isolated_db):
    buyer = Buyer(
        buyer_id="BUYER-PREVIEW",
        primary_supplier_id="SUPP-1",
        credit_limit=Decimal("100000.00"),
        tier=None,
        tier_basis=None,
    )
    isolated_db.add(buyer)
    isolated_db.commit()

    # Create 5 settled invoices
    for i in range(5):
        inv = Invoice(
            invoice_id=100 + i,
            supplier_id="SUPP-1",
            buyer_id="BUYER-PREVIEW",
            invoice_amount=Decimal("1000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 28),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        )
        isolated_db.add(inv)
    isolated_db.commit()

    preview = preview_buyer_score(isolated_db, "BUYER-PREVIEW", as_of_date=date(2025, 2, 1))
    assert preview["tier"] == "A"
    assert preview["tier_basis"] == "scored"

    # Verify Buyer record in DB was NOT changed
    isolated_db.refresh(buyer)
    assert buyer.tier is None
    assert buyer.tier_basis is None

    # Verify no RiskScore records were created
    risk_count = isolated_db.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-PREVIEW").count()
    assert risk_count == 0


@pytest.mark.unit
def test_persist_scored_buyer(isolated_db):
    buyer = Buyer(
        buyer_id="BUYER-SCORED",
        primary_supplier_id="SUPP-1",
        credit_limit=Decimal("50000.00"),
        tier=None,
        tier_basis=None,
    )
    isolated_db.add(buyer)
    isolated_db.commit()

    for i in range(5):
        inv = Invoice(
            invoice_id=200 + i,
            supplier_id="SUPP-1",
            buyer_id="BUYER-SCORED",
            invoice_amount=Decimal("2000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 25),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        )
        isolated_db.add(inv)

    open_inv = Invoice(
        invoice_id=299,
        supplier_id="SUPP-1",
        buyer_id="BUYER-SCORED",
        invoice_amount=Decimal("5000.00"),
        invoice_date=date(2025, 1, 15),
        due_date=date(2025, 2, 15),
        invoice_status="open",
    )
    isolated_db.add(open_inv)
    isolated_db.commit()

    result = calculate_and_persist_buyer_score(
        isolated_db,
        "BUYER-SCORED",
        as_of_date=date(2025, 2, 1),
        model_version="v1.0",
    )

    assert result["tier"] == "A"
    assert result["tier_basis"] == "scored"
    assert result["status"] == "calculated"

    # Verify Buyer was persisted
    isolated_db.refresh(buyer)
    assert buyer.tier == "A"
    assert buyer.tier_basis == "scored"

    # Verify RiskScore ledger entry
    risk_record = (
        isolated_db.query(RiskScore)
        .filter(RiskScore.buyer_id == "BUYER-SCORED")
        .first()
    )
    assert risk_record is not None
    assert risk_record.tier == "A"
    assert risk_record.tier_basis == "scored"
    assert risk_record.payment_reliability == Decimal(str(result["reliability_score"]))
    assert risk_record.financial_risk == Decimal(str(result["financial_score"]))
    assert risk_record.liquidity_risk == Decimal(str(result["liquidity_score"]))
    assert risk_record.overall_risk == Decimal(str(result["overall_score"]))
    assert risk_record.model_version == "v1.0"


@pytest.mark.unit
def test_persist_cold_start_buyer(isolated_db):
    buyer = Buyer(
        buyer_id="BUYER-COLD",
        primary_supplier_id="SUPP-1",
        credit_limit=Decimal("50000.00"),
        tier=None,
        tier_basis=None,
    )
    isolated_db.add(buyer)
    isolated_db.commit()

    # Only 2 settled invoices (< 5)
    for i in range(2):
        inv = Invoice(
            invoice_id=300 + i,
            supplier_id="SUPP-1",
            buyer_id="BUYER-COLD",
            invoice_amount=Decimal("1000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 25),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        )
        isolated_db.add(inv)
    isolated_db.commit()

    result = calculate_and_persist_buyer_score(
        isolated_db,
        "BUYER-COLD",
        as_of_date=date(2025, 2, 1),
    )

    assert result["tier"] == "B"
    assert result["tier_basis"] == "cold_start"
    assert result["status"] == "provisional"

    isolated_db.refresh(buyer)
    assert buyer.tier == "B"
    assert buyer.tier_basis == "cold_start"

    risk_count = isolated_db.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-COLD").count()
    assert risk_count == 0


@pytest.mark.unit
def test_persist_scoring_blocked_buyer(isolated_db):
    buyer = Buyer(
        buyer_id="BUYER-BLOCKED",
        primary_supplier_id="SUPP-1",
        credit_limit=Decimal("0.00"),
        tier=None,
        tier_basis=None,
    )
    isolated_db.add(buyer)
    isolated_db.commit()

    for i in range(5):
        inv = Invoice(
            invoice_id=400 + i,
            supplier_id="SUPP-1",
            buyer_id="BUYER-BLOCKED",
            invoice_amount=Decimal("1000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 25),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        )
        isolated_db.add(inv)
    isolated_db.commit()

    result = calculate_and_persist_buyer_score(
        isolated_db,
        "BUYER-BLOCKED",
        as_of_date=date(2025, 2, 1),
    )

    assert result["tier"] is None
    assert result["tier_basis"] == "scoring_blocked"
    assert result["status"] == "credit_limit_decision_required"

    isolated_db.refresh(buyer)
    assert buyer.tier is None
    assert buyer.tier_basis == "scoring_blocked"

    risk_count = isolated_db.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-BLOCKED").count()
    assert risk_count == 0


# ==============================================================================
# Endpoint tests (POST /buyers/{buyer_id}/score and GET /buyers/{buyer_id}/score)
# ==============================================================================

@pytest.fixture
def api_test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Company 1
    c1 = Company(id=1, name="Company 1", industry="Tech")
    c2 = Company(id=2, name="Company 2", industry="Retail")
    session.add_all([c1, c2])
    session.commit()

    # Users
    hashed_pw = get_password_hash("Secret123!")
    admin_c1 = User(id=1, username="admin_c1", hashed_password=hashed_pw, role="admin", company_id=1, is_active=True)
    finance_c1 = User(id=2, username="finance_c1", hashed_password=hashed_pw, role="finance_manager", company_id=1, is_active=True)
    analyst_c1 = User(id=3, username="analyst_c1", hashed_password=hashed_pw, role="analyst", company_id=1, is_active=True)
    admin_c2 = User(id=4, username="admin_c2", hashed_password=hashed_pw, role="admin", company_id=2, is_active=True)
    session.add_all([admin_c1, finance_c1, analyst_c1, admin_c2])
    session.commit()

    # Suppliers
    sup1 = Supplier(supplier_id="SUP-C1", name="Supplier C1", company_id=1, is_active=True)
    sup2 = Supplier(supplier_id="SUP-C2", name="Supplier C2", company_id=2, is_active=True)
    session.add_all([sup1, sup2])
    session.commit()

    # Scored Buyer under SUP-C1
    buyer_scored = Buyer(
        buyer_id="BUYER-API-SCORED",
        primary_supplier_id="SUP-C1",
        credit_limit=Decimal("50000.00"),
        tier=None,
        tier_basis=None,
    )
    buyer_cold = Buyer(
        buyer_id="BUYER-API-COLD",
        primary_supplier_id="SUP-C1",
        credit_limit=Decimal("50000.00"),
        tier=None,
        tier_basis=None,
    )
    buyer_blocked = Buyer(
        buyer_id="BUYER-API-BLOCKED",
        primary_supplier_id="SUP-C1",
        credit_limit=Decimal("0.00"),
        tier=None,
        tier_basis=None,
    )
    session.add_all([buyer_scored, buyer_cold, buyer_blocked])
    session.commit()

    # Invoices for buyer_scored (5 settled, 1 open)
    for i in range(5):
        inv = Invoice(
            invoice_id=1000 + i,
            supplier_id="SUP-C1",
            buyer_id="BUYER-API-SCORED",
            invoice_amount=Decimal("2000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 25),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        )
        session.add(inv)

    open_inv = Invoice(
        invoice_id=1099,
        supplier_id="SUP-C1",
        buyer_id="BUYER-API-SCORED",
        invoice_amount=Decimal("5000.00"),
        invoice_date=date(2025, 1, 15),
        due_date=date(2025, 2, 15),
        invoice_status="open",
    )
    session.add(open_inv)

    # 1 settled invoice for buyer_cold (< 5)
    session.add(Invoice(
        invoice_id=1100,
        supplier_id="SUP-C1",
        buyer_id="BUYER-API-COLD",
        invoice_amount=Decimal("1000.00"),
        invoice_date=date(2025, 1, 1),
        due_date=date(2025, 1, 30),
        settled_date=date(2025, 1, 25),
        invoice_status="settled",
        is_late=0,
        days_late=0,
    ))

    # 5 settled invoices for buyer_blocked (credit_limit is 0.00)
    for i in range(5):
        session.add(Invoice(
            invoice_id=1200 + i,
            supplier_id="SUP-C1",
            buyer_id="BUYER-API-BLOCKED",
            invoice_amount=Decimal("1000.00"),
            invoice_date=date(2025, 1, 1),
            due_date=date(2025, 1, 30),
            settled_date=date(2025, 1, 25),
            invoice_status="settled",
            is_late=0,
            days_late=0,
        ))
    session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()


@pytest.mark.unit
def test_post_buyer_score_unauthenticated(api_test_env):
    client, _ = api_test_env
    res = client.post("/buyers/BUYER-API-SCORED/score")
    assert res.status_code == 401


@pytest.mark.unit
def test_post_buyer_score_forbidden_for_analyst(api_test_env):
    client, _ = api_test_env
    token = create_access_token(data={"sub": "analyst_c1", "role": "analyst"})
    res = client.post(
        "/buyers/BUYER-API-SCORED/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert "Required roles: admin, finance_manager" in res.json()["detail"]


@pytest.mark.unit
def test_post_buyer_score_cross_company_forbidden(api_test_env):
    client, _ = api_test_env
    # admin from Company 2 cannot access buyer from Company 1
    token = create_access_token(data={"sub": "admin_c2", "role": "admin"})
    res = client.post(
        "/buyers/BUYER-API-SCORED/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


@pytest.mark.unit
def test_post_buyer_score_success_and_persists(api_test_env):
    client, session = api_test_env
    token = create_access_token(data={"sub": "finance_c1", "role": "finance_manager"})

    res = client.post(
        "/buyers/BUYER-API-SCORED/score?as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["buyer_id"] == "BUYER-API-SCORED"
    assert data["tier"] == "A"
    assert data["tier_basis"] == "scored"
    assert data["status"] == "calculated"
    assert data["overall_score"] is not None

    # Verify Buyer record in DB was persisted
    buyer = session.query(Buyer).filter(Buyer.buyer_id == "BUYER-API-SCORED").first()
    session.refresh(buyer)
    assert buyer.tier == "A"
    assert buyer.tier_basis == "scored"

    # Verify RiskScore ledger record was inserted
    risk = session.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-API-SCORED").all()
    assert len(risk) == 1
    assert risk[0].tier == "A"
    assert risk[0].tier_basis == "scored"
    assert risk[0].overall_risk == Decimal(str(data["overall_score"]))


@pytest.mark.unit
def test_post_buyer_score_repeated_calculations_appends(api_test_env):
    client, session = api_test_env
    token = create_access_token(data={"sub": "admin_c1", "role": "admin"})

    # First calculation
    res1 = client.post(
        "/buyers/BUYER-API-SCORED/score?as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200

    # Second calculation (e.g. later date)
    res2 = client.post(
        "/buyers/BUYER-API-SCORED/score?as_of_date=2025-02-10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200

    # Verify append-only ledger has 2 records
    risk_records = session.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-API-SCORED").all()
    assert len(risk_records) == 2


@pytest.mark.unit
def test_post_buyer_score_cold_start(api_test_env):
    client, session = api_test_env
    token = create_access_token(data={"sub": "admin_c1", "role": "admin"})

    res = client.post(
        "/buyers/BUYER-API-COLD/score?as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "B"
    assert data["tier_basis"] == "cold_start"
    assert data["status"] == "provisional"

    buyer = session.query(Buyer).filter(Buyer.buyer_id == "BUYER-API-COLD").first()
    session.refresh(buyer)
    assert buyer.tier == "B"
    assert buyer.tier_basis == "cold_start"

    # No risk score row for cold start
    risk_count = session.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-API-COLD").count()
    assert risk_count == 0


@pytest.mark.unit
def test_post_buyer_score_blocked(api_test_env):
    client, session = api_test_env
    token = create_access_token(data={"sub": "admin_c1", "role": "admin"})

    res = client.post(
        "/buyers/BUYER-API-BLOCKED/score?as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] is None
    assert data["tier_basis"] == "scoring_blocked"
    assert data["status"] == "credit_limit_decision_required"

    buyer = session.query(Buyer).filter(Buyer.buyer_id == "BUYER-API-BLOCKED").first()
    session.refresh(buyer)
    assert buyer.tier is None
    assert buyer.tier_basis == "scoring_blocked"

    risk_count = session.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-API-BLOCKED").count()
    assert risk_count == 0


@pytest.mark.unit
def test_get_buyer_score_preview_remains_read_only(api_test_env):
    client, session = api_test_env
    # Unscored buyer initially
    buyer = session.query(Buyer).filter(Buyer.buyer_id == "BUYER-API-SCORED").first()
    buyer.tier = None
    buyer.tier_basis = None
    session.commit()

    token = create_access_token(data={"sub": "analyst_c1", "role": "analyst"})
    # GET preview can be called even by analyst
    res = client.get(
        "/buyers/BUYER-API-SCORED/score?as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "A"

    # Verify DB was NOT touched by GET
    session.refresh(buyer)
    assert buyer.tier is None
    assert buyer.tier_basis is None

    risk_count = session.query(RiskScore).filter(RiskScore.buyer_id == "BUYER-API-SCORED").count()
    assert risk_count == 0

@pytest.mark.unit
def test_bulk_score_dry_run_does_not_write_to_database(api_test_env):
    client, session = api_test_env
    token = create_access_token(
        data={"sub": "admin_c1", "role": "admin"}
    )

    response = client.post(
        "/buyers/scores/bulk?dry_run=true&as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["dry_run"] is True
    assert data["total"] == 3
    assert data["previewed"] == 3
    assert data["failed"] == 0

    # Preview must not modify stored tiers.
    buyers = session.query(Buyer).filter(
        Buyer.buyer_id.in_([
            "BUYER-API-SCORED",
            "BUYER-API-COLD",
            "BUYER-API-BLOCKED",
        ])
    ).all()

    assert all(buyer.tier is None for buyer in buyers)
    assert session.query(RiskScore).count() == 0


@pytest.mark.unit
def test_bulk_score_persists_all_buyers(api_test_env):
    client, session = api_test_env
    token = create_access_token(
        data={"sub": "admin_c1", "role": "admin"}
    )

    response = client.post(
        "/buyers/scores/bulk?dry_run=false&as_of_date=2025-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["dry_run"] is False
    assert data["total"] == 3
    assert data["processed"] == 3
    assert data["failed"] == 0

    session.expire_all()

    scored = session.query(Buyer).filter_by(
        buyer_id="BUYER-API-SCORED"
    ).one()
    cold = session.query(Buyer).filter_by(
        buyer_id="BUYER-API-COLD"
    ).one()
    blocked = session.query(Buyer).filter_by(
        buyer_id="BUYER-API-BLOCKED"
    ).one()

    assert scored.tier == "A"
    assert scored.tier_basis == "scored"

    assert cold.tier == "B"
    assert cold.tier_basis == "cold_start"

    assert blocked.tier is None
    assert blocked.tier_basis == "scoring_blocked"

    # Only the fully scored buyer gets a RiskScore ledger record.
    assert session.query(RiskScore).filter_by(
        buyer_id="BUYER-API-SCORED"
    ).count() == 1

    assert session.query(RiskScore).filter_by(
        buyer_id="BUYER-API-COLD"
    ).count() == 0

    assert session.query(RiskScore).filter_by(
        buyer_id="BUYER-API-BLOCKED"
    ).count() == 0


@pytest.mark.unit
def test_bulk_score_forbidden_for_analyst(api_test_env):
    client, _ = api_test_env
    token = create_access_token(
        data={"sub": "analyst_c1", "role": "analyst"}
    )

    response = client.post(
        "/buyers/scores/bulk?dry_run=true",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.unit
def test_bulk_score_unauthenticated(api_test_env):
    client, _ = api_test_env

    response = client.post(
        "/buyers/scores/bulk?dry_run=true"
    )

    assert response.status_code == 401
