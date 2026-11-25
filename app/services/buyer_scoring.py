
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.clock import business_today
from app.models.invoice import Invoice
from app.models.buyer import Buyer
from app.models.risk_score import RiskScore


def _clamp_score(score: float) -> float:
    """Keep a score within the 0–100 range."""
    return round(max(0.0, min(100.0, score)), 2)


def calculate_reliability_score(
    late_rate: float,
    avg_days_late: float,
    late_rate_last_5_settled: float,
) -> float:
    """
    Reliability =
        50*(1-late_rate)
        + 25*(1-min(avg_days_late/15, 1))
        + 25*(1-late_rate_last_5_settled)

    Rates are decimals: 0.20 means 20%.
    """
    if not 0 <= late_rate <= 1:
        raise ValueError("late_rate must be between 0 and 1")

    if not 0 <= late_rate_last_5_settled <= 1:
        raise ValueError(
            "late_rate_last_5_settled must be between 0 and 1"
        )

    if avg_days_late < 0:
        raise ValueError("avg_days_late cannot be negative")

    score = (
        50 * (1 - late_rate)
        + 25 * (1 - min(avg_days_late / 15, 1))
        + 25 * (1 - late_rate_last_5_settled)
    )

    return _clamp_score(score)


def calculate_financial_score(
    open_exposure: float,
    credit_limit: float,
) -> float:
    """
    Financial health =
        100*(1-min(open_exposure/credit_limit, 1)).

    Zero-credit-limit behavior is not finalized.
    """
    if open_exposure < 0 or credit_limit < 0:
        raise ValueError("Exposure and credit limit cannot be negative")

    if credit_limit == 0:
        raise ValueError(
            "Zero credit limit requires a business-rule decision"
        )

    score = 100 * (1 - min(open_exposure / credit_limit, 1))

    return _clamp_score(score)


def calculate_liquidity_score(
    overdue_open_exposure: float,
    open_exposure: float,
) -> float:
    """
    Liquidity health =
        100*(1-overdue_open_exposure/open_exposure).

    If open exposure is zero, liquidity health is 100.
    """
    if overdue_open_exposure < 0 or open_exposure < 0:
        raise ValueError("Exposure values cannot be negative")

    if overdue_open_exposure > open_exposure:
        raise ValueError(
            "Overdue exposure cannot exceed open exposure"
        )

    if open_exposure == 0:
        return 100.0

    score = 100 * (
        1 - overdue_open_exposure / open_exposure
    )

    return _clamp_score(score)


def calculate_overall_score(
    reliability: float,
    financial: float,
    liquidity: float,
) -> float:
    """Overall score = 80% reliability + 10% financial + 10% liquidity."""
    for name, score in (
        ("reliability", reliability),
        ("financial", financial),
        ("liquidity", liquidity),
    ):
        if not 0 <= score <= 100:
            raise ValueError(
                f"{name} score must be between 0 and 100"
            )

    overall = (
        0.80 * reliability
        + 0.10 * financial
        + 0.10 * liquidity
    )

    return _clamp_score(overall)


def assign_tier(overall_score: float) -> str:
    """Tier A: >=80, Tier B: >=50 and <80, Tier C: <50."""
    if not 0 <= overall_score <= 100:
        raise ValueError("Overall score must be between 0 and 100")

    if overall_score >= 80:
        return "A"

    if overall_score >= 50:
        return "B"

    return "C"


def calculate_buyer_payment_metrics(
    db: Session,
    buyer_id: str,
) -> dict:
    """Calculate payment metrics from settled invoices only."""

    settled_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == buyer_id,
            Invoice.invoice_status == "settled",
            Invoice.settled_date.isnot(None),
        )
        .order_by(
            Invoice.settled_date.desc(),
            Invoice.invoice_id.desc(),
        )
        .all()
    )

    total_settled = len(settled_invoices)

    if total_settled == 0:
        return {
            "resolved_invoice_count": 0,
            "late_rate": 0.0,
            "avg_days_late": 0.0,
            "late_rate_last_5_settled": 0.0,
        }

    late_flags = [
        bool(invoice.is_late)
        if invoice.is_late is not None
        else (invoice.days_late or 0) > 0
        for invoice in settled_invoices
    ]

    days_late_values = [
        max(invoice.days_late or 0, 0)
        for invoice in settled_invoices
    ]

    last_five_flags = late_flags[:5]

    return {
        "resolved_invoice_count": total_settled,
        "late_rate": sum(late_flags) / total_settled,
        "avg_days_late": (
            sum(days_late_values) / total_settled
        ),
        "late_rate_last_5_settled": (
            sum(last_five_flags) / len(last_five_flags)
        ),
    }


def get_business_as_of_date(db: Session) -> date:
    """Return the business as-of date for scoring and optimization.

    Uses settings.BUSINESS_AS_OF_DATE if configured (env var BUSINESS_AS_OF_DATE).
    Otherwise uses the latest invoice_date in the invoices table.
    Never defaults to today's date for scoring.
    """
    if getattr(settings, "BUSINESS_AS_OF_DATE", None) is not None:
        return settings.BUSINESS_AS_OF_DATE

    latest_invoice_date = db.query(func.max(Invoice.invoice_date)).scalar()
    if latest_invoice_date is not None:
        return latest_invoice_date

    if getattr(settings, "REFERENCE_DATE", None) is not None:
        return settings.REFERENCE_DATE

    raise ValueError(
        "Cannot determine business as-of date: no invoices found and BUSINESS_AS_OF_DATE is unset."
    )


