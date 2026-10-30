import pytest
import numpy as np
from datetime import date, timedelta

from app.db.session import Base
from app.models.invoice import Invoice
from app.models.buyer import Buyer
from app.models.supplier import Supplier
from app.models.company import Company
from app.models.user import User
from app.core.security import create_access_token, get_password_hash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.prediction import build_features_from_invoice

@pytest.fixture
def db_setup():
    # In‑memory SQLite DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    # Minimal required data: company, user, buyer, supplier
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

    yield db

    Base.metadata.drop_all(engine)

def add_invoice(db, invoice_id, buyer_id, supplier_id, invoice_date, settled_date=None, days_late=None, is_late=None, status="settled"):
    inv = Invoice(
        invoice_id=invoice_id,
        buyer_id=buyer_id,
        supplier_id=supplier_id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=30),
        payment_terms_days=30,
        invoice_amount=1000,
        currency="INR",
        disputed=False,
        invoice_status=status,
        settled_date=settled_date,
        days_late=days_late,
        is_late=is_late,
    )
    db.add(inv)
    db.commit()
    return inv

def test_std_and_max_delay(db_setup):
    db = db_setup
    target_date = date(2023, 5, 10)

    # Historical settled invoices before target date with known delays
    add_invoice(db, 1, "BUY-01", "SUP-01", date(2023, 4, 1), settled_date=date(2023, 4, 5), days_late=2, is_late=1)
    add_invoice(db, 2, "BUY-01", "SUP-01", date(2023, 4, 10), settled_date=date(2023, 4, 15), days_late=5, is_late=1)
    add_invoice(db, 3, "BUY-01", "SUP-01", date(2023, 4, 20), settled_date=date(2023, 4, 28), days_late=8, is_late=1)

    # Target invoice (excluded from history)
    add_invoice(db, 99, "BUY-01", "SUP-01", target_date, settled_date=None, days_late=None, is_late=None, status="open")

    features = build_features_from_invoice(99, db)
    expected_std = float(np.std([2.0, 5.0, 8.0], ddof=0))
    expected_max = 8.0
    assert features["buyer_hist_delay_std"] == expected_std
    assert features["buyer_hist_max_delay"] == expected_max

def test_missing_delay_values_ignored(db_setup):
    db = db_setup
    target_date = date(2023, 6, 1)
    # One invoice without days_late, another with a valid delay
    add_invoice(db, 10, "BUY-01", "SUP-01", date(2023, 5, 1), settled_date=date(2023, 5, 5), days_late=None, is_late=0)
    add_invoice(db, 11, "BUY-01", "SUP-01", date(2023, 5, 10), settled_date=date(2023, 5, 15), days_late=4, is_late=1)
    add_invoice(db, 99, "BUY-01", "SUP-01", target_date, settled_date=None, days_late=None, is_late=None, status="open")

    features = build_features_from_invoice(99, db)
    assert features["buyer_hist_delay_std"] == float(np.std([4.0], ddof=0))
    assert features["buyer_hist_max_delay"] == 4.0

def test_no_usable_delays_results_in_none(db_setup):
    db = db_setup
    target_date = date(2023, 7, 1)
    # Historical invoices without any days_late information
    add_invoice(db, 20, "BUY-01", "SUP-01", date(2023, 6, 1), settled_date=date(2023, 6, 5), days_late=None, is_late=0)
    add_invoice(db, 21, "BUY-01", "SUP-01", date(2023, 6, 10), settled_date=date(2023, 6, 12), days_late=None, is_late=0)
    add_invoice(db, 99, "BUY-01", "SUP-01", target_date, settled_date=None, days_late=None, is_late=None, status="open")

    features = build_features_from_invoice(99, db)
    assert features["buyer_hist_delay_std"] is None
    assert features["buyer_hist_max_delay"] is None
