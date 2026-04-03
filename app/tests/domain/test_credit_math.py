import pytest
from decimal import Decimal
from app.core.config import settings

def calculate_credits(naira_amount: float, exchange_rate: float) -> float:
    """Business logic for credit calculation (extracted from payment_service)"""
    return naira_amount / exchange_rate

def calculate_cost_with_markup(base_cost: Decimal, markup_percent: int) -> Decimal:
    """Business logic for markup calculation (extracted from requesty_ai)"""
    markup_multiplier = Decimal("1.0") + (Decimal(str(markup_percent)) / Decimal("100.0"))
    return (base_cost * markup_multiplier).quantize(Decimal("0.000001"))

def test_naira_to_credit_conversion():
    """Test standard conversion: ₦1650 = 1 AI Credit"""
    rate = 1650.0
    # ₦16,500 should be 10 credits
    assert calculate_credits(16500.0, rate) == 10.0
    # Smallest topup ₦100
    assert calculate_credits(100.0, rate) == pytest.approx(0.060606, 0.0001)

def test_markup_calculation():
    """Test applying 15% platform markup to AI costs"""
    base = Decimal("0.100000") # $0.10 base cost
    markup = 15 # 15%
    # $0.10 * 1.15 = $0.115
    result = calculate_cost_with_markup(base, markup)
    assert result == Decimal("0.115000")

def test_markup_zero():
    """Test 0% markup (cost unchanged)"""
    base = Decimal("1.234567")
    assert calculate_cost_with_markup(base, 0) == base.quantize(Decimal("0.000001"))

def test_markup_high():
    """Test high markup (e.g. 100%)"""
    base = Decimal("1.0")
    assert calculate_cost_with_markup(base, 100) == Decimal("2.000000")
