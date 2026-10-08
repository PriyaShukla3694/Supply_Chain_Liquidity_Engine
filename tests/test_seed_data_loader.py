import csv
from decimal import Decimal
import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.buyer import Buyer
from app.models.cash_flow import CashFlow
from app.models.company import Company
from app.models.discount_offer import DiscountOffer
from app.models.invoice import Invoice
from app.models.supplier import Supplier
from scripts.load_seed_data import load_all_seed_data


@pytest.fixture
def sqlite_db_session(tmp_path):
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fixture_seed_dir(tmp_path):
    seed_dir = tmp_path / "seed_data"
    seed_dir.mkdir()

    # 1. invoices_merged_clean.csv
    invoices_file = seed_dir / "invoices_merged_clean.csv"
    inv_fieldnames = [
        "invoice_id",
        "buyer_id",
        "supplier_id",
        "country_code",
        "invoice_date",
        "due_date",
        "payment_terms_days",
        "invoice_amount",
        "invoice_amount_display",
        "disputed",
        "paperless_bill",
        "invoice_status",
        "days_until_due",
        "discount_eligible_flag",
        "settled_date",
        "days_late",
        "is_late",
    ]
    with invoices_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=inv_fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "invoice_id": "1001",
                "buyer_id": "BUY-01",
                "supplier_id": "SUP-01",
                "country_code": "IN",
                "invoice_date": "2024-01-01",
                "due_date": "2024-01-31",
                "payment_terms_days": "30",
                "invoice_amount": "50.00",
                "invoice_amount_display": "50000.00",
                "disputed": "0",
                "paperless_bill": "1",
                "invoice_status": "open",
                "days_until_due": "15",
                "discount_eligible_flag": "1",
                "settled_date": "",
                "days_late": "",
                "is_late": "",
            }
        )
        writer.writerow(
            {
                "invoice_id": "1002",
                "buyer_id": "BUY-02",
                "supplier_id": "SUP-02",
                "country_code": "US",
                "invoice_date": "2024-01-05",
                "due_date": "2024-02-04",
                "payment_terms_days": "30",
                "invoice_amount": "120.00",
                "invoice_amount_display": "120000.00",
                "disputed": "1",
                "paperless_bill": "0",
                "invoice_status": "settled",
                "days_until_due": "0",
                "discount_eligible_flag": "0",
                "settled_date": "2024-02-10",
                "days_late": "6",
                "is_late": "1",
            }
        )

    # 2. discount_offers.csv
    offers_file = seed_dir / "discount_offers.csv"
    offer_fieldnames = [
        "offer_id",
        "invoice_id",
        "buyer_id",
        "supplier_id",
        "offer_date",
        "deadline_date",
        "due_date",
        "invoice_amount",
        "offered_rate_pct",
        "discount_amount",
        "net_payable_if_accepted",
        "days_accelerated",
        "status",
        "recommended_by",
        "approved_by",
        "data_origin",
        "ml_use_allowed",
        "recommendation_payload",
    ]
    with offers_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=offer_fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "offer_id": "OFF-0001",
                "invoice_id": "1001",
                "buyer_id": "BUY-01",
                "supplier_id": "SUP-01",
                "offer_date": "2024-01-10",
                "deadline_date": "2024-01-20",
                "due_date": "2024-01-31",
                "invoice_amount": "55.94",
                "offered_rate_pct": "1.48",
                "discount_amount": "0.83",
                "net_payable_if_accepted": "55.11",
                "days_accelerated": "11",
                "status": "accepted",
                "recommended_by": "optimizer",
                "approved_by": "",
                "data_origin": "SIMULATED_DEMONSTRATION_OFFER_HISTORY",
                "ml_use_allowed": "0",
                "recommendation_payload": json.dumps({"test": True}),
            }
        )

    return seed_dir


@pytest.mark.unit
def test_conversion_applied_exactly_once(sqlite_db_session, fixture_seed_dir):
    """Test that ₹000 -> ₹ is applied exactly once to monetary fields in discount_offers,

    and invoice_amount_display is used as-is without multiplying again.
    """
    summary = load_all_seed_data(sqlite_db_session, fixture_seed_dir)
    assert summary["invoices"] == 2
    assert summary["discount_offers"] == 1

    # Check offer amounts (converted * 1000 once)
    offer = sqlite_db_session.query(DiscountOffer).filter_by(offer_id="OFF-0001").first()
    assert offer is not None
    assert offer.invoice_amount == Decimal("55940.00")
    assert offer.discount_amount == Decimal("830.00")
    assert offer.net_payable_if_accepted == Decimal("55110.00")

    # Check invoice amounts (invoice_amount_display taken directly)
    inv1 = sqlite_db_session.query(Invoice).filter_by(invoice_id=1001).first()
    assert inv1 is not None
    assert inv1.invoice_amount == Decimal("50000.00")

    inv2 = sqlite_db_session.query(Invoice).filter_by(invoice_id=1002).first()
    assert inv2 is not None
    assert inv2.invoice_amount == Decimal("120000.00")


@pytest.mark.unit
def test_idempotent_rerun(sqlite_db_session, fixture_seed_dir):
    """Test that re-running the loader causes no duplicate rows and inserts 0 new rows."""
    summary1 = load_all_seed_data(sqlite_db_session, fixture_seed_dir)
    assert summary1["invoices"] == 2
    assert summary1["discount_offers"] == 1

    summary2 = load_all_seed_data(sqlite_db_session, fixture_seed_dir)
    assert summary2["companies"] == 0
    assert summary2["suppliers"] == 0
    assert summary2["buyers"] == 0
    assert summary2["invoices"] == 0
    assert summary2["discount_offers"] == 0

    assert sqlite_db_session.query(Invoice).count() == 2
    assert sqlite_db_session.query(DiscountOffer).count() == 1


@pytest.mark.unit
def test_fk_order_and_integrity(sqlite_db_session, fixture_seed_dir):
    """Test that records are inserted in proper FK order without integrity violations."""
    load_all_seed_data(sqlite_db_session, fixture_seed_dir)

    company = sqlite_db_session.query(Company).filter_by(name="Default Company").first()
    assert company is not None

    suppliers = sqlite_db_session.query(Supplier).all()
    assert len(suppliers) == 2
    for s in suppliers:
        assert s.company_id == company.id

    buyers = sqlite_db_session.query(Buyer).all()
    assert len(buyers) == 2
    for b in buyers:
        assert b.tier is None  # tier left NULL for now
        assert b.primary_supplier_id in ("SUP-01", "SUP-02")

    offer = sqlite_db_session.query(DiscountOffer).filter_by(offer_id="OFF-0001").first()
    assert offer.invoice is not None
    assert offer.buyer is not None
    assert offer.approved_by is None


@pytest.mark.unit
def test_offers_keep_ml_use_allowed_false(sqlite_db_session, fixture_seed_dir):
    """Test that discount offers preserve ml_use_allowed=False and data_origin metadata."""
    load_all_seed_data(sqlite_db_session, fixture_seed_dir)

    offer = sqlite_db_session.query(DiscountOffer).filter_by(offer_id="OFF-0001").first()
    assert offer is not None
    assert offer.ml_use_allowed is False
    assert offer.data_origin == "SIMULATED_DEMONSTRATION_OFFER_HISTORY"
    assert offer.recommendation_payload == {"test": True}
