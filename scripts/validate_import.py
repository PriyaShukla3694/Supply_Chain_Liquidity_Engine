import csv
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BUYERS_FILE = ROOT / "source_data" / "buyers_clean.csv"
INVOICES_FILE = ROOT / "seed_data" / "invoices_merged_clean.csv"
OFFERS_FILE = ROOT / "seed_data" / "discount_offers.csv"

errors = []
warnings = []


def read_csv(path):
    if not path.exists():
        errors.append(f"Missing file: {path}")
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def check_unique(rows, column, label):
    values = [row.get(column, "").strip() for row in rows]
    duplicates = [key for key, count in Counter(values).items()
                  if key and count > 1]
    blanks = sum(not value for value in values)

    if duplicates:
        errors.append(f"{label}: {len(duplicates)} duplicate {column} values")
    if blanks:
        errors.append(f"{label}: {blanks} blank {column} values")

    print(f"{label}: {len(rows)} rows; duplicate {column}: {len(duplicates)}")


def valid_date(value, required=False):
    val = (value or "").strip()
    if not val:
        return not required
    try:
        date.fromisoformat(val)
        return True
    except ValueError:
        return False


buyers = read_csv(BUYERS_FILE)
invoices = read_csv(INVOICES_FILE)
offers = read_csv(OFFERS_FILE)

print("=== READ-ONLY IMPORT VALIDATION ===")
print(f"Buyers CSV:   {len(buyers)} rows")
print(f"Invoices CSV: {len(invoices)} rows")
print(f"Offers CSV:   {len(offers)} rows")

check_unique(buyers, "buyer_id", "Buyers")
check_unique(invoices, "invoice_id", "Invoices")
check_unique(offers, "offer_id", "Offers")

buyer_ids = {r["buyer_id"].strip() for r in buyers if r.get("buyer_id")}
invoice_ids = {r["invoice_id"].strip() for r in invoices if r.get("invoice_id")}
supplier_ids = {r["supplier_id"].strip() for r in invoices if r.get("supplier_id")}
invoices_by_id = {r["invoice_id"].strip(): r for r in invoices if r.get("invoice_id")}

print(f"\nUnique supplier IDs from invoices: {sorted(supplier_ids)}")

# Buyer references and fields validation
missing_primary_supplier = sum(
    1 for r in buyers
    if r.get("primary_supplier_id", "").strip()
    and r["primary_supplier_id"].strip() not in supplier_ids
)
if missing_primary_supplier:
    errors.append(f"Buyers with primary supplier absent from invoices: {missing_primary_supplier}")

bad_buyer_numeric_fields = 0
bad_buyer_dates = 0
for b in buyers:
    try:
        credit = Decimal(b.get("credit_limit", "0") or "0")
        exposure = Decimal(b.get("open_exposure_amount", "0") or "0")
        total_amt = Decimal(b.get("total_invoiced_amount", "0") or "0")
        resp = Decimal(b.get("discount_responsiveness", "0") or "0")
        open_cnt = int(b.get("open_invoice_count", "0") or "0")
        tot_cnt = int(b.get("total_invoices", "0") or "0")

        if credit < 0 or exposure < 0 or total_amt < 0 or open_cnt < 0 or tot_cnt < 0:
            bad_buyer_numeric_fields += 1
        elif not (Decimal("0") <= resp <= Decimal("1")):
            bad_buyer_numeric_fields += 1
        elif open_cnt > tot_cnt:
            bad_buyer_numeric_fields += 1
    except Exception:
        bad_buyer_numeric_fields += 1

    first_d = b.get("first_invoice_date", "").strip()
    last_d = b.get("last_invoice_date", "").strip()
    if not valid_date(first_d, required=False) or not valid_date(last_d, required=False):
        bad_buyer_dates += 1
    elif first_d and last_d and first_d > last_d:
        bad_buyer_dates += 1

if bad_buyer_numeric_fields:
    errors.append(f"Buyers with invalid numeric fields: {bad_buyer_numeric_fields}")
if bad_buyer_dates:
    errors.append(f"Buyers with invalid date fields or sequences: {bad_buyer_dates}")

# Invoice references, status, supplier, dates and amounts
missing_invoice_buyers = sum(
    1 for r in invoices if r.get("buyer_id", "").strip() not in buyer_ids
)
if missing_invoice_buyers:
    errors.append(f"Invoices referencing missing buyers: {missing_invoice_buyers}")

