from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BuyerBase(BaseModel):
    country_code: Optional[str] = Field(None, max_length=10, description="ISO country code (e.g. 'IN')")
    primary_supplier_id: Optional[str] = Field(None, max_length=50, description="Primary supplier ID (must belong to current user's company)")
    behavioural_segment: Optional[str] = Field(None, max_length=100, description="Behavioural segment classification")
    tier: Optional[str] = Field(None, description="Risk tier: 'A', 'B', 'C' or null")
    tier_basis: Optional[str] = Field(None, max_length=30, description="Basis for tier rating")
    credit_limit: Optional[Decimal] = Field(Decimal("0.00"), description="Credit limit in INR")
    discount_responsiveness: Optional[float] = Field(None, ge=0.0, description="Responsiveness score")
    blacklisted: Optional[bool] = Field(False, description="Whether buyer is blacklisted")
    disputed_flag: Optional[bool] = Field(False, description="Whether buyer has active disputes")
    first_invoice_date: Optional[date] = None
    last_invoice_date: Optional[date] = None

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().upper()
            if v_clean not in ("A", "B", "C"):
                raise ValueError("Tier must be one of: 'A', 'B', 'C' or null")
            return v_clean
        return None


class BuyerCreate(BuyerBase):
    buyer_id: str = Field(..., min_length=1, max_length=50, description="Unique buyer code (e.g. '0187-ERLSR')")
    primary_supplier_id: str = Field(..., min_length=1, max_length=50, description="Primary supplier ID (must belong to your company)")


class BuyerUpdate(BaseModel):
    country_code: Optional[str] = Field(None, max_length=10)
    primary_supplier_id: Optional[str] = Field(None, max_length=50)
    behavioural_segment: Optional[str] = Field(None, max_length=100)
    tier: Optional[str] = None
    tier_basis: Optional[str] = Field(None, max_length=30)
    credit_limit: Optional[Decimal] = None
    discount_responsiveness: Optional[float] = Field(None, ge=0.0)
    blacklisted: Optional[bool] = None
    disputed_flag: Optional[bool] = None
    first_invoice_date: Optional[date] = None
    last_invoice_date: Optional[date] = None

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().upper()
            if v_clean not in ("A", "B", "C"):
                raise ValueError("Tier must be one of: 'A', 'B', 'C' or null")
            return v_clean
        return None


class BuyerRead(BuyerBase):
    model_config = ConfigDict(from_attributes=True)

    buyer_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BuyerDetailRead(BuyerRead):
    invoice_count: int = Field(0, description="Total number of invoices for this buyer")
    open_exposure: Decimal = Field(Decimal("0.00"), description="Total outstanding open invoice amount in INR")
