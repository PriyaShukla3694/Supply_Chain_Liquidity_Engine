
"""Safe Data Importer for AI-Driven Discount Engine.

Reads buyers and invoice datasets, extracts suppliers from invoices,
validates schema and referential constraints, and converts monetary values
from ₹000 to INR exactly once.

Default behavior: DRY RUN ONLY (read-only).
Commit mode: --commit (single atomic database transaction).

Important:
- Buyer credit_limit is stored in ₹000 in the source CSV and converted to INR once.
- Invoice amounts are converted from ₹000 to INR once.
- Do not run --commit against a database that already contains imported records.
"""

import argparse
import csv
import subprocess
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VALIDATE_SCRIPT = ROOT / "scripts" / "validate_import.py"
BUYERS_FILE = ROOT / "source_data" / "buyers_clean.csv"
INVOICES_FILE = ROOT / "seed_data" / "invoices_merged_clean.csv"
ADVISORY_LOCK_KEY = 8472910482910481
EXPECTED_SUPPLIERS = 4
EXPECTED_BUYERS = 130
EXPECTED_INVOICES = 5000
EXPECTED_TOTAL_INR = Decimal("299405630.00")


def read_csv(path: Path):
    """Read a CSV file with UTF-8 BOM handling."""
    if not path.exists():
        raise FileNotFoundError(f"Missing required dataset: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader)


def valid_date(value: str, required: bool = False) -> bool:
    """Return whether value is a valid ISO date."""
    val = (value or "").strip()
    if not val:
        return not required
    try:
        date.fromisoformat(val)
        return True
    except (ValueError, TypeError):
        return False


def parse_decimal(value, field_name: str) -> Decimal:
    """Parse a required decimal value without silently accepting invalid data."""
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"{field_name} is blank")
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} is not a valid decimal: {text!r}")
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def run_pre_import_validation():
    """Run the shared pre-import validation script."""
    if not VALIDATE_SCRIPT.exists():
        return False, "", "Validation script scripts/validate_import.py not found."

    proc = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode == 0, proc.stdout, proc.stderr


