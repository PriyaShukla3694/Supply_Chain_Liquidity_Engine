"""Seed Data Loader for Supply Chain Liquidity Engine.

Loads initial data in foreign key order:
1. Default Company
2. Suppliers (distinct supplier_id from invoices)
3. Buyers (from seed_data/buyers_clean.csv if present, else derived from invoices)
4. Invoices (from seed_data/invoices_merged_clean.csv)
5. Cash Flows (from seed_data/daily_cash_flow_clean.csv if present)
6. Discount Offers (from seed_data/discount_offers.csv)

Idempotent: Safe to re-run without duplicate rows or errors.
"""

from collections import Counter
import csv
from datetime import date, datetime
from decimal import Decimal
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.business_rules import DEFAULT_BUSINESS_RULES, get_business_rule
from app.db.session import SessionLocal
from app.models.buyer import Buyer
from app.models.cash_flow import CashFlow
from app.models.company import Company
from app.models.discount_offer import DiscountOffer
from app.models.invoice import Invoice
from app.models.supplier import Supplier

logger = logging.getLogger("seed_data_loader")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

ALLOWED_OFFER_STATUSES = {
    "recommended",
    "offered",
    "accepted",
    "declined",
    "expired",
    "rejected",
}


def parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("none", "nan", "null"):
        return None
    try:
        return datetime.strptime(val_str, "%Y-%m-%d").date()
    except ValueError:
        return datetime.fromisoformat(val_str).date()


def upsert_records(
    db: Session,
    model: Any,
    records: List[Dict[str, Any]],
    conflict_target: Optional[List[str]] = None,
    batch_size: int = 500,
) -> int:
    """Inserts records using ON CONFLICT DO NOTHING / insert or ignore.

    Returns the number of newly inserted rows.
    """
    if not records:
        return 0

    count_before = db.query(model).count()
    dialect_name = db.bind.dialect.name
    table = model.__table__

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        if dialect_name == "postgresql":
            stmt = pg_insert(table).values(batch)
            if conflict_target:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_target)
            else:
                stmt = stmt.on_conflict_do_nothing()
            db.execute(stmt)
        elif dialect_name == "sqlite":
            stmt = sqlite_insert(table).values(batch)
            if conflict_target:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_target)
            else:
                stmt = stmt.on_conflict_do_nothing()
            db.execute(stmt)
        else:
            for item in batch:
                obj = model(**item)
                db.merge(obj)
        db.commit()

    count_after = db.query(model).count()
    return count_after - count_before


def load_default_company(db: Session) -> Company:
    company = db.query(Company).filter(Company.name == "Default Company").first()
    if not company:
        company = Company(name="Default Company", industry="Supply Chain")
        db.add(company)
        db.commit()
        db.refresh(company)
        logger.info("Created Default Company (ID: %s)", company.id)
    return company


def load_suppliers(
    db: Session, company_id: int, invoice_rows: List[Dict[str, str]]
) -> int:
    distinct_suppliers = sorted(
        list(set(row["supplier_id"].strip() for row in invoice_rows if row.get("supplier_id")))
    )
    records = [
        {"supplier_id": s_id, "company_id": company_id}
        for s_id in distinct_suppliers
    ]
    return upsert_records(db, Supplier, records, conflict_target=["supplier_id"])


def load_buyers(
    db: Session,
    seed_dir: Path,
    invoice_rows: List[Dict[str, str]],
) -> int:
    buyers_path = seed_dir / "buyers_clean.csv"
    buyer_records: List[Dict[str, Any]] = []

    if buyers_path.exists():
        logger.info("Loading buyers from %s", buyers_path)
        with buyers_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                credit_limit_raw = row.get("credit_limit")
                credit_limit = None
                if credit_limit_raw not in (None, ""):
                    try:
                        credit_limit = round(Decimal(str(credit_limit_raw)) * 1000, 2)
                    except Exception:
                        credit_limit = None

                disc_resp = None
                if row.get("discount_responsiveness") not in (None, ""):
                    try:
                        disc_resp = float(row["discount_responsiveness"])
                    except Exception:
                        disc_resp = None

                buyer_records.append(
                    {
                        "buyer_id": row["buyer_id"].strip(),
                        "country_code": row.get("country_code") or None,
                        "primary_supplier_id": row.get("primary_supplier_id") or None,
                        "behavioural_segment": row.get("behavioural_segment") or None,
                        "tier": None,  # tier left NULL for now
                        "tier_basis": row.get("tier_basis") or None,
                        "credit_limit": credit_limit,
                        "discount_responsiveness": disc_resp,
                        "blacklisted": str(row.get("blacklisted", "0")).strip().lower() in ("1", "true"),
                        "disputed_flag": str(row.get("disputed_flag", "0")).strip().lower() in ("1", "true"),
                        "first_invoice_date": parse_date(row.get("first_invoice_date")),
                        "last_invoice_date": parse_date(row.get("last_invoice_date")),
                    }
                )
    else:
        logger.warning(
            "Optional file '%s' not found. Deriving buyers from invoice data.",
            buyers_path,
        )
        grouped_by_buyer: Dict[str, List[Dict[str, str]]] = {}
        for row in invoice_rows:
            b_id = row.get("buyer_id", "").strip()
            if b_id:
                grouped_by_buyer.setdefault(b_id, []).append(row)

        for b_id, invs in grouped_by_buyer.items():
            supplier_counts = Counter(
                inv.get("supplier_id") for inv in invs if inv.get("supplier_id")
            )
            primary_supplier = supplier_counts.most_common(1)[0][0] if supplier_counts else None

            inv_dates = [parse_date(inv.get("invoice_date")) for inv in invs if inv.get("invoice_date")]
            valid_dates = [d for d in inv_dates if d is not None]
            first_inv = min(valid_dates) if valid_dates else None
            last_inv = max(valid_dates) if valid_dates else None

            country = invs[0].get("country_code") or None
            any_disputed = any(
                str(inv.get("disputed", "0")).strip().lower() in ("1", "true")
                for inv in invs
            )

            buyer_records.append(
                {
                    "buyer_id": b_id,
                    "country_code": country,
                    "primary_supplier_id": primary_supplier,
                    "behavioural_segment": None,
                    "tier": None,  # tier left NULL for now
                    "tier_basis": None,
                    "credit_limit": None,
                    "discount_responsiveness": None,
                    "blacklisted": False,
                    "disputed_flag": any_disputed,
                    "first_invoice_date": first_inv,
                    "last_invoice_date": last_inv,
                }
            )

    return upsert_records(db, Buyer, buyer_records, conflict_target=["buyer_id"])


