from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.db.session import Base
from app.main import app
from app.models.buyer import Buyer
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.model_prediction import ModelPrediction
from app.models.risk_score import RiskScore
from app.models.supplier import Supplier
from app.models.user import User
from app.services.prediction import (
    MODEL_NAME,
    MODEL_PATH,
    MODEL_VERSION,
    build_features_from_invoice,
    load_payment_model,
)


@pytest.fixture
def predict_test_env():
    """Isolated SQLite test environment for prediction endpoints."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    company = Company(id=1, name="Test Company", industry="Supply Chain")
    session.add(company)
    session.commit()

    hashed_pw = get_password_hash("SecretPass123!")
    analyst = User(
        id=1,
        username="analyst_user",
        email="analyst@example.com",
        hashed_password=hashed_pw,
        role="analyst",
        company_id=1,
        is_active=True,
    )
    session.add(analyst)
    session.commit()

    supplier = Supplier(
        supplier_id="SUPP-PRED-1",
        name="Predict Supplier",
        company_id=1,
        is_active=True,
    )
    buyer = Buyer(
        buyer_id="BUYER-PRED-1",
        country_code="770",
        primary_supplier_id="SUPP-PRED-1",
        credit_limit=Decimal("500000.00"),
        tier="A",
        tier_basis="scored",
    )
    session.add_all([supplier, buyer])
    session.commit()

    # Create target invoice and some historical invoices
    target_invoice = Invoice(
        invoice_id=9001,
        buyer_id="BUYER-PRED-1",
        supplier_id="SUPP-PRED-1",
        invoice_date=date(2025, 2, 1),
        due_date=date(2025, 3, 3),
        payment_terms_days=30,
        invoice_amount=Decimal("45000.00"),
        currency="INR",
        disputed=False,
        invoice_status="open",
    )
    # Historical settled invoice
    hist_invoice = Invoice(
        invoice_id=9000,
        buyer_id="BUYER-PRED-1",
        supplier_id="SUPP-PRED-1",
        invoice_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
        settled_date=date(2025, 1, 25),
        payment_terms_days=30,
        invoice_amount=Decimal("50000.00"),
        currency="INR",
        invoice_status="settled",
        is_late=False,
        days_late=0,
    )
    session.add_all([target_invoice, hist_invoice])
    session.commit()

    # RiskScore record for customer-risk endpoint
    risk_score = RiskScore(
        buyer_id="BUYER-PRED-1",
        payment_reliability=Decimal("85.50"),
        financial_risk=Decimal("90.00"),
        liquidity_risk=Decimal("88.00"),
        overall_risk=Decimal("86.20"),
        tier="A",
        tier_basis="scored",
        model_version="rules_v1",
        computed_at=datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    session.add(risk_score)
    session.commit()

    def override_get_db():
        db_sess = TestingSession()
        try:
            yield db_sess
        finally:
            db_sess.close()

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token({"sub": "analyst_user", "role": "analyst", "company_id": 1})
    client = TestClient(app)

    try:
        yield {
            "client": client,
            "session": session,
            "token": token,
            "invoice_id": 9001,
            "buyer_id": "BUYER-PRED-1",
        }
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)


@pytest.mark.unit
def test_predict_endpoints_200_and_response_fields(predict_test_env):
    """Verify 200 OK with real artifact, all expected response fields,

    calibrated probabilities in [0, 1], and on_time = 1 - late.
    """
    if not MODEL_PATH.exists():
        pytest.skip(f"Model artifact {MODEL_PATH} not present.")

    client = predict_test_env["client"]
    token = predict_test_env["token"]
    inv_id = predict_test_env["invoice_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Test GET /predict/payment-risk/{invoice_id}
    res = client.get(f"/predict/payment-risk/{inv_id}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    # Contract fields verification
    expected_fields = [
        "predicted_label",
        "late_probability",
        "threshold",
        "model_name",
        "model_version",
        "calibrated",
        "scored_at",
        "features_used",
        "on_time_probability",
        "risk_label",
        "reasons",
    ]
    for field in expected_fields:
        assert field in data, f"Missing required response field: {field}"

    late_p = data["late_probability"]
    on_time_p = data["on_time_probability"]

    assert 0.0 <= late_p <= 1.0, f"late_probability {late_p} out of [0, 1]"
    assert 0.0 <= on_time_p <= 1.0, f"on_time_probability {on_time_p} out of [0, 1]"
    assert abs((late_p + on_time_p) - 1.0) < 1e-4

    assert data["model_name"] == MODEL_NAME
    assert data["model_version"] == MODEL_VERSION
    assert data["threshold"] == 0.25
    assert data["calibrated"] is True
    assert data["risk_label"] in ("LOW", "MEDIUM", "HIGH")
    assert isinstance(data["reasons"], list)

    # Test GET /invoices/{invoice_id}/predict/auto route
    res_auto_get = client.get(f"/invoices/{inv_id}/predict/auto", headers=headers)
    assert res_auto_get.status_code == 200

    # Test POST /invoices/{invoice_id}/predict/auto route
    res_auto_post = client.post(f"/invoices/{inv_id}/predict/auto", headers=headers)
    assert res_auto_post.status_code == 200

    # Test POST /invoices/{invoice_id}/predict with 12 partial features
    payload_partial = {
        "invoice_id": inv_id,
        "invoice_amount": 45000.0,
        "invoice_month": 2,
        "invoice_dow": 5,
        "has_history": 1,
        "outstanding_amount_at_invoice": 0.0,
        "outstanding_count_at_invoice": 0,
        "buyer_hist_late_rate": 0.0,
        "buyer_hist_avg_delay_days": 0.0,
        "buyer_hist_delay_std": 0.0,
        "buyer_hist_max_delay": 0,
        "country_code": "770",
        "paperless_bill": None,
    }
    res_partial = client.post(f"/invoices/{inv_id}/predict", json=payload_partial, headers=headers)
    assert res_partial.status_code == 200, res_partial.text
    data_partial = res_partial.json()
    assert data_partial["partial_features"] is True
    assert 0.0 <= data_partial["late_probability"] <= 1.0


@pytest.mark.unit
def test_predict_endpoints_404_unknown_invoice(predict_test_env):
    """Accessing an unknown invoice returns 404."""
    client = predict_test_env["client"]
    token = predict_test_env["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/predict/payment-risk/999999", headers=headers)
    assert res.status_code == 404
    assert res.json()["code"] == "NOT_FOUND"


@pytest.mark.unit
def test_predict_endpoints_401_without_token(predict_test_env):
    """Calling prediction endpoints without authorization returns 401."""
    client = predict_test_env["client"]
    inv_id = predict_test_env["invoice_id"]

    res = client.get(f"/predict/payment-risk/{inv_id}")
    assert res.status_code == 401


@pytest.mark.unit
def test_predict_endpoints_503_when_loader_fails(predict_test_env):
    """When the model loader raises or fails, endpoints return HTTP 503

    {"detail":"Model not available","code":"MODEL_UNAVAILABLE"} while the app starts.
    """
    client = predict_test_env["client"]
    token = predict_test_env["token"]
    inv_id = predict_test_env["invoice_id"]
    headers = {"Authorization": f"Bearer {token}"}

    def failing_loader():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "Model not available", "code": "MODEL_UNAVAILABLE"},
        )

    with patch("app.services.prediction.load_payment_model", side_effect=failing_loader):
        res = client.get(f"/predict/payment-risk/{inv_id}", headers=headers)
        assert res.status_code == 503
        data = res.json()
        assert data.get("code") == "MODEL_UNAVAILABLE"
        assert "Model not available" in str(data.get("detail"))


@pytest.mark.unit
def test_batch_payment_risk_endpoint(predict_test_env):
    """Batch prediction supports up to 200 IDs and rejects 201 IDs with 422."""
    if not MODEL_PATH.exists():
        pytest.skip(f"Model artifact {MODEL_PATH} not present.")

    client = predict_test_env["client"]
    token = predict_test_env["token"]
    inv_id = predict_test_env["invoice_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Limit exceeded (201 ids) -> 422
    too_many = [inv_id] * 201
    res_422 = client.post("/predict/payment-risk/batch", json={"invoice_ids": too_many}, headers=headers)
    assert res_422.status_code == 422

    # Valid batch (1 id)
    res_200 = client.post("/predict/payment-risk/batch", json={"invoice_ids": [inv_id]}, headers=headers)
    assert res_200.status_code == 200
    batch_data = res_200.json()
    assert batch_data["count"] == 1
    assert len(batch_data["predictions"]) == 1


@pytest.mark.unit
def test_customer_risk_endpoint(predict_test_env):
    """GET /predict/customer-risk/{buyer_id} returns 200 for existing buyer and 404 for unknown."""
    client = predict_test_env["client"]
    token = predict_test_env["token"]
    buyer_id = predict_test_env["buyer_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 404 for unknown buyer
    res_404 = client.get("/predict/customer-risk/NON-EXISTENT", headers=headers)
    assert res_404.status_code == 404

    # 200 for valid buyer
    res_200 = client.get(f"/predict/customer-risk/{buyer_id}", headers=headers)
    assert res_200.status_code == 200
    data = res_200.json()
    assert data["buyer_id"] == buyer_id
    assert data["overall_risk"] == pytest.approx(86.20)
    assert data["payment_reliability"] == pytest.approx(85.50)
    assert data["financial_risk"] == pytest.approx(90.00)
    assert data["liquidity_risk"] == pytest.approx(88.00)
    assert data["tier"] == "A"
    assert data["tier_basis"] == "scored"
    assert data["as_of_date"] == "2025-02-01"


@pytest.mark.unit
def test_features_never_include_later_invoices(predict_test_env):
    """Features built strictly as of target invoice_date must ignore all later invoices

    and invoices settled after the target invoice date.
    """
    session = predict_test_env["session"]

    # Target invoice on 2025-06-01
    target = Invoice(
        invoice_id=8800,
        buyer_id="BUYER-DATE-ISOLATION",
        supplier_id="SUPP-PRED-1",
        invoice_date=date(2025, 6, 1),
        due_date=date(2025, 7, 1),
        invoice_amount=Decimal("10000.00"),
        invoice_status="open",
    )
    buyer = Buyer(
        buyer_id="BUYER-DATE-ISOLATION",
        country_code="770",
        primary_supplier_id="SUPP-PRED-1",
    )
    # Earlier invoice settled BEFORE target date (5 days late)
    inv_settled_before = Invoice(
        invoice_id=8801,
        buyer_id="BUYER-DATE-ISOLATION",
        supplier_id="SUPP-PRED-1",
        invoice_date=date(2025, 4, 1),
        due_date=date(2025, 5, 1),
        settled_date=date(2025, 5, 6),  # Settled before 2025-06-01
        invoice_amount=Decimal("20000.00"),
        invoice_status="settled",
        days_late=5,
        is_late=True,
    )
    # Earlier invoice settled AFTER target date (25 days late)
    inv_settled_after = Invoice(
        invoice_id=8802,
        buyer_id="BUYER-DATE-ISOLATION",
        supplier_id="SUPP-PRED-1",
        invoice_date=date(2025, 5, 1),
        due_date=date(2025, 5, 31),
        settled_date=date(2025, 6, 20),  # Settled AFTER 2025-06-01
        invoice_amount=Decimal("30000.00"),
        invoice_status="settled",
        days_late=25,
        is_late=True,
    )
    # Later invoice created AFTER target date
    inv_future = Invoice(
        invoice_id=8803,
        buyer_id="BUYER-DATE-ISOLATION",
        supplier_id="SUPP-PRED-1",
        invoice_date=date(2025, 8, 1),
        due_date=date(2025, 8, 31),
        settled_date=date(2025, 8, 25),
        invoice_amount=Decimal("40000.00"),
        invoice_status="settled",
        days_late=10,
        is_late=True,
    )
    session.add_all([buyer, target, inv_settled_before, inv_settled_after, inv_future])
    session.commit()

    features = build_features_from_invoice(invoice_id=8800, db=session)

    # 1. Prior invoice count: only invoices issued before 2025-06-01 (inv 8801 and 8802 -> 2 invoices)
    assert features["buyer_prior_invoice_count"] == 2

    # 2. Outcome metrics: ONLY inv 8801 was settled before 2025-06-01
    # inv 8802 (settled on 2025-06-20 with days_late=25) MUST BE IGNORED.
    assert features["buyer_hist_max_delay"] == 5.0
    assert features["buyer_hist_avg_delay_days"] == 5.0
    assert features["buyer_last_invoice_delay"] == 5.0
    assert features["has_history"] == 1

    # 3. Outstanding exposure at target date:
    # inv 8802 was issued before 2025-06-01 and not yet settled by 2025-06-01
    assert features["outstanding_count_at_invoice"] == 1
    assert features["outstanding_amount_at_invoice"] == pytest.approx(30000.00)

