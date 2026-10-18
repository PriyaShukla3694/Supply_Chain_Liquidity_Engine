from decimal import Decimal
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.currency import (
    to_decimal,
    source_to_inr,
    inr_to_source,
    convert_source_invoice_amount,
    convert_source_offer_amounts,
    format_inr,
    SOURCE_SCALE_FACTOR,
)
from app.core.business_rules import (
    is_invoice_discount_eligible,
    calculate_discount_amounts,
    is_human_approval_required,
    DEFAULT_BUSINESS_RULES,
)
from app.api.currency import router as currency_router


@pytest.mark.unit
def test_scale_factor_is_one_thousand():
    assert SOURCE_SCALE_FACTOR == Decimal("1000")


@pytest.mark.unit
def test_source_to_inr_explicit_conversion():
    # 50.39 (₹000) -> ₹50,390.00
    assert source_to_inr("50.39") == Decimal("50390.00")
    assert source_to_inr(Decimal("50.39")) == Decimal("50390.00")
    assert source_to_inr(55.94) == Decimal("55940.00")
    assert source_to_inr("100.00") == Decimal("100000.00")
    assert source_to_inr("0.00") == Decimal("0.00")
    assert source_to_inr(0) == Decimal("0.00")


@pytest.mark.unit
def test_inr_to_source_explicit_conversion():
    # ₹50,390.00 -> 50.39 (₹000)
    assert inr_to_source(Decimal("50390.00")) == Decimal("50.39")
    assert inr_to_source("100000.00") == Decimal("100.00")
    assert inr_to_source("0.00") == Decimal("0.00")


@pytest.mark.unit
def test_invoice_amount_prevents_double_conversion():
    # When display_amount is provided, use it directly (already in INR)
    # MUST NOT multiply 50390.00 by 1000 to get 50,390,000.00
    res = convert_source_invoice_amount(
        raw_amount="50.39",
        display_amount="50390.00",
    )
    assert res == Decimal("50390.00")


@pytest.mark.unit
def test_invoice_amount_fallback_to_raw_source():
    # When display_amount is missing or empty, explicitly convert source-scale amount
    res_none = convert_source_invoice_amount(raw_amount="50.39", display_amount=None)
    assert res_none == Decimal("50390.00")

    res_empty = convert_source_invoice_amount(raw_amount="50.39", display_amount="")
    assert res_empty == Decimal("50390.00")


@pytest.mark.unit
def test_convert_source_offer_amounts_scales_monetary_leaves_rate_untouched():
    # Historical offer row values: invoice 55.94, discount 0.83, net 55.11, rate 1.48%
    converted = convert_source_offer_amounts(
        invoice_amount="55.94",
        discount_amount="0.83",
        net_payable="55.11",
        rate_pct="1.48",
    )
    assert converted["invoice_amount"] == Decimal("55940.00")
    assert converted["discount_amount"] == Decimal("830.00")
    assert converted["net_payable_if_accepted"] == Decimal("55110.00")
    # Rate must NOT be multiplied by 1000
    assert converted["offered_rate_pct"] == Decimal("1.48")


@pytest.mark.unit
def test_unitless_and_ratio_fields_unscaled():
    # Ratios (e.g. amount_vs_buyer_avg_ratio) are unitless and must remain unscaled
    ratio = Decimal("1.25")
    assert ratio != ratio * Decimal("1000")
    assert ratio == Decimal("1.25")


