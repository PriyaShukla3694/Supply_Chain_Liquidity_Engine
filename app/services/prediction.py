
from datetime import datetime, timezone
from functools import lru_cache
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ml.features import FEATURES
from app.models.buyer import Buyer
from app.models.invoice import Invoice
from app.models.model_prediction import ModelPrediction
from app.schemas.prediction import (
    LatePaymentPredictionRequest,
    LatePaymentPredictionResponse,
    LatePaymentPredictionResponseExtended,
)

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Model configuration
# -------------------------------------------------------------------

MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "payment_risk_v1.joblib"
)

MODEL_NAME = "payment_risk_xgb"
MODEL_VERSION = "payment_risk_v1"

DEFAULT_THRESHOLD = 0.25
LOW_RISK_THRESHOLD = 0.25
HIGH_RISK_THRESHOLD = 0.55


# -------------------------------------------------------------------
# Risk classification
# -------------------------------------------------------------------

def get_risk_label(probability: float) -> str:
    if probability < LOW_RISK_THRESHOLD:
        return "LOW"

    if probability < HIGH_RISK_THRESHOLD:
        return "MEDIUM"

    return "HIGH"


# -------------------------------------------------------------------
# Model loading
# -------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_payment_model() -> dict:
    """
    Load the calibrated payment_risk_v1 artifact.

    The artifact contains:
      - model
      - calibrator
      - threshold
      - threshold_recall80
      - features
      - version
    """

    if not MODEL_PATH.exists():
        logger.error("Payment model artifact not found: %s", MODEL_PATH)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Model not available",
                "code": "MODEL_UNAVAILABLE",
            },
        )

    try:
        artifact = joblib.load(MODEL_PATH)

        if not isinstance(artifact, dict):
            raise ValueError("Unexpected model artifact format")

        required_keys = {
            "model",
            "calibrator",
            "threshold",
            "features",
            "version",
        }

        missing = required_keys - set(artifact.keys())

        if missing:
            raise ValueError(
                f"Model artifact is missing keys: {sorted(missing)}"
            )

        if artifact["version"] != MODEL_VERSION:
            raise ValueError(
                f"Unexpected model version: {artifact['version']}"
            )

        if list(artifact["features"]) != list(FEATURES):
            raise ValueError(
                "Artifact feature order does not match app.ml.features.FEATURES"
            )

        model = artifact["model"]
        calibrator = artifact["calibrator"]

        if not hasattr(model, "predict_proba"):
            raise ValueError("Model does not support predict_proba")

        if not hasattr(calibrator, "predict_proba"):
            raise ValueError("Calibrator does not support predict_proba")

        threshold = float(artifact["threshold"])

        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Invalid model threshold")

        logger.info(
            "Loaded payment model: version=%s threshold=%.4f",
            artifact["version"],
            threshold,
        )

        return artifact

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Failed to load payment model")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Model not available",
                "code": "MODEL_UNAVAILABLE",
            },
        ) from exc


# -------------------------------------------------------------------
# Feature conversion helpers
# -------------------------------------------------------------------

def _to_numeric(value: Any) -> Optional[float]:
    """Convert a value to float; return None for invalid or missing data."""

    if value is None:
        return None

    try:
        result = float(value)

        if not np.isfinite(result):
            return None

        return result

    except (TypeError, ValueError):
        return None


def _build_model_dataframe(features: dict) -> pd.DataFrame:
    """
    Build the numeric model input using the exact 16-feature order.

    Missing values are represented as NaN. The XGBoost model supports
    missing numeric values.
    """

    missing_features = [
        feature for feature in FEATURES
        if feature not in features
    ]

    if missing_features:
        raise ValueError(
            f"Missing required model features: {missing_features}"
        )

    row = {}

    for feature in FEATURES:
        value = _to_numeric(features[feature])
        row[feature] = np.nan if value is None else value

    return pd.DataFrame(
        [[row[feature] for feature in FEATURES]],
        columns=FEATURES,
        dtype=float,
    )


# -------------------------------------------------------------------
# Prediction explanations
# -------------------------------------------------------------------

