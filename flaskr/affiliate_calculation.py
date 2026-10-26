"""Pure affiliate price calculation models and service boundary."""

import hashlib
import re
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


def derive_guest_key(*, email: str | None = None, phone: str | None = None) -> str:
    """Derive a stable privacy-preserving key from normalized guest identity."""
    normalized_email = (email or "").strip().casefold()
    normalized_phone = re.sub(r"\D", "", phone or "")
    if not normalized_email and not normalized_phone:
        raise ValueError("email or phone is required to derive guest key")
    source = f"guest-key-v1\0{normalized_email}\0{normalized_phone}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PricingInput:
    """Request-independent booking prices expressed in whole Hungarian forints."""

    booking_total_huf: int
    participant_prices_huf: tuple[int, ...] = ()
    tour_id: int | None = None
    location_id: int | None = None
    booking_at: datetime | None = None
    guest_key: str | None = None

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
        if self.guest_key is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.guest_key
        ):
            raise ValueError("guest_key must be a SHA-256 hex digest")

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
    total_usage_limit: int | None = None
    guest_usage_limit: int | None = None

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
        for value, field_name in (
            (self.total_usage_limit, "total_usage_limit"),
            (self.guest_usage_limit, "guest_usage_limit"),
        ):
            if value is not None:
                _non_negative_integer(value, field_name)


@dataclass(frozen=True)
class UsageSnapshot:
    """Already consumed units for the resolved budget period and guest."""

    total_used: int = 0
    guest_used: int = 0

    def __post_init__(self) -> None:
        _non_negative_integer(self.total_used, "total_used")
        _non_negative_integer(self.guest_used, "guest_used")


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


def _percentage_huf(total_huf: int, percentage: int) -> int:
    """Round positive percentage results to the nearest forint, halves upward."""
    return (total_huf * percentage + 50) // 100


class AffiliateCalculationService:
    """Flask-independent calculation entry point."""

    def calculate(
        self,
        pricing: PricingInput,
        rule: RuleInput,
        usage: UsageSnapshot | None = None,
    ) -> CalculationResult:
        reason = _ineligibility_reason(pricing, rule)
        usage = usage or UsageSnapshot()
        usage_quantity = 1 if rule.usage_unit == "booking" else pricing.participant_count
        if (
            reason is None
            and rule.total_usage_limit is not None
            and usage.total_used + usage_quantity > rule.total_usage_limit
        ):
            reason = "total_usage_limit"
        if reason is None and rule.guest_usage_limit is not None:
            if pricing.guest_key is None:
                reason = "missing_guest_key"
            elif usage.guest_used + usage_quantity > rule.guest_usage_limit:
                reason = "guest_usage_limit"
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
            discount_huf = _percentage_huf(
                pricing.booking_total_huf, rule.discount_value
            )
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
        if rule.max_discount_amount_huf is not None:
            discount_huf = min(discount_huf, rule.max_discount_amount_huf)
        discount_huf = min(discount_huf, pricing.booking_total_huf)
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
