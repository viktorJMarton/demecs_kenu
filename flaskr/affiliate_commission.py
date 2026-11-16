"""Pure affiliate commission calculation in whole Hungarian forints.

Percentage commission uses the post-discount amount actually payable by the
guest. Fractional forints are rounded to the nearest whole forint with exact
halves rounded upward. Fixed commission is a per-booking amount and therefore
does not depend on the payable amount. This module calculates values only; it
never initiates a payment or settlement.
"""

from __future__ import annotations

from typing import Literal


CommissionType = Literal["none", "percentage", "fixed"]


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


class AffiliateCommissionService:
    """Calculate a deterministic commission amount without side effects."""

    def calculate(
        self,
        *,
        paid_amount_huf: int,
        commission_type: CommissionType,
        commission_value: int,
    ) -> int:
        paid_amount_huf = _non_negative_integer(
            paid_amount_huf, "paid_amount_huf"
        )
        commission_value = _non_negative_integer(
            commission_value, "commission_value"
        )
        if commission_type == "none":
            return 0
        if commission_type == "fixed":
            return commission_value
        if commission_type == "percentage":
            if commission_value > 100:
                raise ValueError("percentage commission_value cannot exceed 100")
            return (paid_amount_huf * commission_value + 50) // 100
        raise ValueError("unsupported commission_type")
