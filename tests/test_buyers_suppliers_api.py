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
from app.models.supplier import Supplier
from app.models.user import User


@pytest.fixture
def api_test_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()

    # Create Companies
    company1 = Company(id=1, name="Company 1", industry="Tech")
    company2 = Company(id=2, name="Company 2", industry="Retail")
    db.add_all([company1, company2])
    db.commit()

    # Create Users
    hashed_pw = get_password_hash("Secret123!")
    admin_c1 = User(id=1, username="admin1", email="a1@c1.com", hashed_password=hashed_pw, role="admin", company_id=1, is_active=True)
    finance_c1 = User(id=2, username="finance1", email="f1@c1.com", hashed_password=hashed_pw, role="finance_manager", company_id=1, is_active=True)
    analyst_c1 = User(id=3, username="analyst1", email="an1@c1.com", hashed_password=hashed_pw, role="analyst", company_id=1, is_active=True)
    admin_c2 = User(id=4, username="admin2", email="a2@c2.com", hashed_password=hashed_pw, role="admin", company_id=2, is_active=True)
    db.add_all([admin_c1, finance_c1, analyst_c1, admin_c2])
    db.commit()

    # Create Suppliers
    sup1 = Supplier(supplier_id="SUP-01", name="Alpha Logistics", company_id=1, is_active=True)
    sup2 = Supplier(supplier_id="SUP-02", name="Beta Freight", company_id=1, is_active=False)
    sup_c2 = Supplier(supplier_id="SUP-C2", name="Gamma Supply", company_id=2, is_active=True)
    db.add_all([sup1, sup2, sup_c2])
    db.commit()

    # Create Buyers
    buyer1 = Buyer(
        buyer_id="BUY-01",
        country_code="IN",
        primary_supplier_id="SUP-01",
        behavioural_segment="Segment_A",
        tier="A",
        credit_limit=Decimal("500000.00"),
        discount_responsiveness=0.8,
        blacklisted=False,
    )
    buyer2 = Buyer(
        buyer_id="BUY-02",
        country_code="US",
        primary_supplier_id="SUP-02",
        behavioural_segment="Segment_B",
        tier="B",
        credit_limit=Decimal("200000.00"),
        discount_responsiveness=0.4,
        blacklisted=True,
    )
    buyer_c2 = Buyer(
        buyer_id="BUY-C2",
        country_code="UK",
        primary_supplier_id="SUP-C2",
        behavioural_segment="Segment_C",
        tier="C",
        credit_limit=Decimal("100000.00"),
        discount_responsiveness=0.2,
        blacklisted=False,
    )
    db.add_all([buyer1, buyer2, buyer_c2])
    db.commit()

    # Create Invoices for BUY-01
    inv1 = Invoice(
        invoice_id=101,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=date(2024, 1, 1),
        due_date=date(2024, 1, 31),
        payment_terms_days=30,
        invoice_amount=Decimal("1000.00"),
        invoice_status="open",
    )
    inv2 = Invoice(
        invoice_id=102,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=date(2024, 1, 5),
        due_date=date(2024, 2, 4),
        payment_terms_days=30,
        invoice_amount=Decimal("500.00"),
        invoice_status="open",
    )
    inv3 = Invoice(
        invoice_id=103,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=date(2024, 1, 10),
        due_date=date(2024, 2, 9),
        payment_terms_days=30,
        invoice_amount=Decimal("300.00"),
        invoice_status="settled",
    )
    db.add_all([inv1, inv2, inv3])
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    tokens = {
        "admin1": create_access_token({"sub": "admin1", "role": "admin", "company_id": 1}),
        "finance1": create_access_token({"sub": "finance1", "role": "finance_manager", "company_id": 1}),
        "analyst1": create_access_token({"sub": "analyst1", "role": "analyst", "company_id": 1}),
        "admin2": create_access_token({"sub": "admin2", "role": "admin", "company_id": 2}),
    }

    with TestClient(app) as client:
        yield client, tokens

    app.dependency_overrides.clear()


@pytest.mark.unit
def test_auth_required_for_all_endpoints(api_test_setup):
    client, _ = api_test_setup
    assert client.get("/suppliers").status_code == 401
    assert client.post("/suppliers", json={"supplier_id": "SUP-NEW"}).status_code == 401
    assert client.get("/buyers").status_code == 401
    assert client.post("/buyers", json={"buyer_id": "BUY-NEW", "primary_supplier_id": "SUP-01"}).status_code == 401