missing_invoice_suppliers = sum(
    1 for r in invoices if not r.get("supplier_id", "").strip()
)
if missing_invoice_suppliers:
    errors.append(f"Invoices with missing supplier ID: {missing_invoice_suppliers}")

bad_invoice_status = [
    r.get("invoice_id", "") for r in invoices
    if r.get("invoice_status", "").strip() not in {"open", "settled"}
]
if bad_invoice_status:
    errors.append(f"Invalid invoice statuses: {len(bad_invoice_status)}")

bad_invoice_dates = 0
bad_invoice_date_sequences = 0
for r in invoices:
    inv_date = r.get("invoice_date", "").strip()
    due_date = r.get("due_date", "").strip()
    settled_date = r.get("settled_date", "").strip()
    status = r.get("invoice_status", "").strip().lower()

    date_valid = (
        valid_date(inv_date, required=True)
        and valid_date(due_date, required=True)
        and valid_date(settled_date, required=False)
    )
    if not date_valid:
        bad_invoice_dates += 1
        continue

    # Sequence and status consistency
    if inv_date > due_date:
        bad_invoice_date_sequences += 1
    elif status == "settled":
        if not settled_date or settled_date < inv_date:
            bad_invoice_date_sequences += 1
    elif status == "open":
        if settled_date:
            bad_invoice_date_sequences += 1

if bad_invoice_dates:
    errors.append(f"Invoices with invalid dates: {bad_invoice_dates}")
if bad_invoice_date_sequences:
    errors.append(f"Invoices with invalid date sequences: {bad_invoice_date_sequences}")

bad_invoice_amounts = 0
amount_scale_mismatches = 0
for row in invoices:
    try:
        raw_amount = Decimal(row["invoice_amount"])
        display_amount = Decimal(row["invoice_amount_display"])
        if raw_amount <= 0 or display_amount <= 0:
            bad_invoice_amounts += 1
        if raw_amount * Decimal("1000") != display_amount:
            amount_scale_mismatches += 1
    except Exception:
        bad_invoice_amounts += 1

if bad_invoice_amounts:
    errors.append(f"Invalid or non-positive invoice amounts: {bad_invoice_amounts}")
if amount_scale_mismatches:
    errors.append(f"Invoice amount scale mismatches: {amount_scale_mismatches}")

# Offer references, statuses, cross-entity consistency, amounts, arithmetic and payload
allowed_offer_statuses = {
    "recommended", "offered", "accepted", "declined", "expired", "rejected"
}
missing_offer_invoices = sum(
    1 for r in offers if r.get("invoice_id", "").strip() not in invoice_ids
)
missing_offer_buyers = sum(
    1 for r in offers if r.get("buyer_id", "").strip() not in buyer_ids
)
bad_offer_status = sum(
    1 for r in offers
    if r.get("status", "").strip() not in allowed_offer_statuses
)

mismatched_offer_buyers = 0
mismatched_offer_suppliers = 0
bad_offer_dates = 0
bad_offer_date_sequences = 0
bad_offer_amounts = 0
bad_offer_arithmetic = 0
offer_scale_mismatches = 0
bad_offer_payloads = 0

