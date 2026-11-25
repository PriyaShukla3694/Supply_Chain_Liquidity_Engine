
from datetime import datetime, timezone
import functools
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.currency import inr_to_source
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


# Existing trained Logistic Regression pipeline.
MODEL_PATH = Path("models/late_payment_model.joblib")
MODEL_NAME = "late_payment_logistic"
MODEL_VERSION = "late_payment_v1"


# Original trained model supports exactly these 12 features.
MODEL_FEATURES = [
    "invoice_amount",
    "invoice_month",
    "invoice_dow",
    "has_history",
    "outstanding_amount_at_invoice",
    "outstanding_count_at_invoice",
    "buyer_hist_late_rate",
    "buyer_hist_avg_delay_days",
    "buyer_hist_delay_std",
    "buyer_hist_max_delay",
    "country_code",
    "paperless_bill",
]


RISK_THRESHOLD_LOW = 0.25
RISK_THRESHOLD_MEDIUM = 0.55

# Original Logistic Regression model uses threshold 0.5.
PREDICTION_THRESHOLD = 0.5


def get_risk_label(probability: float) -> str:
    """Categorize late-payment probability into risk tiers."""

    if probability < RISK_THRESHOLD_LOW:
        return "LOW"

    if probability <= RISK_THRESHOLD_MEDIUM:
        return "MEDIUM"

    return "HIGH"


@functools.lru_cache(maxsize=1)
def load_payment_model():
    """Load and validate the existing sklearn Pipeline."""

    if not MODEL_PATH.exists():
        logger.error("Payment model not found: %s", MODEL_PATH)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Payment prediction model is unavailable",
                "code": "MODEL_UNAVAILABLE",
            },
        )

    try:
        model = joblib.load(MODEL_PATH)

        if not hasattr(model, "predict_proba"):
            raise ValueError(
                "Loaded model does not support predict_proba"
            )

        if not hasattr(model, "feature_names_in_"):
            raise ValueError(
                "Model does not contain feature_names_in_"
            )

        saved_features = list(model.feature_names_in_)

        if saved_features != MODEL_FEATURES:
            raise ValueError(
                f"Model feature mismatch. "
                f"Expected {MODEL_FEATURES}, received {saved_features}"
            )

        logger.info("Payment prediction model loaded successfully")

        return model

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Failed to load payment model")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "detail": "Payment prediction model is unavailable",
                "code": "MODEL_UNAVAILABLE",
            },
        ) from exc


def _to_model_country_code(value: Any):
    """Keep country code categorical, matching model training."""

    if value is None:
        return None

    value = str(value).strip()

    return value if value else None


def _to_model_paperless(value: Any):
    """Convert paperless billing to original training categories."""

    if value is None:
        return None

    value = str(value).strip().lower()

    if value in ("electronic", "1", "true", "yes"):
        return "Electronic"

    if value in ("paper", "0", "false", "no"):
        return "Paper"

    return None


def _build_model_dataframe(features: dict) -> pd.DataFrame:
    """Create a DataFrame containing exactly the original 12 features."""

    missing = [
        feature
        for feature in MODEL_FEATURES
        if feature not in features
    ]

    if missing:
        raise ValueError(f"Missing model features: {missing}")

    model_features = {
        feature: features[feature]
        for feature in MODEL_FEATURES
    }

    model_features["country_code"] = _to_model_country_code(
        model_features["country_code"]
    )

    model_features["paperless_bill"] = _to_model_paperless(
        model_features["paperless_bill"]
    )

    # Do not cast the whole DataFrame to float.
    # country_code and paperless_bill are categorical.
    return pd.DataFrame(
        [model_features],
        columns=MODEL_FEATURES,
    )


def format_feature_reason(feat_name: str, value: Any) -> str:
    """Create simple explanations for prediction features."""

    if value is None or pd.isna(value):
        return (
            f"Historical {feat_name.replace('_', ' ')} "
            "information is unavailable"
        )

    try:
        numeric_value = float(value)
    except (ValueError, TypeError):
        return (
            f"{feat_name.replace('_', ' ').capitalize()} "
            "contributes to the risk assessment"
        )

    if feat_name == "buyer_hist_late_rate":
        return (
            f"Buyer previously paid late on "
            f"{numeric_value * 100:.0f}% of invoices"
        )

    if feat_name == "buyer_hist_avg_delay_days":
        return (
            f"Buyer's average historical delay is "
            f"{numeric_value:.1f} days"
        )

    if feat_name == "buyer_hist_max_delay":
        return (
            f"Buyer's maximum historical payment delay "
            f"is {numeric_value:.0f} days"
        )

    if feat_name == "buyer_hist_delay_std":
        return (
            f"Historical payment delay variation is "
            f"{numeric_value:.1f} days"
        )

    if feat_name == "invoice_amount":
        return (
            f"Invoice amount is approximately "
            f"₹{numeric_value * 1000:,.2f}"
        )

    if feat_name == "outstanding_amount_at_invoice":
        return (
            f"Outstanding buyer exposure is approximately "
            f"₹{numeric_value * 1000:,.2f}"
        )

    if feat_name == "outstanding_count_at_invoice":
        return (
            f"Buyer had {int(numeric_value)} outstanding invoices"
        )

    if feat_name == "has_history":
        return (
            "Buyer has previous payment history"
            if numeric_value == 1
            else "Buyer has no previous payment history"
        )

    return (
        f"{feat_name.replace('_', ' ').capitalize()} "
        "contributes to the prediction"
    )


