from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, get_password_hash
from app.db.session import Base, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.buyer import Buyer
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.models.user import User


@pytest.fixture
def invoices_api_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()

    # Companies
    c1 = Company(id=1, name="Company 1", industry="Supply Chain")
    c2 = Company(id=2, name="Company 2", industry="Retail")
    db.add_all([c1, c2])
    db.commit()

    # Users
    hashed_pw = get_password_hash("Secret123!")
    admin_c1 = User(id=1, username="admin1", email="a1@c1.com", hashed_password=hashed_pw, role="admin", company_id=1, is_active=True)
    finance_c1 = User(id=2, username="finance1", email="f1@c1.com", hashed_password=hashed_pw, role="finance_manager", company_id=1, is_active=True)
    analyst_c1 = User(id=3, username="analyst1", email="an1@c1.com", hashed_password=hashed_pw, role="analyst", company_id=1, is_active=True)
    admin_c2 = User(id=4, username="admin2", email="a2@c2.com", hashed_password=hashed_pw, role="admin", company_id=2, is_active=True)
    db.add_all([admin_c1, finance_c1, analyst_c1, admin_c2])
    db.commit()

    # Suppliers
    sup1 = Supplier(supplier_id="SUP-01", name="Supplier One", company_id=1, is_active=True)
    sup2 = Supplier(supplier_id="SUP-02", name="Supplier Two", company_id=1, is_active=True)
    sup_c2 = Supplier(supplier_id="SUP-C2", name="Supplier C2", company_id=2, is_active=True)
    db.add_all([sup1, sup2, sup_c2])
    db.commit()

    # Buyers
    buyer1 = Buyer(buyer_id="BUY-01", country_code="IN", primary_supplier_id="SUP-01", credit_limit=Decimal("500000.00"), tier="A")
    buyer2 = Buyer(buyer_id="BUY-02", country_code="IN", primary_supplier_id="SUP-02", credit_limit=Decimal("300000.00"), tier="B")
    buyer_c2 = Buyer(buyer_id="BUY-C2", country_code="US", primary_supplier_id="SUP-C2", credit_limit=Decimal("200000.00"), tier="C")
    db.add_all([buyer1, buyer2, buyer_c2])
    db.commit()

    today = date.today()

    # Invoices for Company 1
    # 1. Open invoice (future due)
    inv1 = Invoice(
        invoice_id=101,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=today - timedelta(days=10),
        due_date=today + timedelta(days=20),
        payment_terms_days=30,
        invoice_amount=Decimal("50000.00"),
        currency="INR",
        disputed=False,
        invoice_status="open",
    )
    # 2. Overdue open invoice
    inv2 = Invoice(
        invoice_id=102,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=today - timedelta(days=40),
        due_date=today - timedelta(days=10),
        payment_terms_days=30,
        invoice_amount=Decimal("75000.00"),
        currency="INR",
        disputed=True,
        invoice_status="open",
    )
    # 3. Settled invoice
    inv3 = Invoice(
        invoice_id=103,
        buyer_id="BUY-02",
        supplier_id="SUP-02",
        invoice_date=today - timedelta(days=60),
        due_date=today - timedelta(days=30),
        payment_terms_days=30,
        invoice_amount=Decimal("120000.00"),
        currency="INR",
        disputed=False,
        invoice_status="settled",
        settled_date=today - timedelta(days=35),
        days_late=0,
        is_late=False,
    )
    # 4. Invoice for Company 2
    inv_c2 = Invoice(
        invoice_id=201,
        buyer_id="BUY-C2",
        supplier_id="SUP-C2",
        invoice_date=today - timedelta(days=15),
        due_date=today + timedelta(days=15),
        payment_terms_days=30,
        invoice_amount=Decimal("30000.00"),
        currency="INR",
        disputed=False,
        invoice_status="open",
    )
    db.add_all([inv1, inv2, inv3, inv_c2])
    db.commit()

    # Payments for inv3
    pay1 = Payment(
        payment_id=1,
        invoice_id=103,
        payment_date=today - timedelta(days=35),
        payment_amount=Decimal("120000.00"),
        payment_method="bank_transfer",
        status="completed",
        discount_applied=Decimal("0.00"),
    )
    db.add(pay1)
    db.commit()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    token_admin1 = create_access_token({"sub": "admin1", "role": "admin", "company_id": 1})
    token_finance1 = create_access_token({"sub": "finance1", "role": "finance_manager", "company_id": 1})
    token_analyst1 = create_access_token({"sub": "analyst1", "role": "analyst", "company_id": 1})
    token_admin2 = create_access_token({"sub": "admin2", "role": "admin", "company_id": 2})

    client = TestClient(app)

    yield {
        "client": client,
        "db": db,
        "token_admin1": token_admin1,
        "token_finance1": token_finance1,
        "token_analyst1": token_analyst1,
        "token_admin2": token_admin2,
    }

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.mark.unit
def test_invoices_auth_required(invoices_api_setup):
    client = invoices_api_setup["client"]

    # All endpoints reject without token
    assert client.get("/invoices").status_code == 401
    assert client.get("/invoices/101").status_code == 401
    assert client.get("/invoices/summary").status_code == 401
    assert client.post("/invoices", json={}).status_code == 401
    assert client.patch("/invoices/101", json={}).status_code == 401
    assert client.post("/invoices/101/settle", json={}).status_code == 401
    assert client.delete("/invoices/101").status_code == 401