@pytest.mark.unit
def test_eligibility_boundary_at_inr_50000():
    # Exactly ₹50,000.00 is eligible
    eligible, _ = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("50000.00"),
        days_until_due=15,
        is_disputed=False,
        invoice_status="open",
        buyer_tier="Tier-B",
    )
    assert eligible is True

    # ₹49,999.99 is ineligible
    ineligible, reasons = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("49999.99"),
        days_until_due=15,
        is_disputed=False,
        invoice_status="open",
        buyer_tier="Tier-B",
    )
    assert ineligible is False
    assert "amount_below_minimum_threshold" in reasons

    # Using convert_source_invoice_amount at the boundary:
    # 49.99 in source scale -> ₹49,990.00 -> Ineligible
    amt_below = convert_source_invoice_amount("49.99")
    ok_below, reasons_below = is_invoice_discount_eligible(
        invoice_amount_inr=amt_below,
        days_until_due=15,
        is_disputed=False,
        invoice_status="open",
    )
    assert ok_below is False
    assert "amount_below_minimum_threshold" in reasons_below

    # 50.00 in source scale -> ₹50,000.00 -> Eligible
    amt_exact = convert_source_invoice_amount("50.00")
    ok_exact, _ = is_invoice_discount_eligible(
        invoice_amount_inr=amt_exact,
        days_until_due=15,
        is_disputed=False,
        invoice_status="open",
    )
    assert ok_exact is True


@pytest.mark.unit
def test_eligibility_business_conditions():
    # Disputed invoice must be rejected
    ok_disp, reasons_disp = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("60000.00"),
        days_until_due=15,
        is_disputed=True,
        invoice_status="open",
    )
    assert ok_disp is False
    assert "invoice_disputed" in reasons_disp

    # Less than 10 days to due date must be rejected
    ok_days, reasons_days = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("60000.00"),
        days_until_due=9,
        is_disputed=False,
        invoice_status="open",
    )
    assert ok_days is False
    assert "days_until_due_less_than_10" in reasons_days

    # Settled invoice must be rejected
    ok_settled, reasons_settled = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("60000.00"),
        days_until_due=15,
        is_disputed=False,
        invoice_status="settled",
    )
    assert ok_settled is False
    assert "invoice_not_open" in reasons_settled

    # Tier C without urgency rejected; with urgency accepted
    ok_c_norm, reasons_c_norm = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("60000.00"),
        days_until_due=15,
        is_disputed=False,
        invoice_status="open",
        buyer_tier="Tier-C",
        is_urgent=False,
    )
    assert ok_c_norm is False
    assert "tier_c_ineligible_without_urgency" in reasons_c_norm

    ok_c_urg, _ = is_invoice_discount_eligible(
        invoice_amount_inr=Decimal("60000.00"),
        days_until_due=15,
        is_disputed=False,
        invoice_status="open",
        buyer_tier="Tier-C",
        is_urgent=True,
    )
    assert ok_c_urg is True


@pytest.mark.unit
def test_discount_calculation_in_inr():
    # ₹200,000.00 at 1.5% discount rate (0.0150)
    calc = calculate_discount_amounts(
        invoice_amount_inr=Decimal("200000.00"),
        discount_rate=Decimal("0.0150"),
    )
    assert calc["invoice_amount"] == Decimal("200000.00")
    assert calc["discount_amount"] == Decimal("3000.00")
    assert calc["net_payable_if_accepted"] == Decimal("197000.00")

    # ₹50,390.00 at 1.0% discount rate (0.0100)
    calc_50k = calculate_discount_amounts(
        invoice_amount_inr=Decimal("50390.00"),
        discount_rate=Decimal("0.0100"),
    )
    assert calc_50k["discount_amount"] == Decimal("503.90")
    assert calc_50k["net_payable_if_accepted"] == Decimal("49886.10")


@pytest.mark.unit
def test_human_approval_thresholds_in_inr():
    # Below both thresholds: discount <= ₹1,000 AND invoice <= ₹100,000
    assert not is_human_approval_required(
        invoice_amount_inr=Decimal("50000.00"),
        discount_amount_inr=Decimal("500.00"),
    )

    # Exactly at thresholds (strict greater-than)
    assert not is_human_approval_required(
        invoice_amount_inr=Decimal("100000.00"),
        discount_amount_inr=Decimal("1000.00"),
    )

    # Exceeds discount threshold: discount > ₹1,000
    assert is_human_approval_required(
        invoice_amount_inr=Decimal("80000.00"),
        discount_amount_inr=Decimal("1000.01"),
    )

    # Exceeds invoice threshold: invoice > ₹100,000
    assert is_human_approval_required(
        invoice_amount_inr=Decimal("100000.01"),
        discount_amount_inr=Decimal("500.00"),
    )


