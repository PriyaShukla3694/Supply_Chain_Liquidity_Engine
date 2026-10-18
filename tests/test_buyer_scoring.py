
import pytest

from app.services.buyer_scoring import (
    calculate_reliability_score,
    calculate_financial_score,
    calculate_liquidity_score,
    calculate_overall_score,
    assign_tier,
    calculate_buyer_payment_metrics,
)


@pytest.mark.unit
def test_reliability_score():
    score = calculate_reliability_score(
        late_rate=0.20,
        avg_days_late=3,
        late_rate_last_5_settled=0.20,
    )

    # 50*(1-.20) + 25*(1-3/15) + 25*(1-.20)
    assert score == pytest.approx(80.0)


@pytest.mark.unit
def test_financial_score():
    score = calculate_financial_score(
        open_exposure=20000,
        credit_limit=100000,
    )

    assert score == pytest.approx(80.0)


@pytest.mark.unit
def test_liquidity_score():
    score = calculate_liquidity_score(
        overdue_open_exposure=20000,
        open_exposure=100000,
    )

    assert score == pytest.approx(80.0)


@pytest.mark.unit
def test_liquidity_score_when_no_open_exposure():
    assert calculate_liquidity_score(
        overdue_open_exposure=0,
        open_exposure=0,
    ) == pytest.approx(100.0)


@pytest.mark.unit
def test_overall_score_uses_80_10_10_weights():
    score = calculate_overall_score(
        reliability=80,
        financial=60,
        liquidity=100,
    )

    assert score == pytest.approx(80.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "expected_tier"),
    [
        (80, "A"),
        (79.99, "B"),
        (50, "B"),
        (49.99, "C"),
    ],
)
def test_assign_tier(score, expected_tier):
    assert assign_tier(score) == expected_tier


@pytest.mark.unit
def test_buyer_payment_metrics_with_no_settled_invoices():
    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return []

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    metrics = calculate_buyer_payment_metrics(
        FakeDB(),
        "BUYER-1",
    )

    assert metrics["resolved_invoice_count"] == 0
    assert metrics["late_rate"] == 0.0
    assert metrics["avg_days_late"] == 0.0
    assert metrics["late_rate_last_5_settled"] == 0.0