def format_feature_reason(feat_name: str, value: Any) -> str:
    """Create a human-readable explanation for an important feature."""

    numeric_value = _to_numeric(value)

    if numeric_value is None:
        return f"{feat_name.replace('_', ' ').capitalize()} is unavailable."

    if feat_name == "buyer_hist_late_rate":
        return (
            f"Buyer historical late-payment rate is "
            f"{numeric_value:.0%}."
        )

    if feat_name == "buyer_hist_avg_delay_days":
        return (
            f"Buyer historically takes an average of "
            f"{numeric_value:.1f} days late."
        )

    if feat_name == "buyer_hist_delay_std":
        return (
            f"Buyer payment delays vary by approximately "
            f"{numeric_value:.1f} days."
        )

    if feat_name == "buyer_hist_max_delay":
        return (
            f"Buyer has a historical maximum payment delay of "
            f"{numeric_value:.0f} days."
        )

    if feat_name == "buyer_last_invoice_delay":
        return (
            f"Buyer's most recent known payment delay was "
            f"{numeric_value:.0f} days."
        )

    if feat_name == "buyer_days_since_last_invoice":
        return (
            f"{numeric_value:.0f} days have passed since "
            f"the buyer's previous invoice."
        )

    if feat_name == "buyer_prior_invoice_count":
        return (
            f"Buyer has {numeric_value:.0f} previous invoices."
        )

    if feat_name == "invoice_amount":
        return (
            f"Invoice amount is ₹{numeric_value:,.2f}."
        )

    if feat_name == "buyer_hist_avg_amount":
        return (
            f"Buyer's historical average invoice amount is "
            f"₹{numeric_value:,.2f}."
        )

    if feat_name == "amount_vs_buyer_avg_ratio":
        return (
            f"Invoice amount is {numeric_value:.2f} times "
            f"the buyer's historical average."
        )

    if feat_name == "outstanding_amount_at_invoice":
        return (
            f"Buyer had ₹{numeric_value:,.2f} outstanding "
            f"at the invoice date."
        )

    if feat_name == "outstanding_count_at_invoice":
        return (
            f"Buyer had {numeric_value:.0f} outstanding invoices."
        )

    if feat_name == "has_history":
        return (
            "Historical payment outcomes are available."
            if numeric_value == 1
            else "No settled historical payment outcomes are available."
        )

    if feat_name == "country_code":
        return f"Buyer country code is {numeric_value:g}."

    if feat_name == "invoice_month":
        return f"Invoice was issued in month {numeric_value:.0f}."

    if feat_name == "invoice_dow":
        return f"Invoice weekday value is {numeric_value:.0f}."

    return (
        f"{feat_name.replace('_', ' ').capitalize()}: "
        f"{numeric_value:.2f}."
    )


def explain_prediction(
    artifact: dict,
    features_df: pd.DataFrame,
    features_dict: dict,
    top_k: int = 3,
) -> List[str]:
    """
    Generate feature-importance-based explanations.

    These explanations describe influential model inputs. They are not
    guaranteed to represent the direction or causal effect of each input.
    """

    try:
        model = artifact["model"]
        importances = getattr(model, "feature_importances_", None)

        if importances is None:
            return []

        importances = np.asarray(importances, dtype=float)

        if len(importances) != len(FEATURES):
            logger.warning(
                "Feature importance count does not match feature count"
            )
            return []

        ranked_indices = np.argsort(importances)[::-1]

        reasons = []

        for index in ranked_indices:
            if importances[index] <= 0:
                continue

            feature_name = FEATURES[index]
            value = features_dict.get(feature_name)

            if value is None:
                continue

            reason = format_feature_reason(feature_name, value)

            if reason not in reasons:
                reasons.append(reason)

            if len(reasons) >= top_k:
                break

        return reasons

    except Exception:
        logger.exception("Could not generate prediction explanations")
        return []


# -------------------------------------------------------------------
# Build features from database
# -------------------------------------------------------------------

