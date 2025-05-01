"""Basic tests for *economic_accessibility* utilities (Step 6.1)."""

from pathlib import Path

from src.economic_accessibility import (
    EconomicAccessibilityStore,
    PricingTierEntry,
    DiscountEntry,
)


def test_aggregate_empty(tmp_path: Path) -> None:
    """Aggregating an empty store should return zeroed statistics."""

    store_file = tmp_path / "ea.jsonl"
    store = EconomicAccessibilityStore(store_file)

    stats = store.aggregate()
    assert stats["tiers"] == 0
    assert stats["discounts"] == 0
    assert stats["average_monthly_cost_usd"] == 0.0
    assert stats["average_discount_pct"] == 0.0
    assert stats["accessibility_score"] == 0.0


def test_basic_scoring(tmp_path: Path) -> None:
    """Verify score calculation with sample tier & discount."""

    store_file = tmp_path / "ea.jsonl"
    store = EconomicAccessibilityStore(store_file)

    store.append(PricingTierEntry(name="Free", monthly_cost=0.0, platform="All"))
    store.append(PricingTierEntry(name="Pro", monthly_cost=10.0, platform="All"))
    store.append(DiscountEntry(category="student", percent=50, eligibility="Valid .edu email"))

    stats = store.aggregate()

    # With 2 tiers ($0 + $10 → avg $5). Price component ~1 - 5/50 = 0.9 → 63
    expected_price_component = (1 - (5 / 50)) * 70  # 63
    expected_discount_component = (50 / 100) * 30  # 15
    expected_score = round(expected_price_component + expected_discount_component, 2)

    assert stats["tiers"] == 2
    assert stats["discounts"] == 1
    assert stats["average_monthly_cost_usd"] == 5.0
    assert stats["average_discount_pct"] == 50.0
    assert stats["accessibility_score"] == expected_score