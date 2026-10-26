"""Pure affiliate price calculation models and service boundary."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


DiscountType = Literal["percentage", "fixed", "free_participants", "tracking"]
UsageUnit = Literal["booking", "participant"]
CommissionType = Literal["none", "percentage", "fixed"]
ScopeType = Literal["all", "tour", "location"]


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class PricingInput:
    """Request-independent booking prices expressed in whole Hungarian forints."""

    booking_total_huf: int
    participant_prices_huf: tuple[int, ...] = ()
    tour_id: int | None = None
    location_id: int | None = None
    booking_at: datetime | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.booking_total_huf, "booking_total_huf")
        for price in self.participant_prices_huf:
            _non_negative_integer(price, "participant_prices_huf")
        for value, field_name in (
            (self.tour_id, "tour_id"),
            (self.location_id, "location_id"),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"{field_name} must be a positive integer")

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
    commission_type: CommissionType = "none"
    commission_value: int = 0
    scope_type: ScopeType = "all"
    scope_ids: frozenset[int] = frozenset()
    valid_from: datetime | None = None
    valid_until: datetime | None = None

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
        if (
            self.discount_type == "free_participants"
            and self.discount_participant_count is None
        ):
            raise ValueError(
                "free_participants requires discount_participant_count"
            )
        if self.max_discount_amount_huf is not None:
            _non_negative_integer(
                self.max_discount_amount_huf, "max_discount_amount_huf"
            )
        if self.usage_unit not in {"booking", "participant"}:
            raise ValueError("unsupported usage_unit")
        if self.commission_type not in {"none", "percentage", "fixed"}:
            raise ValueError("unsupported commission_type")
        _non_negative_integer(self.commission_value, "commission_value")
        if self.commission_type == "percentage" and self.commission_value > 100:
            raise ValueError("percentage commission_value cannot exceed 100")
        if self.scope_type not in {"all", "tour", "location"}:
            raise ValueError("unsupported scope_type")
        if self.scope_type != "all" and not self.scope_ids:
            raise ValueError("scoped rules require scope_ids")
        if any(
            isinstance(scope_id, bool)
            or not isinstance(scope_id, int)
            or scope_id <= 0
            for scope_id in self.scope_ids
        ):
            raise ValueError("scope_ids must contain positive integers")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and _as_utc(self.valid_until) < _as_utc(self.valid_from)
        ):
            raise ValueError("valid_until cannot precede valid_from")


@dataclass(frozen=True)
class CalculationResult:
    """Deterministic whole-forint result returned to payment integration."""

    rule_version_id: int
    original_total_huf: int
    discount_huf: int
    payable_total_huf: int
    usage_quantity: int
    attribution_retained: bool
    commission_type: CommissionType
    commission_value: int
    is_eligible: bool = True
    ineligibility_reason: str | None = None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ineligibility_reason(pricing: PricingInput, rule: RuleInput) -> str | None:
    if (
        pricing.booking_at is None
        and (rule.valid_from is not None or rule.valid_until is not None)
    ):
        return "missing_booking_time"
    if pricing.booking_at is not None:
        booking_at = _as_utc(pricing.booking_at)
        if rule.valid_from is not None and booking_at < _as_utc(rule.valid_from):
            return "before_validity"
        if rule.valid_until is not None and booking_at > _as_utc(rule.valid_until):
            return "after_validity"
    if rule.scope_type == "tour" and pricing.tour_id not in rule.scope_ids:
        return "tour_scope"
    if rule.scope_type == "location" and pricing.location_id not in rule.scope_ids:
        return "location_scope"
    return None


class AffiliateCalculationService:
    """Flask-independent calculation entry point."""

    def calculate(self, pricing: PricingInput, rule: RuleInput) -> CalculationResult:
        reason = _ineligibility_reason(pricing, rule)
        if reason is not None:
            return CalculationResult(
                rule_version_id=rule.rule_version_id,
                original_total_huf=pricing.booking_total_huf,
                discount_huf=0,
                payable_total_huf=pricing.booking_total_huf,
                usage_quantity=0,
                attribution_retained=False,
                commission_type="none",
                commission_value=0,
                is_eligible=False,
                ineligibility_reason=reason,
            )
        if rule.discount_type == "percentage":
            discount_huf = (
                pricing.booking_total_huf * rule.discount_value + 50
            ) // 100
        elif rule.discount_type == "fixed":
            discount_huf = rule.discount_value
        elif rule.discount_type == "free_participants":
            free_count = min(
                rule.discount_participant_count or 0,
                pricing.participant_count,
            )
            discount_huf = sum(sorted(pricing.participant_prices_huf)[:free_count])
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
            commission_type=rule.commission_type,
            commission_value=rule.commission_value,
        )