def build_features_from_invoice(
    invoice_id: int,
    db: Session,
) -> dict:
    """
    Build the exact 16 application features using information available
    as of the target invoice's invoice_date.

    Database monetary values and model monetary inputs are both INR.
    """

    target = (
        db.query(Invoice)
        .filter(Invoice.invoice_id == invoice_id)
        .first()
    )

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    buyer = (
        db.query(Buyer)
        .filter(Buyer.buyer_id == target.buyer_id)
        .first()
    )

    if buyer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Buyer not found",
        )

    target_date = target.invoice_date

    if target_date is None:
        raise ValueError("Target invoice has no invoice_date")

    # 1. All invoices issued before the target invoice date.
    prior_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_date < target_date,
        )
        .all()
    )

    buyer_prior_invoice_count = len(prior_invoices)

    if prior_invoices:
        prior_dates = [
            invoice.invoice_date
            for invoice in prior_invoices
            if invoice.invoice_date is not None
        ]

        days_since_last_invoice = (
            float((target_date - max(prior_dates)).days)
            if prior_dates
            else None
        )

        prior_amounts = [
            float(invoice.invoice_amount)
            for invoice in prior_invoices
            if invoice.invoice_amount is not None
        ]

        buyer_hist_avg_amount = (
            float(np.mean(prior_amounts))
            if prior_amounts
            else None
        )

        if (
            buyer_hist_avg_amount is not None
            and buyer_hist_avg_amount > 0
            and target.invoice_amount is not None
        ):
            amount_vs_buyer_avg_ratio = round(
                float(target.invoice_amount) / buyer_hist_avg_amount,
                4,
            )
        else:
            amount_vs_buyer_avg_ratio = None

    else:
        days_since_last_invoice = None
        buyer_hist_avg_amount = None
        amount_vs_buyer_avg_ratio = None

    # 2. Historical outcomes known before the target invoice date.
    outcome_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_id != target.invoice_id,
            Invoice.invoice_date < target_date,
            Invoice.invoice_status == "settled",
            Invoice.settled_date.isnot(None),
            Invoice.settled_date < target_date,
        )
        .all()
    )

    outcome_invoices.sort(
        key=lambda invoice: (
            invoice.settled_date,
            invoice.invoice_date,
            invoice.invoice_id,
        )
    )

    has_history = int(bool(outcome_invoices))

    late_flags = [
        1 if invoice.is_late else 0
        for invoice in outcome_invoices
        if invoice.is_late is not None
    ]

    buyer_hist_late_rate = (
        float(sum(late_flags) / len(late_flags))
        if late_flags
        else None
    )

    delays = [
        float(invoice.days_late)
        for invoice in outcome_invoices
        if invoice.days_late is not None
    ]

    if delays:
        buyer_hist_avg_delay_days = float(np.mean(delays))

        # Match test_prediction_features.py: sample standard deviation.
        buyer_hist_delay_std = (
            float(np.std(delays, ddof=1))
            if len(delays) > 1
            else 0.0
        )

        buyer_hist_max_delay = float(max(delays))

    else:
        buyer_hist_avg_delay_days = None
        buyer_hist_delay_std = None
        buyer_hist_max_delay = None

    latest_outcome = (
        outcome_invoices[-1]
        if outcome_invoices
        else None
    )

    buyer_last_invoice_delay = (
        float(latest_outcome.days_late)
        if latest_outcome is not None
        and latest_outcome.days_late is not None
        else None
    )

    # 3. Outstanding invoices as of target invoice issue date.
    issued_prior = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_id != target.invoice_id,
            Invoice.invoice_date < target_date,
        )
        .all()
    )

    outstanding_invoices = [
        invoice
        for invoice in issued_prior
        if (
            invoice.settled_date is None
            or invoice.settled_date >= target_date
        )
    ]

    outstanding_amount_at_invoice = float(
        sum(
            float(invoice.invoice_amount)
            for invoice in outstanding_invoices
            if invoice.invoice_amount is not None
        )
    )

    outstanding_count_at_invoice = len(outstanding_invoices)

    # 4. Numeric country code. Unknown categorical values become missing.
    country_code = _to_numeric(buyer.country_code)

    # 5. Build exact model features. Amounts remain in INR.
    features = {
        "country_code": country_code,
        "invoice_amount": (
            float(target.invoice_amount)
            if target.invoice_amount is not None
            else None
        ),
        "invoice_month": target_date.month,
        "invoice_dow": target_date.weekday(),
        "buyer_prior_invoice_count": buyer_prior_invoice_count,
        "buyer_hist_late_rate": buyer_hist_late_rate,
        "buyer_hist_avg_delay_days": buyer_hist_avg_delay_days,
        "buyer_hist_delay_std": buyer_hist_delay_std,
        "buyer_hist_max_delay": buyer_hist_max_delay,
        "buyer_last_invoice_delay": buyer_last_invoice_delay,
        "buyer_days_since_last_invoice": days_since_last_invoice,
        "buyer_hist_avg_amount": buyer_hist_avg_amount,
        "amount_vs_buyer_avg_ratio": amount_vs_buyer_avg_ratio,
        "outstanding_amount_at_invoice": outstanding_amount_at_invoice,
        "outstanding_count_at_invoice": outstanding_count_at_invoice,
        "has_history": has_history,
    }

    if list(features.keys()) != list(FEATURES):
        raise RuntimeError(
            "Feature order mismatch between prediction service "
            "and app.ml.features.FEATURES"
        )

    return features