def explain_prediction(
    model,
    features_df: pd.DataFrame,
    features_dict: dict,
    top_k: int = 3,
) -> list[str]:
    """
    Generate simple explanations from the trained pipeline.

    The model uses preprocessing with one-hot encoding.
    """

    try:
        classifier = model.named_steps.get("classifier")

        if classifier is None or not hasattr(classifier, "coef_"):
            return []

        coefficients = classifier.coef_[0]

        preprocessor = model.named_steps.get("preprocessing")

        if preprocessor is None:
            return []

        transformed = preprocessor.transform(features_df)

        if hasattr(transformed, "toarray"):
            transformed = transformed.toarray()

        values = np.asarray(transformed)[0]

        contributions = coefficients * values

        if len(contributions) != len(values):
            return []

        try:
            transformed_names = (
                preprocessor.get_feature_names_out()
            )
        except Exception:
            return []

        ranked = sorted(
            zip(contributions, transformed_names),
            key=lambda item: item[0],
            reverse=True,
        )

        reasons = []

        for contribution, transformed_name in ranked:
            if contribution <= 0:
                continue

            matched_feature = next(
                (
                    name
                    for name in MODEL_FEATURES
                    if name in transformed_name
                ),
                None,
            )

            if matched_feature is None:
                continue

            reason = format_feature_reason(
                matched_feature,
                features_dict.get(matched_feature),
            )

            if reason not in reasons:
                reasons.append(reason)

            if len(reasons) >= top_k:
                break

        return reasons

    except Exception:
        logger.exception("Could not generate prediction explanations")
        return []


