"""Pure affiliate price calculation models and service boundary."""

from dataclasses import dataclass
from typing import Literal


DiscountType = Literal["percentage", "fixed", "free_participants", "tracking"]
UsageUnit = Literal["booking", "participant"]


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class PricingInput:
    """Request-independent booking prices expressed in whole Hungarian forints."""

    booking_total_huf: int
    participant_prices_huf: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _non_negative_integer(self.booking_total_huf, "booking_total_huf")
        for price in self.participant_prices_huf:
            _non_negative_integer(price, "participant_prices_huf")

    @property
    def participant_count(self) -> int:
        return len(self.participant_prices_huf)


@dataclass(frozen=True)
class RuleInput:
    """Immutable rule snapshot pinned by an attribution."""

    rule_version_id: int
    discount_type: DiscountType
    discount_value: int = 0
    discount_participant_count: int | None = None
    max_discount_amount_huf: int | None = None
    usage_unit: UsageUnit = "booking"

    def __post_init__(self) -> None:
        if (
            isinstance(self.rule_version_id, bool)
            or not isinstance(self.rule_version_id, int)
            or self.rule_version_id <= 0
        ):
            raise ValueError("rule_version_id must be a positive integer")
        if self.discount_type not in {
            "percentage",
            "fixed",
            "free_participants",
            "tracking",
        }:
            raise ValueError("unsupported discount_type")
        _non_negative_integer(self.discount_value, "discount_value")
        if self.discount_type == "percentage" and self.discount_value > 100:
            raise ValueError("percentage discount_value cannot exceed 100")
        if self.discount_participant_count is not None:
            if (
                isinstance(self.discount_participant_count, bool)
                or self.discount_participant_count <= 0
            ):
                raise ValueError("discount_participant_count must be positive")
        if self.max_discount_amount_huf is not None:
            _non_negative_integer(
                self.max_discount_amount_huf, "max_discount_amount_huf"
            )
        if self.usage_unit not in {"booking", "participant"}:
            raise ValueError("unsupported usage_unit")


@dataclass(frozen=True)
class CalculationResult:
    """Deterministic whole-forint result returned to payment integration."""

    rule_version_id: int
    original_total_huf: int
    discount_huf: int
    payable_total_huf: int
    usage_quantity: int
    attribution_retained: bool


class AffiliateCalculationService:
    """Flask-independent calculation entry point."""

    def calculate(self, pricing: PricingInput, rule: RuleInput) -> CalculationResult:
        if rule.discount_type == "percentage":
            discount_huf = (
                pricing.booking_total_huf * rule.discount_value + 50
            ) // 100
        elif rule.discount_type == "fixed":
            discount_huf = rule.discount_value
        elif rule.discount_type == "tracking":
            discount_huf = 0
        else:
            raise NotImplementedError(
                f"discount type {rule.discount_type!r} is not implemented"
            )
        discount_huf = min(discount_huf, pricing.booking_total_huf)
        usage_quantity = 1 if rule.usage_unit == "booking" else pricing.participant_count
        return CalculationResult(
            rule_version_id=rule.rule_version_id,
            original_total_huf=pricing.booking_total_huf,
            discount_huf=discount_huf,
            payable_total_huf=pricing.booking_total_huf - discount_huf,
            usage_quantity=usage_quantity,
            attribution_retained=True,
        )
