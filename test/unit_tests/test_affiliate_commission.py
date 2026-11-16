"""Unit tests for the side-effect-free affiliate commission service."""

import pytest

from flaskr.affiliate_commission import AffiliateCommissionService


@pytest.mark.parametrize(
    ("paid_amount", "percentage", "expected"),
    [
        (0, 25, 0),
        (10_000, 0, 0),
        (10_000, 100, 10_000),
        (1_001, 33, 330),
        (49, 1, 0),
        (50, 1, 1),
    ],
)
def test_percentage_uses_paid_amount_and_rounds_half_up(
    paid_amount, percentage, expected
):
    amount = AffiliateCommissionService().calculate(
        paid_amount_huf=paid_amount,
        commission_type="percentage",
        commission_value=percentage,
    )

    assert amount == expected


def test_fixed_is_per_booking_and_none_is_zero():
    service = AffiliateCommissionService()

    assert service.calculate(
        paid_amount_huf=1, commission_type="fixed", commission_value=2_500
    ) == 2_500
    assert service.calculate(
        paid_amount_huf=100_000, commission_type="none", commission_value=9_999
    ) == 0


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"paid_amount_huf": -1}, "paid_amount_huf"),
        ({"paid_amount_huf": True}, "paid_amount_huf"),
        ({"paid_amount_huf": 1.5}, "paid_amount_huf"),
        ({"commission_value": -1}, "commission_value"),
        ({"commission_value": True}, "commission_value"),
        ({"commission_value": 1.5}, "commission_value"),
        ({"commission_type": "percentage", "commission_value": 101}, "exceed 100"),
        ({"commission_type": "unknown"}, "unsupported commission_type"),
    ],
)
def test_invalid_commission_inputs_fail_closed(values, message):
    inputs = {
        "paid_amount_huf": 10_000,
        "commission_type": "fixed",
        "commission_value": 1_000,
    }
    inputs.update(values)

    with pytest.raises(ValueError, match=message):
        AffiliateCommissionService().calculate(**inputs)
