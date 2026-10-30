from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LatePaymentPredictionRequest(BaseModel):
    """Input features required by the late‑payment model.

    All fields correspond to the legacy column names used during initial prototyping.
    """
    invoice_id: int = Field(..., description="Invoice identifier to associate prediction")
    invoice_amount: float = Field(..., description="Invoice amount in ₹ (INR)")
    invoice_month: int = Field(..., ge=1, le=12, description="Month of invoice date (1‑12)")
    invoice_dow: int = Field(..., ge=0, le=6, description="Day of week of invoice date (0=Mon … 6=Sun)")
    has_history: int = Field(..., ge=0, le=1, description="Whether buyer has prior settled history (0/1)")
    outstanding_amount_at_invoice: float = Field(..., description="Open exposure at invoice creation (₹)")
    outstanding_count_at_invoice: int = Field(..., description="Number of open invoices at creation")
    buyer_hist_late_rate: Optional[float] = Field(None, description="Historical buyer late rate (0‑1)")
    buyer_hist_avg_delay_days: Optional[float] = Field(None, description="Historical average days late")
    buyer_hist_delay_std: Optional[float] = Field(None, description="Historical std dev of days late")
    buyer_hist_max_delay: Optional[int] = Field(None, description="Historical maximum days late")
    country_code: Optional[str] = Field(None, description="Buyer country code (ISO or numeric)")
    paperless_bill: Optional[str] = Field(None, description="Paperless billing flag as stored in DB")


class LatePaymentPredictionResponse(BaseModel):
    """Result returned to the caller after scoring an invoice."""
    late_probability: float = Field(..., description="Probability that the invoice will be late (0‑1)")
    predicted_label: int = Field(..., description="Binary prediction (0=on‑time, 1=late)")
    on_time_probability: Optional[float] = Field(None, description="Probability that invoice is on time (1 - late_probability)")
    risk_label: Optional[str] = Field(None, description="Categorical risk tier: LOW, MEDIUM, or HIGH")
    partial_features: Optional[bool] = Field(None, description="Flag indicating if partial features were supplied")
    reasons: Optional[List[str]] = Field(None, description="Top positive factors contributing to late risk")


class LatePaymentPredictionResponseExtended(LatePaymentPredictionResponse):
    """Extended response for payment-risk prediction."""
    model_config = ConfigDict(protected_namespaces=())

    threshold: float = Field(
        default=0.25,
        description="Model decision threshold",
    )
    model_name: str = Field(
        default="payment_risk_xgb",
        description="Name of the model used",
    )
    model_version: str = Field(
        default="payment_risk_v1",
        description="Version identifier of the model",
    )
    features_used: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Feature values supplied to the model",
    )
    calibrated: bool = Field(
        default=True,
        description="Whether probability calibration has been applied",
    )
    scored_at: datetime = Field(
        ...,
        description="Timestamp when the prediction was generated",
    )


class BatchPaymentRiskRequest(BaseModel):
    """Request payload for batch invoice payment risk prediction."""
    invoice_ids: List[int] = Field(..., description="List of invoice IDs to predict (max 200)")

    @field_validator("invoice_ids")
    @classmethod
    def validate_batch_size(cls, v: List[int]) -> List[int]:
        if len(v) > 200:
            raise ValueError("Maximum of 200 invoice IDs allowed per batch request")
        if len(v) == 0:
            raise ValueError("At least one invoice ID must be provided")
        return v


class BatchPaymentRiskResponse(BaseModel):
    """Response containing multiple payment risk predictions."""
    predictions: List[LatePaymentPredictionResponseExtended]
    count: int


class CustomerRiskResponse(BaseModel):
    """Response representing persisted buyer customer risk score."""
    model_config = ConfigDict(protected_namespaces=())

    buyer_id: str = Field(..., description="Buyer identifier")
    overall_risk: float = Field(..., description="Higher-is-better overall score (0-100)")
    payment_reliability: float = Field(..., description="Higher-is-better payment reliability score (0-100)")
    financial_risk: float = Field(..., description="Higher-is-better financial health score (0-100)")
    liquidity_risk: float = Field(..., description="Higher-is-better liquidity health score (0-100)")
    tier: Optional[str] = Field(None, description="Assigned risk tier: A, B, or C")
    tier_basis: Optional[str] = Field(None, description="Scoring basis (e.g. scored, cold_start, scoring_blocked)")
    as_of_date: Optional[str] = Field(None, description="As-of date of the scoring calculation")
    model_version: str = Field(default="rules_v1", description="Scoring model version")