for row in offers:
    inv_id = row.get("invoice_id", "").strip()
    inv = invoices_by_id.get(inv_id)

    # Cross-entity matching with referenced invoice
    if inv:
        if row.get("buyer_id", "").strip() != inv.get("buyer_id", "").strip():
            mismatched_offer_buyers += 1
        if row.get("supplier_id", "").strip() != inv.get("supplier_id", "").strip():
            mismatched_offer_suppliers += 1

    # Date format and sequence
    off_date = row.get("offer_date", "").strip()
    dl_date = row.get("deadline_date", "").strip()
    due_date = row.get("due_date", "").strip()
    dec_date = row.get("decision_date", "").strip()

    date_valid = (
        valid_date(off_date, required=True)
        and valid_date(dl_date, required=True)
        and valid_date(due_date, required=False)
        and valid_date(dec_date, required=False)
    )
    if not date_valid:
        bad_offer_dates += 1
    else:
        if off_date > dl_date:
            bad_offer_date_sequences += 1
        elif inv and valid_date(inv.get("due_date"), required=True):
            if dl_date > inv["due_date"].strip():
                bad_offer_date_sequences += 1

    # Amount validations (single increment per row on invalid amounts)
    try:
        invoice_amount = Decimal(row["invoice_amount"])
        discount_amount = Decimal(row["discount_amount"])
        net_amount = Decimal(row["net_payable_if_accepted"])
        rate = Decimal(row["offered_rate_pct"])

        row_bad_amount = False
        if min(invoice_amount, discount_amount, net_amount, rate) < 0:
            row_bad_amount = True
        if invoice_amount <= 0 or net_amount > invoice_amount:
            row_bad_amount = True

        if row_bad_amount:
            bad_offer_amounts += 1

        # Arithmetic consistency: invoice_amount == discount_amount + net_amount (within 0.02)
        if abs(invoice_amount - (discount_amount + net_amount)) > Decimal("0.02"):
            bad_offer_arithmetic += 1

        # Currency scale match against invoice display amount
        if inv and invoice_amount * Decimal("1000") != Decimal(inv["invoice_amount_display"]):
            offer_scale_mismatches += 1
    except Exception:
        if inv_id in invoice_ids:
            bad_offer_amounts += 1

    # Validate recommendation_payload JSON
    payload_raw = row.get("recommendation_payload", "").strip()
    if payload_raw:
        try:
            payload_obj = json.loads(payload_raw)
            if not isinstance(payload_obj, dict):
                bad_offer_payloads += 1
        except Exception:
            bad_offer_payloads += 1

if missing_offer_invoices:
    errors.append(f"Offers referencing missing invoices: {missing_offer_invoices}")
if missing_offer_buyers:
    errors.append(f"Offers referencing missing buyers: {missing_offer_buyers}")
if mismatched_offer_buyers:
    errors.append(f"Offers with buyer_id not matching invoice buyer: {mismatched_offer_buyers}")
if mismatched_offer_suppliers:
    errors.append(f"Offers with supplier_id not matching invoice supplier: {mismatched_offer_suppliers}")
if bad_offer_status:
    errors.append(f"Invalid offer statuses: {bad_offer_status}")
if bad_offer_dates:
    errors.append(f"Offers with invalid dates: {bad_offer_dates}")
if bad_offer_date_sequences:
    errors.append(f"Offers with invalid date sequences: {bad_offer_date_sequences}")
if bad_offer_amounts:
    errors.append(f"Offers with invalid amounts: {bad_offer_amounts}")
if bad_offer_arithmetic:
    errors.append(f"Offers with arithmetic mismatch (invoice != discount + net): {bad_offer_arithmetic}")
if offer_scale_mismatches:
    errors.append(f"Offer-to-invoice amount scale mismatches: {offer_scale_mismatches}")
if bad_offer_payloads:
    errors.append(f"Offers with invalid recommendation_payload JSON: {bad_offer_payloads}")

# Historical offer safety flags and governance
ml_disabled_count = sum(
    1 for r in offers if r.get("ml_use_allowed", "").strip() in {"0", "false", "False"}
)
ml_enabled_violations = len(offers) - ml_disabled_count

invalid_data_origin = sum(
    1 for r in offers
    if r.get("data_origin", "").strip() != "SIMULATED_DEMONSTRATION_OFFER_HISTORY"
)
noncompliant_offers = sum(
    1 for r in offers if r.get("policy_compliant", "").strip() not in {"1", "true", "True"}
)

print(f"\nOffers with ML disabled (compliant): {ml_disabled_count}")
print(f"Offers with ML enabled (non-compliant): {ml_enabled_violations}")
print(f"Offers with expected simulated data_origin tag: {len(offers) - invalid_data_origin}")
print(f"Offers marked policy-noncompliant: {noncompliant_offers}")

if ml_enabled_violations:
    warnings.append(f"{ml_enabled_violations} offers do not have an explicit ML-disabled flag")
if invalid_data_origin:
    warnings.append(f"{invalid_data_origin} offers do not have the required simulated data_origin tag")

print("\n=== RESULTS ===")
print(f"Errors: {len(errors)}")
for item in errors:
    print("ERROR:", item)

print(f"Warnings: {len(warnings)}")
for item in warnings:
    print("WARNING:", item)

print("\nDRY RUN ONLY — no database changes were made.")
sys.exit(1 if errors else 0)
