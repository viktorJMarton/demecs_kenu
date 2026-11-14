"""Server-authoritative affiliate revalidation for checkout."""

from dataclasses import dataclass
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


class AffiliateCheckoutConfigurationError(ValueError):
    """Raised when a persisted affiliate rule cannot be evaluated safely."""


@dataclass(frozen=True)
class CheckoutAffiliateCalculation:
    rule: RuleInput
    result: CalculationResult
    budget_period_id: int | None
    commission_amount_huf: int


def _datetime_value(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


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
    start = period.starts_at.strftime("%Y-%m-%d %H:%M:%S")
    end = period.ends_at.strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        """
        SELECT id
          FROM affiliate_budget_periods
         WHERE rule_version_id = ? AND starts_at = ? AND ends_at = ?
         ORDER BY id DESC LIMIT 1
        """,
        (rule.rule_version_id, start, end),
    ).fetchone()
    return row["id"] if row is not None else None


def _usage_snapshot(
    db,
    rule_version_id: int,
    guest_key_hash: str,
    budget_period_id: int | None,
    period_is_lifetime: bool,
) -> UsageSnapshot:
    period_clause = "" if period_is_lifetime else "AND budget_period_id IS ?"
    parameters = [rule_version_id]
    if not period_is_lifetime:
        parameters.append(budget_period_id)
    rows = db.execute(
        f"""
        SELECT guest_key_hash, quantity
          FROM affiliate_usages
         WHERE rule_version_id = ?
           AND status IN ('pending', 'final')
           {period_clause}
        """,
        parameters,
    ).fetchall()
    return UsageSnapshot(
        total_used=sum(row["quantity"] for row in rows),
        guest_used=sum(
            row["quantity"] for row in rows
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
    at = at or datetime.now(timezone.utc)
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
    usage = _usage_snapshot(
        db,
        rule.rule_version_id,
        guest_key_hash,
        budget_period_id,
        period.starts_at is None and period.ends_at is None,
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
    if result.commission_type == "percentage":
        commission_amount_huf = (
            result.payable_total_huf * result.commission_value + 50
        ) // 100
    elif result.commission_type == "fixed":
        commission_amount_huf = result.commission_value
    else:
        commission_amount_huf = 0
    return CheckoutAffiliateCalculation(
        rule=rule,
        result=result,
        budget_period_id=budget_period_id,
        commission_amount_huf=commission_amount_huf if result.is_eligible else 0,
    )
