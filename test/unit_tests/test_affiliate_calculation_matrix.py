"""Cross-product and invalid-configuration matrix for affiliate calculations."""

from datetime import datetime, timezone

import pytest

from flaskr.affiliate_calculation import (
    AffiliateCalculationService,
    PricingInput,
    RuleInput,
    UsageSnapshot,
    derive_guest_key,
    resolve_budget_period,
)


@pytest.mark.parametrize(
    ("discount_type", "rule_values", "expected_discount"),
    [
        ("percentage", {"discount_value": 10}, 3_000),
        ("fixed", {"discount_value": 4_000}, 4_000),
        ("free_participants", {"discount_participant_count": 2}, 20_000),
        ("tracking", {}, 0),
    ],
)
@pytest.mark.parametrize(
    ("usage_unit", "expected_quantity"),
    [("booking", 1), ("participant", 3)],
)
def test_discount_type_and_usage_mode_cross_product(
    discount_type,
    rule_values,
    expected_discount,
    usage_unit,
    expected_quantity,
):
    result = AffiliateCalculationService().calculate(
        PricingInput(
            booking_total_huf=30_000,
            participant_prices_huf=(10_000, 10_000, 10_000),
            booked_participants=3,
        ),
        RuleInput(
            rule_version_id=100,
            discount_type=discount_type,
            usage_unit=usage_unit,
            commission_type="percentage",
            commission_value=8,
            **rule_values,
        ),
    )

    assert result.is_eligible is True
    assert result.discount_huf == expected_discount
    assert result.payable_total_huf == 30_000 - expected_discount
    assert result.usage_quantity == expected_quantity
    assert result.commission_type == "percentage"
    assert result.commission_value == 8


@pytest.mark.parametrize(
    ("scope_type", "scope_ids"),
    [
        ("all", frozenset()),
        ("tour", frozenset({40})),
        ("location", frozenset({7})),
    ],
)
def test_every_scope_mode_accepts_matching_booking(scope_type, scope_ids):
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=12_000, tour_id=40, location_id=7),
        RuleInput(
            rule_version_id=101,
            discount_type="fixed",
            discount_value=1_000,
            scope_type=scope_type,
            scope_ids=scope_ids,
        ),
    )

    assert result.is_eligible is True
    assert result.discount_huf == 1_000


def test_combined_limits_accept_exact_boundary_then_close():
    guest_key = derive_guest_key(phone="+36 30 111 2233")
    pricing = PricingInput(
        booking_total_huf=30_000,
        booked_participants=3,
        guest_key=guest_key,
    )
    rule = RuleInput(
        rule_version_id=102,
        discount_type="percentage",
        discount_value=10,
        usage_unit="participant",
        total_usage_limit=10,
        guest_usage_limit=5,
    )
    service = AffiliateCalculationService()

    boundary = service.calculate(
        pricing,
        rule,
        UsageSnapshot(total_used=7, guest_used=2),
    )
    total_closed = service.calculate(
        pricing,
        rule,
        UsageSnapshot(total_used=8, guest_used=2),
    )
    guest_closed = service.calculate(
        pricing,
        rule,
        UsageSnapshot(total_used=7, guest_used=3),
    )

    assert boundary.is_eligible is True
    assert total_closed.ineligibility_reason == "total_usage_limit"
    assert guest_closed.ineligibility_reason == "guest_usage_limit"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"rule_version_id": 0}, "positive integer"),
        ({"discount_type": "unknown"}, "unsupported discount_type"),
        ({"discount_value": -1}, "non-negative integer"),
        ({"discount_type": "percentage", "discount_value": 101}, "exceed 100"),
        ({"discount_type": "free_participants"}, "requires"),
        ({"max_discount_amount_huf": -1}, "non-negative integer"),
        ({"usage_unit": "unknown"}, "unsupported usage_unit"),
        ({"commission_type": "unknown"}, "unsupported commission_type"),
        ({"commission_type": "percentage", "commission_value": 101}, "exceed 100"),
        ({"scope_type": "tour"}, "require scope_ids"),
        ({"total_usage_limit": -1}, "non-negative integer"),
        ({"guest_usage_limit": -1}, "non-negative integer"),
        ({"budget_period_type": "unknown"}, "unsupported budget_period_type"),
        ({"budget_period_type": "manual"}, "requires start and end"),
    ],
)
def test_invalid_rule_configuration_matrix(overrides, message):
    values = {"rule_version_id": 1, "discount_type": "tracking"}
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        RuleInput(**values)


def test_invalid_time_windows_and_missing_period_reference_are_rejected():
    with pytest.raises(ValueError, match="cannot precede"):
        RuleInput(
            rule_version_id=103,
            discount_type="tracking",
            valid_from=datetime(2026, 2, 1, tzinfo=timezone.utc),
            valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="end must follow start"):
        RuleInput(
            rule_version_id=104,
            discount_type="tracking",
            budget_period_type="manual",
            manual_period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            manual_period_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="require a reference time"):
        resolve_budget_period(
            RuleInput(
                rule_version_id=105,
                discount_type="tracking",
                budget_period_type="monthly",
            ),
            None,
        )
