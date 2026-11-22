"""Read-only partner settlement previews built from locked booking snapshots."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_SETTLEMENT_TIMEZONE = ZoneInfo("Europe/Budapest")


@dataclass(frozen=True)
class SettlementItem:
    booking_id: int
    order_ref: str
    paid_at: str
    rule_version_id: int
    original_amount: int
    discount_amount: int
    paid_amount: int
    commission_amount: int
    commission_type: str
    commission_value: int


@dataclass(frozen=True)
class SettlementPreview:
    items: tuple[SettlementItem, ...]
    original_amount_total: int
    discount_amount_total: int
    paid_amount_total: int
    commission_amount_total: int


def preview_affiliate_settlement(db, partner_id: int, period_start: date, period_end: date) -> SettlementPreview:
    """Select unsettled paid bookings for inclusive Budapest payment dates."""
    if type(partner_id) is not int or partner_id < 1:
        raise ValueError("partner_id must be a positive integer")
    if type(period_start) is not date or type(period_end) is not date or period_end < period_start:
        raise ValueError("a valid settlement date range is required")
    try:
        bounds = tuple(
            datetime.combine(day, time.min, tzinfo=_SETTLEMENT_TIMEZONE)
            .astimezone(timezone.utc)
            .strftime("%Y-%m-%d %H:%M:%S")
            for day in (period_start, period_end + timedelta(days=1))
        )
    except OverflowError as exc:
        raise ValueError("settlement date range cannot be represented") from exc

    rows = db.execute(
        """
        SELECT b.id AS booking_id, b.order_ref, CAST(b.payment_date AS TEXT) AS paid_at,
               b.affiliate_rule_version_id AS rule_version_id,
               b.affiliate_original_price AS original_amount,
               b.affiliate_discount_amount AS discount_amount,
               b.affiliate_payable_price AS paid_amount,
               b.affiliate_commission_amount AS commission_amount,
               b.affiliate_commission_type AS commission_type,
               b.affiliate_commission_value AS commission_value
          FROM bookings b
         WHERE b.affiliate_partner_id = ?
           AND b.payment_status = 'paid' AND b.cancellation_date IS NULL
           AND b.affiliate_commission_status = 'earned' AND b.affiliate_snapshot_locked = 1
           AND b.payment_date >= ? AND b.payment_date < ?
           AND NOT EXISTS (SELECT 1 FROM affiliate_settlement_items item WHERE item.booking_id = b.id)
         ORDER BY b.payment_date, b.id
        """,
        (partner_id, *bounds),
    ).fetchall()
    items = tuple(SettlementItem(**dict(row)) for row in rows)
    for item in items:
        if (
            type(item.rule_version_id) is not int
            or item.commission_type not in {"percentage", "fixed"}
            or any(type(amount) is not int or amount < 0 for amount in (
                item.original_amount, item.discount_amount, item.paid_amount,
                item.commission_amount, item.commission_value,
            ))
            or item.original_amount - item.discount_amount != item.paid_amount
        ):
            raise ValueError(f"incomplete or inconsistent settlement snapshot for booking {item.booking_id}")

    return SettlementPreview(
        items=items,
        original_amount_total=sum(item.original_amount for item in items),
        discount_amount_total=sum(item.discount_amount for item in items),
        paid_amount_total=sum(item.paid_amount for item in items),
        commission_amount_total=sum(item.commission_amount for item in items),
    )
