from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    payment_id: Optional[int] = None
    transaction_type: str
    amount: Decimal
    transaction_date: datetime
    currency: str
    account_number: Optional[str] = None
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
