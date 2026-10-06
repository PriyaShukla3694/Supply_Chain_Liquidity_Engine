from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.db.session import Base
from app.models import (
    Company,
    BusinessRule,
    User,
    Supplier,
    Buyer,
    Invoice,
    Payment,
    Transaction,
    CashFlow,
    RiskScore,
    DiscountOffer,
    Forecast,
    ModelPrediction,
    Document,
    DocumentChunk,
    AuditLog,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.unit
def test_all_tables_created(db_session):
    expected_tables = {
        "companies",
        "business_rules",
        "users",
        "suppliers",
        "buyers",
        "invoices",
        "payments",
        "transactions",
        "cash_flows",
        "risk_scores",
        "discount_offers",
        "forecasts",
        "model_predictions",
        "documents",
        "document_chunks",
        "audit_logs",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables), f"Missing tables: {expected_tables - actual_tables}"


@pytest.mark.unit
def test_supplier_and_buyer_creation(db_session):
    company = Company(name="Acme Corp", industry="Manufacturing")
    db_session.add(company)
    db_session.commit()

    # Verify supplier works with ONLY supplier_id (all other columns nullable)
    minimal_supplier = Supplier(supplier_id="SUP-99")
    db_session.add(minimal_supplier)
    db_session.commit()
    assert minimal_supplier.name is None

    supplier = Supplier(
        supplier_id="SUP-02",
        name="Global Steel Ltd",
        company_id=company.id,
        country_code="IN",
        is_active=True,
    )
    db_session.add(supplier)
    db_session.commit()

    buyer = Buyer(
        buyer_id="0187-ERLSR",
        country_code="IN",
        primary_supplier_id="SUP-02",
        behavioural_segment="Prompt Payer",
        tier="A",
        credit_limit=Decimal("5000000.00"),
        discount_responsiveness=0.85,
        blacklisted=False,
        disputed_flag=False,
        first_invoice_date=date(2025, 1, 1),
        last_invoice_date=date(2026, 2, 1),
    )
    db_session.add(buyer)
    db_session.commit()

    retrieved_buyer = db_session.query(Buyer).filter_by(buyer_id="0187-ERLSR").first()
    assert retrieved_buyer is not None
    assert retrieved_buyer.primary_supplier.name == "Global Steel Ltd"
    assert retrieved_buyer.credit_limit == Decimal("5000000.00")
    assert retrieved_buyer.tier == "A"

    # Verify buyer tier check constraint (tier not in 'A', 'B', 'C' and not null raises IntegrityError)
    invalid_buyer = Buyer(buyer_id="0188-INVALID", tier="D")
    db_session.add(invalid_buyer)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.unit
def test_invoice_bigint_and_relationships(db_session):
    supplier = Supplier(supplier_id="SUP-01", name="Apex Supplies")
    buyer = Buyer(buyer_id="BUY-100", country_code="IN", tier="B")
    db_session.add_all([supplier, buyer])
    db_session.commit()

    # invoice_id values go up to ~5.9 billion
    large_invoice_id = 5_900_000_001
    invoice = Invoice(
        invoice_id=large_invoice_id,
        buyer_id="BUY-100",
        supplier_id="SUP-01",
        invoice_date=date(2026, 1, 15),
        due_date=date(2026, 2, 15),
        payment_terms_days=31,
        invoice_amount=Decimal("1250000.50"),
        disputed=False,
        invoice_status="open",
    )
    db_session.add(invoice)
    db_session.commit()

    retrieved_invoice = db_session.query(Invoice).filter_by(invoice_id=large_invoice_id).first()
    assert retrieved_invoice is not None
    assert retrieved_invoice.invoice_amount == Decimal("1250000.50")
    assert retrieved_invoice.buyer.buyer_id == "BUY-100"
    assert retrieved_invoice.supplier.supplier_id == "SUP-01"


@pytest.mark.unit
def test_discount_offer_creation(db_session):
    company = Company(name="Finance Co")
    db_session.add(company)
    db_session.commit()

    user = User(
        username="fin_mgr",
        hashed_password="secretpasswordhash",
        role="finance_manager",
        company_id=company.id,
    )
    supplier = Supplier(supplier_id="SUP-03", name="Steel Inc")
    buyer = Buyer(buyer_id="BUY-200", country_code="IN", tier="A")
    db_session.add_all([user, supplier, buyer])
    db_session.commit()

    invoice = Invoice(
        invoice_id=1000001,
        buyer_id="BUY-200",
        supplier_id="SUP-03",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        payment_terms_days=30,
        invoice_amount=Decimal("200000.00"),
        invoice_status="open",
    )
    db_session.add(invoice)
    db_session.commit()

    payload_data = {
        "reasons": ["strong_payment_history", "sufficient_liquidity"],
        "delay_probability": 0.12,
        "liquidity_status": "HEALTHY",
    }

    offer = DiscountOffer(
        offer_id="OFF-2026-0001",
        invoice_id=1000001,
        buyer_id="BUY-200",
        offer_date=date(2026, 3, 5),
        deadline_date=date(2026, 3, 15),
        offered_rate_pct=Decimal("0.0150"),
        discount_amount=Decimal("3000.00"),
        net_payable_if_accepted=Decimal("197000.00"),
        days_accelerated=16,
        status="offered",
        recommended_by="optimizer",
        approved_by=user.id,
        approved_at=datetime.now(timezone.utc),
        requires_approval=False,
        recommendation_payload=payload_data,
    )
    db_session.add(offer)
    db_session.commit()

    retrieved = db_session.query(DiscountOffer).filter_by(offer_id="OFF-2026-0001").first()
    assert retrieved is not None
    assert retrieved.approved_by_user.username == "fin_mgr"
    assert retrieved.invoice.invoice_amount == Decimal("200000.00")
    assert retrieved.recommendation_payload["liquidity_status"] == "HEALTHY"


@pytest.mark.unit
def test_risk_scores_and_check_constraints(db_session):
    buyer = Buyer(buyer_id="BUY-300", country_code="IN", tier="A")
    db_session.add(buyer)
    db_session.commit()

    valid_risk = RiskScore(
        buyer_id="BUY-300",
        payment_reliability=Decimal("85.50"),
        financial_risk=Decimal("20.00"),
        liquidity_risk=Decimal("15.00"),
        overall_risk=Decimal("78.00"),
        tier="A",
        model_version="v1.0",
    )
    db_session.add(valid_risk)
    db_session.commit()

    # Out of range test (e.g. > 100) should trigger check constraint
    invalid_risk = RiskScore(
        buyer_id="BUY-300",
        payment_reliability=Decimal("105.00"),
        financial_risk=Decimal("20.00"),
        liquidity_risk=Decimal("15.00"),
        overall_risk=Decimal("78.00"),
        tier="A",
    )
    db_session.add(invalid_risk)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid tier test (e.g. 'Z') should trigger tier check constraint
    invalid_tier_risk = RiskScore(
        buyer_id="BUY-300",
        payment_reliability=Decimal("70.00"),
        financial_risk=Decimal("30.00"),
        liquidity_risk=Decimal("30.00"),
        overall_risk=Decimal("50.00"),
        tier="Z",
    )
    db_session.add(invalid_tier_risk)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.unit
def test_cash_flow_composite_unique_and_forecast(db_session):
    comp1 = Company(name="Supply Chain Corp")
    comp2 = Company(name="Partner Corp")
    db_session.add_all([comp1, comp2])
    db_session.commit()

    # Two different companies with the same date must succeed
    cf1 = CashFlow(
        company_id=comp1.id,
        date=date(2026, 4, 1),
        inflow_actual=Decimal("500000.00"),
        outflow_actual=Decimal("350000.00"),
        net_cash_flow=Decimal("150000.00"),
        opening_balance=Decimal("1000000.00"),
        closing_balance=Decimal("1150000.00"),
        outstanding_receivables=Decimal("2000000.00"),
        min_cash_buffer=Decimal("500000.00"),
        liquidity_gap=Decimal("0.00"),
    )
    cf2 = CashFlow(
        company_id=comp2.id,
        date=date(2026, 4, 1),
        inflow_actual=Decimal("300000.00"),
        outflow_actual=Decimal("200000.00"),
        net_cash_flow=Decimal("100000.00"),
        opening_balance=Decimal("500000.00"),
        closing_balance=Decimal("600000.00"),
        outstanding_receivables=Decimal("800000.00"),
        min_cash_buffer=Decimal("200000.00"),
        liquidity_gap=Decimal("0.00"),
    )
    db_session.add_all([cf1, cf2])
    db_session.commit()

    # Same company on the same date must fail due to UniqueConstraint(company_id, date)
    duplicate_cf = CashFlow(
        company_id=comp1.id,
        date=date(2026, 4, 1),
        inflow_actual=Decimal("10000.00"),
    )
    db_session.add(duplicate_cf)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    fc = Forecast(
        company_id=comp1.id,
        forecast_date=date(2026, 4, 1),
        horizon_days=7,
        expected_inflow=Decimal("200000.00"),
        expected_outflow=Decimal("250000.00"),
        net_liquidity=Decimal("-50000.00"),
        liquidity_gap=Decimal("50000.00"),
        status="URGENT",
    )
    db_session.add(fc)
    db_session.commit()

    assert cf1.id is not None
    assert cf2.id is not None
    assert fc.id is not None
    assert fc.status == "URGENT"


@pytest.mark.unit
def test_documents_chunks_and_audit_logs(db_session):
    company = Company(name="Logistics Co")
    db_session.add(company)
    db_session.commit()

    user = User(
        username="auditor",
        hashed_password="hash",
        role="admin",
        company_id=company.id,
    )
    db_session.add(user)
    db_session.commit()

    doc = Document(
        company_id=company.id,
        document_name="Discounting Policy 2026.pdf",
        document_type="policy",
        version="1.0",
        effective_date=date(2026, 1, 1),
        active_status=True,
        uploaded_by=user.id,
    )
    db_session.add(doc)
    db_session.commit()

    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        chunk_text="Tier A buyers are eligible for up to 1.75% discount.",
        metadata_json={"section": "3.1", "page": 2},
    )
    db_session.add(chunk)

    audit = AuditLog(
        user_id=user.id,
        action="policy_upload",
        entity_type="document",
        entity_id=str(doc.id),
        payload={"filename": "Discounting Policy 2026.pdf", "size_kb": 120},
    )
    db_session.add(audit)
    db_session.commit()

    retrieved_doc = db_session.query(Document).filter_by(id=doc.id).first()
    assert len(retrieved_doc.chunks) == 1
    assert retrieved_doc.chunks[0].chunk_text == "Tier A buyers are eligible for up to 1.75% discount."
    assert retrieved_doc.uploader.username == "auditor"

    retrieved_audit = db_session.query(AuditLog).filter_by(id=audit.id).first()
    assert retrieved_audit.payload["filename"] == "Discounting Policy 2026.pdf"
    assert retrieved_audit.user.username == "auditor"


