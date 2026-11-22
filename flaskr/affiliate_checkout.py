"""Server-authoritative affiliate revalidation for checkout."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from .affiliate_calculation import (
    AffiliateCalculationService,
    BudgetPeriod,
    CalculationResult,
    PricingInput,
    RuleInput,
    UsageSnapshot,
    resolve_budget_period,
)
from .affiliate_commission import AffiliateCommissionService
from .affiliate_usage import RESERVATION_WINDOW


class AffiliateCheckoutConfigurationError(ValueError):
    """Raised when a persisted affiliate rule cannot be evaluated safely."""


@dataclass(frozen=True)
class CheckoutAffiliateCalculation:
    rule: RuleInput
    result: CalculationResult
    budget_period_id: int | None
    budget_period: BudgetPeriod
    commission_amount_huf: int


def _datetime_value(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _load_scope(db, rule_version_id: int) -> tuple[str, frozenset[int]]:
    rows = db.execute(
        """
        SELECT scope_type, tour_id, tour_location_id
          FROM affiliate_rule_scopes
         WHERE rule_version_id = ?
         ORDER BY id
        """,
        (rule_version_id,),
    ).fetchall()
    scope_types = {row["scope_type"] for row in rows}
    if len(scope_types) != 1:
        raise AffiliateCheckoutConfigurationError("rule must have one scope mode")
    scope_type = scope_types.pop()
    if scope_type == "all":
        if len(rows) != 1:
            raise AffiliateCheckoutConfigurationError("all scope must have one row")
        return "all", frozenset()
    field = "tour_id" if scope_type == "tour" else "tour_location_id"
    scope_ids = frozenset(row[field] for row in rows if row[field] is not None)
    if not scope_ids:
        raise AffiliateCheckoutConfigurationError("scoped rule has no targets")
    return scope_type, scope_ids


def _manual_period(db, rule_row, at: datetime) -> tuple[BudgetPeriod, int]:
    at_sql = at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        """
        SELECT id, starts_at, ends_at
          FROM affiliate_budget_periods
         WHERE rule_version_id = ? AND status = 'open'
           AND (starts_at IS NULL OR starts_at <= ?)
           AND (ends_at IS NULL OR ends_at > ?)
         ORDER BY starts_at DESC, id DESC
         LIMIT 1
        """,
        (rule_row["id"], at_sql, at_sql),
    ).fetchone()
    if row is None or row["starts_at"] is None or row["ends_at"] is None:
        raise AffiliateCheckoutConfigurationError("manual budget period is unavailable")
    return (
        BudgetPeriod(_datetime_value(row["starts_at"]), _datetime_value(row["ends_at"])),
        row["id"],
    )


def _period_id(db, rule: RuleInput, period: BudgetPeriod) -> int | None:
    if period.starts_at is None and period.ends_at is None:
        return None
    rows = db.execute(
        """
        SELECT id, CAST(starts_at AS TEXT) AS starts_at, CAST(ends_at AS TEXT) AS ends_at
          FROM affiliate_budget_periods
         WHERE rule_version_id = ?
        """,
        (rule.rule_version_id,),
    ).fetchall()
    period_id = None
    for row in rows:
        start = _datetime_value(row["starts_at"])
        end = _datetime_value(row["ends_at"])
        if start is None or end is None:
            raise AffiliateCheckoutConfigurationError("automatic budget period has missing bounds")
        start = _as_utc(start)
        end = _as_utc(end)
        if start == period.starts_at and end == period.ends_at and period_id is None:
            period_id = row["id"]
        elif start < period.ends_at and end > period.starts_at:
            raise AffiliateCheckoutConfigurationError("automatic budget periods overlap")
    return period_id


def ensure_checkout_budget_period(db, attribution, calculation: CheckoutAffiliateCalculation) -> int | None:
    """Persist an automatic period only when preparing a real booking."""
    if calculation.budget_period_id is not None:
        return calculation.budget_period_id
    period = calculation.budget_period
    if period.starts_at is None:
        return None
    start = period.starts_at.strftime("%Y-%m-%d %H:%M:%S")
    end = period.ends_at.strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(rule_version_id, period_key) DO NOTHING
        """,
        (
            attribution["partner_id"], calculation.rule.rule_version_id,
            f"{calculation.rule.budget_period_type}:{start}", start, end,
            calculation.rule.total_usage_limit,
        ),
    )
    period_id = _period_id(db, calculation.rule, period)
    if period_id is None:
        raise AffiliateCheckoutConfigurationError("automatic budget period could not be resolved")
    return period_id


