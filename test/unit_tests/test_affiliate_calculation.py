"""Unit coverage for the pure affiliate calculation boundary."""

from datetime import datetime, timezone

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
            commission_type="percentage",
            commission_value=12,
        ),
    )

    assert result.rule_version_id == 42
    assert result.original_total_huf == 27_500
    assert result.discount_huf == 0
    assert result.payable_total_huf == 27_500
    assert result.usage_quantity == 2
    assert result.attribution_retained is True
    assert result.commission_type == "percentage"
    assert result.commission_value == 12


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


def test_free_participant_discount_uses_lowest_prices_independent_of_order():
    service = AffiliateCalculationService()
    rule = RuleInput(
        rule_version_id=3,
        discount_type="free_participants",
        discount_participant_count=2,
    )

    first = service.calculate(
        PricingInput(
            booking_total_huf=35_000,
            participant_prices_huf=(15_000, 8_000, 12_000),
        ),
        rule,
    )
    reordered = service.calculate(
        PricingInput(
            booking_total_huf=35_000,
            participant_prices_huf=(12_000, 15_000, 8_000),
        ),
        rule,
    )

    assert first.discount_huf == reordered.discount_huf == 20_000
    assert first.payable_total_huf == reordered.payable_total_huf == 15_000


def test_free_participant_discount_cannot_exceed_available_people_or_total():
    result = AffiliateCalculationService().calculate(
        PricingInput(
            booking_total_huf=10_000,
            participant_prices_huf=(8_000, 7_000),
        ),
        RuleInput(
            rule_version_id=4,
            discount_type="free_participants",
            discount_participant_count=5,
        ),
    )

    assert result.discount_huf == 10_000
    assert result.payable_total_huf == 0


def test_free_participant_rule_requires_positive_count():
    with pytest.raises(ValueError, match="requires discount_participant_count"):
        RuleInput(rule_version_id=5, discount_type="free_participants")


def test_tracking_rule_keeps_fixed_commission_without_discount():
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=18_000),
        RuleInput(
            rule_version_id=6,
            discount_type="tracking",
            commission_type="fixed",
            commission_value=2_500,
        ),
    )

    assert result.discount_huf == 0
    assert result.payable_total_huf == 18_000
    assert result.attribution_retained is True
    assert result.commission_type == "fixed"
    assert result.commission_value == 2_500


@pytest.mark.parametrize(
    ("scope_type", "scope_ids", "tour_id", "location_id", "reason"),
    [
        ("tour", frozenset({10, 11}), 12, 5, "tour_scope"),
        ("location", frozenset({5}), 12, 6, "location_scope"),
    ],
)
def test_out_of_scope_booking_gets_no_benefit_or_usage(
    scope_type, scope_ids, tour_id, location_id, reason
):
    result = AffiliateCalculationService().calculate(
        PricingInput(
            booking_total_huf=20_000,
            tour_id=tour_id,
            location_id=location_id,
        ),
        RuleInput(
            rule_version_id=7,
            discount_type="fixed",
            discount_value=3_000,
            commission_type="percentage",
            commission_value=10,
            scope_type=scope_type,
            scope_ids=scope_ids,
        ),
    )

    assert result.is_eligible is False
    assert result.ineligibility_reason == reason
    assert result.discount_huf == 0
    assert result.payable_total_huf == 20_000
    assert result.usage_quantity == 0
    assert result.attribution_retained is False
    assert result.commission_type == "none"


@pytest.mark.parametrize(
    ("booking_at", "reason"),
    [
        (datetime(2026, 4, 30, 23, 59, tzinfo=timezone.utc), "before_validity"),
        (datetime(2026, 6, 1, 0, 1, tzinfo=timezone.utc), "after_validity"),
    ],
)
def test_booking_outside_rule_validity_gets_no_discount(booking_at, reason):
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=10_000, booking_at=booking_at),
        RuleInput(
            rule_version_id=8,
            discount_type="percentage",
            discount_value=10,
            valid_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
            valid_until=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
    )

    assert result.is_eligible is False
    assert result.ineligibility_reason == reason
    assert result.discount_huf == 0


def test_matching_scope_and_validity_apply_discount():
    result = AffiliateCalculationService().calculate(
        PricingInput(
            booking_total_huf=10_000,
            tour_id=10,
            booking_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
        ),
        RuleInput(
            rule_version_id=9,
            discount_type="percentage",
            discount_value=10,
            scope_type="tour",
            scope_ids=frozenset({10, 11}),
            valid_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
            valid_until=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
    )

    assert result.is_eligible is True
    assert result.discount_huf == 1_000
    assert result.usage_quantity == 1


@pytest.mark.parametrize(
    ("total", "percentage", "expected"),
    [
        (4, 10, 0),
        (5, 10, 1),
        (14, 10, 1),
        (15, 10, 2),
    ],
)
def test_percentage_rounds_half_forints_up(total, percentage, expected):
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=total),
        RuleInput(
            rule_version_id=10,
            discount_type="percentage",
            discount_value=percentage,
        ),
    )

    assert result.discount_huf == expected


@pytest.mark.parametrize(
    ("rule", "pricing"),
    [
        (
            RuleInput(
                rule_version_id=11,
                discount_type="percentage",
                discount_value=50,
                max_discount_amount_huf=3_000,
            ),
            PricingInput(booking_total_huf=10_000),
        ),
        (
            RuleInput(
                rule_version_id=12,
                discount_type="fixed",
                discount_value=5_000,
                max_discount_amount_huf=3_000,
            ),
            PricingInput(booking_total_huf=10_000),
        ),
        (
            RuleInput(
                rule_version_id=13,
                discount_type="free_participants",
                discount_participant_count=2,
                max_discount_amount_huf=3_000,
            ),
            PricingInput(
                booking_total_huf=10_000,
                participant_prices_huf=(4_000, 6_000),
            ),
        ),
    ],
)
def test_discount_cap_applies_to_every_monetary_discount(rule, pricing):
    result = AffiliateCalculationService().calculate(pricing, rule)

    assert result.discount_huf == 3_000
    assert result.payable_total_huf == 7_000