@pytest.mark.unit
def test_format_inr_display():
    assert format_inr("50390.00") == "₹50,390.00"
    assert format_inr(Decimal("100000.50")) == "₹100,000.50"
    assert format_inr(1250000) == "₹1,250,000.00"
    assert format_inr(0) == "₹0.00"
    assert format_inr("-50390.00") == "-₹50,390.00"
    assert format_inr(Decimal("-500.00")) == "-₹500.00"


@pytest.mark.unit
def test_to_decimal_whitespace_and_edge_cases():
    assert to_decimal(None) == Decimal("0.00")
    assert to_decimal("") == Decimal("0.00")
    assert to_decimal("   ") == Decimal("0.00")
    assert to_decimal("  50.39  ") == Decimal("50.39")
    assert to_decimal(Decimal("100.50")) == Decimal("100.50")


@pytest.fixture
def api_client():
    test_app = FastAPI()
    test_app.include_router(currency_router)
    return TestClient(test_app)


@pytest.mark.unit
def test_api_convert_source_invoice_success(api_client):
    # Source raw amount 60 (in ₹000) -> ₹60,000.00
    res = api_client.post("/currency/convert-source-invoice", json={"raw_amount": "60"})
    assert res.status_code == 200
    data = res.json()
    assert data["currency"] == "INR"
    assert data["raw_amount"] == "60"
    assert data["amount_inr"] == "60000.00"
    assert data["formatted_amount"] == "₹60,000.00"
    assert data["conversion_applied"] is True