def load_invoices(db: Session, invoice_rows: List[Dict[str, str]]) -> int:
    records: List[Dict[str, Any]] = []
    for row in invoice_rows:
        amount_raw = row.get("invoice_amount_display")
        if amount_raw in (None, ""):
            continue
        invoice_amount = round(Decimal(str(amount_raw)), 2)

        terms_raw = row.get("payment_terms_days")
        terms = int(float(terms_raw)) if terms_raw not in (None, "") else 30

        disputed = str(row.get("disputed", "0")).strip().lower() in ("1", "true")
        raw_status = row.get("invoice_status", "open").strip().lower()
        invoice_status = raw_status if raw_status in ("open", "settled") else "open"

        settled_date = parse_date(row.get("settled_date"))
        days_late_raw = row.get("days_late")
        days_late = int(float(days_late_raw)) if days_late_raw not in (None, "") else None

        is_late_raw = row.get("is_late")
        is_late = None
        if is_late_raw not in (None, ""):
            is_late = str(is_late_raw).strip().lower() in ("1", "true")

        records.append(
            {
                "invoice_id": int(row["invoice_id"]),
                "buyer_id": row["buyer_id"].strip(),
                "supplier_id": row["supplier_id"].strip(),
                "invoice_date": parse_date(row["invoice_date"]),
                "due_date": parse_date(row["due_date"]),
                "payment_terms_days": terms,
                "invoice_amount": invoice_amount,
                "currency": "INR",
                "disputed": disputed,
                "invoice_status": invoice_status,
                "settled_date": settled_date,
                "days_late": days_late,
                "is_late": is_late,
            }
        )

    return upsert_records(db, Invoice, records, conflict_target=["invoice_id"])


def load_cash_flows(db: Session, seed_dir: Path, company_id: int) -> int:
    cf_path = seed_dir / "daily_cash_flow_clean.csv"
    if not cf_path.exists():
        logger.warning(
            "Optional file '%s' not found. Skipping cash flows.", cf_path
        )
        return 0

    logger.info("Loading cash flows from %s", cf_path)
    records: List[Dict[str, Any]] = []
    with cf_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = parse_date(row.get("date"))
            if not dt:
                continue

            def conv(key: str) -> Decimal:
                val = row.get(key)
                if val in (None, ""):
                    return Decimal("0.00")
                return round(Decimal(str(val)) * 1000, 2)

            records.append(
                {
                    "company_id": company_id,
                    "date": dt,
                    "inflow_actual": conv("inflow_actual"),
                    "outflow_actual": conv("outflow_actual"),
                    "net_cash_flow": conv("net_cash_flow"),
                    "opening_balance": conv("opening_balance"),
                    "closing_balance": conv("closing_balance"),
                    "outstanding_receivables": conv("outstanding_receivables"),
                    "min_cash_buffer": conv("min_cash_buffer"),
                    "liquidity_gap": conv("liquidity_gap"),
                }
            )

    return upsert_records(
        db, CashFlow, records, conflict_target=["company_id", "date"]
    )


