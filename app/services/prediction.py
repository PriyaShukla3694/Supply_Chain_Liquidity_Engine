from datetime import datetime, timezone
import functools
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
import joblib
import numpy as np
import pandas as pd
import sklearn
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

# Model configuration constants
MODEL_PATH = Path("models/payment_risk_v1.joblib")
MODEL_NAME = "payment_risk_xgb"
MODEL_VERSION = "payment_risk_v1"

# Risk label thresholds (kept in one place)
RISK_THRESHOLD_LOW = 0.25
RISK_THRESHOLD_MEDIUM = 0.55


def get_risk_label(probability: float) -> str:
    """Categorize late payment probability into risk tiers:

    LOW: < 0.25
    MEDIUM: 0.25 - 0.55
    HIGH: > 0.55
    """
    if probability < RISK_THRESHOLD_LOW:
        return "LOW"
    elif probability <= RISK_THRESHOLD_MEDIUM:
        return "MEDIUM"
    else:
        return "HIGH"


@functools.lru_cache(maxsize=1)
def load_payment_model() -> dict:
    """Load the calibrated payment risk model artifact with caching.

    If the artifact is missing or fails to unpickle, raises HTTP 503
    with code 'MODEL_UNAVAILABLE' while allowing the main app to start.
    Logs a warning if the pickled sklearn version differs from the runtime version.
    """
    if not MODEL_PATH.exists():
        logger.warning("Payment risk model artifact missing at %s", MODEL_PATH)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "Model not available", "code": "MODEL_UNAVAILABLE"},
        )

    try:
        artifact = joblib.load(MODEL_PATH)
    except Exception as exc:
        logger.warning("Failed to load payment risk model from %s: %s", MODEL_PATH, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "Model not available", "code": "MODEL_UNAVAILABLE"},
        ) from exc

    saved_version = artifact.get("sklearn_version")
    if saved_version and saved_version != sklearn.__version__:
        logger.warning(
            "Saved sklearn_version (%s) differs from installed version (%s)",
            saved_version,
            sklearn.__version__,
        )

    return artifact


def format_feature_reason(feat_name: str, val: Any) -> str:
    """Format a single feature's plain-English reason template."""
    if val is None or pd.isna(val):
        if feat_name == "has_history":
            return "Buyer has no prior settled payment history"
        elif feat_name == "country_code":
            return "Buyer country risk profile contributes to delay probability"
        return f"Historical {feat_name.replace('_', ' ')} value absent or limited"

    try:
        val_float = float(val)
    except (ValueError, TypeError):
        return f"{feat_name.replace('_', ' ').capitalize()} contributes to delay probability"

    if feat_name == "buyer_hist_late_rate":
        return f"Buyer paid late on {val_float * 100:.0f}% of past invoices"
    elif feat_name == "buyer_hist_avg_delay_days":
        return f"Buyer had an average historical delay of {val_float:.1f} days on past invoices"
    elif feat_name == "buyer_hist_max_delay":
        return f"Buyer previously experienced a maximum payment delay of {val_float:.0f} days"
    elif feat_name == "buyer_hist_delay_std":
        return f"Buyer payment timing has high historical variance (standard deviation of {val_float:.1f} days)"
    elif feat_name == "buyer_days_since_last_invoice":
        return f"Long gap of {val_float:.0f} days since the buyer's last invoice"
    elif feat_name == "outstanding_amount_at_invoice":
        return f"Significant open exposure of ₹{val_float:,.2f} at time of invoice creation"
    elif feat_name == "outstanding_count_at_invoice":
        return f"Buyer had {int(val_float)} unresolved open invoice(s) at time of invoice issuance"
    elif feat_name == "invoice_amount":
        return f"High invoice amount of ₹{val_float:,.2f}"
    elif feat_name == "amount_vs_buyer_avg_ratio":
        return f"Invoice amount is {val_float:.1f}x higher than the buyer's historical average"
    elif feat_name == "buyer_hist_avg_amount":
        return f"Buyer has a large average historical invoice size of ₹{val_float:,.2f}"
    elif feat_name == "country_code":
        return f"Buyer location country code ({int(val_float)}) associated with higher delay risk"
    elif feat_name == "buyer_last_invoice_delay":
        return f"Buyer's most recent settled invoice was delayed by {val_float:.0f} days"
    elif feat_name == "invoice_dow":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dow_str = days[int(val_float)] if 0 <= int(val_float) < 7 else str(int(val_float))
        return f"Invoice issued on {dow_str} associated with higher processing delay"
    elif feat_name == "invoice_month":
        months = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        m_str = months[int(val_float)] if 1 <= int(val_float) <= 12 else str(int(val_float))
        return f"Invoice issued in {m_str} with higher seasonal payment risk"
    elif feat_name == "buyer_prior_invoice_count":
        return f"Buyer has limited prior transaction history ({int(val_float)} prior invoice(s))"
    elif feat_name == "has_history":
        return "Buyer has no prior settled payment history" if val_float == 0 else "Limited established settlement history"
    return f"{feat_name.replace('_', ' ').capitalize()} contributes to delay probability"


