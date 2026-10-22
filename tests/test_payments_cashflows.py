from datetime import date, datetime, timedelta, timezone
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
from app.models.cash_flow import CashFlow
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.models.transaction import Transaction
from app.models.user import User


@pytest.fixture
def api_setup():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    # Companies
    c1 = Company(id=1, name="Acme Logistics", industry="Supply Chain")
    c2 = Company(id=2, name="Beta Retail", industry="Retail")
    db.add_all([c1, c2])
    db.commit()

    # Users
    hashed = get_password_hash("Secret123!")
    admin_c1 = User(id=1, username="admin1", email="a1@c1.com", hashed_password=hashed, role="admin", company_id=1, is_active=True)
    finance_c1 = User(id=2, username="finance1", email="f1@c1.com", hashed_password=hashed, role="finance_manager", company_id=1, is_active=True)
    analyst_c1 = User(id=3, username="analyst1", email="an1@c1.com", hashed_password=hashed, role="analyst", company_id=1, is_active=True)
    admin_c2 = User(id=4, username="admin2", email="a2@c2.com", hashed_password=hashed, role="admin", company_id=2, is_active=True)
    db.add_all([admin_c1, finance_c1, analyst_c1, admin_c2])
    db.commit()

    # Suppliers
    s1 = Supplier(supplier_id="SUP-01", name="Supplier One", company_id=1, is_active=True)
    s2 = Supplier(supplier_id="SUP-C2", name="Supplier C2", company_id=2, is_active=True)
    db.add_all([s1, s2])
    db.commit()

    # Buyers
    b1 = Buyer(buyer_id="BUY-01", country_code="IN", primary_supplier_id="SUP-01", credit_limit=Decimal("500000.00"), tier="A")
    db.add(b1)
    db.commit()

    today = date(2025, 3, 15)

    # Invoices
    inv1 = Invoice(
        invoice_id=101,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=today - timedelta(days=20),
        due_date=today - timedelta(days=5),  # Overdue by 5 days
        payment_terms_days=15,
        invoice_amount=Decimal("100000.00"),
        currency="INR",
        disputed=False,
        invoice_status="open",
    )
    inv2 = Invoice(
        invoice_id=102,
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
    inv_c2 = Invoice(
        invoice_id=201,
        buyer_id="BUY-01",
        supplier_id="SUP-C2",
        invoice_date=today - timedelta(days=5),
        due_date=today + timedelta(days=25),
        payment_terms_days=30,
        invoice_amount=Decimal("75000.00"),
        currency="INR",
        disputed=False,
        invoice_status="open",
    )
    db.add_all([inv1, inv2, inv_c2])
    db.commit()

    # Seed daily cash flows for Company 1 across 35 days
    ref_date = date(2015, 4, 15)
    balance = Decimal("1000000.00")
    for i in range(35):
        d = ref_date - timedelta(days=34 - i)
        inflow = Decimal("50000.00") + Decimal(i * 1000)
        outflow = Decimal("40000.00") + Decimal(i * 500)
        net = inflow - outflow
        closing = balance + net
        gap = Decimal("20000.00") if i % 2 == 0 else Decimal("0.00")
        cf = CashFlow(
            company_id=1,
            date=d,
            inflow_actual=inflow,
            outflow_actual=outflow,
            net_cash_flow=net,
            opening_balance=balance,
            closing_balance=closing,
            outstanding_receivables=Decimal("300000.00"),
            min_cash_buffer=Decimal("150000.00"),
            liquidity_gap=gap,
        )
        db.add(cf)
        balance = closing
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    tokens = {
        "admin_c1": create_access_token({"sub": "admin1", "role": "admin", "company_id": 1}),
        "finance_c1": create_access_token({"sub": "finance1", "role": "finance_manager", "company_id": 1}),
        "analyst_c1": create_access_token({"sub": "analyst1", "role": "analyst", "company_id": 1}),
        "admin_c2": create_access_token({"sub": "admin2", "role": "admin", "company_id": 2}),
    }

    yield client, tokens, db, ref_date

    app.dependency_overrides.clear()
    db.close()


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# PAYMENTS TESTS
# ==============================================================================

@pytest.mark.unit
def test_create_payment_validation(api_setup):
    client, tokens, db, _ = api_setup
    admin_hdr = auth_header(tokens["admin_c1"])

    # 1. Negative amount -> 422
    payload = {
        "invoice_id": 101,
        "payment_date": "2025-03-15",
        "payment_amount": -500.00,
        "status": "completed",
    }
    r = client.post("/payments", json=payload, headers=admin_hdr)
    assert r.status_code == 422

    # 2. Invalid status -> 422
    payload["payment_amount"] = 5000.00
    payload["status"] = "in_transit"
    r = client.post("/payments", json=payload, headers=admin_hdr)
    assert r.status_code == 422

    # 3. Non-existent invoice -> 404
    payload["invoice_id"] = 99999
    payload["status"] = "completed"
    r = client.post("/payments", json=payload, headers=admin_hdr)
    assert r.status_code == 404

    # 4. Payment date before invoice_date -> 400
    payload["invoice_id"] = 101
    payload["payment_date"] = "2025-01-01"
    r = client.post("/payments", json=payload, headers=admin_hdr)
    assert r.status_code == 400
    assert "earlier than invoice_date" in r.json()["detail"]


@pytest.mark.unit
def test_payment_settlement_trigger(api_setup):
    client, tokens, db, _ = api_setup
    fin_hdr = auth_header(tokens["finance_c1"])

    # Invoice 101 amount = 100000.00, due 2025-03-10, payment on 2025-03-15 (5 days late)
    payload = {
        "invoice_id": 101,
        "payment_date": "2025-03-15",
        "payment_amount": 100000.00,
        "payment_method": "NEFT",
        "reference_number": "UTR12345678",
        "status": "completed",
    }
    res = client.post("/payments", json=payload, headers=fin_hdr)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "completed"
    assert Decimal(str(data["payment_amount"])) == Decimal("100000.00")

    # Verify invoice 101 is settled
    inv = db.query(Invoice).filter(Invoice.invoice_id == 101).first()
    assert inv.invoice_status == "settled"
    assert inv.settled_date == date(2025, 3, 15)
    assert inv.days_late == 5
    assert inv.is_late is True

    # Verify audit logs created for both payment creation and invoice settlement
    payment_audits = db.query(AuditLog).filter(AuditLog.entity_type == "payment", AuditLog.action == "create").all()
    assert len(payment_audits) == 1
    invoice_audits = db.query(AuditLog).filter(AuditLog.entity_type == "invoice", AuditLog.action == "settle").all()
    assert len(invoice_audits) >= 1

    # Verify transaction record was automatically generated
    txns = db.query(Transaction).filter(Transaction.payment_id == data["payment_id"]).all()
    assert len(txns) == 1
    assert txns[0].status == "settled"
    assert txns[0].amount == Decimal("100000.00")


@pytest.mark.unit
def test_partial_payment_does_not_settle_invoice(api_setup):
    client, tokens, db, _ = api_setup
    fin_hdr = auth_header(tokens["finance_c1"])

    # Partial payment on invoice 102 (amount 50000)
    payload = {
        "invoice_id": 102,
        "payment_date": "2025-03-15",
        "payment_amount": 20000.00,
        "status": "completed",
    }
    res = client.post("/payments", json=payload, headers=fin_hdr)
    assert res.status_code == 201

    inv = db.query(Invoice).filter(Invoice.invoice_id == 102).first()
    assert inv.invoice_status == "open"  # still open


@pytest.mark.unit
def test_patch_payment_status_triggers_settlement(api_setup):
    client, tokens, db, _ = api_setup
    fin_hdr = auth_header(tokens["finance_c1"])

    # Create pending payment for invoice 102
    p_res = client.post(
        "/payments",
        json={
            "invoice_id": 102,
            "payment_date": "2025-03-15",
            "payment_amount": 50000.00,
            "status": "pending",
        },
        headers=fin_hdr,
    )
    assert p_res.status_code == 201
    payment_id = p_res.json()["payment_id"]

    inv = db.query(Invoice).filter(Invoice.invoice_id == 102).first()
    assert inv.invoice_status == "open"

    # Patch status to completed
    patch_res = client.patch(
        f"/payments/{payment_id}",
        json={"status": "completed"},
        headers=fin_hdr,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "completed"

    db.refresh(inv)
    assert inv.invoice_status == "settled"


@pytest.mark.unit
def test_payments_role_permissions_and_scoping(api_setup):
    client, tokens, db, _ = api_setup
    analyst_hdr = auth_header(tokens["analyst_c1"])
    admin_c1_hdr = auth_header(tokens["admin_c1"])
    admin_c2_hdr = auth_header(tokens["admin_c2"])

    # Analyst cannot create payments (403)
    r_post = client.post(
        "/payments",
        json={"invoice_id": 102, "payment_date": "2025-03-15", "payment_amount": 1000.0, "status": "completed"},
        headers=analyst_hdr,
    )
    assert r_post.status_code == 403

    # Admin 1 creates payment
    p_res = client.post(
        "/payments",
        json={"invoice_id": 102, "payment_date": "2025-03-15", "payment_amount": 1000.0, "status": "pending"},
        headers=admin_c1_hdr,
    )
    assert p_res.status_code == 201
    p_id = p_res.json()["payment_id"]

    # Analyst can GET payment list & get one
    r_list = client.get("/payments", headers=analyst_hdr)
    assert r_list.status_code == 200
    assert len(r_list.json()["items"]) >= 1

    r_one = client.get(f"/payments/{p_id}", headers=analyst_hdr)
    assert r_one.status_code == 200

    # Admin C2 cannot see Company 1's payment (404 scoping)
    r_c2 = client.get(f"/payments/{p_id}", headers=admin_c2_hdr)
    assert r_c2.status_code == 404

    # Hard delete is forbidden -> 405
    r_del = client.delete(f"/payments/{p_id}", headers=admin_c1_hdr)
    assert r_del.status_code == 405


# ==============================================================================
# TRANSACTIONS TESTS
# ==============================================================================

@pytest.mark.unit
def test_transactions_read_only(api_setup):
    client, tokens, db, _ = api_setup
    admin_hdr = auth_header(tokens["admin_c1"])
    analyst_hdr = auth_header(tokens["analyst_c1"])

    # Create payment to produce transaction
    p_res = client.post(
        "/payments",
        json={"invoice_id": 102, "payment_date": "2025-03-15", "payment_amount": 5000.0, "status": "completed"},
        headers=admin_hdr,
    )
    assert p_res.status_code == 201
    pid = p_res.json()["payment_id"]

    # List transactions
    r_txns = client.get(f"/transactions?payment_id={pid}", headers=analyst_hdr)
    assert r_txns.status_code == 200
    items = r_txns.json()["items"]
    assert len(items) == 1
    txn_id = items[0]["transaction_id"]

    # Get single transaction
    r_get = client.get(f"/transactions/{txn_id}", headers=analyst_hdr)
    assert r_get.status_code == 200
    assert r_get.json()["amount"] == "5000.00"

    # POST or DELETE /transactions returns 405
    r_post = client.post("/transactions", json={}, headers=admin_hdr)
    assert r_post.status_code == 405
    r_del = client.delete(f"/transactions/{txn_id}", headers=admin_hdr)
    assert r_del.status_code == 405


# ==============================================================================
# CASH FLOWS TESTS
# ==============================================================================

@pytest.mark.unit
def test_cash_flow_math_validation_and_409(api_setup):
    client, tokens, db, _ = api_setup
    admin_hdr = auth_header(tokens["admin_c1"])

    # 1. Invalid net math: 100 - 40 != 50
    bad_net = {
        "date": "2025-06-01",
        "inflow_actual": 100.00,
        "outflow_actual": 40.00,
        "net_cash_flow": 50.00,  # should be 60.00
        "opening_balance": 1000.00,
        "closing_balance": 1050.00,
    }
    r1 = client.post("/cash-flows", json=bad_net, headers=admin_hdr)
    assert r1.status_code == 422

    # 2. Invalid closing math: 1000 + 60 != 1100
    bad_closing = {
        "date": "2025-06-01",
        "inflow_actual": 100.00,
        "outflow_actual": 40.00,
        "net_cash_flow": 60.00,
        "opening_balance": 1000.00,
        "closing_balance": 1100.00,  # should be 1060.00
    }
    r2 = client.post("/cash-flows", json=bad_closing, headers=admin_hdr)
    assert r2.status_code == 422

    # 3. Valid creation
    valid_payload = {
        "date": "2025-06-01",
        "inflow_actual": 100.00,
        "outflow_actual": 40.00,
        "net_cash_flow": 60.00,
        "opening_balance": 1000.00,
        "closing_balance": 1060.00,
    }
    r3 = client.post("/cash-flows", json=valid_payload, headers=admin_hdr)
    assert r3.status_code == 201
    cf_id = r3.json()["id"]

    # 4. Duplicate (company, date) -> 409 Conflict
    r4 = client.post("/cash-flows", json=valid_payload, headers=admin_hdr)
    assert r4.status_code == 409
    assert "already exists" in r4.json()["detail"]

    # 5. Patch math validation
    r5 = client.patch(
        f"/cash-flows/{cf_id}",
        json={"closing_balance": 9999.00},
        headers=admin_hdr,
    )
    assert r5.status_code == 422


@pytest.mark.unit
def test_cash_flow_role_permissions_and_delete_405(api_setup):
    client, tokens, db, _ = api_setup
    analyst_hdr = auth_header(tokens["analyst_c1"])
    fin_hdr = auth_header(tokens["finance_c1"])

    # Analyst cannot create -> 403
    r_post = client.post(
        "/cash-flows",
        json={
            "date": "2025-07-01",
            "inflow_actual": 100.0,
            "outflow_actual": 50.0,
            "net_cash_flow": 50.0,
            "opening_balance": 500.0,
            "closing_balance": 550.0,
        },
        headers=analyst_hdr,
    )
    assert r_post.status_code == 403

    # Finance manager can create
    r_fin = client.post(
        "/cash-flows",
        json={
            "date": "2025-07-01",
            "inflow_actual": 100.0,
            "outflow_actual": 50.0,
            "net_cash_flow": 50.0,
            "opening_balance": 500.0,
            "closing_balance": 550.0,
        },
        headers=fin_hdr,
    )
    assert r_fin.status_code == 201
    cf_id = r_fin.json()["id"]

    # Delete -> 405
    r_del = client.delete(f"/cash-flows/{cf_id}", headers=fin_hdr)
    assert r_del.status_code == 405


@pytest.mark.unit
def test_cash_flow_summary_maths_against_seeded_data(api_setup):
    client, tokens, db, ref_date = api_setup
    analyst_hdr = auth_header(tokens["analyst_c1"])

    # Fetch summary as_of_date=2015-04-15
    res = client.get(f"/cash-flows/summary?as_of_date={ref_date.isoformat()}", headers=analyst_hdr)
    assert res.status_code == 200
    summary = res.json()

    last_7 = summary["last_7_days"]
    last_30 = summary["last_30_days"]

    # Calculate expected values directly from DB
    d7_start = ref_date - timedelta(days=6)
    d30_start = ref_date - timedelta(days=29)

    rows_7 = db.query(CashFlow).filter(CashFlow.company_id == 1, CashFlow.date >= d7_start, CashFlow.date <= ref_date).all()
    exp_inflow_7 = sum(r.inflow_actual for r in rows_7)
    exp_outflow_7 = sum(r.outflow_actual for r in rows_7)
    exp_net_7 = sum(r.net_cash_flow for r in rows_7)
    exp_gap_7 = sum(1 for r in rows_7 if r.liquidity_gap > Decimal("0.00"))

    assert len(rows_7) == 7
    assert Decimal(str(last_7["total_inflow"])) == exp_inflow_7
    assert Decimal(str(last_7["total_outflow"])) == exp_outflow_7
    assert Decimal(str(last_7["net_cash_flow"])) == exp_net_7
    assert last_7["days_with_liquidity_gap"] == exp_gap_7

    rows_30 = db.query(CashFlow).filter(CashFlow.company_id == 1, CashFlow.date >= d30_start, CashFlow.date <= ref_date).all()
    exp_inflow_30 = sum(r.inflow_actual for r in rows_30)
    exp_outflow_30 = sum(r.outflow_actual for r in rows_30)
    exp_net_30 = sum(r.net_cash_flow for r in rows_30)
    exp_gap_30 = sum(1 for r in rows_30 if r.liquidity_gap > Decimal("0.00"))

    assert len(rows_30) == 30
    assert Decimal(str(last_30["total_inflow"])) == exp_inflow_30
    assert Decimal(str(last_30["total_outflow"])) == exp_outflow_30
    assert Decimal(str(last_30["net_cash_flow"])) == exp_net_30
    assert last_30["days_with_liquidity_gap"] == exp_gap_30


@pytest.mark.unit
def test_cash_flow_latest(api_setup):
    client, tokens, db, ref_date = api_setup
    analyst_hdr = auth_header(tokens["analyst_c1"])

    res = client.get("/cash-flows/latest", headers=analyst_hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["date"] == ref_date.isoformat()
