from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional


SOURCE_SCALE_FACTOR = Decimal("1000")


def to_decimal(value: Any) -> Decimal:
    """Converts a numeric or string value to Decimal safely."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    val_str = str(value).strip()
    if val_str == "":
        return Decimal("0.00")
    return Decimal(val_str)


def source_to_inr(value: Any) -> Decimal:
    """Explicitly converts a verified source-scale monetary amount (₹000) to INR (₹).

    Multiplies by 1,000 and rounds to 2 decimal places.
    """
    dec_val = to_decimal(value)
    inr_val = dec_val * SOURCE_SCALE_FACTOR
    return inr_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def inr_to_source(value: Any) -> Decimal:
    """Explicitly converts an INR monetary amount (₹) to source-scale (₹000).

    Divides by 1,000 and rounds to 2 decimal places for ML feature alignment.
    """
    dec_val = to_decimal(value)
    source_val = dec_val / SOURCE_SCALE_FACTOR
    return source_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def convert_source_invoice_amount(
    raw_amount: Any,
    display_amount: Any = None,
) -> Decimal:
    """Explicit conversion boundary for invoice amounts from datasets or source records.

    - If display_amount is provided and non-empty (e.g. from invoice_amount_display),
      it is already expressed in INR and used directly, preventing double conversion.
    - If only raw_amount (invoice_amount in ₹000) is provided, it is explicitly
      converted from source scale to INR via source_to_inr (x1000).
    """
    if display_amount is not None and str(display_amount).strip() != "":
        return to_decimal(display_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return source_to_inr(raw_amount)


def convert_source_offer_amounts(
    invoice_amount: Any,
    discount_amount: Any,
    net_payable: Any,
    rate_pct: Any,
) -> Dict[str, Decimal]:
    """Utility function to convert historical demonstration offer records to INR.

    - invoice_amount, discount_amount, and net_payable_if_accepted are verified
      as source-scale monetary fields (₹000) and converted by multiplying by 1,000 once.
    - offered_rate_pct is a percentage rate and is preserved as-is (NOT multiplied by 1,000).

    NOTE: This is strictly a conversion/validation utility and does not alter
    or import database records or historical files.
    """
    inv_inr = source_to_inr(invoice_amount)
    disc_inr = source_to_inr(discount_amount)
    net_inr = source_to_inr(net_payable)
    rate = to_decimal(rate_pct)

    return {
        "invoice_amount": inv_inr,
        "discount_amount": disc_inr,
        "net_payable_if_accepted": net_inr,
        "offered_rate_pct": rate,
    }


def format_inr(value: Any) -> str:
    """Formats an INR monetary amount with rupee symbol and standard comma grouping.

    Example: Decimal("50390.00") -> "₹50,390.00"
    """
    dec = to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if dec < 0:
        return f"-₹{abs(dec):,.2f}"
    return f"₹{dec:,.2f}"
