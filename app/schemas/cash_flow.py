from datetime import date as dt_date, datetime as dt_datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CashFlowBase(BaseModel):
    date: dt_date = Field(..., description="Date of the cash flow snapshot")
    inflow_actual: Decimal = Field(..., ge=Decimal("0.00"), description="Total actual cash inflow for the day")
    outflow_actual: Decimal = Field(..., ge=Decimal("0.00"), description="Total actual cash outflow for the day")
    net_cash_flow: Decimal = Field(..., description="Net cash flow (inflow_actual - outflow_actual)")
    opening_balance: Decimal = Field(..., description="Opening bank/cash balance")
    closing_balance: Decimal = Field(..., description="Closing balance (opening_balance + net_cash_flow)")
    outstanding_receivables: Decimal = Field(Decimal("0.00"), ge=Decimal("0.00"), description="Total pending receivables")
    min_cash_buffer: Decimal = Field(Decimal("0.00"), ge=Decimal("0.00"), description="Target minimum operating liquidity buffer")
    liquidity_gap: Decimal = Field(Decimal("0.00"), description="Liquidity gap (positive if below buffer)")
    company_id: Optional[int] = Field(None, description="Company ID (defaults to current user's company)")


class CashFlowCreate(CashFlowBase):
    @model_validator(mode="after")
    def validate_cash_flow_math(self) -> "CashFlowCreate":
        expected_net = self.inflow_actual - self.outflow_actual
        if abs(self.net_cash_flow - expected_net) > Decimal("0.01"):
            raise ValueError(
                f"net_cash_flow ({self.net_cash_flow}) must equal inflow_actual ({self.inflow_actual}) - outflow_actual ({self.outflow_actual}) = {expected_net}"
            )
        expected_closing = self.opening_balance + self.net_cash_flow
        if abs(self.closing_balance - expected_closing) > Decimal("0.01"):
            raise ValueError(
                f"closing_balance ({self.closing_balance}) must equal opening_balance ({self.opening_balance}) + net_cash_flow ({self.net_cash_flow}) = {expected_closing}"
            )
        return self


class CashFlowUpdate(BaseModel):
    inflow_actual: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    outflow_actual: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    net_cash_flow: Optional[Decimal] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    outstanding_receivables: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    min_cash_buffer: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    liquidity_gap: Optional[Decimal] = None


class CashFlowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    date: dt_date
    inflow_actual: Decimal
    outflow_actual: Decimal
    net_cash_flow: Decimal
    opening_balance: Decimal
    closing_balance: Decimal
    outstanding_receivables: Decimal
    min_cash_buffer: Decimal
    liquidity_gap: Decimal
    created_at: Optional[dt_datetime] = None
    updated_at: Optional[dt_datetime] = None


class CashFlowPeriodSummary(BaseModel):
    start_date: dt_date
    end_date: dt_date
    total_inflow: Decimal
    total_outflow: Decimal
    net_cash_flow: Decimal
    days_with_liquidity_gap: int


class CashFlowSummary(BaseModel):
    as_of_date: dt_date
    last_7_days: CashFlowPeriodSummary
    last_30_days: CashFlowPeriodSummary
