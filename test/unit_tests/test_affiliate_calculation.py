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


def test_unsupported_discount_calculation_is_explicit():
    with pytest.raises(NotImplementedError, match="percentage"):
        AffiliateCalculationService().calculate(
            PricingInput(booking_total_huf=10_000),
            RuleInput(rule_version_id=1, discount_type="percentage", discount_value=10),
        )
