"""Feature definitions and dataset loader for payment delay risk prediction.

Strictly enforces business rules and prevents target leakage.
"""

from pathlib import Path
from typing import Iterable, List, NamedTuple, Union
import pandas as pd

# 1. Allowed feature list (model inputs)
FEATURES: List[str] = [
    "country_code",
    "invoice_amount",
    "invoice_month",
    "invoice_dow",
    "buyer_prior_invoice_count",
    "buyer_hist_late_rate",
    "buyer_hist_avg_delay_days",
    "buyer_hist_delay_std",
    "buyer_hist_max_delay",
    "buyer_last_invoice_delay",
    "buyer_days_since_last_invoice",
    "buyer_hist_avg_amount",
    "amount_vs_buyer_avg_ratio",
    "outstanding_amount_at_invoice",
    "outstanding_count_at_invoice",
    "has_history",
]

# 2. Forbidden list: labels, future leakages, and non-feature metadata
FORBIDDEN: List[str] = [
    "payment_date",
    "settled_date",
    "days_to_settle",
    "days_late",
    "delay_bucket",
    "invoice_status",
    "disputed",
    "buyer_hist_dispute_rate",
    "is_late",
    "split",
    "discount_eligible_flag",
]

# Monetary columns in raw CSV are in ₹000 and must be converted to ₹ (x1000)
MONETARY_COLUMNS: List[str] = [
    "invoice_amount",
    "buyer_hist_avg_amount",
    "outstanding_amount_at_invoice",
]


class DataLeakageError(ValueError):
    """Raised when target or post-issuance leakage features are detected in feature list."""
    pass


def assert_no_leakage(feature_names: Iterable[str]) -> None:
    """Raises ValueError/DataLeakageError if any forbidden feature is present."""
    forbidden_set = set(FORBIDDEN)
    leaked = [f for f in feature_names if f in forbidden_set]
    if leaked:
        raise DataLeakageError(
            f"Data leakage detected! Forbidden features found in feature set: {sorted(leaked)}"
        )


class TrainingSplits(NamedTuple):
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def load_training_frame(
    csv_path: Union[str, Path] = "seed_data/invoices_merged_clean.csv",
) -> TrainingSplits:
    """Reads CSV, filters to settled invoices, converts ₹000 amount columns to ₹

    exactly once, maps paperless_bill (Electronic=1, Paper=0), and returns
    train/validation/test splits using the existing 'split' column.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Invoice dataset not found at {path}")

    df = pd.read_csv(path)

    # Filter to only settled invoices (business_rules.md: uncompleted invoices excluded from training)
    df = df[df["invoice_status"] == "settled"].copy()

    # Convert ₹000 amount columns to ₹ exactly once
    for col in MONETARY_COLUMNS:
        if col in df.columns:
            df[col] = df[col] * 1000.0

    # Ensure paperless_bill is binary integer (Electronic=1, Paper=0)
    if "paperless_bill" in df.columns:
        df["paperless_bill"] = (
            df["paperless_bill"].astype(str).str.strip().str.lower() == "electronic"
        ).astype(int)

    # Split using existing 'split' column
    train_df = df[df["split"] == "train"].copy().reset_index(drop=True)
    val_df = df[df["split"] == "validation"].copy().reset_index(drop=True)
    test_df = df[df["split"] == "test"].copy().reset_index(drop=True)

    return TrainingSplits(train=train_df, validation=val_df, test=test_df)