@pytest.mark.unit
def test_payments_and_transactions(db_session):
    supplier = Supplier(supplier_id="SUP-04", name="Logistics Partner")
    buyer = Buyer(buyer_id="BUY-400", country_code="IN", tier="B")
    db_session.add_all([supplier, buyer])
    db_session.commit()

    invoice = Invoice(
        invoice_id=2000001,
        buyer_id="BUY-400",
        supplier_id="SUP-04",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        payment_terms_days=30,
        invoice_amount=Decimal("500000.00"),
        invoice_status="settled",
        settled_date=date(2026, 3, 20),
        days_late=0,
        is_late=False,
    )
    db_session.add(invoice)
    db_session.commit()

    payment = Payment(
        invoice_id=2000001,
        payment_date=date(2026, 3, 20),
        payment_amount=Decimal("495000.00"),
        payment_method="neft",
        reference_number="REF-NEFT-991",
        status="completed",
        discount_applied=Decimal("5000.00"),
    )
    db_session.add(payment)
    db_session.commit()

    tx = Transaction(
        payment_id=payment.payment_id,
        transaction_type="credit",
        amount=Decimal("495000.00"),
        transaction_date=datetime(2026, 3, 20, 10, 30, tzinfo=timezone.utc),
        status="settled",
        description="Invoice 2000001 settlement",
    )
    db_session.add(tx)
    db_session.commit()

    retrieved_pmt = db_session.query(Payment).filter_by(payment_id=payment.payment_id).first()
    assert retrieved_pmt is not None
    assert retrieved_pmt.invoice.invoice_id == 2000001
    assert len(retrieved_pmt.transactions) == 1
    assert retrieved_pmt.transactions[0].amount == Decimal("495000.00")


@pytest.mark.unit
def test_model_predictions(db_session):
    supplier = Supplier(supplier_id="SUP-05", name="Parts Corp")
    buyer = Buyer(buyer_id="BUY-500", country_code="IN", tier="C")
    db_session.add_all([supplier, buyer])
    db_session.commit()

    invoice = Invoice(
        invoice_id=3000001,
        buyer_id="BUY-500",
        supplier_id="SUP-05",
        invoice_date=date(2026, 4, 1),
        due_date=date(2026, 4, 30),
        invoice_amount=Decimal("150000.00"),
    )
    db_session.add(invoice)
    db_session.commit()

    pred = ModelPrediction(
        invoice_id=3000001,
        model_name="delay_xgboost",
        model_version="v2.1",
        late_probability=0.23,
        predicted_days_late=0,
    )
    db_session.add(pred)
    db_session.commit()

    retrieved = db_session.query(ModelPrediction).filter_by(invoice_id=3000001).first()
    assert retrieved is not None
    assert retrieved.late_probability == 0.23
    assert retrieved.invoice.invoice_id == 3000001