def load_discount_offers(db: Session, seed_dir: Path) -> int:
    offers_path = seed_dir / "discount_offers.csv"
    if not offers_path.exists():
        logger.warning(
            "Optional file '%s' not found. Skipping discount offers.", offers_path
        )
        return 0

    logger.info("Loading discount offers from %s", offers_path)

    # Human approval thresholds from business rules
    human_rules = (
        get_business_rule(db, "human_approval_thresholds")
        or DEFAULT_BUSINESS_RULES.get("human_approval_thresholds", {})
    )
    max_discount_thresh = Decimal(str(human_rules.get("max_discount_amount", 1000.0)))
    max_invoice_thresh = Decimal(str(human_rules.get("max_invoice_amount", 100000.0)))

    records: List[Dict[str, Any]] = []
    with offers_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            offer_id = row.get("offer_id", "").strip()
            if not offer_id:
                continue

            inv_id = int(row["invoice_id"])
            buyer_id = row["buyer_id"].strip()
            offer_date = parse_date(row["offer_date"])
            deadline_date = parse_date(row["deadline_date"])

            rate_pct = Decimal(str(row.get("offered_rate_pct") or 0))

            # Monetary columns converted x1000 once
            inv_amt = round(Decimal(str(row.get("invoice_amount") or 0)) * 1000, 2)
            disc_amt = round(Decimal(str(row.get("discount_amount") or 0)) * 1000, 2)
            net_payable = round(Decimal(str(row.get("net_payable_if_accepted") or 0)) * 1000, 2)

            days_acc_raw = row.get("days_accelerated")
            days_acc = int(float(days_acc_raw)) if days_acc_raw not in (None, "") else 0

            raw_status = row.get("status", "").strip().lower()
            status = raw_status if raw_status in ALLOWED_OFFER_STATUSES else "recommended"

            rec_by = row.get("recommended_by") or "optimizer"

            # Parse recommendation_payload to JSON object
            raw_payload = row.get("recommendation_payload")
            payload = None
            if isinstance(raw_payload, str) and raw_payload.strip():
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {"raw": raw_payload}
            elif isinstance(raw_payload, dict):
                payload = raw_payload

            data_origin = row.get("data_origin")
            ml_use_allowed = str(row.get("ml_use_allowed", "0")).strip().lower() in ("1", "true")

            # requires_approval = discount_amount > 1000 OR invoice_amount > 100000
            requires_approval = bool(
                disc_amt > max_discount_thresh or inv_amt > max_invoice_thresh
            )

            records.append(
                {
                    "offer_id": offer_id,
                    "invoice_id": inv_id,
                    "buyer_id": buyer_id,
                    "offer_date": offer_date,
                    "deadline_date": deadline_date,
                    "invoice_amount": inv_amt,
                    "offered_rate_pct": rate_pct,
                    "discount_amount": disc_amt,
                    "net_payable_if_accepted": net_payable,
                    "days_accelerated": days_acc,
                    "status": status,
                    "recommended_by": rec_by,
                    "approved_by": None,  # approved_by stays NULL
                    "approved_at": None,
                    "requires_approval": requires_approval,
                    "recommendation_payload": payload,
                    "data_origin": data_origin,
                    "ml_use_allowed": ml_use_allowed,
                }
            )

    return upsert_records(
        db, DiscountOffer, records, conflict_target=["offer_id"]
    )


def load_all_seed_data(
    db: Session, seed_dir: Optional[Path] = None
) -> Dict[str, int]:
    """Loads all seed data in foreign key order idempotently.

    Returns a dictionary of inserted row counts per table.
    """
    if seed_dir is None:
        seed_dir = BASE_DIR / "seed_data"

    logger.info("Starting seed data loader from directory: %s", seed_dir)

    invoices_file = seed_dir / "invoices_merged_clean.csv"
    if not invoices_file.exists():
        raise FileNotFoundError(f"Invoices seed file not found: {invoices_file}")

    with invoices_file.open("r", encoding="utf-8-sig") as f:
        invoice_rows = list(csv.DictReader(f))

    # 1. Company
    company_before = db.query(Company).filter(Company.name == "Default Company").count()
    default_company = load_default_company(db)
    inserted_companies = 1 if company_before == 0 else 0

    # 2. Suppliers
    inserted_suppliers = load_suppliers(db, default_company.id, invoice_rows)

    # 3. Buyers
    inserted_buyers = load_buyers(db, seed_dir, invoice_rows)

    # 4. Invoices
    inserted_invoices = load_invoices(db, invoice_rows)

    # 5. Cash Flows (optional)
    inserted_cash_flows = load_cash_flows(db, seed_dir, default_company.id)

    # 6. Discount Offers (optional)
    inserted_offers = load_discount_offers(db, seed_dir)

    summary = {
        "companies": inserted_companies,
        "suppliers": inserted_suppliers,
        "buyers": inserted_buyers,
        "invoices": inserted_invoices,
        "cash_flows": inserted_cash_flows,
        "discount_offers": inserted_offers,
    }

    print("\n--- Seed Data Loading Summary ---")
    for table_name, count in summary.items():
        print(f"  {table_name}: {count} inserted")
    print("---------------------------------\n")

    return summary


def main():
    db = SessionLocal()
    try:
        load_all_seed_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
