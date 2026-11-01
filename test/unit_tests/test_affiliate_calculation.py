"""Unit coverage for the pure affiliate calculation boundary."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from flaskr.affiliate_calculation import (
    AffiliateCalculationService,
    PricingInput,
    RuleInput,
    UsageSnapshot,
    derive_guest_key,
    normalize_guest_email,
    resolve_budget_period,
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


def test_guest_key_is_normalized_stable_and_contains_no_raw_identity():
    first = derive_guest_key(email="  TESZT.ELEK@Example.HU ", phone="+36 30 123-4567")
    second = derive_guest_key(email="teszt.elek@example.hu", phone="36301234567")

    assert first == second
    assert len(first) == 64
    assert "teszt" not in first
    assert "1234567" not in first


def test_guest_email_normalization_handles_unicode_case_space_and_idn():
    first = normalize_guest_email("  TÉSZT@MÜNCHEN.example. ")
    second = normalize_guest_email("te\u0301szt@xn--mnchen-3ya.example")

    assert first == second == "tészt@xn--mnchen-3ya.example"
    assert derive_guest_key(email=first) == derive_guest_key(email=second)


@pytest.mark.parametrize(
    "invalid_email",
    ["", "missing-at", "two@@example.test", "space @example.test", "a@"],
)
def test_invalid_guest_email_is_rejected(invalid_email):
    with pytest.raises(ValueError, match="guest email is invalid"):
        normalize_guest_email(invalid_email)


def test_usage_limit_allows_exact_boundary_and_closes_after_it():
    rule = RuleInput(
        rule_version_id=14,
        discount_type="fixed",
        discount_value=1_000,
        total_usage_limit=5,
    )
    service = AffiliateCalculationService()

    boundary = service.calculate(
        PricingInput(booking_total_huf=10_000),
        rule,
        UsageSnapshot(total_used=4),
    )
    exceeded = service.calculate(
        PricingInput(booking_total_huf=10_000),
        rule,
        UsageSnapshot(total_used=5),
    )

    assert boundary.is_eligible is True
    assert boundary.usage_quantity == 1
    assert exceeded.is_eligible is False
    assert exceeded.ineligibility_reason == "total_usage_limit"
    assert exceeded.discount_huf == 0


def test_guest_limit_uses_derived_key_and_participant_quantity():
    guest_key = derive_guest_key(email="guest@example.test")
    rule = RuleInput(
        rule_version_id=15,
        discount_type="percentage",
        discount_value=10,
        usage_unit="participant",
        guest_usage_limit=4,
    )
    pricing = PricingInput(
        booking_total_huf=20_000,
        participant_prices_huf=(10_000, 10_000),
        guest_key=guest_key,
    )

    boundary = AffiliateCalculationService().calculate(
        pricing, rule, UsageSnapshot(guest_used=2)
    )
    exceeded = AffiliateCalculationService().calculate(
        pricing, rule, UsageSnapshot(guest_used=3)
    )

    assert boundary.is_eligible is True
    assert boundary.usage_quantity == 2
    assert exceeded.is_eligible is False
    assert exceeded.ineligibility_reason == "guest_usage_limit"


def test_guest_limit_fails_closed_without_guest_key():
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=10_000),
        RuleInput(
            rule_version_id=16,
            discount_type="tracking",
            guest_usage_limit=1,
        ),
    )

    assert result.is_eligible is False
    assert result.ineligibility_reason == "missing_guest_key"


def test_booking_and_participant_usage_modes_return_exact_quantities():
    pricing = PricingInput(
        booking_total_huf=40_000,
        booked_participants=4,
    )
    service = AffiliateCalculationService()

    booking = service.calculate(
        pricing,
        RuleInput(
            rule_version_id=17,
            discount_type="tracking",
            usage_unit="booking",
        ),
    )
    participants = service.calculate(
        pricing,
        RuleInput(
            rule_version_id=18,
            discount_type="tracking",
            usage_unit="participant",
        ),
    )

    assert booking.usage_quantity == 1
    assert participants.usage_quantity == 4


def test_participant_usage_fails_closed_without_booked_quantity():
    result = AffiliateCalculationService().calculate(
        PricingInput(booking_total_huf=10_000),
        RuleInput(
            rule_version_id=19,
            discount_type="tracking",
            usage_unit="participant",
        ),
    )

    assert result.is_eligible is False
    assert result.ineligibility_reason == "missing_participants"
    assert result.usage_quantity == 0


def test_explicit_participant_quantity_must_match_price_breakdown():
    with pytest.raises(ValueError, match="must match participant prices"):
        PricingInput(
            booking_total_huf=20_000,
            participant_prices_huf=(10_000, 10_000),
            booked_participants=3,
        )


def test_lifetime_and_manual_budget_period_resolution():
    lifetime = resolve_budget_period(
        RuleInput(rule_version_id=20, discount_type="tracking"),
        datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    manual = resolve_budget_period(
        RuleInput(
            rule_version_id=21,
            discount_type="tracking",
            budget_period_type="manual",
            manual_period_start=datetime(2026, 3, 1, 8, tzinfo=timezone.utc),
            manual_period_end=datetime(2026, 4, 1, 8, tzinfo=timezone.utc),
        ),
        None,
    )

    assert lifetime.starts_at is None and lifetime.ends_at is None
    assert manual.starts_at == datetime(2026, 3, 1, 8, tzinfo=timezone.utc)
    assert manual.ends_at == datetime(2026, 4, 1, 8, tzinfo=timezone.utc)


def test_monthly_period_observes_budapest_dst_boundary():
    period = resolve_budget_period(
        RuleInput(
            rule_version_id=22,
            discount_type="tracking",
            budget_period_type="monthly",
        ),
        datetime(2026, 10, 27, tzinfo=timezone.utc),
        ZoneInfo("Europe/Budapest"),
    )

    assert period.starts_at == datetime(2026, 9, 30, 22, tzinfo=timezone.utc)
    assert period.ends_at == datetime(2026, 10, 31, 23, tzinfo=timezone.utc)


def test_monthly_december_and_yearly_period_cross_year_boundaries():
    rule = RuleInput(
        rule_version_id=23,
        discount_type="tracking",
        budget_period_type="monthly",
    )
    monthly = resolve_budget_period(
        rule,
        datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc),
        timezone.utc,
    )
    yearly = resolve_budget_period(
        RuleInput(
            rule_version_id=24,
            discount_type="tracking",
            budget_period_type="yearly",
        ),
        datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc),
        timezone.utc,
    )

    assert monthly.starts_at == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert monthly.ends_at == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert yearly.starts_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert yearly.ends_at == datetime(2027, 1, 1, tzinfo=timezone.utc)