def execute_commit_import(
    planned_suppliers: list,
    planned_buyers: list,
    planned_invoices: list,
    unique_supplier_ids: list,
):
    """Insert records in one atomic transaction; abort on existing target data."""
    try:
        from sqlalchemy import select, text
        from app.db.session import SessionLocal
        from app.models.supplier import Supplier
        from app.models.buyer import Buyer
        from app.models.invoice import Invoice
    except ImportError as exc:
        print(f"[ERROR] Database infrastructure import error: {exc}")
        print("Run this script inside the backend container with dependencies installed.")
        sys.exit(1)

    print("\n" + "=" * 65)
    print("      EXECUTING LIVE DATABASE IMPORT (--commit)")
    print("=" * 65)

    with SessionLocal() as session:
        try:
            with session.begin():
                print(f"1. Acquiring transaction advisory lock ({ADVISORY_LOCK_KEY})...")
                lock_acquired = session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                    {"lock_key": ADVISORY_LOCK_KEY},
                ).scalar()

                if not lock_acquired:
                    raise RuntimeError("Another import process holds the advisory lock.")
                print("   [LOCK ACQUIRED]")

                print("2. Checking target tables are empty...")
                pre_sup = session.scalar(text("SELECT count(*) FROM suppliers"))
                pre_buy = session.scalar(text("SELECT count(*) FROM buyers"))
                pre_inv = session.scalar(text("SELECT count(*) FROM invoices"))

                if pre_sup != 0 or pre_buy != 0 or pre_inv != 0:
                    raise ValueError(
                        "Target tables are not empty; refusing to overwrite or duplicate data. "
                        f"Found suppliers={pre_sup}, buyers={pre_buy}, invoices={pre_inv}."
                    )

                existing_suppliers = set(
                    session.scalars(
                        select(Supplier.supplier_id).where(
                            Supplier.supplier_id.in_(unique_supplier_ids)
                        )
                    ).all()
                )
                if existing_suppliers:
                    raise ValueError(
                        f"Supplier ID conflicts: {sorted(existing_suppliers)}"
                    )

                buyer_ids = [buyer["buyer_id"] for buyer in planned_buyers]
                existing_buyers = set(
                    session.scalars(
                        select(Buyer.buyer_id).where(Buyer.buyer_id.in_(buyer_ids))
                    ).all()
                )
                if existing_buyers:
                    raise ValueError(
                        f"Found {len(existing_buyers)} buyer ID conflicts; "
                        f"sample={sorted(existing_buyers)[:5]}"
                    )

                invoice_ids = [
                    inv["invoice_id"]
                    for inv in planned_invoices
                    if inv["invoice_id"] is not None
                ]
                existing_invoices = set(
                    session.scalars(
                        select(Invoice.invoice_id).where(
                            Invoice.invoice_id.in_(invoice_ids)
                        )
                    ).all()
                )
                if existing_invoices:
                    raise ValueError(
                        f"Found {len(existing_invoices)} invoice ID conflicts; "
                        f"sample={sorted(existing_invoices)[:5]}"
                    )

                print("3. Inserting suppliers...")
                session.add_all([Supplier(**item) for item in planned_suppliers])
                session.flush()

                print("4. Inserting buyers...")
                session.add_all([Buyer(**item) for item in planned_buyers])
                session.flush()

                print("5. Inserting invoices...")
                session.add_all([Invoice(**item) for item in planned_invoices])
                session.flush()

                print("6. Verifying pre-commit assertions...")
                counts = {
                    "suppliers": session.scalar(text("SELECT count(*) FROM suppliers")),
                    "buyers": session.scalar(text("SELECT count(*) FROM buyers")),
                    "invoices": session.scalar(text("SELECT count(*) FROM invoices")),
                }
                expected_counts = {
                    "suppliers": EXPECTED_SUPPLIERS,
                    "buyers": EXPECTED_BUYERS,
                    "invoices": EXPECTED_INVOICES,
                }
                if counts != expected_counts:
                    raise AssertionError(
                        f"Unexpected table counts: {counts}; expected {expected_counts}"
                    )

                if session.scalar(text("SELECT count(*) FROM companies WHERE id = 1")) != 1:
                    raise AssertionError("Expected company id=1 to remain intact.")
                if session.scalar(text("SELECT count(*) FROM users WHERE id = 1")) != 1:
                    raise AssertionError("Expected admin user id=1 to remain intact.")

                excluded_tables = [
                    "discount_offers",
                    "risk_scores",
                    "model_predictions",
                    "cash_flows",
                    "payments",
                    "transactions",
                ]
                for table in excluded_tables:
                    count = session.scalar(text(f"SELECT count(*) FROM {table}"))
                    if count != 0:
                        raise AssertionError(
                            f"Excluded table {table!r} must be empty; found {count} rows."
                        )

                total_inr_db = session.scalar(
                    text("SELECT COALESCE(sum(invoice_amount), 0) FROM invoices")
                )
                if total_inr_db != EXPECTED_TOTAL_INR:
                    raise AssertionError(
                        f"Expected total INR {EXPECTED_TOTAL_INR}, got {total_inr_db}"
                    )

                orphan_queries = {
                    "orphan buyers": """
                        SELECT count(*) FROM buyers b
                        WHERE b.primary_supplier_id IS NOT NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM suppliers s
                            WHERE s.supplier_id = b.primary_supplier_id
                          )
                    """,
                    "orphan invoice buyers": """
                        SELECT count(*) FROM invoices i
                        WHERE NOT EXISTS (
                            SELECT 1 FROM buyers b WHERE b.buyer_id = i.buyer_id
                        )
                    """,
                    "orphan invoice suppliers": """
                        SELECT count(*) FROM invoices i
                        WHERE NOT EXISTS (
                            SELECT 1 FROM suppliers s WHERE s.supplier_id = i.supplier_id
                        )
                    """,
                }
                for label, query in orphan_queries.items():
                    count = session.scalar(text(query))
                    if count != 0:
                        raise AssertionError(f"Found {count} {label}.")

                print("   [ALL ASSERTIONS PASSED]")
                print("7. Transaction will commit on successful exit.")

            print("\n[SUCCESS] Transaction committed successfully.")
            print(
                f"Imported {EXPECTED_SUPPLIERS} suppliers, {EXPECTED_BUYERS} buyers, "
                f"{EXPECTED_INVOICES} invoices."
            )
            print(f"Total invoice amount: ₹{EXPECTED_TOTAL_INR:,.2f}")

        except Exception as exc:
            print(f"\n[ABORTED] Transaction rolled back: {exc}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Safe Data Importer for AI-Driven Discount Engine."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write data to the database in one atomic transaction. Default is dry run.",
    )
    args = parser.parse_args()

    print("=" * 65)
    print("      AI-DRIVEN DISCOUNT ENGINE — DATA IMPORTER")
    print("=" * 65)
    if args.commit:
        print("Execution Mode: COMMIT (database writes enabled)")
    else:
        print("Execution Mode: DRY RUN (database writes disabled)")
    print()

    print("--- Step 1: Pre-import validation ---")
    validation_ok, validation_stdout, validation_stderr = run_pre_import_validation()
    if validation_stdout:
        print(validation_stdout, end="" if validation_stdout.endswith("\n") else "\n")
    if not validation_ok:
        if validation_stderr:
            print(validation_stderr)
        print("[FAIL] Pre-import validation failed; stopping.")
        sys.exit(1)
    print("[PASS] Pre-import validation passed.\n")

    print("--- Step 2: Reading datasets ---")
    try:
        buyers_raw = read_csv(BUYERS_FILE)
        invoices_raw = read_csv(INVOICES_FILE)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    print(f"Loaded buyers: {len(buyers_raw)}")
    print(f"Loaded invoices: {len(invoices_raw)}\n")

    required_buyer_columns = {
        "buyer_id", "primary_supplier_id", "credit_limit",
        "discount_responsiveness", "first_invoice_date", "last_invoice_date",
        "open_exposure_amount", "total_invoiced_amount",
        "open_invoice_count", "total_invoices",
    }
    required_invoice_columns = {
        "invoice_id", "buyer_id", "supplier_id", "invoice_date", "due_date",
        "payment_terms_days", "invoice_amount", "invoice_amount_display",
        "disputed", "invoice_status", "settled_date", "days_late", "is_late",
    }
    if not required_buyer_columns.issubset(buyers_raw[0].keys() if buyers_raw else set()):
        missing = sorted(required_buyer_columns - set(buyers_raw[0].keys() if buyers_raw else set()))
        print(f"[ERROR] Buyer CSV is missing required columns: {missing}")
        sys.exit(1)
    if not required_invoice_columns.issubset(invoices_raw[0].keys() if invoices_raw else set()):
        missing = sorted(required_invoice_columns - set(invoices_raw[0].keys() if invoices_raw else set()))
        print(f"[ERROR] Invoice CSV is missing required columns: {missing}")
        sys.exit(1)

    print("--- Step 3: Identifying suppliers from invoices ---")
    raw_supplier_ids = [row.get("supplier_id", "").strip() for row in invoices_raw]
    unique_supplier_ids = sorted({sid for sid in raw_supplier_ids if sid})
    missing_supplier_invoices = sum(not sid for sid in raw_supplier_ids)

    planned_suppliers = [
        {
            "supplier_id": sid,
            "name": None,
            "company_id": None,
            "contact_email": None,
            "contact_phone": None,
            "country_code": None,
            "bank_account_number": None,
            "ifsc_code": None,
            "is_active": True,
        }
        for sid in unique_supplier_ids
    ]
    print(f"Unique suppliers: {len(unique_supplier_ids)} -> {unique_supplier_ids}")
    print(f"Invoices with blank supplier ID: {missing_supplier_invoices}\n")

    print("--- Step 4: Staging buyers and validating constraints ---")
    buyer_ids = [row.get("buyer_id", "").strip() for row in buyers_raw]
    buyer_duplicates = [key for key, count in Counter(buyer_ids).items() if key and count > 1]
    blank_buyer_ids = sum(not buyer_id for buyer_id in buyer_ids)
    known_suppliers_set = set(unique_supplier_ids)

    unmatched_buyer_primary_suppliers = 0
    bad_buyer_numeric_fields = 0
    bad_buyer_dates = 0
    planned_buyers = []

    for row in buyers_raw:
        buyer_id = row.get("buyer_id", "").strip()
        primary_supplier = row.get("primary_supplier_id", "").strip() or None

        if primary_supplier and primary_supplier not in known_suppliers_set:
            unmatched_buyer_primary_suppliers += 1

        credit_limit = Decimal("0.00")
        responsiveness = None
        try:
            # Source credit_limit is in ₹000; convert to INR exactly once.
            credit_limit_raw = parse_decimal(
                row.get("credit_limit"), "credit_limit"
            )
            credit_limit = (
                credit_limit_raw * Decimal("1000")
            ).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            exposure = parse_decimal(
                row.get("open_exposure_amount"), "open_exposure_amount"
            )
            total_invoiced = parse_decimal(
                row.get("total_invoiced_amount"), "total_invoiced_amount"
            )
            open_count = int(row.get("open_invoice_count", "0") or "0")
            total_count = int(row.get("total_invoices", "0") or "0")
            resp_text = (row.get("discount_responsiveness") or "").strip()
            responsiveness = float(resp_text) if resp_text else None

            if min(credit_limit, exposure, total_invoiced) < 0:
                raise ValueError("monetary values cannot be negative")
            if open_count < 0 or total_count < 0 or open_count > total_count:
                raise ValueError("invalid invoice counts")
            if responsiveness is not None and not (0.0 <= responsiveness <= 1.0):
                raise ValueError("discount_responsiveness must be between 0 and 1")
        except (ValueError, TypeError, OverflowError, InvalidOperation) as exc:
            bad_buyer_numeric_fields += 1
            print(f"[ERROR] Buyer {buyer_id or '<blank ID>'}: {exc}")

        first_text = (row.get("first_invoice_date") or "").strip() or None
        last_text = (row.get("last_invoice_date") or "").strip() or None
        first_date = date.fromisoformat(first_text) if valid_date(first_text) and first_text else None
        last_date = date.fromisoformat(last_text) if valid_date(last_text) and last_text else None

        if not valid_date(first_text) or not valid_date(last_text):
            bad_buyer_dates += 1
            print(f"[ERROR] Buyer {buyer_id or '<blank ID>'}: invalid ISO date")
        elif first_date and last_date and first_date > last_date:
            bad_buyer_dates += 1
            print(f"[ERROR] Buyer {buyer_id}: first_invoice_date is after last_invoice_date")

        planned_buyers.append({
            "buyer_id": buyer_id,
            "country_code": (row.get("country_code") or "").strip() or None,
            "primary_supplier_id": primary_supplier,
            "behavioural_segment": (row.get("behavioural_segment") or "").strip() or None,
            "tier": None,
            "credit_limit": credit_limit,
            "discount_responsiveness": responsiveness,
            "blacklisted": False,
            "disputed_flag": False,
            "first_invoice_date": first_date,
            "last_invoice_date": last_date,
        })

    print(f"Planned buyers: {len(planned_buyers)}")
    print(f"Duplicate buyer IDs: {len(buyer_duplicates)}")
    print(f"Blank buyer IDs: {blank_buyer_ids}")
    print(f"Unmatched primary supplier references: {unmatched_buyer_primary_suppliers}")
    print(f"Invalid buyer numeric records: {bad_buyer_numeric_fields}")
    print(f"Invalid buyer dates/sequences: {bad_buyer_dates}\n")

    print("--- Step 5: Staging invoices and converting amounts ---")
    known_buyers_set = set(buyer_ids)
    invoice_id_texts = [row.get("invoice_id", "").strip() for row in invoices_raw]
    invoice_duplicates = [key for key, count in Counter(invoice_id_texts).items() if key and count > 1]
    blank_invoice_ids = sum(not value for value in invoice_id_texts)

    bad_invoice_ids = 0
    unmatched_invoice_buyers = 0
    unmatched_invoice_suppliers = 0
    bad_invoice_dates = 0
    bad_invoice_statuses = 0
    scale_mismatches = 0
    bad_invoice_amounts = 0
    bad_invoice_terms = 0
    bad_invoice_disputed = 0
    bad_invoice_delay_fields = 0

    total_raw_amount = Decimal("0.00")
    total_converted_inr = Decimal("0.00")
    sample_conversions = []
    planned_invoices = []

    for index, row in enumerate(invoices_raw):
        invoice_id_text = row.get("invoice_id", "").strip()
        buyer_id = row.get("buyer_id", "").strip()
        supplier_id = row.get("supplier_id", "").strip()
        status = row.get("invoice_status", "").strip().lower()

        if not invoice_id_text:
            parsed_invoice_id = None
        elif not invoice_id_text.isdigit():
            bad_invoice_ids += 1
            print(f"[ERROR] Row {index + 1}: invoice_id must contain digits only.")
            parsed_invoice_id = None
        else:
            parsed_invoice_id = int(invoice_id_text)

        if buyer_id not in known_buyers_set:
            unmatched_invoice_buyers += 1
        if supplier_id not in set(unique_supplier_ids):
            unmatched_invoice_suppliers += 1
        if status not in {"open", "settled"}:
            bad_invoice_statuses += 1

        invoice_date_text = row.get("invoice_date", "").strip()
        due_date_text = row.get("due_date", "").strip()
        settled_date_text = row.get("settled_date", "").strip() or None

        dates_valid = (
            valid_date(invoice_date_text, required=True)
            and valid_date(due_date_text, required=True)
            and valid_date(settled_date_text, required=False)
        )
        if not dates_valid:
            bad_invoice_dates += 1
        else:
            if invoice_date_text > due_date_text:
                bad_invoice_dates += 1
            elif status == "settled" and (
                not settled_date_text or settled_date_text < invoice_date_text
            ):
                bad_invoice_dates += 1
            elif status == "open" and settled_date_text:
                bad_invoice_dates += 1

        try:
            raw_amount = parse_decimal(row.get("invoice_amount"), "invoice_amount")
            display_amount = parse_decimal(
                row.get("invoice_amount_display"), "invoice_amount_display"
            )
            if raw_amount <= 0 or display_amount <= 0:
                bad_invoice_amounts += 1

            # The documented and display-validated single conversion boundary.
            inr_amount = (raw_amount * Decimal("1000")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            expected_display = display_amount.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if inr_amount != expected_display:
                scale_mismatches += 1

            total_raw_amount += raw_amount
            total_converted_inr += inr_amount
            if index < 5:
                sample_conversions.append(
                    (invoice_id_text, raw_amount, display_amount, inr_amount)
                )
        except (ValueError, InvalidOperation, TypeError) as exc:
            bad_invoice_amounts += 1
            print(f"[ERROR] Invoice {invoice_id_text or '<blank ID>'}: {exc}")
            inr_amount = Decimal("0.00")

        terms_text = (row.get("payment_terms_days") or "").strip()
        terms = 30
        if terms_text:
            try:
                terms_value = int(terms_text)
                if terms_value <= 0:
                    raise ValueError
                terms = terms_value
            except ValueError:
                bad_invoice_terms += 1
                print(f"[ERROR] Invoice {invoice_id_text}: invalid payment_terms_days")

        disputed_text = (row.get("disputed") or "").strip().lower()
        if disputed_text in {"0", "0.0", "false", "no", ""}:
            disputed = False
        elif disputed_text in {"1", "1.0", "true", "yes"}:
            disputed = True
        else:
            bad_invoice_disputed += 1
            disputed = False

        days_late_text = (row.get("days_late") or "").strip()
        days_late = None
        if days_late_text:
            try:
                late_value = Decimal(days_late_text)
                if not late_value.is_finite() or late_value < 0 or late_value != late_value.to_integral_value():
                    raise ValueError
                days_late = int(late_value)
            except (ValueError, InvalidOperation):
                bad_invoice_delay_fields += 1

        is_late_text = (row.get("is_late") or "").strip().lower()
        is_late = None
        if is_late_text in {"1", "1.0", "true", "yes"}:
            is_late = True
        elif is_late_text in {"0", "0.0", "false", "no"}:
            is_late = False
        elif is_late_text:
            bad_invoice_delay_fields += 1

        planned_invoices.append({
            "invoice_id": parsed_invoice_id,
            "buyer_id": buyer_id,
            "supplier_id": supplier_id,
            "invoice_date": date.fromisoformat(invoice_date_text) if valid_date(invoice_date_text, True) else None,
            "due_date": date.fromisoformat(due_date_text) if valid_date(due_date_text, True) else None,
            "payment_terms_days": terms,
            "invoice_amount": inr_amount,
            "currency": "INR",
            "disputed": disputed,
            "invoice_status": status,
            "settled_date": date.fromisoformat(settled_date_text) if settled_date_text and valid_date(settled_date_text) else None,
            "days_late": days_late,
            "is_late": is_late,
        })

    print(f"Planned invoices: {len(planned_invoices)}")
    print(f"Duplicate invoice IDs: {len(invoice_duplicates)}")
    print(f"Blank invoice IDs: {blank_invoice_ids}")
    print(f"Invalid invoice IDs: {bad_invoice_ids}")
    print(f"Unmatched invoice buyer references: {unmatched_invoice_buyers}")
    print(f"Unmatched invoice supplier references: {unmatched_invoice_suppliers}")
    print(f"Invalid invoice dates/sequences: {bad_invoice_dates}")
    print(f"Invalid invoice statuses: {bad_invoice_statuses}")
    print(f"Invalid invoice amounts: {bad_invoice_amounts}")
    print(f"Currency scale mismatches: {scale_mismatches}")
    print(f"Invalid payment terms: {bad_invoice_terms}")
    print(f"Invalid disputed flags: {bad_invoice_disputed}")
    print(f"Invalid delay fields: {bad_invoice_delay_fields}\n")

    print("--- Step 6: Currency conversion audit (₹000 -> INR) ---")
    print("Buyer credit limit conversion factor: 1,000x, exactly once")
    print("Invoice conversion factor: 1,000x, exactly once")
    print(f"Total source-scale amount: {total_raw_amount:,.2f} (₹000)")
    print(f"Total converted amount: ₹{total_converted_inr:,.2f}")
    print("\nSample conversions:")
    print(f"{'Invoice ID':<14} | {'Raw (₹000)':>14} | {'Display CSV':>14} | {'Converted INR':>16}")
    print("-" * 70)
    for invoice_id, raw, display, converted in sample_conversions:
        print(
            f"{invoice_id:<14} | {raw:>14,.2f} | {display:>14,.2f} | "
            f"₹{converted:>15,.2f}"
        )
    print("-" * 70)

    total_errors = (
        len(buyer_duplicates) + blank_buyer_ids + unmatched_buyer_primary_suppliers
        + bad_buyer_numeric_fields + bad_buyer_dates
        + len(invoice_duplicates) + blank_invoice_ids + bad_invoice_ids
        + unmatched_invoice_buyers + unmatched_invoice_suppliers
        + bad_invoice_dates + bad_invoice_statuses + bad_invoice_amounts
        + scale_mismatches + bad_invoice_terms + bad_invoice_disputed
        + bad_invoice_delay_fields
    )

    print("\n" + "=" * 65)
    print("                 IMPORT SUMMARY")
    print("=" * 65)
    print(f"Planned suppliers: {len(planned_suppliers):>6}")
    print(f"Planned buyers:    {len(planned_buyers):>6}")
    print(f"Planned invoices:  {len(planned_invoices):>6}")
    print(f"Total validation errors: {total_errors:>6}")
    print("=" * 65)

    if total_errors:
        print(f"[ERROR] Found {total_errors} validation issue(s); import is blocked.")
        sys.exit(1)

    if not args.commit:
        print("DRY RUN GUARANTEE: 0 inserts, 0 updates, 0 deletes.")
        print("[SUCCESS] Dry run passed. Database was not modified.")
        return

    execute_commit_import(
        planned_suppliers=planned_suppliers,
        planned_buyers=planned_buyers,
        planned_invoices=planned_invoices,
        unique_supplier_ids=unique_supplier_ids,
    )


if __name__ == "__main__":
    main()