@pytest.mark.unit
def test_invoices_role_permissions(invoices_api_setup):
    client = invoices_api_setup["client"]
    analyst_headers = {"Authorization": f"Bearer {invoices_api_setup['token_analyst1']}"}
    finance_headers = {"Authorization": f"Bearer {invoices_api_setup['token_finance1']}"}
    admin_headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin1']}"}

    # Analyst can read list, detail, and summary
    assert client.get("/invoices", headers=analyst_headers).status_code == 200
    assert client.get("/invoices/101", headers=analyst_headers).status_code == 200
    assert client.get("/invoices/summary", headers=analyst_headers).status_code == 200

    # Analyst cannot create, patch, or settle (403)
    today = date.today()
    create_payload = {
        "buyer_id": "BUY-01",
        "supplier_id": "SUP-01",
        "invoice_date": today.isoformat(),
        "due_date": (today + timedelta(days=30)).isoformat(),
        "payment_terms_days": 30,
        "invoice_amount": "40000.00",
    }
    assert client.post("/invoices", json=create_payload, headers=analyst_headers).status_code == 403
    assert client.patch("/invoices/101", json={"disputed": True}, headers=analyst_headers).status_code == 403
    assert client.post("/invoices/101/settle", json={"settled_date": today.isoformat()}, headers=analyst_headers).status_code == 403

    # Finance manager can patch open invoice
    r_patch = client.patch("/invoices/101", json={"disputed": True}, headers=finance_headers)
    assert r_patch.status_code == 200
    assert r_patch.json()["disputed"] is True

    # Settled invoice: Finance manager cannot patch (403)
    r_settled_finance = client.patch("/invoices/103", json={"disputed": True}, headers=finance_headers)
    assert r_settled_finance.status_code == 403

    # Settled invoice: Admin can patch
    r_settled_admin = client.patch("/invoices/103", json={"disputed": True}, headers=admin_headers)
    assert r_settled_admin.status_code == 200
    assert r_settled_admin.json()["disputed"] is True


