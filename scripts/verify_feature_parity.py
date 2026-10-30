"""
Verify parity between database-computed features and seed_data/invoices_merged_clean.csv.

Compares features for 300 randomly sampled settled invoices using a fixed seed (42).
Tolerances:
- Rates and non-monetary metrics: 1e-6
- Monetary amounts: 0.01 rupee
"""

from datetime import date
from pathlib import Path
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.session import SessionLocal
from app.models.invoice import Invoice
from app.ml.features import FEATURES, MONETARY_COLUMNS
from app.services.prediction import build_features_from_invoice


def verify_feature_parity(sample_size: int = 300, seed: int = 42) -> bool:
    csv_path = REPO_ROOT / "seed_data" / "invoices_merged_clean.csv"
    if not csv_path.exists():
        print(f"ERROR: Dataset not found at {csv_path}")
        return False

    # Load CSV and convert amounts to rupees (x1000)
    df_csv = pd.read_csv(csv_path)
    for col in MONETARY_COLUMNS:
        if col in df_csv.columns:
            df_csv[col] = df_csv[col] * 1000.0

    csv_by_id = df_csv.set_index("invoice_id")

    db = SessionLocal()
    try:
        settled_ids = [
            row[0]
            for row in db.query(Invoice.invoice_id)
            .filter(Invoice.invoice_status == "settled")
            .all()
        ]

        if len(settled_ids) < sample_size:
            print(f"ERROR: Insufficient settled invoices in DB ({len(settled_ids)} < {sample_size})")
            return False

        rng = np.random.RandomState(seed)
        sampled_ids = rng.choice(settled_ids, size=sample_size, replace=False)

        max_diffs: Dict[str, float] = {f: 0.0 for f in FEATURES}
        tolerances: Dict[str, float] = {}

        for f in FEATURES:
            if f in MONETARY_COLUMNS:
                tolerances[f] = 0.01  # 0.01 rupee tolerance
            else:
                tolerances[f] = 1e-6  # 1e-6 rate/metric tolerance

        print("=" * 75)
        print(f"VERIFYING FEATURE PARITY ON {sample_size} INVOICES (Seed: {seed})")
        print("=" * 75)

        for raw_id in sampled_ids:
            inv_id = int(raw_id)
            db_features = build_features_from_invoice(invoice_id=inv_id, db=db)
            csv_row = csv_by_id.loc[inv_id]

            for feat in FEATURES:
                act = csv_row[feat]
                val = db_features[feat]

                if pd.isna(act) and (val is None or pd.isna(val)):
                    diff = 0.0
                elif pd.isna(act) or (val is None or pd.isna(val)):
                    diff = 999999.0
                else:
                    diff = abs(float(val) - float(act))

                if diff > max_diffs[feat]:
                    max_diffs[feat] = diff

        all_passed = True
        print(f"{'Feature Name':<32} {'Max Absolute Diff':<20} {'Tolerance':<12} {'Status'}")
        print("-" * 75)

        for feat in FEATURES:
            max_diff = max_diffs[feat]
            tol = tolerances[feat]
            passed = max_diff <= tol
            status_str = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False

            print(f"{feat:<32} {max_diff:<20.8f} {tol:<12.6f} {status_str}")

        print("=" * 75)
        overall_status = "ALL FEATURES PASSED PARITY CHECK" if all_passed else "PARITY CHECK FAILED"
        print(f"RESULT: {overall_status}")
        print("=" * 75)
        return all_passed
    finally:
        db.close()


if __name__ == "__main__":
    success = verify_feature_parity()
    sys.exit(0 if success else 1)