def explain_prediction(
    artifact: dict,
    features_df: pd.DataFrame,
    features_dict: dict,
    top_k: int = 3,
) -> list[str]:
    """Generate top_k plain English reason statements for features pushing
    the prediction towards late payment (positive contribution = coefficient * scaled_value or SHAP contribution).
    """
    model_pipeline = artifact.get("model")
    if model_pipeline is None:
        return []

    feature_names = artifact.get("features", FEATURES)

    if hasattr(model_pipeline, "named_steps"):
        try:
            imputer = model_pipeline.named_steps["imputer"]
            scaler = model_pipeline.named_steps["scaler"]
            clf = model_pipeline.named_steps["classifier"]
            X_imp = imputer.transform(features_df)
            X_scaled = scaler.transform(X_imp)[0]
            coefs = clf.coef_[0]
            contributions = coefs * X_scaled
        except (KeyError, AttributeError):
            return []
    elif hasattr(model_pipeline, "get_booster"):
        try:
            import xgboost as xgb
            features_float = features_df[feature_names].astype(float)
            dmat = xgb.DMatrix(features_float)
            contribs = model_pipeline.get_booster().predict(dmat, pred_contribs=True)[0]
            contributions = contribs[:len(feature_names)]
        except Exception as exc:
            logger.warning("Failed computing XGBoost feature contributions: %s", exc)
            return []
    elif hasattr(model_pipeline, "feature_importances_"):
        contributions = model_pipeline.feature_importances_
    else:
        return []

    # Collect features pushing the log-odds UP (positive contribution towards delay)
    positive_contribs = []
    for idx, name in enumerate(feature_names):
        c = contributions[idx]
        if c > 0:
            positive_contribs.append((c, name, features_dict.get(name)))

    positive_contribs.sort(key=lambda x: x[0], reverse=True)
    top_features = positive_contribs[:top_k]

    reasons = []
    for _, feat_name, raw_val in top_features:
        sentence = format_feature_reason(feat_name, raw_val)
        if sentence:
            reasons.append(sentence)

    return reasons


