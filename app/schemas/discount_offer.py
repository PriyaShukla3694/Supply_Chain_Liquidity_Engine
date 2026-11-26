from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DiscountOfferCreate(BaseModel):
    """Payload required to create a discount offer."""

    invoice_id: int
    buyer_id: str

    model_config = ConfigDict(from_attributes=True)


class DiscountOfferResponse(BaseModel):
    """Response schema for a persisted discount offer."""

    offer_id: str
    invoice_id: int
    buyer_id: str
    offer_date: date
    deadline_date: date
    invoice_amount: Decimal
    offered_rate_pct: Decimal
    discount_amount: Decimal
    net_payable_if_accepted: Decimal
    days_accelerated: int
    status: str
    recommended_by: str
    requires_approval: bool
    recommendation_payload: dict

    model_config = ConfigDict(from_attributes=True)
