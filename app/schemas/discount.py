
from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict


class DiscountRecommendation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    buyer_id: str
    invoice_amount: Decimal
    days_until_due: int
    buyer_tier: str
    offered_rate_pct: Decimal
    discount_amount: Decimal
    net_payable_if_accepted: Decimal
    requires_approval: bool
    status: str


class ExcludedDiscountInvoice(BaseModel):
    invoice_id: int
    buyer_id: str
    reasons: List[str]


class DiscountRecommendationsResponse(BaseModel):
    business_date: date
    week_start: date
    week_end: date
    is_urgent: bool
    eligible_invoice_value: Decimal
    weekly_budget: Decimal
    existing_allocation: Decimal
    new_recommendation_total: Decimal
    remaining_budget: Decimal
    recommendations: List[DiscountRecommendation]
    excluded_invoices: List[ExcludedDiscountInvoice]
