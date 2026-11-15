import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from flaskr import db as db_module
from flaskr.affiliate_migration import migrate_affiliate_schema
from flaskr.affiliate_usage import (
    cleanup_expired_affiliate_usages,
    finalize_affiliate_usage,
    release_affiliate_usage,
    reserve_affiliate_usage,
)


def _connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _database(tmp_path):
    path = tmp_path / "usage-cleanup.sqlite"
    connection = _connect(path)
    with open("flaskr/schema.sql", encoding="utf-8") as schema:
        connection.executescript(schema.read())
    migrate_affiliate_schema(connection)
    location_id = connection.execute(
        "INSERT INTO tour_locations (name) VALUES ('Tisza-tó')"
    ).lastrowid
    tour_id = connection.execute(
        """
        INSERT INTO tours (title, date, time, price, tour_location_id)
        VALUES ('Cleanup teszt', '2027-06-01', '09:00', 10000, ?)
        """,
        (location_id,),
    ).lastrowid
    booking_ids = []
    for number in range(1, 9):
        booking_ids.append(
            connection.execute(
                """
                INSERT INTO bookings (
                    tour_id, order_ref, customer_name, customer_email,
                    participants_count, total_price
                ) VALUES (?, ?, 'Cleanup Vendég', ?, 1, 10000)
                """,
                (tour_id, f"BUD-06-{number}", f"cleanup{number}@example.test"),
            ).lastrowid
        )
    partner_id = connection.execute(
        "INSERT INTO affiliate_partners (ref_code, name) VALUES ('CLEANUP1', 'Partner')"
    ).lastrowid
    rule_id = connection.execute(
        """
        INSERT INTO affiliate_rule_versions (
            partner_id, version_number, status, discount_type,
            total_usage_limit, guest_usage_limit, budget_period_type
        ) VALUES (?, 1, 'active', 'tracking', 20, NULL, 'monthly')
        """,
        (partner_id,),
    ).lastrowid
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 20)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    return path, connection, booking_ids, partner_id, rule_id, period_id


def _reserve(connection, booking_id, partner_id, rule_id, period_id, key, now):
    return reserve_affiliate_usage(
        connection,
        idempotency_key=key,
        booking_id=booking_id,
        partner_id=partner_id,
        rule_version_id=rule_id,
        budget_period_id=period_id,
        guest_key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
        quantity=1,
        now=now,
    )


def test_cleanup_is_bounded_rerunnable_and_only_releases_expired_pending(tmp_path, caplog):
    _, connection, bookings, partner_id, rule_id, period_id = _database(tmp_path)
    cutoff = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
    expired = [
        _reserve(
            connection,
            bookings[index],
            partner_id,
            rule_id,
            period_id,
            f"expired-{index}",
            cutoff - timedelta(minutes=30 - index),
        )
        for index in range(3)
    ]
    fresh = _reserve(
        connection,
        bookings[3],
        partner_id,
        rule_id,
        period_id,
        "fresh",
        cutoff - timedelta(minutes=19),
    )
    finalized = _reserve(
        connection,
        bookings[4],
        partner_id,
        rule_id,
        period_id,
        "already-final",
        cutoff - timedelta(minutes=30),
    )
    finalize_affiliate_usage(
        connection, usage_id=finalized.usage_id, event_key="already-final-success"
    )
    released = _reserve(
        connection,
        bookings[5],
        partner_id,
        rule_id,
        period_id,
        "already-released",
        cutoff - timedelta(minutes=30),
    )
    release_affiliate_usage(
        connection, usage_id=released.usage_id, event_key="already-released-failure"
    )

    with caplog.at_level(logging.INFO, logger="flaskr.affiliate_usage"):
        first = cleanup_expired_affiliate_usages(
            connection, batch_size=2, now=cutoff
        )
        second = cleanup_expired_affiliate_usages(
            connection, batch_size=2, now=cutoff
        )
        replay = cleanup_expired_affiliate_usages(
            connection, batch_size=2, now=cutoff
        )

    assert first.released_usage_ids == tuple(item.usage_id for item in expired[:2])
    assert first.has_more is True
    assert second.released_usage_ids == (expired[2].usage_id,)
    assert second.has_more is False
    assert replay.released_count == 0
    assert replay.has_more is False
    statuses = {
        row["id"]: row["status"]
        for row in connection.execute("SELECT id, status FROM affiliate_usages")
    }
    assert statuses[fresh.usage_id] == "pending"
    assert statuses[finalized.usage_id] == "final"
    assert statuses[released.usage_id] == "released"
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_key LIKE 'expire:%'"
    ).fetchone()[0] == 3
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (1, 1)
    assert "released_count=2" in caplog.text
    assert "released_count=0" in caplog.text


