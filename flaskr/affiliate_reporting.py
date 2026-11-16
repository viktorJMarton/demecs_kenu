"""Read-only aggregation model for affiliate reporting.

All time windows are half-open (``start <= event < end``).  Click metrics use
the click timestamp, while booking and financial metrics use the booking
timestamp.  Money is returned in whole HUF from the immutable booking snapshot.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .affiliate_retention import merge_monthly_visitor_estimate


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


@dataclass(frozen=True)
class AffiliatePartnerSummary:
    """One partner row for the paginated admin summary."""

    partner_id: int
    partner_name: str
    ref_code: str
    is_active: bool
    total_clicks: int
    bot_clicks: int
    duplicate_clicks: int
    valid_clicks: int
    estimated_unique_visitors: int
    successful_bookings: int
    participants: int
    original_amount_huf: int
    discount_amount_huf: int
    paid_amount_huf: int


@dataclass(frozen=True)
class AffiliateClickBreakdownRow:
    """A bounded click dimension row; the final row may combine the tail."""

    label: str
    total_clicks: int
    valid_clicks: int
    is_other: bool


_CLICK_DIMENSIONS = {
    "source": "utm_source",
    "medium": "utm_medium",
    "campaign": "utm_campaign",
    "landing": "landing_page",
}


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
    partner_id: int | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    source_column: str | None = None,
    source: str | None = None,
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
    if source is not None:
        if source_column is None:
            raise ValueError("source_column is required when source is filtered")
        conditions.append(f"TRIM(COALESCE({source_column}, '')) = ?")
        parameters.append(source)
    return (" AND ".join(conditions) or "1 = 1", tuple(parameters))


def _monthly_where_clause(
    *,
    table_alias: str,
    partner_id: int | None,
    start_at: str | None,
    end_at: str | None,
    source: str | None,
) -> tuple[str, tuple[object, ...]]:
    """Include only archived Budapest-month buckets fully inside the interval."""

    conditions: list[str] = []
    parameters: list[object] = []
    if partner_id is not None:
        conditions.append(f"{table_alias}.partner_id = ?")
        parameters.append(partner_id)
    if start_at is not None:
        conditions.append(f"{table_alias}.bucket_start_at >= ?")
        parameters.append(start_at)
    if end_at is not None:
        conditions.append(f"{table_alias}.bucket_end_at <= ?")
        parameters.append(end_at)
    if source is not None:
        conditions.append(f"{table_alias}.utm_source = ?")
        parameters.append(source)
    return (" AND ".join(conditions) or "1 = 1", tuple(parameters))


def _validate_monthly_filter_precision(
    connection: sqlite3.Connection,
    *,
    partner_id: int | None,
    start_at: str | None,
    end_at: str | None,
    source: str | None,
) -> None:
    if start_at is None and end_at is None:
        return
    conditions = ["aggregate_level = ?"]
    level = (
        "global"
        if partner_id is None
        else ("source" if source is not None else "overall")
    )
    parameters: list[object] = [level]
    if partner_id is not None:
        conditions.append("partner_id = ?")
        parameters.append(partner_id)
    if source is not None:
        conditions.append("utm_source = ?")
        parameters.append(source)

    overlap: list[str] = []
    contained: list[str] = []
    if start_at is not None:
        overlap.append("bucket_end_at > ?")
        parameters.append(start_at)
        contained.append("bucket_start_at >= ?")
    if end_at is not None:
        overlap.append("bucket_start_at < ?")
        parameters.append(end_at)
        contained.append("bucket_end_at <= ?")

    # Parameters must follow the SQL placeholder order: base, overlap, contained.
    contained_parameters: list[object] = []
    if start_at is not None:
        contained_parameters.append(start_at)
    if end_at is not None:
        contained_parameters.append(end_at)
    partial = connection.execute(
        f"""
        SELECT 1
          FROM affiliate_click_monthly_aggregates
         WHERE {' AND '.join(conditions)}
           AND {' AND '.join(overlap)}
           AND NOT ({' AND '.join(contained)})
         LIMIT 1
        """,
        (*parameters, *contained_parameters),
    ).fetchone()
    if partial is not None:
        raise ValueError(
            "archived click date filters must include complete Budapest months"
        )


def validate_affiliate_report_archive_filter(
    connection: sqlite3.Connection,
    *,
    partner_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    source: str | None = None,
) -> None:
    """Reject filters that would silently include only part of an archived month."""

    start_timestamp, end_timestamp, source = _validated_filter_values(
        partner_id=partner_id,
        start_at=start_at,
        end_at=end_at,
        source=source,
    )
    _validate_monthly_filter_precision(
        connection,
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )


def _estimated_unique_visitors(
    connection: sqlite3.Connection,
    *,
    partner_id: int | None,
    start_at: str | None,
    end_at: str | None,
    source: str | None,
) -> int:
    if partner_id is None:
        level = "global"
        partner_scope = 0
        scope = "global" if source is None else f"global-source:{source}"
    else:
        level = "overall" if source is None else "source"
        partner_scope = partner_id
        scope = "overall" if source is None else f"source:{source}"
    source_value = "" if source is None else source

    monthly_conditions = [
        "aggregate_level = ?", "partner_id = ?", "utm_source = ?"
    ]
    monthly_parameters: list[object] = [level, partner_scope, source_value]
    if start_at is not None:
        monthly_conditions.append("bucket_start_at >= ?")
        monthly_parameters.append(start_at)
    if end_at is not None:
        monthly_conditions.append("bucket_end_at <= ?")
        monthly_parameters.append(end_at)
    archived = connection.execute(
        f"""
        SELECT month_start, bucket_start_at, bucket_end_at, visitor_sketch
          FROM affiliate_click_monthly_aggregates
         WHERE {' AND '.join(monthly_conditions)}
         ORDER BY month_start
        """,
        monthly_parameters,
    ).fetchall()

    total = 0
    for bucket in archived:
        live_conditions = [
            "is_bot = 0", "clicked_at >= ?", "clicked_at < ?"
        ]
        live_parameters: list[object] = [
            bucket["bucket_start_at"], bucket["bucket_end_at"]
        ]
        if partner_id is not None:
            live_conditions.append("partner_id = ?")
            live_parameters.append(partner_id)
        if source is not None:
            live_conditions.append("TRIM(COALESCE(utm_source, '')) = ?")
            live_parameters.append(source)
        visitors = connection.execute(
            f"""SELECT DISTINCT visitor_id FROM affiliate_click_events
                 WHERE {' AND '.join(live_conditions)}""",
            live_parameters,
        ).fetchall()
        total += merge_monthly_visitor_estimate(
            bytes(bucket["visitor_sketch"]),
            partner_scope=partner_scope,
            month_start=str(bucket["month_start"]),
            scope=scope,
            visitor_ids=(row["visitor_id"] for row in visitors),
        )

    live_where, live_parameters = _where_clause(
        "events.clicked_at",
        partner_column="events.partner_id",
        partner_id=partner_id,
        start_at=start_at,
        end_at=end_at,
        source_column="events.utm_source",
        source=source,
    )
    outside_archives = connection.execute(
        f"""
        SELECT COUNT(DISTINCT events.visitor_id)
          FROM affiliate_click_events AS events
         WHERE events.is_bot = 0 AND {live_where}
           AND NOT EXISTS (
               SELECT 1 FROM affiliate_click_monthly_aggregates AS monthly
                WHERE monthly.aggregate_level = ?
                  AND monthly.partner_id = ?
                  AND monthly.utm_source = ?
                  AND events.clicked_at >= monthly.bucket_start_at
                  AND events.clicked_at < monthly.bucket_end_at
           )
        """,
        (*live_parameters, level, partner_scope, source_value),
    ).fetchone()[0]
    return total + int(outside_archives)


def _validated_filter_values(
    *,
    partner_id: int | None,
    start_at: datetime | None,
    end_at: datetime | None,
    source: str | None,
) -> tuple[str | None, str | None, str | None]:
    if partner_id is not None and (
        not isinstance(partner_id, int)
        or isinstance(partner_id, bool)
        or partner_id <= 0
    ):
        raise ValueError("partner_id must be a positive integer")

    normalized_source = None
    if source is not None:
        if not isinstance(source, str):
            raise ValueError("source must be a string")
        normalized_source = source.strip()
        if (
            not normalized_source
            or len(normalized_source) > 200
            or any(ord(character) < 32 or ord(character) == 127 for character in normalized_source)
        ):
            raise ValueError("source must be a non-empty printable value up to 200 characters")

    start_timestamp = _utc_db_timestamp(start_at, "start_at")
    end_timestamp = _utc_db_timestamp(end_at, "end_at")
    if start_timestamp is not None and end_timestamp is not None:
        if start_timestamp >= end_timestamp:
            raise ValueError("end_at must be later than start_at")
    return start_timestamp, end_timestamp, normalized_source


def get_affiliate_report_metrics(
    connection: sqlite3.Connection,
    *,
    partner_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    source: str | None = None,
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

    start_timestamp, end_timestamp, source = _validated_filter_values(
        partner_id=partner_id,
        start_at=start_at,
        end_at=end_at,
        source=source,
    )
    _validate_monthly_filter_precision(
        connection,
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )

    click_where, click_params = _where_clause(
        "clicked_at",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source_column="utm_source",
        source=source,
    )
    monthly_click_where, monthly_click_params = _monthly_where_clause(
        table_alias="monthly",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )
    booking_where, booking_params = _where_clause(
        "booking_date",
        partner_column="affiliate_partner_id",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source_column="bookings.affiliate_utm_source",
        source=source,
    )
    payment_where, payment_params = _where_clause(
        "payment_transactions.created_at",
        partner_column="bookings.affiliate_partner_id",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source_column="bookings.affiliate_utm_source",
        source=source,
    )

    click_row = connection.execute(
        f"""
        WITH live AS (
            SELECT COUNT(*) AS total_clicks,
                   COALESCE(SUM(CASE WHEN is_bot = 1 THEN 1 ELSE 0 END), 0)
                       AS bot_clicks,
                   COALESCE(SUM(CASE
                       WHEN is_bot = 0 AND is_duplicate = 1 THEN 1 ELSE 0 END
                   ), 0) AS duplicate_clicks,
                   COALESCE(SUM(CASE
                       WHEN is_bot = 0 AND is_duplicate = 0 THEN 1 ELSE 0 END
                   ), 0) AS valid_clicks,
                   COUNT(DISTINCT CASE WHEN is_bot = 0 THEN visitor_id END)
                       AS estimated_unique_visitors
              FROM affiliate_click_events
             WHERE {click_where}
        ),
        archived AS (
            SELECT COALESCE(SUM(total_clicks), 0) AS total_clicks,
                   COALESCE(SUM(bot_clicks), 0) AS bot_clicks,
                   COALESCE(SUM(duplicate_clicks), 0) AS duplicate_clicks,
                   COALESCE(SUM(valid_clicks), 0) AS valid_clicks,
                   COALESCE(SUM(estimated_unique_visitors), 0)
                       AS estimated_unique_visitors
              FROM affiliate_click_monthly_aggregates AS monthly
             WHERE monthly.aggregate_level = ? AND {monthly_click_where}
        ),
        combined AS (
            SELECT * FROM live
            UNION ALL
            SELECT * FROM archived
        )
        SELECT SUM(total_clicks) AS total_clicks,
               SUM(bot_clicks) AS bot_clicks,
               SUM(duplicate_clicks) AS duplicate_clicks,
               SUM(valid_clicks) AS valid_clicks,
               SUM(estimated_unique_visitors) AS estimated_unique_visitors
          FROM combined
        """,
        (*click_params, "source" if source is not None else "overall", *monthly_click_params),
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

    unique_visitors = _estimated_unique_visitors(
        connection,
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )
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


def count_affiliate_partners(
    connection: sqlite3.Connection,
    *,
    partner_id: int | None = None,
) -> int:
    """Return the number of partners available to the summary view."""

    _validated_filter_values(
        partner_id=partner_id,
        start_at=None,
        end_at=None,
        source=None,
    )
    where = "WHERE id = ?" if partner_id is not None else ""
    parameters = () if partner_id is None else (partner_id,)

    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM affiliate_partners {where}", parameters
        ).fetchone()[0]
    )


def get_affiliate_source_options(connection: sqlite3.Connection) -> list[str]:
    """Return the exact, persisted non-empty UTM sources accepted by the UI."""

    rows = connection.execute(
            """
            SELECT source
              FROM (
                    SELECT DISTINCT TRIM(utm_source) AS source
                      FROM affiliate_click_events
                     WHERE TRIM(COALESCE(utm_source, '')) <> ''
                    UNION
                    SELECT DISTINCT TRIM(affiliate_utm_source) AS source
                      FROM bookings
                     WHERE TRIM(COALESCE(affiliate_utm_source, '')) <> ''
                    UNION
                    SELECT DISTINCT utm_source AS source
                      FROM affiliate_click_monthly_aggregates
                     WHERE aggregate_level = 'source' AND utm_source <> ''
                   )
             ORDER BY source COLLATE NOCASE, source
            """
        ).fetchall()
    return [
        value
        for row in rows
        if len(value := str(row["source"])) <= 200
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
    ]


def get_affiliate_partner_summaries(
    connection: sqlite3.Connection,
    *,
    limit: int = 25,
    offset: int = 0,
    partner_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    source: str | None = None,
) -> list[AffiliatePartnerSummary]:
    """Return one fanout-safe aggregate row per partner.

    Partners are paged before event aggregation, keeping the response bounded
    even when the click and booking tables are large. Financial values and
    participants include only currently paid booking snapshots.
    """

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 100
    ):
        raise ValueError("limit must be an integer between 1 and 100")
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
    ):
        raise ValueError("offset must be a non-negative integer")

    start_timestamp, end_timestamp, source = _validated_filter_values(
        partner_id=partner_id,
        start_at=start_at,
        end_at=end_at,
        source=source,
    )
    _validate_monthly_filter_precision(
        connection,
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )
    selected_where = "WHERE id = ?" if partner_id is not None else ""
    selected_params: tuple[object, ...] = () if partner_id is None else (partner_id,)
    click_where, click_params = _where_clause(
        "events.clicked_at",
        start_at=start_timestamp,
        end_at=end_timestamp,
        source_column="events.utm_source",
        source=source,
    )
    monthly_click_where, monthly_click_params = _monthly_where_clause(
        table_alias="monthly",
        partner_id=None,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )
    booking_where, booking_params = _where_clause(
        "bookings.booking_date",
        start_at=start_timestamp,
        end_at=end_timestamp,
        source_column="bookings.affiliate_utm_source",
        source=source,
    )

    rows = connection.execute(
        f"""
        WITH selected_partners AS (
            SELECT id, name, ref_code, is_active
              FROM affiliate_partners
             {selected_where}
             ORDER BY is_active DESC, name COLLATE NOCASE, id
             LIMIT ? OFFSET ?
        ),
        live_click_totals AS (
            SELECT events.partner_id,
                   COUNT(*) AS total_clicks,
                   COALESCE(SUM(CASE
                       WHEN events.is_bot = 1 THEN 1 ELSE 0 END
                   ), 0) AS bot_clicks,
                   COALESCE(SUM(CASE
                       WHEN events.is_bot = 0 AND events.is_duplicate = 1
                       THEN 1 ELSE 0 END
                   ), 0) AS duplicate_clicks,
                   COALESCE(SUM(CASE
                       WHEN events.is_bot = 0 AND events.is_duplicate = 0
                       THEN 1 ELSE 0 END
                   ), 0) AS valid_clicks,
                   COUNT(DISTINCT CASE
                       WHEN events.is_bot = 0 THEN events.visitor_id END
                   ) AS estimated_unique_visitors
              FROM affiliate_click_events AS events
              JOIN selected_partners AS partners
                ON partners.id = events.partner_id
             WHERE {click_where}
             GROUP BY events.partner_id
        ),
        monthly_click_totals AS (
            SELECT monthly.partner_id,
                   SUM(monthly.total_clicks) AS total_clicks,
                   SUM(monthly.bot_clicks) AS bot_clicks,
                   SUM(monthly.duplicate_clicks) AS duplicate_clicks,
                   SUM(monthly.valid_clicks) AS valid_clicks,
                   SUM(monthly.estimated_unique_visitors)
                       AS estimated_unique_visitors
              FROM affiliate_click_monthly_aggregates AS monthly
              JOIN selected_partners AS partners
                ON partners.id = monthly.partner_id
             WHERE monthly.aggregate_level = ? AND {monthly_click_where}
             GROUP BY monthly.partner_id
        ),
        click_components AS (
            SELECT * FROM live_click_totals
            UNION ALL
            SELECT * FROM monthly_click_totals
        ),
        click_totals AS (
            SELECT partner_id,
                   SUM(total_clicks) AS total_clicks,
                   SUM(bot_clicks) AS bot_clicks,
                   SUM(duplicate_clicks) AS duplicate_clicks,
                   SUM(valid_clicks) AS valid_clicks,
                   SUM(estimated_unique_visitors) AS estimated_unique_visitors
              FROM click_components
             GROUP BY partner_id
        ),
        booking_totals AS (
            SELECT bookings.affiliate_partner_id AS partner_id,
                   COUNT(*) AS successful_bookings,
                   COALESCE(SUM(bookings.participants_count), 0) AS participants,
                   COALESCE(SUM(bookings.affiliate_original_price), 0)
                       AS original_amount_huf,
                   COALESCE(SUM(bookings.affiliate_discount_amount), 0)
                       AS discount_amount_huf,
                   COALESCE(SUM(bookings.affiliate_payable_price), 0)
                       AS paid_amount_huf
              FROM bookings
              JOIN selected_partners AS partners
                ON partners.id = bookings.affiliate_partner_id
             WHERE bookings.payment_status = 'paid' AND {booking_where}
             GROUP BY bookings.affiliate_partner_id
        )
        SELECT partners.id AS partner_id,
               partners.name AS partner_name,
               partners.ref_code,
               partners.is_active,
               COALESCE(clicks.total_clicks, 0) AS total_clicks,
               COALESCE(clicks.bot_clicks, 0) AS bot_clicks,
               COALESCE(clicks.duplicate_clicks, 0) AS duplicate_clicks,
               COALESCE(clicks.valid_clicks, 0) AS valid_clicks,
               COALESCE(clicks.estimated_unique_visitors, 0)
                   AS estimated_unique_visitors,
               COALESCE(bookings.successful_bookings, 0) AS successful_bookings,
               COALESCE(bookings.participants, 0) AS participants,
               COALESCE(bookings.original_amount_huf, 0) AS original_amount_huf,
               COALESCE(bookings.discount_amount_huf, 0) AS discount_amount_huf,
               COALESCE(bookings.paid_amount_huf, 0) AS paid_amount_huf
          FROM selected_partners AS partners
     LEFT JOIN click_totals AS clicks ON clicks.partner_id = partners.id
     LEFT JOIN booking_totals AS bookings ON bookings.partner_id = partners.id
         ORDER BY partners.is_active DESC, partners.name COLLATE NOCASE, partners.id
        """,
        (
            *selected_params,
            limit,
            offset,
            *click_params,
            "source" if source is not None else "overall",
            *monthly_click_params,
            *booking_params,
        ),
    ).fetchall()

    return [
        AffiliatePartnerSummary(
            partner_id=int(row["partner_id"]),
            partner_name=str(row["partner_name"]),
            ref_code=str(row["ref_code"]),
            is_active=bool(row["is_active"]),
            total_clicks=int(row["total_clicks"]),
            bot_clicks=int(row["bot_clicks"]),
            duplicate_clicks=int(row["duplicate_clicks"]),
            valid_clicks=int(row["valid_clicks"]),
            estimated_unique_visitors=_estimated_unique_visitors(
                connection,
                partner_id=int(row["partner_id"]),
                start_at=start_timestamp,
                end_at=end_timestamp,
                source=source,
            ),
            successful_bookings=int(row["successful_bookings"]),
            participants=int(row["participants"]),
            original_amount_huf=int(row["original_amount_huf"]),
            discount_amount_huf=int(row["discount_amount_huf"]),
            paid_amount_huf=int(row["paid_amount_huf"]),
        )
        for row in rows
    ]


def get_affiliate_click_breakdown(
    connection: sqlite3.Connection,
    *,
    dimension: str,
    partner_id: int | None = None,
    limit: int = 10,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    source: str | None = None,
) -> list[AffiliateClickBreakdownRow]:
    """Aggregate one allow-listed click dimension with an exact tail bucket.

    The top ``limit`` groups are shown separately. Remaining groups are summed
    into one ``Egyéb (összevont)`` row, so both raw and valid row totals always
    reconcile with the corresponding filtered click total.
    """

    column = _CLICK_DIMENSIONS.get(dimension)
    if column is None:
        raise ValueError("unsupported click breakdown dimension")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 50
    ):
        raise ValueError("limit must be an integer between 1 and 50")

    start_timestamp, end_timestamp, source = _validated_filter_values(
        partner_id=partner_id,
        start_at=start_at,
        end_at=end_at,
        source=source,
    )
    _validate_monthly_filter_precision(
        connection,
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )
    where, where_params = _where_clause(
        "clicked_at",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source_column="utm_source",
        source=source,
    )
    monthly_where, monthly_params = _monthly_where_clause(
        table_alias="monthly",
        partner_id=partner_id,
        start_at=start_timestamp,
        end_at=end_timestamp,
        source=source,
    )
    parameters: list[object] = list(where_params)
    parameters.append("detail")
    parameters.extend(monthly_params)
    parameters.extend((limit, limit + 1, limit))
    rows = connection.execute(
        f"""
        WITH live_grouped AS (
            SELECT CASE
                       WHEN TRIM(COALESCE({column}, '')) = '' THEN 'Nincs megadva'
                       ELSE TRIM({column})
                   END AS dimension_value,
                   COUNT(*) AS total_clicks,
                   COALESCE(SUM(CASE
                       WHEN is_bot = 0 AND is_duplicate = 0 THEN 1 ELSE 0 END
                   ), 0) AS valid_clicks
              FROM affiliate_click_events
             WHERE {where}
             GROUP BY dimension_value
        ),
        monthly_grouped AS (
            SELECT CASE
                       WHEN monthly.{column} = '' THEN 'Nincs megadva'
                       ELSE monthly.{column}
                   END AS dimension_value,
                   SUM(monthly.total_clicks) AS total_clicks,
                   SUM(monthly.valid_clicks) AS valid_clicks
              FROM affiliate_click_monthly_aggregates AS monthly
             WHERE monthly.aggregate_level = ? AND {monthly_where}
             GROUP BY dimension_value
        ),
        grouped_components AS (
            SELECT * FROM live_grouped
            UNION ALL
            SELECT * FROM monthly_grouped
        ),
        grouped AS (
            SELECT dimension_value,
                   SUM(total_clicks) AS total_clicks,
                   SUM(valid_clicks) AS valid_clicks
              FROM grouped_components
             GROUP BY dimension_value
        ),
        ranked AS (
            SELECT dimension_value, total_clicks, valid_clicks,
                   ROW_NUMBER() OVER (
                       ORDER BY total_clicks DESC,
                                dimension_value COLLATE NOCASE,
                                dimension_value
                   ) AS row_number
              FROM grouped
        )
        SELECT dimension_value, total_clicks, valid_clicks,
               0 AS is_other, row_number AS sort_order
          FROM ranked
         WHERE row_number <= ?
        UNION ALL
        SELECT 'Egyéb (összevont)', SUM(total_clicks), SUM(valid_clicks),
               1 AS is_other, ? AS sort_order
          FROM ranked
         WHERE row_number > ?
        HAVING COUNT(*) > 0
         ORDER BY sort_order
        """,
        parameters,
    ).fetchall()

    return [
        AffiliateClickBreakdownRow(
            label=str(row["dimension_value"]),
            total_clicks=int(row["total_clicks"]),
            valid_clicks=int(row["valid_clicks"]),
            is_other=bool(row["is_other"]),
        )
        for row in rows
    ]