def build_features_from_invoice(
    invoice_id: int,
    db: Session,
) -> dict:
    """Auto feature building from the database, STRICTLY as of the invoice_date.

    Business rules:
    - For an invoice, use only the same buyer's earlier invoices (invoice_date < target_date).
    - For outcome-based features, use only earlier invoices whose settled_date is strictly before
      invoice_date (settled_date < target_date). Never use later invoices or the invoice's own outcome.
    - All 16 FEATURES from app/ml/features.py are returned in order.
    - Amounts in the DB are in rupees (no x1000 scaling applied).
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

    # 1. Prior invoices issued strictly before this invoice's creation date
    prior_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_date < target_date,
        )
        .all()
    )
    prior_count = len(prior_invoices)

    if prior_count > 0:
        prior_dates = [x.invoice_date for x in prior_invoices]
        days_since_last_invoice = float((target_date - max(prior_dates)).days)
        prior_amounts = [float(x.invoice_amount) for x in prior_invoices]
        buyer_hist_avg_amount = float(sum(prior_amounts) / len(prior_amounts))
        amount_vs_buyer_avg_ratio = float(
            round(float(target.invoice_amount) / buyer_hist_avg_amount, 4)
        )
    else:
        days_since_last_invoice = None
        buyer_hist_avg_amount = None
        amount_vs_buyer_avg_ratio = None

    # 2. Outcome-based features: only prior settled invoices with settled_date < target_date
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
    outcome_invoices.sort(key=lambda x: (x.settled_date, x.invoice_date, x.invoice_id))

    num_outcomes = len(outcome_invoices)
    has_history = int(num_outcomes > 0)

    if has_history:
        late_flags = [
            1 if x.is_late else 0
            for x in outcome_invoices
            if x.is_late is not None
        ]
        buyer_hist_late_rate = (
            float(sum(late_flags) / len(late_flags))
            if late_flags
            else None
        )
        delays = [
            float(x.days_late)
            for x in outcome_invoices
            if x.days_late is not None
        ]
        if delays:
            buyer_hist_avg_delay_days = float(sum(delays) / len(delays))
            buyer_hist_delay_std = (
                float(np.std(delays, ddof=1))
                if len(delays) > 1
                else 0.0
            )
            buyer_hist_max_delay = float(max(delays))
            last_delay_val = outcome_invoices[-1].days_late
            buyer_last_invoice_delay = (
                float(last_delay_val)
                if last_delay_val is not None
                else delays[-1]
            )
        else:
            buyer_hist_avg_delay_days = None
            buyer_hist_delay_std = None
            buyer_hist_max_delay = None
            buyer_last_invoice_delay = None
    else:
        buyer_hist_late_rate = None
        buyer_hist_avg_delay_days = None
        buyer_hist_delay_std = None
        buyer_hist_max_delay = None
        buyer_last_invoice_delay = None

    # 3. Outstanding exposure at invoice issuance:
    # Invoices issued strictly before target_date that are still open or settled >= target_date
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
        inv
        for inv in issued_prior
        if inv.settled_date is None or inv.settled_date >= target_date
    ]
    outstanding_amount_at_invoice = float(
        sum(float(x.invoice_amount) for x in outstanding_invoices)
    )
    outstanding_count_at_invoice = len(outstanding_invoices)

    country_code = None
    if buyer.country_code is not None and str(buyer.country_code).strip() != "":
        try:
            country_code = float(buyer.country_code)
        except (ValueError, TypeError):
            country_code = None

    return {
        "country_code": country_code,
        "invoice_amount": float(target.invoice_amount),
        "invoice_month": target.invoice_date.month,
        "invoice_dow": target.invoice_date.weekday(),
        "buyer_prior_invoice_count": prior_count,
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


def predict_late_payment(
    request: LatePaymentPredictionRequest,
    db: Session,
) -> LatePaymentPredictionResponse:
    """Predict late payment from manually supplied 12 features (POST /invoices/{id}/predict).

    Fills the 5 missing features with NaN so the pipeline imputer handles them.
    Saves the prediction to model_predictions with model_name='payment_risk_logreg' and
    model_version='payment_risk_v1', and sets partial_features=True in the response.
    """
    artifact = load_payment_model()
    calibrator = artifact["calibrator"]
    threshold = float(artifact.get("threshold", 0.25))

    country_val = None
    if request.country_code is not None:
        try:
            country_val = float(request.country_code)
        except (ValueError, TypeError):
            country_val = None

    features_dict = {
        "country_code": country_val,
        "invoice_amount": float(request.invoice_amount),
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
        "outstanding_amount_at_invoice": float(request.outstanding_amount_at_invoice),
        "outstanding_count_at_invoice": request.outstanding_count_at_invoice,
        "has_history": request.has_history,
    }

    features_df = pd.DataFrame([[features_dict[col] for col in FEATURES]], columns=FEATURES, dtype=float)

    prob = float(calibrator.predict_proba(features_df)[0, 1])
    label = int(prob >= threshold)
    on_time_prob = float(np.clip(1.0 - prob, 0.0, 1.0))
    risk_label = get_risk_label(prob)
    reasons = explain_prediction(artifact, features_df, features_dict)

    prediction = ModelPrediction(
        invoice_id=request.invoice_id,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        late_probability=prob,
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
        late_probability=prob,
        predicted_label=label,
        on_time_probability=on_time_prob,
        risk_label=risk_label,
        partial_features=True,
        reasons=reasons,
    )


def predict_late_payment_features(
    invoice_id: int,
    features: dict,
    db: Session,
) -> LatePaymentPredictionResponseExtended:
    """Predict late payment from 16 database-built features and persist the result."""
    artifact = load_payment_model()
    calibrator = artifact["calibrator"]
    threshold = float(artifact.get("threshold", 0.25))

    features_df = pd.DataFrame([[features[col] for col in FEATURES]], columns=FEATURES, dtype=float)

    prob = float(calibrator.predict_proba(features_df)[0, 1])
    label = int(prob >= threshold)
    on_time_prob = float(np.clip(1.0 - prob, 0.0, 1.0))
    risk_label = get_risk_label(prob)
    reasons = explain_prediction(artifact, features_df, features)

    prediction = ModelPrediction(
        invoice_id=invoice_id,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        late_probability=prob,
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
        late_probability=prob,
        predicted_label=label,
        on_time_probability=on_time_prob,
        risk_label=risk_label,
        threshold=threshold,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        features_used=features,
        calibrated=True,
        scored_at=scored_at,
        partial_features=False,
        reasons=reasons,
    )