def test_cleanup_backfills_legacy_expiry_and_rejects_invalid_batch_sizes(tmp_path):
    _, connection, bookings, partner_id, rule_id, period_id = _database(tmp_path)
    cutoff = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
    fresh = _reserve(
        connection,
        bookings[3],
        partner_id,
        rule_id,
        period_id,
        "legacy-cleanup-fresh",
        cutoff - timedelta(minutes=10),
    )
    expired = []
    for index in range(3):
        reservation = _reserve(
            connection,
            bookings[index],
            partner_id,
            rule_id,
            period_id,
            f"legacy-cleanup-{index}",
            cutoff - timedelta(minutes=30 - index),
        )
        expired.append(reservation)
    for index, reservation in enumerate(expired):
        connection.execute(
            """
            UPDATE affiliate_usages
               SET expires_at = NULL, created_at = ?
             WHERE id = ?
            """,
            (f"2026-11-14 13:{30 + index:02d}:00", reservation.usage_id),
        )
    connection.execute(
        """
        UPDATE affiliate_usages
           SET expires_at = NULL, created_at = '2026-11-14 13:50:00'
         WHERE id = ?
        """,
        (fresh.usage_id,),
    )
    connection.commit()

    first = cleanup_expired_affiliate_usages(connection, batch_size=2, now=cutoff)

    assert first.released_usage_ids == tuple(item.usage_id for item in expired[:2])
    assert first.has_more is True
    untouched = connection.execute(
        "SELECT id, expires_at FROM affiliate_usages WHERE id IN (?, ?) ORDER BY id",
        (expired[2].usage_id, fresh.usage_id),
    ).fetchall()
    assert {row["id"]: row["expires_at"] for row in untouched} == {
        expired[2].usage_id: None,
        fresh.usage_id: None,
    }

    second = cleanup_expired_affiliate_usages(connection, batch_size=2, now=cutoff)
    assert second.released_usage_ids == (expired[2].usage_id,)
    assert second.has_more is False
    assert connection.execute(
        "SELECT expires_at FROM affiliate_usages WHERE id = ?", (fresh.usage_id,)
    ).fetchone()[0] is None
    for invalid in (True, 0, 1001):
        with pytest.raises(ValueError, match="batch_size"):
            cleanup_expired_affiliate_usages(
                connection, batch_size=invalid, now=cutoff
            )


def test_cleanup_event_failure_rolls_back_the_entire_batch(tmp_path):
    _, connection, bookings, partner_id, rule_id, period_id = _database(tmp_path)
    cutoff = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
    reservations = [
        _reserve(
            connection,
            bookings[index],
            partner_id,
            rule_id,
            period_id,
            f"rollback-{index}",
            cutoff - timedelta(minutes=30),
        )
        for index in range(2)
    ]
    connection.execute(
        f"""
        CREATE TRIGGER reject_second_cleanup_event
        BEFORE INSERT ON affiliate_usage_events
        WHEN NEW.event_key = 'expire:{reservations[1].usage_id}'
        BEGIN
            SELECT RAISE(ABORT, 'forced cleanup event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced cleanup event failure"):
        cleanup_expired_affiliate_usages(connection, batch_size=2, now=cutoff)

    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usages WHERE status = 'pending'"
    ).fetchone()[0] == 2
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (2, 0)
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_key LIKE 'expire:%'"
    ).fetchone()[0] == 0


def test_legacy_cleanup_preserves_microseconds_at_the_exact_expiry_boundary(tmp_path):
    _, connection, bookings, partner_id, rule_id, period_id = _database(tmp_path)
    reservation = _reserve(
        connection,
        bookings[0],
        partner_id,
        rule_id,
        period_id,
        "fractional-legacy-cleanup",
        datetime(2026, 11, 14, 13, 40, 0, 123456, tzinfo=timezone.utc),
    )
    connection.execute(
        """
        UPDATE affiliate_usages
           SET expires_at = NULL, created_at = '2026-11-14 13:40:00.123456'
         WHERE id = ?
        """,
        (reservation.usage_id,),
    )
    connection.commit()

    early = cleanup_expired_affiliate_usages(
        connection,
        batch_size=1,
        now=datetime(2026, 11, 14, 14, 0, 0, 123000, tzinfo=timezone.utc),
    )
    untouched = connection.execute(
        "SELECT status, expires_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()
    assert early.released_count == 0
    assert tuple(untouched) == ("pending", None)

    exact = cleanup_expired_affiliate_usages(
        connection,
        batch_size=1,
        now=datetime(2026, 11, 14, 14, 0, 0, 123456, tzinfo=timezone.utc),
    )
    released = connection.execute(
        "SELECT status, expires_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()
    assert exact.released_usage_ids == (reservation.usage_id,)
    assert tuple(released) == ("released", "2026-11-14 14:00:00.123456")


def test_parallel_cleanup_workers_release_each_expired_usage_once(tmp_path):
    path, seed, bookings, partner_id, rule_id, period_id = _database(tmp_path)
    cutoff = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
    reservation = _reserve(
        seed,
        bookings[0],
        partner_id,
        rule_id,
        period_id,
        "parallel-cleanup",
        cutoff - timedelta(minutes=30),
    )
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt():
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            result = cleanup_expired_affiliate_usages(
                connection, batch_size=1, now=cutoff
            )
            outcome = ("ok", result.released_count)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == [("ok", 0), ("ok", 1)]
    verification = _connect(path)
    assert verification.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (reservation.usage_id,)
    ).fetchone()[0] == "released"
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_key = ?",
        (f"expire:{reservation.usage_id}",),
    ).fetchone()[0] == 1
    verification.close()


def test_cleanup_cli_processes_one_bounded_batch(tmp_path):
    path, seed, bookings, partner_id, rule_id, period_id = _database(tmp_path)
    old = datetime(2000, 1, 1, tzinfo=timezone.utc)
    for index in range(2):
        _reserve(
            seed,
            bookings[index],
            partner_id,
            rule_id,
            period_id,
            f"cli-cleanup-{index}",
            old,
        )
    seed.close()
    app = Flask(__name__)
    app.config.update(TESTING=True, DATABASE=str(path))
    db_module.init_app(app)

    first = app.test_cli_runner().invoke(
        args=["cleanup-affiliate-usages", "--batch-size", "1"]
    )
    second = app.test_cli_runner().invoke(
        args=["cleanup-affiliate-usages", "--batch-size", "1"]
    )

    assert first.exit_code == 0
    assert "released=1, has_more=yes" in first.output
    assert second.exit_code == 0
    assert "released=1, has_more=no" in second.output