def preview_buyer_score(
    db: Session,
    buyer_id: str,
    as_of_date: date | None = None,
) -> dict:
    """
    Read-only buyer scoring preview.

    Does not update Buyer or RiskScore records.
    """
    buyer = (
        db.query(Buyer)
        .filter(Buyer.buyer_id == buyer_id)
        .first()
    )

    if buyer is None:
        raise ValueError(f"Buyer not found: {buyer_id}")

    # Use specified as_of_date or resolve via business as-of date helper.
    as_of_date = as_of_date or get_business_as_of_date(db)

    metrics = calculate_buyer_payment_metrics(db, buyer_id)

    open_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == buyer_id,
            Invoice.invoice_status == "open",
        )
        .all()
    )

    open_exposure = sum(
        (
            Decimal(str(invoice.invoice_amount))
            for invoice in open_invoices
        ),
        Decimal("0"),
    )

    overdue_open_exposure = sum(
        (
            Decimal(str(invoice.invoice_amount))
            for invoice in open_invoices
            if invoice.due_date < as_of_date
        ),
        Decimal("0"),
    )

    credit_limit = (
        Decimal(str(buyer.credit_limit))
        if buyer.credit_limit is not None
        else Decimal("0")
    )

    result = {
        "buyer_id": buyer_id,
        **metrics,
        "open_exposure": float(open_exposure),
        "overdue_open_exposure": float(overdue_open_exposure),
        "credit_limit": float(credit_limit),
        "as_of_date": as_of_date.isoformat(),
    }

    # Handle credit_limit NULL or 0 without crashing: tier stays NULL, tier_basis='scoring_blocked'
    if credit_limit <= 0:
        result.update({
            "reliability_score": None,
            "financial_score": None,
            "liquidity_score": None,
            "overall_score": None,
            "tier": None,
            "tier_basis": "scoring_blocked",
            "status": "credit_limit_decision_required",
        })
        return result

    # Cold-start: fewer than 5 resolved invoices.
    if metrics["resolved_invoice_count"] < 5:
        result.update({
            "reliability_score": None,
            "financial_score": None,
            "liquidity_score": None,
            "overall_score": None,
            "tier": "B",
            "tier_basis": "cold_start",
            "status": "provisional",
        })
        return result

    reliability = calculate_reliability_score(
        late_rate=metrics["late_rate"],
        avg_days_late=metrics["avg_days_late"],
        late_rate_last_5_settled=metrics["late_rate_last_5_settled"],
    )

    financial = calculate_financial_score(
        open_exposure=float(open_exposure),
        credit_limit=float(credit_limit),
    )

    liquidity = calculate_liquidity_score(
        overdue_open_exposure=float(overdue_open_exposure),
        open_exposure=float(open_exposure),
    )

    overall = calculate_overall_score(
        reliability=reliability,
        financial=financial,
        liquidity=liquidity,
    )

    result.update({
        "reliability_score": reliability,
        "financial_score": financial,
        "liquidity_score": liquidity,
        "overall_score": overall,
        "tier": assign_tier(overall),
        "tier_basis": "scored",
        "status": "calculated",
    })

    return result


def calculate_and_persist_buyer_score(
    db: Session,
    buyer_id: str,
    as_of_date: date | None = None,
    model_version: str = "v1.0",
    commit: bool = True,
) -> dict:
    """
    Calculate buyer score and persist the tier and tier_basis to the Buyer record,
    and append a record to the RiskScore ledger when scoring is computed.

    Preserves preview_buyer_score calculation formulas.
    """
    score_result = preview_buyer_score(
        db=db,
        buyer_id=buyer_id,
        as_of_date=as_of_date,
    )

    buyer = (
        db.query(Buyer)
        .filter(Buyer.buyer_id == buyer_id)
        .first()
    )
    if buyer is None:
        raise ValueError(f"Buyer not found: {buyer_id}")

    buyer.tier = score_result.get("tier")
    buyer.tier_basis = score_result.get("tier_basis")

    # Only insert into risk_scores if we have complete numeric scores,
    # because these columns are NOT NULL with range constraints 0-100.
    risk_score_record = None
    if score_result.get("status") == "calculated":
        risk_score_record = RiskScore(
            buyer_id=buyer_id,
            payment_reliability=Decimal(
                str(score_result["reliability_score"])
            ),
            financial_risk=Decimal(
                str(score_result["financial_score"])
            ),
            liquidity_risk=Decimal(
                str(score_result["liquidity_score"])
            ),
            overall_risk=Decimal(
                str(score_result["overall_score"])
            ),
            tier=score_result.get("tier"),
            tier_basis=score_result.get("tier_basis"),
            model_version=model_version,
        )
        db.add(risk_score_record)

    if commit:
        db.commit()
        db.refresh(buyer)
        if risk_score_record:
            db.refresh(risk_score_record)

    return score_result
