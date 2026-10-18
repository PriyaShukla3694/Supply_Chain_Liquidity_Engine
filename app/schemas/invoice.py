from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BuyerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    buyer_id: str
    country_code: Optional[str] = None
    tier: Optional[str] = None
    credit_limit: Optional[Decimal] = None
    blacklisted: Optional[bool] = False


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


class InvoiceBase(BaseModel):
    buyer_id: str = Field(..., min_length=1, max_length=50, description="Buyer ID")
    supplier_id: str = Field(..., min_length=1, max_length=50, description="Supplier ID")
    invoice_date: date = Field(..., description="Date invoice was issued")
    due_date: date = Field(..., description="Payment due date")
    payment_terms_days: int = Field(30, gt=0, description="Payment terms in days (must be > 0)")
    invoice_amount: Decimal = Field(..., gt=Decimal("0.00"), description="Invoice amount in INR (must be > 0)")
    currency: str = Field("INR", max_length=10, description="Currency code (default 'INR')")
    disputed: bool = Field(False, description="Dispute flag")


class InvoiceCreate(InvoiceBase):
    invoice_id: Optional[int] = Field(None, description="Optional invoice ID; generated if omitted")

    @model_validator(mode="after")
    def validate_dates(self) -> "InvoiceCreate":
        if self.due_date < self.invoice_date:
            raise ValueError("due_date must be greater than or equal to invoice_date")
        return self


class InvoiceUpdate(BaseModel):
    disputed: Optional[bool] = Field(None, description="Updated dispute status (allowed while open)")
    invoice_amount: Optional[Decimal] = Field(None, gt=Decimal("0.00"), description="Updated amount in INR (must be > 0, allowed while open)")


class InvoiceSettle(BaseModel):
    settled_date: date = Field(..., description="Date of settlement")


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: int
    buyer_id: str
    supplier_id: str
    invoice_date: date
    due_date: date
    payment_terms_days: int
    invoice_amount: Decimal
    currency: str
    disputed: bool
    invoice_status: str
    settled_date: Optional[date] = None
    days_late: Optional[int] = None
    is_late: Optional[bool] = None
    days_until_due: Optional[int] = Field(None, description="due_date minus today, null if settled")
    overdue_days: int = Field(0, description="days past due for open invoices, 0 otherwise")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InvoiceDetailRead(InvoiceRead):
    buyer: Optional[BuyerSummary] = None
    payments: List[PaymentRead] = Field(default_factory=list)


class MetricSummary(BaseModel):
    count: int = Field(..., description="Count of invoices")
    total_amount: Decimal = Field(..., description="Total amount in INR")


class InvoiceSummary(BaseModel):
    open: MetricSummary
    overdue: MetricSummary
    settled: MetricSummary
    disputed: MetricSummary
    open_count: int
    open_total: Decimal
    overdue_count: int
    overdue_total: Decimal
    settled_count: int
    settled_total: Decimal
    disputed_count: int
    disputed_total: Decimal
