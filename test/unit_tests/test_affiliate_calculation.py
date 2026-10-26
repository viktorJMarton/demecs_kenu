"""Unit coverage for the pure affiliate calculation boundary."""

import pytest

from flaskr.affiliate_calculation import (
    AffiliateCalculationService,
    PricingInput,
    RuleInput,
)


def test_tracking_rule_is_calculated_without_flask_request_context():
    result = AffiliateCalculationService().calculate(
        PricingInput(
            booking_total_huf=27_500,
            participant_prices_huf=(12_500, 15_000),
        ),
        RuleInput(
            rule_version_id=42,
            discount_type="tracking",
            usage_unit="participant",
        ),
    )

    assert result.rule_version_id == 42
    assert result.original_total_huf == 27_500
    assert result.discount_huf == 0
    assert result.payable_total_huf == 27_500
    assert result.usage_quantity == 2
    assert result.attribution_retained is True


@pytest.mark.parametrize("invalid_total", [-1, 12.5, True])
def test_money_requires_non_negative_whole_forints(invalid_total):
    with pytest.raises(ValueError, match="booking_total_huf"):
        PricingInput(booking_total_huf=invalid_total)


@pytest.mark.parametrize(
    ("discount_type", "value", "total", "expected_discount", "expected_payable"),
    [
        ("percentage", 10, 27_500, 2_750, 24_750),
        ("percentage", 33, 1_001, 330, 671),
        ("percentage", 100, 8_500, 8_500, 0),
        ("fixed", 2_000, 8_500, 2_000, 6_500),
        ("fixed", 20_000, 8_500, 8_500, 0),
    ],
)
def test_percentage_and_fixed_discounts_are_whole_forints_and_never_negative(
    discount_type, value, total, expected_discount, expected_payable
):
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=total),
        RuleInput(
            rule_version_id=1,
            discount_type=discount_type,
            discount_value=value,
        ),
    )

    assert result.discount_huf == expected_discount
    assert result.payable_total_huf == expected_payable


def test_percentage_cannot_exceed_full_booking_value():
    with pytest.raises(ValueError, match="cannot exceed 100"):
        RuleInput(rule_version_id=1, discount_type="percentage", discount_value=101)