@pytest.mark.unit
def test_invoices_computed_fields(invoices_api_setup):
    client = invoices_api_setup["client"]
    headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin1']}"}
    today = date.today()

    # 1. Open future invoice (101: due today + 20 days)
    r1 = client.get("/invoices/101", headers=headers)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["invoice_status"] == "open"
    assert d1["days_until_due"] == 20
    assert d1["overdue_days"] == 0

    # 2. Open overdue invoice (102: due today - 10 days)
    r2 = client.get("/invoices/102", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["invoice_status"] == "open"
    assert d2["days_until_due"] == -10
    assert d2["overdue_days"] == 10

    # 3. Settled invoice (103: settled)
    r3 = client.get("/invoices/103", headers=headers)
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["invoice_status"] == "settled"
    assert d3["days_until_due"] is None
    assert d3["overdue_days"] == 0
    # Also verify buyer summary and payments attached
    assert d3["buyer"]["buyer_id"] == "BUY-02"
    assert len(d3["payments"]) == 1
    assert d3["payments"][0]["payment_amount"] == "120000.00"


@pytest.mark.unit
def test_invoices_pagination_and_filters(invoices_api_setup):
    client = invoices_api_setup["client"]
    headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin1']}"}

    # Default list: 3 invoices for company 1
    r_all = client.get("/invoices", headers=headers)
    assert r_all.status_code == 200
    data = r_all.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Pagination: page_size=2
    r_page = client.get("/invoices?page=1&page_size=2", headers=headers)
    assert r_page.status_code == 200
    pdata = r_page.json()
    assert pdata["total"] == 3
    assert len(pdata["items"]) == 2
    assert pdata["page"] == 1
    assert pdata["page_size"] == 2

    # Filter: invoice_status=open
    r_open = client.get("/invoices?invoice_status=open", headers=headers)
    assert r_open.status_code == 200
    assert r_open.json()["total"] == 2

    # Filter: buyer_id=BUY-02
    r_b2 = client.get("/invoices?buyer_id=BUY-02", headers=headers)
    assert r_b2.status_code == 200
    assert r_b2.json()["total"] == 1
    assert r_b2.json()["items"][0]["buyer_id"] == "BUY-02"

    # Filter: min_amount=60000.00
    r_amt = client.get("/invoices?min_amount=60000.00", headers=headers)
    assert r_amt.status_code == 200
    assert r_amt.json()["total"] == 2  # 75000 and 120000

    # Sorting
    r_sort = client.get("/invoices?sort_by=invoice_amount&order=asc", headers=headers)
    assert r_sort.status_code == 200
    amounts = [float(item["invoice_amount"]) for item in r_sort.json()["items"]]
    assert amounts == [50000.0, 75000.0, 120000.0]


@pytest.mark.unit
def test_invoices_validation_errors(invoices_api_setup):
    client = invoices_api_setup["client"]
    headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin1']}"}
    today = date.today()

    # 1. due_date < invoice_date
    bad_dates = {
        "buyer_id": "BUY-01",
        "supplier_id": "SUP-01",
        "invoice_date": today.isoformat(),
        "due_date": (today - timedelta(days=1)).isoformat(),
        "payment_terms_days": 30,
        "invoice_amount": "50000.00",
    }
    r1 = client.post("/invoices", json=bad_dates, headers=headers)
    assert r1.status_code == 422

    # 2. invoice_amount <= 0
    bad_amount = {
        "buyer_id": "BUY-01",
        "supplier_id": "SUP-01",
        "invoice_date": today.isoformat(),
        "due_date": (today + timedelta(days=30)).isoformat(),
        "payment_terms_days": 30,
        "invoice_amount": "0.00",
    }
    r2 = client.post("/invoices", json=bad_amount, headers=headers)
    assert r2.status_code == 422

    # 3. Non-existent buyer
    bad_buyer = {
        "buyer_id": "NON-EXISTENT",
        "supplier_id": "SUP-01",
        "invoice_date": today.isoformat(),
        "due_date": (today + timedelta(days=30)).isoformat(),
        "payment_terms_days": 30,
        "invoice_amount": "50000.00",
    }
    r3 = client.post("/invoices", json=bad_buyer, headers=headers)
    assert r3.status_code == 400

    # 4. Supplier from other company
    bad_supplier = {
        "buyer_id": "BUY-01",
        "supplier_id": "SUP-C2",
        "invoice_date": today.isoformat(),
        "due_date": (today + timedelta(days=30)).isoformat(),
        "payment_terms_days": 30,
        "invoice_amount": "50000.00",
    }
    r4 = client.post("/invoices", json=bad_supplier, headers=headers)
    assert r4.status_code == 400

    # 5. Duplicate invoice_id
    dup_id = {
        "invoice_id": 101,
        "buyer_id": "BUY-01",
        "supplier_id": "SUP-01",
        "invoice_date": today.isoformat(),
        "due_date": (today + timedelta(days=30)).isoformat(),
        "payment_terms_days": 30,
        "invoice_amount": "50000.00",
    }
    r5 = client.post("/invoices", json=dup_id, headers=headers)
    assert r5.status_code == 409


@pytest.mark.unit
def test_invoices_settle_logic_and_audit(invoices_api_setup):
    client = invoices_api_setup["client"]
    db = invoices_api_setup["db"]
    headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin1']}"}
    today = date.today()

    # 1. Late settlement: Invoice 102 was due 10 days ago (today - 10)
    # Settling today means 10 days late!
    r_late = client.post("/invoices/102/settle", json={"settled_date": today.isoformat()}, headers=headers)
    assert r_late.status_code == 200
    d_late = r_late.json()
    assert d_late["invoice_status"] == "settled"
    assert d_late["days_late"] == 10
    assert d_late["is_late"] is True
    assert d_late["settled_date"] == today.isoformat()

    # Attempting to re-settle 102 fails with 400
    r_re = client.post("/invoices/102/settle", json={"settled_date": today.isoformat()}, headers=headers)
    assert r_re.status_code == 400

    # 2. On-time settlement: Create open invoice due in 15 days, settle today
    create_payload = {
        "invoice_id": 301,
        "buyer_id": "BUY-01",
        "supplier_id": "SUP-01",
        "invoice_date": today.isoformat(),
        "due_date": (today + timedelta(days=15)).isoformat(),
        "payment_terms_days": 15,
        "invoice_amount": "65000.00",
    }
    r_cr = client.post("/invoices", json=create_payload, headers=headers)
    assert r_cr.status_code == 201

    r_ontime = client.post("/invoices/301/settle", json={"settled_date": today.isoformat()}, headers=headers)
    assert r_ontime.status_code == 200
    d_ontime = r_ontime.json()
    assert d_ontime["invoice_status"] == "settled"
    assert d_ontime["days_late"] == 0
    assert d_ontime["is_late"] is False

    # 3. Verify audit log entries
    logs = db.query(AuditLog).filter(AuditLog.entity_type == "invoice").all()
    actions = [l.action for l in logs]
    assert "create" in actions
    assert "settle" in actions


@pytest.mark.unit
def test_invoices_company_scoping_and_summary(invoices_api_setup):
    client = invoices_api_setup["client"]
    c1_headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin1']}"}
    c2_headers = {"Authorization": f"Bearer {invoices_api_setup['token_admin2']}"}

    # Company 1 user cannot access invoice 201 (belongs to Company 2)
    assert client.get("/invoices/201", headers=c1_headers).status_code == 404
    assert client.patch("/invoices/201", json={"disputed": True}, headers=c1_headers).status_code == 404
    assert client.post("/invoices/201/settle", json={"settled_date": date.today().isoformat()}, headers=c1_headers).status_code == 404

    # Company 2 user cannot access invoice 101 (belongs to Company 1)
    assert client.get("/invoices/101", headers=c2_headers).status_code == 404

    # Hard delete is blocked (405)
    assert client.delete("/invoices/101", headers=c1_headers).status_code == 405

    # Summary for Company 1
    r_sum1 = client.get("/invoices/summary", headers=c1_headers)
    assert r_sum1.status_code == 200
    s1 = r_sum1.json()
    # At setup: inv1 (open 50k), inv2 (open 75k, overdue, disputed), inv3 (settled 120k)
    assert s1["open"]["count"] == 2
    assert Decimal(s1["open"]["total_amount"]) == Decimal("125000.00")
    assert s1["overdue"]["count"] == 1
    assert Decimal(s1["overdue"]["total_amount"]) == Decimal("75000.00")
    assert s1["settled"]["count"] == 1
    assert Decimal(s1["settled"]["total_amount"]) == Decimal("120000.00")
    assert s1["disputed"]["count"] == 1
    assert Decimal(s1["disputed"]["total_amount"]) == Decimal("75000.00")

    # Summary for Company 2
    r_sum2 = client.get("/invoices/summary", headers=c2_headers)
    assert r_sum2.status_code == 200
    s2 = r_sum2.json()
    assert s2["open"]["count"] == 1
    assert Decimal(s2["open"]["total_amount"]) == Decimal("30000.00")
    assert s2["settled"]["count"] == 0