def build_features_from_invoice(
    invoice_id: int,
    db: Session,
) -> dict:
    """
    Build all 17 application features using information available
    strictly as of the target invoice's invoice_date.

    Database monetary values are INR.
    Model monetary inputs are in ₹000.
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

    # 1. Previous invoices issued before target date.
    prior_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_date < target_date,
        )
        .all()
    )

    prior_count = len(prior_invoices)

    if prior_count:
        prior_dates = [
            invoice.invoice_date
            for invoice in prior_invoices
        ]

        days_since_last_invoice = float(
            (target_date - max(prior_dates)).days
        )

        prior_amounts = [
            float(invoice.invoice_amount)
            for invoice in prior_invoices
            if invoice.invoice_amount is not None
        ]

        buyer_hist_avg_amount_inr = (
            sum(prior_amounts) / len(prior_amounts)
            if prior_amounts
            else None
        )

        if (
            buyer_hist_avg_amount_inr is not None
            and buyer_hist_avg_amount_inr > 0
        ):
            amount_vs_buyer_avg_ratio = round(
                float(target.invoice_amount)
                / buyer_hist_avg_amount_inr,
                4,
            )
        else:
            amount_vs_buyer_avg_ratio = None

    else:
        days_since_last_invoice = None
        buyer_hist_avg_amount_inr = None
        amount_vs_buyer_avg_ratio = None

    # 2. Settled outcomes already known before target invoice date.
    outcome_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_id != target.invoice_id,
            Invoice.invoice_status == "settled",
            Invoice.settled_date.isnot(None),
            Invoice.settled_date < target_date,
        )
        .all()
    )

    outcome_invoices.sort(
        key=lambda invoice: (
            invoice.invoice_date,
            invoice.settled_date,
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

    # Collect all known historical delays.
    # Missing days_late values are ignored.
    delays = [
        float(invoice.days_late)
        for invoice in outcome_invoices
        if invoice.days_late is not None
    ]

    if delays:
        buyer_hist_avg_delay_days = float(np.mean(delays))

        # Population standard deviation: ddof=0.
        buyer_hist_delay_std = float(np.std(delays, ddof=0))

        buyer_hist_max_delay = float(max(delays))

    else:
        buyer_hist_avg_delay_days = None
        buyer_hist_delay_std = None
        buyer_hist_max_delay = None

    # Latest prior outcome's delay.
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

    # 3. Outstanding invoices at target invoice issue date.
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

    outstanding_amount_inr = sum(
        float(invoice.invoice_amount)
        for invoice in outstanding_invoices
        if invoice.invoice_amount is not None
    )

    outstanding_count_at_invoice = len(outstanding_invoices)

    # 4. Country code is categorical in the original model.
    country_code = _to_model_country_code(
        buyer.country_code
    )

    # 5. Build the full 17-feature application feature dictionary.
    features = {
        "country_code": country_code,

        "invoice_amount": float(
            inr_to_source(float(target.invoice_amount))
        ),

        # No reliable paperless_bill field exists in the current
        # database model, so do not invent a value.
        "paperless_bill": None,

        "invoice_month": target.invoice_date.month,
        "invoice_dow": target.invoice_date.weekday(),

        "buyer_prior_invoice_count": prior_count,

        "buyer_hist_late_rate": buyer_hist_late_rate,
        "buyer_hist_avg_delay_days": buyer_hist_avg_delay_days,
        "buyer_hist_delay_std": buyer_hist_delay_std,
        "buyer_hist_max_delay": buyer_hist_max_delay,

        "buyer_last_invoice_delay": buyer_last_invoice_delay,
        "buyer_days_since_last_invoice": days_since_last_invoice,

        "buyer_hist_avg_amount": (
            float(inr_to_source(buyer_hist_avg_amount_inr))
            if buyer_hist_avg_amount_inr is not None
            else None
        ),

        "amount_vs_buyer_avg_ratio": amount_vs_buyer_avg_ratio,

        "outstanding_amount_at_invoice": float(
            inr_to_source(outstanding_amount_inr)
        ),

        "outstanding_count_at_invoice": outstanding_count_at_invoice,

        "has_history": has_history,
    }

    if set(features.keys()) != set(FEATURES):
        raise RuntimeError(
            "Feature mismatch between prediction service and "
            "app.ml.features.FEATURES"
        )

    return features


def _predict_probability(model, features: dict) -> tuple:
    """Run prediction using the original 12-feature model contract."""

    features_df = _build_model_dataframe(features)

    probability = float(
        model.predict_proba(features_df)[0, 1]
    )

    if not np.isfinite(probability):
        raise ValueError("Model returned an invalid probability")

    label = int(probability >= PREDICTION_THRESHOLD)

    on_time_probability = float(
        np.clip(1.0 - probability, 0.0, 1.0)
    )

    risk_label = get_risk_label(probability)

    reasons = explain_prediction(
        model,
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


def predict_late_payment(
    request: LatePaymentPredictionRequest,
    db: Session,
) -> LatePaymentPredictionResponse:
    """
    Predict using manually supplied partial features.

    Missing historical values are imputed by the original
    sklearn preprocessing pipeline.
    """

    model = load_payment_model()

    country_code = _to_model_country_code(
        request.country_code
    )

    features_dict = {
        "country_code": country_code,

        "invoice_amount": float(
            inr_to_source(float(request.invoice_amount))
        ),

        "paperless_bill": _to_model_paperless(
            getattr(request, "paperless_bill", None)
        ),

        "invoice_month": request.invoice_month,
        "invoice_dow": request.invoice_dow,

        "buyer_prior_invoice_count": np.nan,

        "buyer_hist_late_rate": request.buyer_hist_late_rate,
        "buyer_hist_avg_delay_days": request.buyer_hist_avg_delay_days,
        "buyer_hist_delay_std": request.buyer_hist_delay_std,
        "buyer_hist_max_delay": request.buyer_hist_max_delay,

        "buyer_last_invoice_delay": np.nan,
        "buyer_days_since_last_invoice": np.nan,
        "buyer_hist_avg_amount": np.nan,
        "amount_vs_buyer_avg_ratio": np.nan,

        "outstanding_amount_at_invoice": float(
            inr_to_source(
                float(request.outstanding_amount_at_invoice)
            )
        ),

        "outstanding_count_at_invoice": (
            request.outstanding_count_at_invoice
        ),

        "has_history": request.has_history,
    }

    (
        probability,
        label,
        on_time_probability,
        risk_label,
        reasons,
    ) = _predict_probability(model, features_dict)

    prediction = ModelPrediction(
        invoice_id=request.invoice_id,
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

    return LatePaymentPredictionResponse(
        late_probability=probability,
        predicted_label=label,
        on_time_probability=on_time_probability,
        risk_label=risk_label,
        partial_features=True,
        reasons=reasons,
    )


def predict_late_payment_features(
    invoice_id: int,
    features: dict,
    db: Session,
) -> LatePaymentPredictionResponseExtended:
    """
    Predict using all 17 database-built features.

    The existing trained model receives only its original
    12 supported features.
    """

    model = load_payment_model()

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
    ) = _predict_probability(model, features)

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

    scored_at = (
        getattr(prediction, "predicted_at", None)
        or datetime.now(timezone.utc)
    )

    return LatePaymentPredictionResponseExtended(
        late_probability=probability,
        predicted_label=label,
        on_time_probability=on_time_probability,
        risk_label=risk_label,
        threshold=PREDICTION_THRESHOLD,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        features_used=features,
        calibrated=False,
        scored_at=scored_at,
        partial_features=False,
        reasons=reasons,
    )
