
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.currency import convert_source_invoice_amount, format_inr
from app.core.business_rules import (
    calculate_discount_amounts,
    is_invoice_discount_eligible,
    is_human_approval_required,
)

router = APIRouter(prefix="/currency", tags=["Currency"])


class SourceInvoiceRequest(BaseModel):
    raw_amount: Decimal = Field(ge=0)
    display_amount: Decimal | None = Field(default=None, ge=0)


class DiscountPreviewRequest(BaseModel):
    invoice_amount_inr: Decimal = Field(gt=0)
    discount_rate: Decimal = Field(gt=0, le=Decimal("0.015"))
    days_until_due: int = Field(ge=0)
    is_disputed: bool = False
    invoice_status: Literal["open", "settled"] = "open"
    buyer_tier: Literal["Tier-A", "Tier-B", "Tier-C"] = "Tier-B"
    is_urgent: bool = False


@router.post("/convert-source-invoice")
def convert_invoice_amount(request: SourceInvoiceRequest):
    try:
        amount_inr = convert_source_invoice_amount(
            raw_amount=request.raw_amount,
            display_amount=request.display_amount,
        )
    except (ValueError, ArithmeticError):
        raise HTTPException(
            status_code=422,
            detail="Invalid monetary amount.",
        )

    return {
        "currency": "INR",
        "raw_amount": str(request.raw_amount),
        "amount_inr": str(amount_inr),
        "formatted_amount": format_inr(amount_inr),
        "conversion_applied": request.display_amount is None,
    }


@router.post("/discount-preview")
def preview_discount(request: DiscountPreviewRequest):
    eligible, reasons = is_invoice_discount_eligible(
        invoice_amount_inr=request.invoice_amount_inr,
        days_until_due=request.days_until_due,
        is_disputed=request.is_disputed,
        invoice_status=request.invoice_status,
        buyer_tier=request.buyer_tier,
        is_urgent=request.is_urgent,
    )

    if not eligible:
        return {
            "eligible": False,
            "reasons": reasons,
            "currency": "INR",
        }

    tier_caps = {
        "Tier-A": Decimal("0.015"),
        "Tier-B": Decimal("0.01"),
        "Tier-C": (
            Decimal("0.01")
            if request.is_urgent
            else Decimal("0.005")
        ),
    }

    if request.discount_rate > tier_caps[request.buyer_tier]:
        raise HTTPException(
            status_code=422,
            detail=f"Discount rate exceeds the cap for {request.buyer_tier}.",
        )

    amounts = calculate_discount_amounts(
        invoice_amount_inr=request.invoice_amount_inr,
        discount_rate=request.discount_rate,
    )

    approval_required = is_human_approval_required(
        invoice_amount_inr=amounts["invoice_amount"],
        discount_amount_inr=amounts["discount_amount"],
    )

    return {
        "eligible": True,
        "currency": "INR",
        "invoice_amount": str(amounts["invoice_amount"]),
        "discount_rate": str(request.discount_rate),
        "discount_amount": str(amounts["discount_amount"]),
        "net_payable_if_accepted": str(
            amounts["net_payable_if_accepted"]
        ),
        "requires_approval": approval_required,
        "message": "Preview only; no database changes made.",
    }
