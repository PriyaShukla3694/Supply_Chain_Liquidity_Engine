from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

class LatePaymentPredictionRequest(BaseModel):
    """Input features required by the late‑payment model.

    All fields correspond exactly to the column names used during training.
    Types are chosen to match the raw data format before any conversion.
    """
    invoice_id: int = Field(..., description='Invoice identifier to associate prediction')
    invoice_amount: float = Field(..., description='Invoice amount in source scale (₹000)')
    invoice_month: int = Field(..., ge=1, le=12, description='Month of invoice date (1‑12)')
    invoice_dow: int = Field(..., ge=0, le=6, description='Day of week of invoice date (0=Mon … 6=Sun)')
    has_history: int = Field(..., ge=0, le=1, description='Whether buyer has prior settled history (0/1)')
    outstanding_amount_at_invoice: float = Field(..., description='Open exposure at invoice creation (₹000)')
    outstanding_count_at_invoice: int = Field(..., description='Number of open invoices at creation')
    buyer_hist_late_rate: Optional[float] = Field(None, description='Historical buyer late rate (0‑1)')
    buyer_hist_avg_delay_days: Optional[float] = Field(None, description='Historical average days late')
    buyer_hist_delay_std: Optional[float] = Field(None, description='Historical std dev of days late')
    buyer_hist_max_delay: Optional[int] = Field(None, description='Historical maximum days late')
    country_code: Optional[str] = Field(None, description='Buyer country code (ISO)')
    paperless_bill: Optional[str] = Field(None, description='Paperless billing flag as stored in DB')

class LatePaymentPredictionResponse(BaseModel):
    """Result returned to the caller after scoring an invoice."""
    late_probability: float = Field(..., description='Probability that the invoice will be late (0‑1)')
    predicted_label: int = Field(..., description='Binary prediction (0=on‑time, 1=late)')

class LatePaymentPredictionResponseExtended(LatePaymentPredictionResponse):
    """Extended response for payment-risk prediction."""

    threshold: float = Field(
        default=0.5,
        description="Model decision threshold",
    )
    model_name: str = Field(
        ...,
        description="Name of the model used",
    )
    model_version: str = Field(
        ...,
        description="Version identifier of the model",
    )
    features_used: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Feature values supplied to the model",
    )
    calibrated: bool = Field(
        default=False,
        description="Whether probability calibration has been applied",
    )
    scored_at: datetime = Field(
        ...,
        description="Timestamp when the prediction was generated",
    )