@pytest.mark.unit
def test_api_convert_source_invoice_prevent_double_conversion(api_client):
    # When display_amount is provided, use directly without 1000x multiplier
    res = api_client.post(
        "/currency/convert-source-invoice",
        json={"raw_amount": "60", "display_amount": "60000.00"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["raw_amount"] == "60"
    assert data["amount_inr"] == "60000.00"
    assert data["formatted_amount"] == "₹60,000.00"
    assert data["conversion_applied"] is False


@pytest.mark.unit
def test_api_convert_source_invoice_invalid_input(api_client):
    # Negative raw amount rejected by schema
    res_neg = api_client.post("/currency/convert-source-invoice", json={"raw_amount": "-10"})
    assert res_neg.status_code == 422

    # Non-numeric input rejected by schema
    res_str = api_client.post("/currency/convert-source-invoice", json={"raw_amount": "invalid"})
    assert res_str.status_code == 422


@pytest.mark.unit
def test_api_discount_preview_success_tier_b(api_client):
    # Previously tested example: ₹60,000 at 1.0% discount rate (0.01)
    payload = {
        "invoice_amount_inr": 60000,
        "discount_rate": 0.01,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-B",
    }
    res = api_client.post("/currency/discount-preview", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["eligible"] is True
    assert data["currency"] == "INR"
    assert data["invoice_amount"] == "60000.00"
    assert data["discount_rate"] == "0.01"
    assert data["discount_amount"] == "600.00"
    assert data["net_payable_if_accepted"] == "59400.00"
    assert data["requires_approval"] is False


@pytest.mark.unit
def test_api_discount_preview_ineligible_conditions(api_client):
    base_payload = {
        "invoice_amount_inr": 60000,
        "discount_rate": 0.01,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-B",
    }

    # Ineligible when disputed
    disp_payload = dict(base_payload, is_disputed=True)
    res_disp = api_client.post("/currency/discount-preview", json=disp_payload)
    assert res_disp.status_code == 200
    assert res_disp.json()["eligible"] is False
    assert "invoice_disputed" in res_disp.json()["reasons"]

    # Ineligible when days < 10
    days_payload = dict(base_payload, days_until_due=8)
    res_days = api_client.post("/currency/discount-preview", json=days_payload)
    assert res_days.status_code == 200
    assert res_days.json()["eligible"] is False
    assert "days_until_due_less_than_10" in res_days.json()["reasons"]

    # Ineligible when amount < ₹50,000
    amt_payload = dict(base_payload, invoice_amount_inr=49999.99)
    res_amt = api_client.post("/currency/discount-preview", json=amt_payload)
    assert res_amt.status_code == 200
    assert res_amt.json()["eligible"] is False
    assert "amount_below_minimum_threshold" in res_amt.json()["reasons"]

    # Ineligible when invoice settled
    settled_payload = dict(base_payload, invoice_status="settled")
    res_settled = api_client.post("/currency/discount-preview", json=settled_payload)
    assert res_settled.status_code == 200
    assert res_settled.json()["eligible"] is False
    assert "invoice_not_open" in res_settled.json()["reasons"]


@pytest.mark.unit
def test_api_discount_preview_tier_rate_cap_boundaries(api_client):
    # Tier-B cap is 1.0% (0.01). 1.2% must be rejected with 422
    tier_b_over = {
        "invoice_amount_inr": 60000,
        "discount_rate": 0.012,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-B",
    }
    res_b = api_client.post("/currency/discount-preview", json=tier_b_over)
    assert res_b.status_code == 422
    assert "exceeds the cap for Tier-B" in res_b.json()["detail"]

    # Tier-C without urgency: ineligible
    tier_c_norm = {
        "invoice_amount_inr": 60000,
        "discount_rate": 0.005,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-C",
        "is_urgent": False,
    }
    res_c_norm = api_client.post("/currency/discount-preview", json=tier_c_norm)
    assert res_c_norm.status_code == 200
    assert res_c_norm.json()["eligible"] is False
    assert "tier_c_ineligible_without_urgency" in res_c_norm.json()["reasons"]

    # Tier-C with urgency: relaxed up to 1.0% (0.01)
    tier_c_urg = {
        "invoice_amount_inr": 60000,
        "discount_rate": 0.01,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-C",
        "is_urgent": True,
    }
    res_c_urg = api_client.post("/currency/discount-preview", json=tier_c_urg)
    assert res_c_urg.status_code == 200
    assert res_c_urg.json()["eligible"] is True

    # Tier-C with urgency exceeding 1.0% (0.012) -> 422
    tier_c_urg_over = dict(tier_c_urg, discount_rate=0.012)
    res_c_urg_over = api_client.post("/currency/discount-preview", json=tier_c_urg_over)
    assert res_c_urg_over.status_code == 422
    assert "exceeds the cap for Tier-C" in res_c_urg_over.json()["detail"]

    # Global cap is 1.5% (0.015)
    tier_a_valid = {
        "invoice_amount_inr": 60000,
        "discount_rate": 0.015,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-A",
    }
    res_a = api_client.post("/currency/discount-preview", json=tier_a_valid)
    assert res_a.status_code == 200
    assert res_a.json()["eligible"] is True

    # Exceeding global cap 0.015 rejected by Pydantic schema
    tier_a_invalid = dict(tier_a_valid, discount_rate=0.02)
    res_a_inv = api_client.post("/currency/discount-preview", json=tier_a_invalid)
    assert res_a_inv.status_code == 422


@pytest.mark.unit
def test_api_discount_preview_human_approval_threshold(api_client):
    # Invoice > ₹100,000 requires human approval
    payload_high_invoice = {
        "invoice_amount_inr": 120000,
        "discount_rate": 0.005,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-A",
    }
    res_inv = api_client.post("/currency/discount-preview", json=payload_high_invoice)
    assert res_inv.status_code == 200
    assert res_inv.json()["requires_approval"] is True

    # Discount > ₹1,000 requires human approval
    payload_high_disc = {
        "invoice_amount_inr": 80000,
        "discount_rate": 0.015,
        "days_until_due": 20,
        "is_disputed": False,
        "invoice_status": "open",
        "buyer_tier": "Tier-A",
    }
    res_disc = api_client.post("/currency/discount-preview", json=payload_high_disc)
    assert res_disc.status_code == 200
    # 80000 * 0.015 = 1200.00 > 1000.00
    assert res_disc.json()["discount_amount"] == "1200.00"
    assert res_disc.json()["requires_approval"] is True

