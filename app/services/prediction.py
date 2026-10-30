
import joblib
import pandas as pd
import numpy as np

from datetime import datetime

from sqlalchemy.orm import Session

from fastapi import HTTPException, status

from app.core.currency import inr_to_source
from app.models.invoice import Invoice
from app.models.buyer import Buyer
from app.models.model_prediction import ModelPrediction

from app.schemas.prediction import (
    LatePaymentPredictionRequest,
    LatePaymentPredictionResponse,
    LatePaymentPredictionResponseExtended,
)


# Load the trained model pipeline (includes preprocessing).
MODEL_PATH = "models/late_payment_model.joblib"
model = joblib.load(MODEL_PATH)


def _prepare_features(
    request: LatePaymentPredictionRequest,
) -> pd.DataFrame:
    """Convert the request into the model's expected feature schema."""

    amount = request.invoice_amount

    # Convert INR to source scale (₹000) if the amount appears to be INR.
    if amount > 1000:
        amount = float(inr_to_source(amount))

    data = {
        "invoice_amount": amount,
        "invoice_month": request.invoice_month,
        "invoice_dow": request.invoice_dow,
        "has_history": request.has_history,
        "outstanding_amount_at_invoice": (
            request.outstanding_amount_at_invoice
        ),
        "outstanding_count_at_invoice": (
            request.outstanding_count_at_invoice
        ),
        "buyer_hist_late_rate": request.buyer_hist_late_rate,
        "buyer_hist_avg_delay_days": (
            request.buyer_hist_avg_delay_days
        ),
        "buyer_hist_delay_std": request.buyer_hist_delay_std,
        "buyer_hist_max_delay": request.buyer_hist_max_delay,
        "country_code": request.country_code,
        "paperless_bill": request.paperless_bill,
    }

    return pd.DataFrame([data])


def predict_late_payment(
    request: LatePaymentPredictionRequest,
    db: Session,
) -> LatePaymentPredictionResponse:
    """Predict late payment from request features and save the result."""

    features_df = _prepare_features(request)

    prob = float(model.predict_proba(features_df)[0, 1])
    label = int(prob >= 0.5)

    prediction = ModelPrediction(
        invoice_id=request.invoice_id,
        model_name="payment_delay_predictor",
        model_version="v1.0",
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
    )


def build_features_from_invoice(
    invoice_id: int,
    db: Session,
) -> dict:
    """Build the trained model's features using invoice and buyer data."""

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

    # Use only settled invoices whose outcomes were known by target_date.
    history = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_id != target.invoice_id,
            Invoice.invoice_status == "settled",
            Invoice.settled_date.isnot(None),
            Invoice.settled_date <= target_date,
        )
        .all()
    )

    has_history = int(len(history) >= 5)

    late_values = [
        int(invoice.is_late)
        for invoice in history
        if invoice.is_late is not None
    ]

    delay_values = [
        float(invoice.days_late)
        for invoice in history
        if invoice.days_late is not None
    ]

    buyer_hist_late_rate = (
        sum(late_values) / len(late_values)
        if late_values
        else None
    )

    buyer_hist_avg_delay_days = (
        sum(delay_values) / len(delay_values)
        if delay_values
        else None
    )

    # Approximate outstanding exposure at the target invoice date.
    buyer_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.buyer_id == target.buyer_id,
            Invoice.invoice_date <= target_date,
            Invoice.invoice_id != target.invoice_id,
        )
        .all()
    )

    outstanding_invoices = [
        invoice
        for invoice in buyer_invoices
        if (
            invoice.invoice_status == "open"
            or (
                invoice.settled_date is None
                or invoice.settled_date > target_date
            )
        )
    ]

    outstanding_amount_inr = sum(
        float(invoice.invoice_amount)
        for invoice in outstanding_invoices
    )

    outstanding_amount_at_invoice = float(
        inr_to_source(outstanding_amount_inr)
    )

    invoice_amount = float(
        inr_to_source(float(target.invoice_amount))
    )

    # Keep these feature names aligned with model training.
    return {
        "invoice_amount": invoice_amount,
        "invoice_month": target.invoice_date.month,
        "invoice_dow": target.invoice_date.weekday(),
        "has_history": has_history,
        "outstanding_amount_at_invoice": (
            outstanding_amount_at_invoice
        ),
        "outstanding_count_at_invoice": len(outstanding_invoices),
        "buyer_hist_late_rate": buyer_hist_late_rate,
        "buyer_hist_avg_delay_days": buyer_hist_avg_delay_days,
        "buyer_hist_delay_std": float(np.std(delay_values, ddof=0)) if delay_values else None,
        "buyer_hist_max_delay": float(max(delay_values)) if delay_values else None,
        "country_code": buyer.country_code,
        "paperless_bill": None,
    }


def predict_late_payment_features(
    invoice_id: int,
    features: dict,
    db: Session,
) -> LatePaymentPredictionResponseExtended:
    """Predict late payment from pre-built features and save the result."""

    features_df = pd.DataFrame([features])

    prob = float(model.predict_proba(features_df)[0, 1])
    threshold = 0.5
    label = int(prob >= threshold)

    prediction = ModelPrediction(
        invoice_id=invoice_id,
        model_name="payment_delay_predictor",
        model_version="v1.0",
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
        or datetime.utcnow()
    )

    return LatePaymentPredictionResponseExtended(
        late_probability=prob,
        predicted_label=label,
        threshold=threshold,
        model_name="payment_delay_predictor",
        model_version="v1.0",
        features_used=features,
        calibrated=False,
        scored_at=scored_at,
    )
