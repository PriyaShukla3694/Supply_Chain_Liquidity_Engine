from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SupplierBase(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Supplier business name")
    contact_email: Optional[str] = Field(None, max_length=255, description="Contact email address")
    contact_phone: Optional[str] = Field(None, max_length=50, description="Contact phone number")
    country_code: Optional[str] = Field(None, max_length=10, description="ISO country code (e.g. 'IN')")
    bank_account_number: Optional[str] = Field(None, max_length=100, description="Bank account number")
    ifsc_code: Optional[str] = Field(None, max_length=50, description="Bank IFSC code")
    is_active: Optional[bool] = Field(True, description="Whether the supplier is active")


class SupplierCreate(SupplierBase):
    supplier_id: str = Field(..., min_length=1, max_length=50, description="Unique supplier code (e.g. 'SUP-02')")


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    country_code: Optional[str] = Field(None, max_length=10)
    bank_account_number: Optional[str] = Field(None, max_length=100)
    ifsc_code: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class SupplierRead(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: str
    company_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
