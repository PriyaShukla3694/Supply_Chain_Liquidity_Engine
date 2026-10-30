"""
Script to compute and persist buyer risk scores using app/services/buyer_scoring.py.

Usage:
    python scripts/compute_buyer_scores.py [--as-of YYYY-MM-DD] [--dry-run]
"""

import argparse
from datetime import date
from decimal import Decimal
import logging
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.buyer import Buyer
from app.models.risk_score import RiskScore
from app.services.buyer_scoring import (
    get_business_as_of_date,
    preview_buyer_score,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def compute_all_buyer_scores(
    db: Session,
    as_of_date: Optional[date] = None,
    dry_run: bool = False,
) -> dict:
    """
    Compute and persist buyer risk scores for all buyers in a single transaction.

    - Resolves business as-of date (provided or via get_business_as_of_date).
    - Iterates over all buyers.
    - Handles credit_limit NULL or <= 0: tier stays NULL, tier_basis='scoring_blocked'.
    - Updates buyer.tier and buyer.tier_basis.
    - Upserts ONE risk_scores row per (buyer_id, model_version='rules_v1') for scored buyers.
    - If dry_run is True, rolls back changes.
    """
    resolved_as_of = as_of_date or get_business_as_of_date(db)

    buyers = db.query(Buyer).order_by(Buyer.buyer_id).all()

    total_buyers = len(buyers)
    scored_count = 0
    tier_a_count = 0
    tier_b_count = 0
    tier_c_count = 0
    cold_start_count = 0
    blocked_count = 0

    reliability_scores: list[float] = []
    financial_scores: list[float] = []
    liquidity_scores: list[float] = []

    for buyer in buyers:
        score_res = preview_buyer_score(
            db=db,
            buyer_id=buyer.buyer_id,
            as_of_date=resolved_as_of,
        )

        tier = score_res.get("tier")
        tier_basis = score_res.get("tier_basis")

        # Update buyer fields
        buyer.tier = tier
        buyer.tier_basis = tier_basis

        # Track tier counts
        if tier == "A":
            tier_a_count += 1
        elif tier == "B":
            tier_b_count += 1
        elif tier == "C":
            tier_c_count += 1

        if tier_basis == "cold_start":
            cold_start_count += 1
        elif tier_basis == "scoring_blocked":
            blocked_count += 1

        # Upsert risk_scores row for scored buyers (status == "calculated")
        if score_res.get("status") == "calculated":
            scored_count += 1
            rel = score_res["reliability_score"]
            fin = score_res["financial_score"]
            liq = score_res["liquidity_score"]
            ovr = score_res["overall_score"]

            reliability_scores.append(rel)
            financial_scores.append(fin)
            liquidity_scores.append(liq)

            # Query existing risk_score for this buyer with model_version='rules_v1'
            risk_record = (
                db.query(RiskScore)
                .filter(
                    RiskScore.buyer_id == buyer.buyer_id,
                    RiskScore.model_version == "rules_v1",
                )
                .first()
            )

            if risk_record is not None:
                risk_record.payment_reliability = Decimal(str(rel))
                risk_record.financial_risk = Decimal(str(fin))
                risk_record.liquidity_risk = Decimal(str(liq))
                risk_record.overall_risk = Decimal(str(ovr))
                risk_record.tier = tier
                risk_record.tier_basis = tier_basis
                risk_record.computed_at = func.now()
            else:
                risk_record = RiskScore(
                    buyer_id=buyer.buyer_id,
                    payment_reliability=Decimal(str(rel)),
                    financial_risk=Decimal(str(fin)),
                    liquidity_risk=Decimal(str(liq)),
                    overall_risk=Decimal(str(ovr)),
                    tier=tier,
                    tier_basis=tier_basis,
                    model_version="rules_v1",
                )
                db.add(risk_record)

    mean_reliability = (
        sum(reliability_scores) / len(reliability_scores)
        if reliability_scores
        else 0.0
    )
    mean_financial = (
        sum(financial_scores) / len(financial_scores)
        if financial_scores
        else 0.0
    )
    mean_liquidity = (
        sum(liquidity_scores) / len(liquidity_scores)
        if liquidity_scores
        else 0.0
    )

    summary = {
        "as_of_date": resolved_as_of.isoformat(),
        "total_buyers": total_buyers,
        "buyers_scored": scored_count,
        "tier_a": tier_a_count,
        "tier_b": tier_b_count,
        "tier_c": tier_c_count,
        "cold_start": cold_start_count,
        "blocked": blocked_count,
        "mean_reliability": round(mean_reliability, 2),
        "mean_financial": round(mean_financial, 2),
        "mean_liquidity": round(mean_liquidity, 2),
        "dry_run": dry_run,
    }

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return summary


def print_summary(summary: dict) -> None:
    mode_str = " (DRY RUN - Not Persisted)" if summary.get("dry_run") else ""
    print("=" * 60)
    print(f"Buyer Scoring Summary{mode_str}")
    print("=" * 60)
    print(f"As-of Date:       {summary['as_of_date']}")
    print(f"Total Buyers:     {summary['total_buyers']}")
    print(f"Buyers Scored:    {summary['buyers_scored']}")
    print(f"Tier A:           {summary['tier_a']}")
    print(f"Tier B:           {summary['tier_b']}")
    print(f"Tier C:           {summary['tier_c']}")
    print(f"Cold-start:       {summary['cold_start']}")
    print(f"Blocked:          {summary['blocked']}")
    print(f"Mean Reliability: {summary['mean_reliability']:.2f}")
    print(f"Mean Financial:   {summary['mean_financial']:.2f}")
    print(f"Mean Liquidity:   {summary['mean_liquidity']:.2f}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Compute and persist buyer risk scores."
    )
    parser.add_argument(
        "--as-of",
        dest="as_of",
        type=str,
        default=None,
        help="As-of date in YYYY-MM-DD format (optional, defaults to business as-of date).",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Simulate execution without committing changes to database.",
    )

    args = parser.parse_args()

    as_of_date = None
    if args.as_of:
        try:
            as_of_date = date.fromisoformat(args.as_of)
        except ValueError as exc:
            logger.error(f"Invalid date format for --as-of: {args.as_of}. Expected YYYY-MM-DD.")
            sys.exit(1)

    db = SessionLocal()
    try:
        summary = compute_all_buyer_scores(
            db=db,
            as_of_date=as_of_date,
            dry_run=args.dry_run,
        )
        print_summary(summary)
    except Exception as exc:
        db.rollback()
        logger.exception("Transaction rolled back due to error during buyer score calculation:")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

