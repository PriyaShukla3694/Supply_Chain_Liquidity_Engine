from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


VALID_PAYMENT_STATUSES = {"completed", "pending", "failed", "refunded"}


class PaymentBase(BaseModel):
    invoice_id: int = Field(..., description="Target invoice ID")
    payment_date: date = Field(..., description="Date payment was made")
    payment_amount: Decimal = Field(..., gt=Decimal("0.00"), description="Payment amount (must be > 0)")
    payment_method: Optional[str] = Field(None, max_length=50, description="Payment method: NEFT, RTGS, UPI, etc.")
    reference_number: Optional[str] = Field(None, max_length=100, description="External reference or UTR number")
    status: str = Field("completed", description="Payment status: completed, pending, failed, refunded")
    discount_applied: Decimal = Field(Decimal("0.00"), ge=Decimal("0.00"), description="Discount applied (if any)")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_PAYMENT_STATUSES)}")
        return val


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    status: Optional[str] = Field(None, description="Updated status: completed, pending, failed, refunded")
    payment_method: Optional[str] = Field(None, max_length=50)
    reference_number: Optional[str] = Field(None, max_length=100)
    discount_applied: Optional[Decimal] = Field(None, ge=Decimal("0.00"))

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            val = v.strip().lower()
            if val not in VALID_PAYMENT_STATUSES:
                raise ValueError(f"status must be one of {sorted(VALID_PAYMENT_STATUSES)}")
            return val
        return v


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: int
    invoice_id: int
    payment_date: date
    payment_amount: Decimal
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    status: str
    discount_applied: Decimal
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