# -------------------------------------------------------------------
# Core calibrated prediction
# -------------------------------------------------------------------

def _predict_probability(
    artifact: dict,
    features: dict,
) -> Tuple[float, int, float, str, List[str]]:
    """Run calibrated prediction using the selected production artifact."""

    features_df = _build_model_dataframe(features)

    calibrator = artifact["calibrator"]
    threshold = float(artifact["threshold"])

    probabilities = calibrator.predict_proba(features_df)

    probability = float(probabilities[0, 1])

    if not np.isfinite(probability):
        raise ValueError("Model returned an invalid probability")

    probability = float(np.clip(probability, 0.0, 1.0))

    label = int(probability >= threshold)
    on_time_probability = float(
        np.clip(1.0 - probability, 0.0, 1.0)
    )

    risk_label = get_risk_label(probability)

    reasons = explain_prediction(
        artifact,
        features_df,
        features,
    )

    return (
        probability,
        label,
        on_time_probability,
        risk_label,
        reasons,
    )


# -------------------------------------------------------------------
# Persist prediction
# -------------------------------------------------------------------

def _save_prediction(
    invoice_id: int,
    probability: float,
    db: Session,
) -> ModelPrediction:
    """Persist a prediction and return the refreshed database record."""

    prediction = ModelPrediction(
        invoice_id=invoice_id,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        late_probability=probability,
        predicted_days_late=None,
    )

    try:
        db.add(prediction)
        db.commit()
        db.refresh(prediction)

    except Exception:
        db.rollback()
        raise

    return prediction


# -------------------------------------------------------------------
# Manual partial-feature prediction
# -------------------------------------------------------------------

def predict_late_payment(
    request: LatePaymentPredictionRequest,
    db: Session,
) -> LatePaymentPredictionResponse:
    """
    Predict using manually supplied partial features.

    Five unavailable model features are passed as missing values.
    """

    artifact = load_payment_model()

    features_dict = {
        "country_code": _to_numeric(request.country_code),
        "invoice_amount": float(request.invoice_amount),
        "invoice_month": request.invoice_month,
        "invoice_dow": request.invoice_dow,
        "buyer_prior_invoice_count": None,
        "buyer_hist_late_rate": request.buyer_hist_late_rate,
        "buyer_hist_avg_delay_days": request.buyer_hist_avg_delay_days,
        "buyer_hist_delay_std": request.buyer_hist_delay_std,
        "buyer_hist_max_delay": request.buyer_hist_max_delay,
        "buyer_last_invoice_delay": None,
        "buyer_days_since_last_invoice": None,
        "buyer_hist_avg_amount": None,
        "amount_vs_buyer_avg_ratio": None,
        "outstanding_amount_at_invoice": float(
            request.outstanding_amount_at_invoice
        ),
        "outstanding_count_at_invoice": request.outstanding_count_at_invoice,
        "has_history": request.has_history,
    }

    (
        probability,
        label,
        on_time_probability,
        risk_label,
        reasons,
    ) = _predict_probability(artifact, features_dict)

    _save_prediction(
        invoice_id=request.invoice_id,
        probability=probability,
        db=db,
    )

    return LatePaymentPredictionResponse(
        late_probability=probability,
        predicted_label=label,
        on_time_probability=on_time_probability,
        risk_label=risk_label,
        partial_features=True,
        reasons=reasons,
    )


# -------------------------------------------------------------------
# Automatic full-feature prediction
# -------------------------------------------------------------------

def predict_late_payment_features(
    invoice_id: int,
    features: dict,
    db: Session,
) -> LatePaymentPredictionResponseExtended:
    """Predict using all 16 database-built model features."""

    artifact = load_payment_model()

    missing_features = [
        feature
        for feature in FEATURES
        if feature not in features
    ]

    if missing_features:
        raise ValueError(
            f"Missing model features: {missing_features}"
        )

    (
        probability,
        label,
        on_time_probability,
        risk_label,
        reasons,
    ) = _predict_probability(artifact, features)

    prediction = _save_prediction(
        invoice_id=invoice_id,
        probability=probability,
        db=db,
    )

    scored_at = (
        getattr(prediction, "predicted_at", None)
        or datetime.now(timezone.utc)
    )

    return LatePaymentPredictionResponseExtended(
        late_probability=probability,
        predicted_label=label,
        on_time_probability=on_time_probability,
        risk_label=risk_label,
        threshold=float(artifact["threshold"]),
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        features_used=features,
        calibrated=True,
        scored_at=scored_at,
        partial_features=False,
        reasons=reasons,
    )