@pytest.mark.unit
def test_role_permissions_analyst_can_read_not_write(api_test_setup):
    client, tokens = api_test_setup
    analyst_headers = {"Authorization": f"Bearer {tokens['analyst1']}"}

    # Reads succeed
    res_sup = client.get("/suppliers", headers=analyst_headers)
    assert res_sup.status_code == 200
    res_buy = client.get("/buyers", headers=analyst_headers)
    assert res_buy.status_code == 200

    # Writes are blocked with 403
    assert client.post(
        "/suppliers",
        json={"supplier_id": "SUP-X", "name": "No Auth"},
        headers=analyst_headers,
    ).status_code == 403

    assert client.patch(
        "/suppliers/SUP-01",
        json={"name": "Updated Name"},
        headers=analyst_headers,
    ).status_code == 403

    assert client.delete(
        "/suppliers/SUP-01",
        headers=analyst_headers,
    ).status_code == 403

    assert client.post(
        "/buyers",
        json={"buyer_id": "BUY-X", "primary_supplier_id": "SUP-01"},
        headers=analyst_headers,
    ).status_code == 403

    assert client.patch(
        "/buyers/BUY-01",
        json={"country_code": "US"},
        headers=analyst_headers,
    ).status_code == 403


@pytest.mark.unit
def test_finance_manager_and_admin_permissions(api_test_setup):
    client, tokens = api_test_setup
    finance_headers = {"Authorization": f"Bearer {tokens['finance1']}"}
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    # Finance Manager can create and update
    res_create_sup = client.post(
        "/suppliers",
        json={"supplier_id": "SUP-FIN", "name": "Finance Added Supplier"},
        headers=finance_headers,
    )
    assert res_create_sup.status_code == 201

    res_patch_sup = client.patch(
        "/suppliers/SUP-FIN",
        json={"name": "Finance Updated Supplier"},
        headers=finance_headers,
    )
    assert res_patch_sup.status_code == 200
    assert res_patch_sup.json()["name"] == "Finance Updated Supplier"

    # Finance Manager CANNOT delete supplier
    assert client.delete("/suppliers/SUP-FIN", headers=finance_headers).status_code == 403

    # Admin CAN soft-delete supplier
    res_del = client.delete("/suppliers/SUP-FIN", headers=admin_headers)
    assert res_del.status_code == 200
    assert res_del.json()["is_active"] is False


