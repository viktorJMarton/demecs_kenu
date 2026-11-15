"""Read-only aggregation model for affiliate reporting.

All time windows are half-open (``start <= event < end``).  Click metrics use
the click timestamp, while booking and financial metrics use the booking
timestamp.  Money is returned in whole HUF from the immutable booking snapshot.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AffiliateReportMetrics:
    """Canonical metric definitions shared by reporting views and exports."""

    total_clicks: int
    bot_clicks: int
    duplicate_clicks: int
    valid_clicks: int
    estimated_unique_visitors: int
    started_bookings: int
    successful_bookings: int
    cancelled_bookings: int
    refunded_bookings: int
    participants: int
    original_amount_huf: int
    discount_amount_huf: int
    paid_amount_huf: int
    commission_amount_huf: int
    unsettled_commission_huf: int
    settled_commission_huf: int
    conversion_rate_percent: float


def _utc_db_timestamp(value: datetime | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _where_clause(
    timestamp_column: str,
    *,
    partner_column: str = "partner_id",
    partner_id: int | None,
    start_at: str | None,
    end_at: str | None,
) -> tuple[str, tuple[object, ...]]:
    # SQLite CURRENT_TIMESTAMP omits fractional seconds. Normalize persisted
    # values to six digits before lexical comparison so an event exactly at an
    # exclusive boundary is not accidentally included (or excluded at start).
    normalized_timestamp = (
        f"CASE WHEN instr({timestamp_column}, '.') = 0 "
        f"THEN {timestamp_column} || '.000000' "
        f"ELSE {timestamp_column} || substr('000000', 1, "
        f"6 - (length({timestamp_column}) - instr({timestamp_column}, '.'))) END"
    )
    conditions: list[str] = []
    parameters: list[object] = []
    if partner_id is not None:
        conditions.append(f"{partner_column} = ?")
        parameters.append(partner_id)
    if start_at is not None:
        conditions.append(f"({normalized_timestamp}) >= ?")
        parameters.append(start_at)
    if end_at is not None:
        conditions.append(f"({normalized_timestamp}) < ?")
        parameters.append(end_at)
    return (" AND ".join(conditions) or "1 = 1", tuple(parameters))


def get_affiliate_report_metrics(
    connection: sqlite3.Connection,
    *,
    partner_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> AffiliateReportMetrics:
    """Aggregate canonical affiliate metrics without returning customer PII.

    ``total_clicks`` is the raw stored event count. ``valid_clicks`` excludes
    bot and duplicate events. Estimated unique visitors count distinct visitor
    identifiers among non-bot events, so repeated events never add visitors.
    Conversion is successful bookings divided by estimated unique visitors;
    a zero denominator produces ``0.0``.

    Payment starts count distinct bookings with a persisted payment transaction
    and use the transaction creation time. Booking money and participants
    include only currently paid bookings. This
    deliberately excludes pending, failed, cancelled and refunded rows. The
    commission split is based on the immutable booking commission snapshot:
    ``pending``/``earned`` are unsettled and ``settled`` is already paid to the
    partner.
    """

    if partner_id is not None and (
        not isinstance(partner_id, int)
        or isinstance(partner_id, bool)
        or partner_id <= 0
    ):
        raise ValueError("partner_id must be a positive integer")

    start_timestamp = _utc_db_timestamp(start_at, "start_at")
    end_timestamp = _utc_db_timestamp(end_at, "end_at")
    if start_timestamp is not None and end_timestamp is not None:
        if start_timestamp >= end_timestamp:
            raise ValueError("end_at must be later than start_at")

    click_where, click_params = _where_clause(
        "clicked_at",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
    )
    booking_where, booking_params = _where_clause(
        "booking_date",
        partner_column="affiliate_partner_id",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
    )
    payment_where, payment_params = _where_clause(
        "payment_transactions.created_at",
        partner_column="bookings.affiliate_partner_id",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
    )

    click_row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS total_clicks,
            COALESCE(SUM(CASE WHEN is_bot = 1 THEN 1 ELSE 0 END), 0) AS bot_clicks,
            COALESCE(SUM(CASE WHEN is_bot = 0 AND is_duplicate = 1 THEN 1 ELSE 0 END), 0)
                AS duplicate_clicks,
            COALESCE(SUM(CASE WHEN is_bot = 0 AND is_duplicate = 0 THEN 1 ELSE 0 END), 0)
                AS valid_clicks,
            COUNT(DISTINCT CASE WHEN is_bot = 0 THEN visitor_id END)
                AS estimated_unique_visitors
        FROM affiliate_click_events
        WHERE {click_where}
        """,
        click_params,
    ).fetchone()

    booking_row = connection.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN 1 ELSE 0 END), 0)
                AS successful_bookings,
            COALESCE(SUM(CASE WHEN payment_status = 'cancelled' THEN 1 ELSE 0 END), 0)
                AS cancelled_bookings,
            COALESCE(SUM(CASE WHEN payment_status = 'refunded' THEN 1 ELSE 0 END), 0)
                AS refunded_bookings,
            COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN participants_count ELSE 0 END), 0)
                AS participants,
            COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN affiliate_original_price ELSE 0 END), 0)
                AS original_amount_huf,
            COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN affiliate_discount_amount ELSE 0 END), 0)
                AS discount_amount_huf,
            COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN affiliate_payable_price ELSE 0 END), 0)
                AS paid_amount_huf,
            COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN affiliate_commission_amount ELSE 0 END), 0)
                AS commission_amount_huf,
            COALESCE(SUM(CASE
                WHEN payment_status = 'paid'
                     AND affiliate_commission_status IN ('pending', 'earned')
                THEN affiliate_commission_amount ELSE 0 END), 0)
                AS unsettled_commission_huf,
            COALESCE(SUM(CASE
                WHEN payment_status = 'paid' AND affiliate_commission_status = 'settled'
                THEN affiliate_commission_amount ELSE 0 END), 0)
                AS settled_commission_huf
        FROM bookings
        WHERE affiliate_partner_id IS NOT NULL AND {booking_where}
        """,
        booking_params,
    ).fetchone()

    # Booking creation precedes payment preparation. A transaction row is the
    # authoritative server-side evidence that a payment start was attempted.
    payment_row = connection.execute(
        f"""
        SELECT COUNT(DISTINCT payment_transactions.booking_id) AS started_bookings
        FROM payment_transactions
        JOIN bookings ON bookings.id = payment_transactions.booking_id
        WHERE bookings.affiliate_partner_id IS NOT NULL AND {payment_where}
        """,
        payment_params,
    ).fetchone()

    unique_visitors = int(click_row["estimated_unique_visitors"])
    successful_bookings = int(booking_row["successful_bookings"])
    conversion_rate = (
        round(successful_bookings * 100 / unique_visitors, 2)
        if unique_visitors
        else 0.0
    )

    return AffiliateReportMetrics(
        total_clicks=int(click_row["total_clicks"]),
        bot_clicks=int(click_row["bot_clicks"]),
        duplicate_clicks=int(click_row["duplicate_clicks"]),
        valid_clicks=int(click_row["valid_clicks"]),
        estimated_unique_visitors=unique_visitors,
        started_bookings=int(payment_row["started_bookings"]),
        successful_bookings=successful_bookings,
        cancelled_bookings=int(booking_row["cancelled_bookings"]),
        refunded_bookings=int(booking_row["refunded_bookings"]),
        participants=int(booking_row["participants"]),
        original_amount_huf=int(booking_row["original_amount_huf"]),
        discount_amount_huf=int(booking_row["discount_amount_huf"]),
        paid_amount_huf=int(booking_row["paid_amount_huf"]),
        commission_amount_huf=int(booking_row["commission_amount_huf"]),
        unsettled_commission_huf=int(booking_row["unsettled_commission_huf"]),
        settled_commission_huf=int(booking_row["settled_commission_huf"]),
        conversion_rate_percent=conversion_rate,
    )
