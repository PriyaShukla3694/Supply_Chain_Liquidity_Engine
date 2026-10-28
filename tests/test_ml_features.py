"""Tests for ML feature definitions, leakage prevention, and training splits."""

from pathlib import Path
import pandas as pd
import pytest

from app.ml.features import (
    FEATURES,
    FORBIDDEN,
    MONETARY_COLUMNS,
    DataLeakageError,
    assert_no_leakage,
    load_training_frame,
)

CSV_PATH = Path("seed_data/invoices_merged_clean.csv")


@pytest.mark.unit
def test_features_and_forbidden_disjoint():
    """Verify standard FEATURES contains no forbidden columns."""
    assert_no_leakage(FEATURES)
    for forbidden in FORBIDDEN:
        assert forbidden not in FEATURES


@pytest.mark.unit
def test_leakage_guard_raises_on_forbidden():
    """Verify assert_no_leakage raises ValueError/DataLeakageError when any forbidden column is added."""
    for col in FORBIDDEN:
        tampered_features = FEATURES + [col]
        with pytest.raises((ValueError, DataLeakageError)):
            assert_no_leakage(tampered_features)

    # Test with multiple forbidden columns
    with pytest.raises((ValueError, DataLeakageError)):
        assert_no_leakage(["invoice_amount", "is_late", "disputed"])


@pytest.mark.unit
def test_split_sizes():
    """Verify split sizes are exactly 3465 / 649 / 457."""
    train_df, val_df, test_df = load_training_frame(CSV_PATH)
    assert len(train_df) == 3465, f"Expected 3465 train rows, got {len(train_df)}"
    assert len(val_df) == 649, f"Expected 649 validation rows, got {len(val_df)}"
    assert len(test_df) == 457, f"Expected 457 test rows, got {len(test_df)}"


@pytest.mark.unit
def test_time_aware_splits_no_date_inversion():
    """Verify time-aware split ordering: no row in an earlier split has a later

    invoice_date than every row in a later split.
    """
    train_df, val_df, test_df = load_training_frame(CSV_PATH)

    train_dates = pd.to_datetime(train_df["invoice_date"])
    val_dates = pd.to_datetime(val_df["invoice_date"])
    test_dates = pd.to_datetime(test_df["invoice_date"])

    max_train_date = train_dates.max()
    min_val_date = val_dates.min()
    max_val_date = val_dates.max()
    min_test_date = test_dates.min()

    # Max train date must be <= min validation date
    assert max_train_date <= min_val_date, (
        f"Train max date ({max_train_date}) > validation min date ({min_val_date})"
    )

    # Max validation date must be <= min test date
    assert max_val_date <= min_test_date, (
        f"Validation max date ({max_val_date}) > test min date ({min_test_date})"
    )

    # Verify no row in train is later than min val date
    assert not (train_dates > min_val_date).any()

    # Verify no row in val is later than min test date
    assert not (val_dates > min_test_date).any()


@pytest.mark.unit
def test_unit_conversion_happens_once():
    """Verify monetary conversion from ₹000 to ₹ happens exactly once (invoice_amount median is ~1000x the raw CSV median)."""
    raw_df = pd.read_csv(CSV_PATH)
    raw_csv_median = raw_df["invoice_amount"].median()

    train_df, val_df, test_df = load_training_frame(CSV_PATH)
    combined = pd.concat([train_df, val_df, test_df], ignore_index=True)

    converted_invoice_median = combined["invoice_amount"].median()

    # invoice_amount median is ~1000x the raw CSV median
    assert pytest.approx(converted_invoice_median, rel=0.01) == raw_csv_median * 1000.0

    # Exactly 1000x for the corresponding subset
    raw_splits_median = raw_df[raw_df["split"].isin(["train", "validation", "test"])]["invoice_amount"].median()
    assert converted_invoice_median == pytest.approx(raw_splits_median * 1000.0)

    # Verify other converted columns are also scaled by 1000
    for col in MONETARY_COLUMNS:
        raw_col_med = raw_df[raw_df["split"].isin(["train", "validation", "test"])][col].median()
        conv_col_med = combined[col].median()
        assert conv_col_med == pytest.approx(raw_col_med * 1000.0)


@pytest.mark.unit
def test_features_present_and_paperless_bill_binary():
    """Verify all defined FEATURES exist in loaded splits and paperless_bill is binary (Electronic=1)."""
    train_df, val_df, test_df = load_training_frame(CSV_PATH)

    for split_df in (train_df, val_df, test_df):
        for feature in FEATURES:
            assert feature in split_df.columns, f"Feature '{feature}' missing from split"

        # Check paperless_bill values are 0 or 1
        assert set(split_df["paperless_bill"].unique()).issubset({0, 1})