@pytest.mark.unit
def test_pagination_and_validation(api_test_setup):
    client, tokens = api_test_setup
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    res = client.get("/suppliers?page=1&page_size=1", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert len(data["items"]) == 1

    # Invalid page number (< 1) returns 422
    res_invalid_page = client.get("/suppliers?page=0", headers=admin_headers)
    assert res_invalid_page.status_code == 422
    assert res_invalid_page.json()["code"] == "VALIDATION_ERROR"

    # Invalid page size (> 100) returns 422
    res_invalid_size = client.get("/suppliers?page_size=101", headers=admin_headers)
    assert res_invalid_size.status_code == 422
    assert res_invalid_size.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.unit
def test_filters_suppliers_and_buyers(api_test_setup):
    client, tokens = api_test_setup
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    # Supplier search
    res_search = client.get("/suppliers?search=Alpha", headers=admin_headers)
    assert res_search.status_code == 200
    items = res_search.json()["items"]
    assert len(items) == 1
    assert items[0]["supplier_id"] == "SUP-01"

    # Supplier is_active filter
    res_inactive = client.get("/suppliers?is_active=false", headers=admin_headers)
    assert res_inactive.status_code == 200
    items = res_inactive.json()["items"]
    assert len(items) == 1
    assert items[0]["supplier_id"] == "SUP-02"

    # Buyer tier filter
    res_tier_a = client.get("/buyers?tier=A", headers=admin_headers)
    assert res_tier_a.status_code == 200
    assert len(res_tier_a.json()["items"]) == 1
    assert res_tier_a.json()["items"][0]["buyer_id"] == "BUY-01"

    # Buyer invalid tier filter
    res_invalid_tier = client.get("/buyers?tier=X", headers=admin_headers)
    assert res_invalid_tier.status_code == 422
    assert res_invalid_tier.json()["code"] == "VALIDATION_ERROR"

    # Buyer blacklisted filter
    res_blacklisted = client.get("/buyers?blacklisted=true", headers=admin_headers)
    assert res_blacklisted.status_code == 200
    assert len(res_blacklisted.json()["items"]) == 1
    assert res_blacklisted.json()["items"][0]["buyer_id"] == "BUY-02"

    # Buyer behavioural_segment filter
    res_seg = client.get("/buyers?behavioural_segment=Segment_A", headers=admin_headers)
    assert res_seg.status_code == 200
    assert len(res_seg.json()["items"]) == 1
    assert res_seg.json()["items"][0]["buyer_id"] == "BUY-01"


@pytest.mark.unit
def test_404_not_found_handling(api_test_setup):
    client, tokens = api_test_setup
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    res_sup = client.get("/suppliers/SUP-NONEXISTENT", headers=admin_headers)
    assert res_sup.status_code == 404
    assert res_sup.json()["code"] == "NOT_FOUND"

    res_buy = client.get("/buyers/BUY-NONEXISTENT", headers=admin_headers)
    assert res_buy.status_code == 404
    assert res_buy.json()["code"] == "NOT_FOUND"

    res_patch = client.patch(
        "/suppliers/SUP-NONEXISTENT",
        json={"name": "None"},
        headers=admin_headers,
    )
    assert res_patch.status_code == 404
    assert res_patch.json()["code"] == "NOT_FOUND"


@pytest.mark.unit
def test_409_duplicate_conflict_handling(api_test_setup):
    client, tokens = api_test_setup
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    # Duplicate supplier
    res_sup_dup = client.post(
        "/suppliers",
        json={"supplier_id": "SUP-01", "name": "Duplicate"},
        headers=admin_headers,
    )
    assert res_sup_dup.status_code == 409
    assert res_sup_dup.json()["code"] == "INTEGRITY_ERROR"

    # Duplicate buyer
    res_buy_dup = client.post(
        "/buyers",
        json={"buyer_id": "BUY-01", "primary_supplier_id": "SUP-01"},
        headers=admin_headers,
    )
    assert res_buy_dup.status_code == 409
    assert res_buy_dup.json()["code"] == "INTEGRITY_ERROR"


@pytest.mark.unit
def test_company_scoping(api_test_setup):
    client, tokens = api_test_setup
    c1_headers = {"Authorization": f"Bearer {tokens['admin1']}"}
    c2_headers = {"Authorization": f"Bearer {tokens['admin2']}"}

    # Company 1 sees only its suppliers (SUP-01, SUP-02)
    res_c1_sups = client.get("/suppliers", headers=c1_headers).json()["items"]
    sup_ids_c1 = [s["supplier_id"] for s in res_c1_sups]
    assert "SUP-01" in sup_ids_c1
    assert "SUP-02" in sup_ids_c1
    assert "SUP-C2" not in sup_ids_c1

    # Company 2 sees only SUP-C2
    res_c2_sups = client.get("/suppliers", headers=c2_headers).json()["items"]
    sup_ids_c2 = [s["supplier_id"] for s in res_c2_sups]
    assert "SUP-C2" in sup_ids_c2
    assert "SUP-01" not in sup_ids_c2

    # Company 1 sees only BUY-01, BUY-02
    res_c1_buyers = client.get("/buyers", headers=c1_headers).json()["items"]
    buy_ids_c1 = [b["buyer_id"] for b in res_c1_buyers]
    assert "BUY-01" in buy_ids_c1
    assert "BUY-02" in buy_ids_c1
    assert "BUY-C2" not in buy_ids_c1

    # Company 2 sees only BUY-C2
    res_c2_buyers = client.get("/buyers", headers=c2_headers).json()["items"]
    buy_ids_c2 = [b["buyer_id"] for b in res_c2_buyers]
    assert "BUY-C2" in buy_ids_c2
    assert "BUY-01" not in buy_ids_c2

    # Cross-company get returns 404
    assert client.get("/suppliers/SUP-01", headers=c2_headers).status_code == 404
    assert client.get("/buyers/BUY-01", headers=c2_headers).status_code == 404

    # Cross-company buyer creation rejected (supplier belongs to other company)
    res_cross_create = client.post(
        "/buyers",
        json={"buyer_id": "BUY-CROSS", "primary_supplier_id": "SUP-01"},
        headers=c2_headers,
    )
    assert res_cross_create.status_code == 400


@pytest.mark.unit
def test_buyer_detail_computed_invoices(api_test_setup):
    client, tokens = api_test_setup
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    res = client.get("/buyers/BUY-01", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["buyer_id"] == "BUY-01"
    assert data["invoice_count"] == 3
    assert Decimal(str(data["open_exposure"])) == Decimal("1500.00")


@pytest.mark.unit
def test_buyer_tier_strict_validation_and_no_delete(api_test_setup):
    client, tokens = api_test_setup
    admin_headers = {"Authorization": f"Bearer {tokens['admin1']}"}

    # Attempt to create with invalid tier 'D'
    res_invalid_create = client.post(
        "/buyers",
        json={"buyer_id": "BUY-NEW-D", "primary_supplier_id": "SUP-01", "tier": "D"},
        headers=admin_headers,
    )
    assert res_invalid_create.status_code == 422
    assert res_invalid_create.json()["code"] == "VALIDATION_ERROR"

    # Attempt to update with invalid tier 'X'
    res_invalid_patch = client.patch(
        "/buyers/BUY-01",
        json={"tier": "X"},
        headers=admin_headers,
    )
    assert res_invalid_patch.status_code == 422
    assert res_invalid_patch.json()["code"] == "VALIDATION_ERROR"

    # Attempt hard delete
    res_delete = client.delete("/buyers/BUY-01", headers=admin_headers)
    assert res_delete.status_code == 405
