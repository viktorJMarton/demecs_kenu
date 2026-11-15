from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from flaskr.affiliate_reporting import get_affiliate_report_metrics
from flaskr.db import get_db


def _seed_partner(connection, ref_code: str) -> tuple[int, int]:
    partner_id = connection.execute(
        "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
        (ref_code, f"Partner {ref_code}"),
    ).lastrowid
    rule_id = connection.execute(
        """
        INSERT INTO affiliate_rule_versions (
            partner_id, version_number, status, discount_type, commission_type
        ) VALUES (?, 1, 'active', 'tracking', 'percentage')
        """,
        (partner_id,),
    ).lastrowid
    return partner_id, rule_id


def _seed_click(
    connection,
    *,
    event_key: str,
    partner_id: int,
    rule_id: int,
    visitor_id: str,
    clicked_at: str,
    is_bot: int = 0,
    is_duplicate: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO affiliate_click_events (
            event_key, partner_id, rule_version_id, visitor_id, clicked_at,
            is_bot, is_duplicate
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_key,
            partner_id,
            rule_id,
            visitor_id,
            clicked_at,
            is_bot,
            is_duplicate,
        ),
    )


def _seed_payment_start(
    connection,
    *,
    booking_id: int,
    order_ref: str,
    amount: int,
    status: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO payment_transactions (
            booking_id, order_ref, amount, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (booking_id, order_ref, amount, status, created_at, created_at),
    )


def _seed_booking(
    connection,
    *,
    order_ref: str,
    partner_id: int,
    rule_id: int,
    payment_status: str,
    booking_date: str,
    participants: int,
    original: int,
    discount: int,
    paid: int,
    commission: int,
    commission_status: str,
) -> int:
    booking_id = connection.execute(
        """
        INSERT INTO bookings (
            tour_id, order_ref, customer_name, customer_email,
            participants_count, total_price, payment_status, booking_date,
            affiliate_partner_id, affiliate_rule_version_id,
            affiliate_original_price, affiliate_discount_amount,
            affiliate_payable_price, affiliate_commission_amount,
            affiliate_commission_status
        ) VALUES (
            1, ?, 'Teszt Elek', 'teszt@example.invalid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            order_ref,
            participants,
            paid,
            payment_status,
            booking_date,
            partner_id,
            rule_id,
            original,
            discount,
            paid,
            commission,
            commission_status,
        ),
    ).lastrowid
    return booking_id


@pytest.fixture
def reporting_data(app):
    with app.app_context():
        connection = get_db()
        suffix = uuid4().hex
        partner_a, rule_a = _seed_partner(connection, f"REPORT-A-{suffix}")
        partner_b, rule_b = _seed_partner(connection, f"REPORT-B-{suffix}")

        # Partner A: 5 raw clicks = 2 valid, 1 repeated, 1 bot, 1 later.
        _seed_click(connection, event_key=f"a-1-{suffix}", partner_id=partner_a, rule_id=rule_a,
                    visitor_id="visitor-1", clicked_at="2026-01-10 10:00:00")
        _seed_click(connection, event_key=f"a-2-{suffix}", partner_id=partner_a, rule_id=rule_a,
                    visitor_id="visitor-1", clicked_at="2026-01-10 10:01:00", is_duplicate=1)
        _seed_click(connection, event_key=f"a-3-{suffix}", partner_id=partner_a, rule_id=rule_a,
                    visitor_id="visitor-2", clicked_at="2026-01-10 10:02:00")
        _seed_click(connection, event_key=f"a-bot-{suffix}", partner_id=partner_a, rule_id=rule_a,
                    visitor_id="crawler", clicked_at="2026-01-10 10:03:00", is_bot=1)
        _seed_click(connection, event_key=f"a-late-{suffix}", partner_id=partner_a, rule_id=rule_a,
                    visitor_id="visitor-3", clicked_at="2026-02-01 00:00:00")
        _seed_click(connection, event_key=f"b-1-{suffix}", partner_id=partner_b, rule_id=rule_b,
                    visitor_id="visitor-b", clicked_at="2026-01-10 11:00:00")

        # The paid rows add up by hand to 4 people, 40k original, 6k discount,
        # 34k paid, 3.4k commission (2.4k unsettled + 1k settled).
        paid_1_ref = f"A-PAID-1-{suffix}"
        paid_1 = _seed_booking(connection, order_ref=paid_1_ref, partner_id=partner_a, rule_id=rule_a,
                      payment_status="paid", booking_date="2026-01-12 12:00:00",
                      participants=3, original=30000, discount=6000, paid=24000,
                      commission=2400, commission_status="pending")
        paid_2_ref = f"A-PAID-2-{suffix}"
        paid_2 = _seed_booking(connection, order_ref=paid_2_ref, partner_id=partner_a, rule_id=rule_a,
                      payment_status="paid", booking_date="2026-01-20 12:00:00",
                      participants=1, original=10000, discount=0, paid=10000,
                      commission=1000, commission_status="settled")
        cancel_ref = f"A-CANCEL-{suffix}"
        cancelled = _seed_booking(connection, order_ref=cancel_ref, partner_id=partner_a, rule_id=rule_a,
                      payment_status="cancelled", booking_date="2026-01-21 12:00:00",
                      participants=8, original=80000, discount=8000, paid=72000,
                      commission=7200, commission_status="reversed")
        refund_ref = f"A-REFUND-{suffix}"
        refunded = _seed_booking(connection, order_ref=refund_ref, partner_id=partner_a, rule_id=rule_a,
                      payment_status="refunded", booking_date="2026-01-22 12:00:00",
                      participants=2, original=20000, discount=2000, paid=18000,
                      commission=1800, commission_status="reversed")
        _seed_booking(connection, order_ref=f"A-PENDING-{suffix}", partner_id=partner_a, rule_id=rule_a,
                      payment_status="pending", booking_date="2026-02-01 00:00:00",
                      participants=5, original=50000, discount=5000, paid=45000,
                      commission=4500, commission_status="pending")
        _seed_booking(connection, order_ref=f"B-PAID-{suffix}", partner_id=partner_b, rule_id=rule_b,
                      payment_status="paid", booking_date="2026-01-15 12:00:00",
                      participants=9, original=90000, discount=0, paid=90000,
                      commission=9000, commission_status="earned")
        # A persisted booking may fail before payment preparation creates a
        # transaction. Such a row is not a payment start.
        _seed_booking(connection, order_ref=f"A-NO-TX-{suffix}", partner_id=partner_a, rule_id=rule_a,
                      payment_status="failed", booking_date="2026-01-23 12:00:00",
                      participants=1, original=10000, discount=0, paid=10000,
                      commission=1000, commission_status="pending")
        _seed_payment_start(connection, booking_id=paid_1, order_ref=paid_1_ref,
                            amount=24000, status="success", created_at="2026-01-12 12:00:01")
        _seed_payment_start(connection, booking_id=paid_2, order_ref=paid_2_ref,
                            amount=10000, status="success", created_at="2026-01-20 12:00:01")
        _seed_payment_start(connection, booking_id=cancelled, order_ref=cancel_ref,
                            amount=72000, status="cancelled", created_at="2026-01-21 12:00:01")
        _seed_payment_start(connection, booking_id=refunded, order_ref=refund_ref,
                            amount=18000, status="refunded", created_at="2026-01-22 12:00:01")
        connection.commit()
        try:
            yield connection, partner_a
        finally:
            connection.execute(
                """DELETE FROM payment_transactions
                   WHERE booking_id IN (
                       SELECT id FROM bookings WHERE affiliate_partner_id IN (?, ?)
                   )""",
                (partner_a, partner_b),
            )
            connection.execute(
                "DELETE FROM bookings WHERE affiliate_partner_id IN (?, ?)",
                (partner_a, partner_b),
            )
            connection.execute(
                "DELETE FROM affiliate_click_events WHERE partner_id IN (?, ?)",
                (partner_a, partner_b),
            )
            connection.execute(
                "DELETE FROM affiliate_rule_versions WHERE partner_id IN (?, ?)",
                (partner_a, partner_b),
            )
            connection.execute(
                "DELETE FROM affiliate_partners WHERE id IN (?, ?)",
                (partner_a, partner_b),
            )
            connection.commit()


def test_metrics_are_hand_verifiable_and_do_not_double_count(reporting_data):
    connection, partner_id = reporting_data

    metrics = get_affiliate_report_metrics(
        connection,
        partner_id=partner_id,
        start_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    assert metrics.total_clicks == 4
    assert metrics.bot_clicks == 1
    assert metrics.duplicate_clicks == 1
    assert metrics.valid_clicks == 2
    assert metrics.estimated_unique_visitors == 2
    assert metrics.started_bookings == 4
    assert metrics.successful_bookings == 2
    assert metrics.cancelled_bookings == 1
    assert metrics.refunded_bookings == 1
    assert metrics.participants == 4
    assert metrics.original_amount_huf == 40000
    assert metrics.discount_amount_huf == 6000
    assert metrics.paid_amount_huf == 34000
    assert metrics.commission_amount_huf == 3400
    assert metrics.unsettled_commission_huf == 2400
    assert metrics.settled_commission_huf == 1000
    assert metrics.conversion_rate_percent == 100.0


def test_empty_result_and_half_open_boundary(reporting_data):
    connection, partner_id = reporting_data

    metrics = get_affiliate_report_metrics(
        connection,
        partner_id=partner_id,
        start_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert set(metrics.__dict__.values()) == {0, 0.0}


def test_fractional_half_open_boundaries_and_timezone_conversion(reporting_data):
    connection, partner_id = reporting_data
    rule_id = connection.execute(
        "SELECT id FROM affiliate_rule_versions WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()["id"]
    suffix = uuid4().hex
    for label, timestamp in (
        ("before", "2026-03-01 09:59:59.999999"),
        ("start", "2026-03-01 10:00:00.000000"),
        ("inside", "2026-03-01 10:00:00.000001"),
        ("last", "2026-03-01 10:00:00.999999"),
        ("end", "2026-03-01 10:00:01.000000"),
    ):
        _seed_click(
            connection,
            event_key=f"boundary-{label}-{suffix}",
            partner_id=partner_id,
            rule_id=rule_id,
            visitor_id=f"boundary-{label}",
            clicked_at=timestamp,
        )
    connection.commit()

    local_zone = timezone(timedelta(hours=1))
    metrics = get_affiliate_report_metrics(
        connection,
        partner_id=partner_id,
        start_at=datetime(2026, 3, 1, 11, 0, 0, tzinfo=local_zone),
        end_at=datetime(2026, 3, 1, 11, 0, 1, tzinfo=local_zone),
    )

    assert metrics.total_clicks == 3
    assert metrics.valid_clicks == 3
    assert metrics.estimated_unique_visitors == 3


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"partner_id": 0}, "positive integer"),
        ({"partner_id": True}, "positive integer"),
        ({"partner_id": 1.0}, "positive integer"),
        ({"partner_id": "1"}, "positive integer"),
        ({"start_at": "2026-01-01"}, "must be a datetime"),
        ({"start_at": datetime(2026, 1, 1)}, "timezone-aware"),
        (
            {
                "start_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "end_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
            "later than",
        ),
    ],
)
def test_invalid_filters_fail_closed(reporting_data, kwargs, message):
    connection, _ = reporting_data

    with pytest.raises(ValueError, match=message):
        get_affiliate_report_metrics(connection, **kwargs)
