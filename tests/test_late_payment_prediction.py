import pytest
from fastapi.testclient import TestClient
from datetime import timedelta
from app.core.clock import business_today
from app.main import app
from app.db.session import Base, get_db
from app.models.model_prediction import ModelPrediction
from app.models.invoice import Invoice
from app.models.buyer import Buyer
from app.models.supplier import Supplier
from app.models.company import Company
from app.models.user import User
from app.core.security import create_access_token, get_password_hash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

@pytest.fixture
def prediction_api_setup():
    # In-memory SQLite DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    # Minimal required data: company, user, buyer, supplier, invoice
    c1 = Company(id=1, name="Company 1", industry="Supply Chain")
    db.add(c1)
    db.commit()

    hashed_pw = get_password_hash("Secret123!")
    admin = User(id=1, username="admin", email="admin@c1.com", hashed_password=hashed_pw, role="admin", company_id=1, is_active=True)
    db.add(admin)
    db.commit()

    buyer = Buyer(buyer_id="BUY-01", country_code="IN", primary_supplier_id="SUP-01", credit_limit=100000, tier="A")
    supplier = Supplier(supplier_id="SUP-01", name="Supplier One", company_id=1, is_active=True)
    db.add_all([buyer, supplier])
    db.commit()

    today = business_today()
    invoice = Invoice(
        invoice_id=101,
        buyer_id="BUY-01",
        supplier_id="SUP-01",
        invoice_date=today - timedelta(days=10),
        due_date=today + timedelta(days=20),
        payment_terms_days=30,
        invoice_amount=50000,
        currency="INR",
        disputed=False,
        invoice_status="open",
    )
    db.add(invoice)
    db.commit()

    # Override DB dependency
    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token({"sub": "admin", "role": "admin", "company_id": 1})
    client = TestClient(app)

    yield {"client": client, "db": db, "token": token}

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)

@pytest.mark.unit
def test_predict_late_payment(prediction_api_setup):
    client = prediction_api_setup["client"]
    token = prediction_api_setup["token"]
    db = prediction_api_setup["db"]

    payload = {
        "invoice_id": 101,
        "invoice_amount": 50000,  # assume source scale (₹000)
        "invoice_month": 5,
        "invoice_dow": 2,
        "has_history": 0,
        "outstanding_amount_at_invoice": 20000,
        "outstanding_count_at_invoice": 3,
        "buyer_hist_late_rate": None,
        "buyer_hist_avg_delay_days": None,
        "buyer_hist_delay_std": None,
        "buyer_hist_max_delay": None,
        "country_code": "IN",
        "paperless_bill": None,
    }

    response = client.post(
        f"/invoices/{payload['invoice_id']}/predict",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "late_probability" in data
    assert "predicted_label" in data
    # Verify persistence
    pred = db.query(ModelPrediction).filter(ModelPrediction.invoice_id == 101).first()
    assert pred is not None
    assert abs(pred.late_probability - data["late_probability"]) < 1e-6