def _usage_snapshot(
    db,
    rule_version_id: int,
    guest_key_hash: str,
    budget_period_id: int | None,
    period_is_lifetime: bool,
    at: datetime,
) -> UsageSnapshot:
    period_clause = "" if period_is_lifetime else "AND budget_period_id IS ?"
    parameters = [rule_version_id]
    if not period_is_lifetime:
        parameters.append(budget_period_id)
    rows = db.execute(
        f"""
        SELECT guest_key_hash, quantity, status, expires_at, created_at
          FROM affiliate_usages
         WHERE rule_version_id = ?
           AND status IN ('pending', 'final')
           {period_clause}
        """,
        parameters,
    ).fetchall()
    active_rows = []
    cutoff = _as_utc(at)
    for row in rows:
        if row["status"] == "pending":
            expiry = _datetime_value(row["expires_at"])
            if expiry is None:
                expiry = _datetime_value(row["created_at"]) + RESERVATION_WINDOW
            if _as_utc(expiry) <= cutoff:
                continue
        active_rows.append(row)
    return UsageSnapshot(
        total_used=sum(row["quantity"] for row in active_rows),
        guest_used=sum(
            row["quantity"] for row in active_rows
            if row["guest_key_hash"] == guest_key_hash
        ),
    )


def calculate_checkout_affiliate(
    db,
    attribution,
    guest_key_hash: str,
    tour,
    participants_count: int,
    at: datetime | None = None,
) -> CheckoutAffiliateCalculation:
    """Reload and evaluate the pinned rule against current server state."""
    at = _as_utc(at) if at else datetime.now(timezone.utc)
    rule_row = db.execute(
        "SELECT * FROM affiliate_rule_versions WHERE id = ? AND partner_id = ?",
        (attribution["rule_version_id"], attribution["partner_id"]),
    ).fetchone()
    if rule_row is None:
        raise AffiliateCheckoutConfigurationError("pinned rule is unavailable")
    scope_type, scope_ids = _load_scope(db, rule_row["id"])

    manual_period = None
    manual_period_id = None
    if rule_row["budget_period_type"] == "manual":
        manual_period, manual_period_id = _manual_period(db, rule_row, at)
    rule = RuleInput(
        rule_version_id=rule_row["id"],
        discount_type=rule_row["discount_type"],
        discount_value=rule_row["discount_value"],
        discount_participant_count=rule_row["discount_participant_count"],
        max_discount_amount_huf=rule_row["max_discount_amount"],
        usage_unit=rule_row["usage_unit"],
        commission_type=rule_row["commission_type"],
        commission_value=rule_row["commission_value"],
        scope_type=scope_type,
        scope_ids=scope_ids,
        valid_from=_datetime_value(rule_row["valid_from"]),
        valid_until=_datetime_value(rule_row["valid_until"]),
        total_usage_limit=rule_row["total_usage_limit"],
        guest_usage_limit=rule_row["guest_usage_limit"],
        budget_period_type=rule_row["budget_period_type"],
        manual_period_start=manual_period.starts_at if manual_period else None,
        manual_period_end=manual_period.ends_at if manual_period else None,
    )
    period = manual_period or resolve_budget_period(rule, at)
    budget_period_id = manual_period_id
    if budget_period_id is None:
        budget_period_id = _period_id(db, rule, period)
    if budget_period_id is not None:
        persisted_period = db.execute(
            "SELECT status, usage_limit FROM affiliate_budget_periods WHERE id = ?",
            (budget_period_id,),
        ).fetchone()
        if persisted_period["status"] != "open":
            raise AffiliateCheckoutConfigurationError("budget period is closed")
        if persisted_period["usage_limit"] is not None:
            rule = replace(rule, total_usage_limit=persisted_period["usage_limit"])
    usage = _usage_snapshot(
        db,
        rule.rule_version_id,
        guest_key_hash,
        budget_period_id,
        period.starts_at is None and period.ends_at is None,
        at,
    )
    unit_price = int(tour["price"])
    pricing = PricingInput(
        booking_total_huf=unit_price * participants_count,
        participant_prices_huf=(unit_price,) * participants_count,
        tour_id=tour["id"],
        location_id=tour["tour_location_id"],
        booking_at=at,
        guest_key=guest_key_hash,
        booked_participants=participants_count,
    )
    result = AffiliateCalculationService().calculate(pricing, rule, usage)
    commission_amount_huf = AffiliateCommissionService().calculate(
        paid_amount_huf=result.payable_total_huf,
        commission_type=result.commission_type,
        commission_value=result.commission_value,
    )
    return CheckoutAffiliateCalculation(
        rule=rule,
        result=result,
        budget_period_id=budget_period_id,
        budget_period=period,
        commission_amount_huf=commission_amount_huf if result.is_eligible else 0,
    )
