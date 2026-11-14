import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from flaskr.affiliate_migration import migrate_affiliate_schema
from flaskr.affiliate_usage import (
    AffiliateUsageConfigurationError,
    AffiliateUsageConflict,
    AffiliateUsageLimitExceeded,
    finalize_affiliate_usage,
    release_affiliate_usage,
    return_affiliate_usage,
    reserve_affiliate_usage,
)


def _connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _guest_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _database(tmp_path, *, total_limit, guest_limit, period_type="lifetime"):
    path = tmp_path / "usage-reservation.sqlite"
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
        VALUES ('Keret teszt', '2027-06-01', '09:00', 10000, ?)
        """,
        (location_id,),
    ).lastrowid
    booking_ids = []
    for number in (1, 2, 3):
        booking_ids.append(
            connection.execute(
                """
                INSERT INTO bookings (
                    tour_id, order_ref, customer_name, customer_email,
                    participants_count, total_price
                ) VALUES (?, ?, 'Teszt Vendég', ?, 1, 10000)
                """,
                (tour_id, f"BUD-01-{number}", f"guest{number}@example.test"),
            ).lastrowid
        )
    partner_id = connection.execute(
        "INSERT INTO affiliate_partners (ref_code, name) VALUES ('BUDGET01', 'Partner')"
    ).lastrowid
    rule_id = connection.execute(
        """
        INSERT INTO affiliate_rule_versions (
            partner_id, version_number, status, discount_type,
            total_usage_limit, guest_usage_limit, budget_period_type
        ) VALUES (?, 1, 'active', 'tracking', ?, ?, ?)
        """,
        (partner_id, total_limit, guest_limit, period_type),
    ).lastrowid
    connection.commit()
    return path, connection, booking_ids, partner_id, rule_id


def _reserve(
    connection,
    *,
    key,
    booking_id,
    partner_id,
    rule_id,
    guest=None,
    quantity=1,
    period_id=None,
    now=None,
):
    return reserve_affiliate_usage(
        connection,
        idempotency_key=key,
        booking_id=booking_id,
        partner_id=partner_id,
        rule_version_id=rule_id,
        budget_period_id=period_id,
        guest_key_hash=guest or _guest_hash("guest-key"),
        quantity=quantity,
        now=now,
    )


def test_idempotent_replay_returns_existing_reservation_without_double_count(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=2, guest_limit=2
    )

    created = _reserve(
        connection,
        key="reserve-1",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )
    replayed = _reserve(
        connection,
        key="reserve-1",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )

    assert created.created is True
    assert replayed.created is False
    assert replayed.usage_id == created.usage_id
    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM affiliate_usage_events").fetchone()[0] == 1


def test_idempotency_key_rejects_a_different_payload(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=3, guest_limit=3
    )
    _reserve(
        connection,
        key="reserve-1",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )

    with pytest.raises(AffiliateUsageConflict, match="payload mismatch"):
        _reserve(
            connection,
            key="reserve-1",
            booking_id=booking_ids[1],
            partner_id=partner_id,
            rule_id=rule_id,
        )

    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 1


@pytest.mark.parametrize(
    ("total_limit", "guest_limit", "guest_keys", "expected_limit"),
    [
        (1, 2, (_guest_hash("guest-a"), _guest_hash("guest-b")), "total"),
        (2, 1, (_guest_hash("guest-a"), _guest_hash("guest-a")), "guest"),
    ],
)
def test_parallel_reservations_cannot_exceed_total_or_guest_limit(
    tmp_path, total_limit, guest_limit, guest_keys, expected_limit
):
    path, seed, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=total_limit, guest_limit=guest_limit
    )
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt(index):
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            reservation = _reserve(
                connection,
                key=f"parallel-{index}",
                booking_id=booking_ids[index],
                partner_id=partner_id,
                rule_id=rule_id,
                guest=guest_keys[index],
            )
            outcome = ("created", reservation.usage_id)
        except AffiliateUsageLimitExceeded as exc:
            outcome = ("limited", exc.limit)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcome[0] for outcome in outcomes) == ["created", "limited"]
    assert ("limited", expected_limit) in outcomes
    verification = _connect(path)
    usage_totals = verification.execute(
        "SELECT COUNT(*), SUM(quantity) FROM affiliate_usages WHERE status = 'pending'"
    ).fetchone()
    assert tuple(usage_totals) == (1, 1)
    verification.close()


def test_period_counter_and_conditional_limit_move_together(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 1)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()

    _reserve(
        connection,
        key="period-1",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )
    with pytest.raises(AffiliateUsageLimitExceeded) as exc_info:
        _reserve(
            connection,
            key="period-2",
            booking_id=booking_ids[1],
            partner_id=partner_id,
            rule_id=rule_id,
            period_id=period_id,
        )

    assert exc_info.value.limit == "total"
    period_counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(period_counters) == (1, 0)
    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 1


def test_event_failure_rolls_back_usage_and_period_counter(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.execute(
        """
        CREATE TRIGGER reject_usage_event
        BEFORE INSERT ON affiliate_usage_events
        BEGIN
            SELECT RAISE(ABORT, 'forced event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced event failure"):
        _reserve(
            connection,
            key="rollback-event",
            booking_id=booking_ids[0],
            partner_id=partner_id,
            rule_id=rule_id,
            period_id=period_id,
        )

    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 0
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 0)


def test_nested_reservation_does_not_commit_callers_transaction(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=2, guest_limit=2
    )
    connection.execute("BEGIN")
    connection.execute(
        "UPDATE affiliate_partners SET name = 'Tranzakción belüli név' WHERE id = ?",
        (partner_id,),
    )

    reservation = _reserve(
        connection,
        key="nested-transaction",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )

    assert reservation.created is True
    assert connection.in_transaction is True
    connection.rollback()
    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 0
    partner_name = connection.execute(
        "SELECT name FROM affiliate_partners WHERE id = ?", (partner_id,)
    ).fetchone()[0]
    assert partner_name == "Partner"


def test_drifted_period_counter_fails_closed_without_a_usage_row(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at,
            usage_limit, reserved_usage
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2, 1)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()

    with pytest.raises(AffiliateUsageConfigurationError, match="counters are inconsistent"):
        _reserve(
            connection,
            key="drifted-counter",
            booking_id=booking_ids[0],
            partner_id=partner_id,
            rule_id=rule_id,
            period_id=period_id,
        )

    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 0


@pytest.mark.parametrize(
    "invalid_guest_key",
    ["guest@example.test", "a" * 63, "A" * 64],
)
def test_noncanonical_guest_identity_is_rejected_before_write(
    tmp_path, invalid_guest_key
):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=2, guest_limit=1
    )

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _reserve(
            connection,
            key="invalid-guest-key",
            booking_id=booking_ids[0],
            partner_id=partner_id,
            rule_id=rule_id,
            guest=invalid_guest_key,
        )

    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 0


def test_parallel_period_reservations_cannot_exceed_period_limit(tmp_path):
    path, seed, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = seed.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 1)
        """,
        (partner_id, rule_id),
    ).lastrowid
    seed.commit()
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt(index):
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            reservation = _reserve(
                connection,
                key=f"parallel-period-{index}",
                booking_id=booking_ids[index],
                partner_id=partner_id,
                rule_id=rule_id,
                guest=_guest_hash(f"period-guest-{index}"),
                period_id=period_id,
            )
            outcome = ("created", reservation.usage_id)
        except AffiliateUsageLimitExceeded as exc:
            outcome = ("limited", exc.limit)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcome[0] for outcome in outcomes) == ["created", "limited"]
    assert ("limited", "total") in outcomes
    verification = _connect(path)
    assert verification.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 1
    counters = verification.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (1, 0)
    verification.close()


def test_reservation_expires_exactly_twenty_minutes_after_start(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=2, guest_limit=2
    )
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)

    reservation = _reserve(
        connection,
        key="twenty-minute-window",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        now=started_at,
    )

    assert reservation.status == "pending"
    assert reservation.expires_at == "2026-11-14 13:20:00.000000"
    stored_expiry = connection.execute(
        "SELECT expires_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()[0]
    assert stored_expiry == reservation.expires_at


def test_expired_lifetime_reservation_no_longer_blocks_limit(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    first = _reserve(
        connection,
        key="expiring-first",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("first-guest"),
        now=started_at,
    )

    with pytest.raises(AffiliateUsageLimitExceeded):
        _reserve(
            connection,
            key="after-expiry",
            booking_id=booking_ids[1],
            partner_id=partner_id,
            rule_id=rule_id,
            guest=_guest_hash("second-guest"),
            now=started_at + timedelta(minutes=19, seconds=59),
        )

    second = _reserve(
        connection,
        key="after-expiry",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("second-guest"),
        now=started_at + timedelta(minutes=20),
    )

    assert second.created is True
    statuses = connection.execute(
        "SELECT id, status FROM affiliate_usages ORDER BY id"
    ).fetchall()
    assert [(row["id"], row["status"]) for row in statuses] == [
        (first.usage_id, "released"),
        (second.usage_id, "pending"),
    ]
    release_events = connection.execute(
        "SELECT event_type, event_key FROM affiliate_usage_events WHERE usage_id = ?",
        (first.usage_id,),
    ).fetchall()
    assert [(row["event_type"], row["event_key"]) for row in release_events] == [
        ("reserve", "reserve:expiring-first"),
        ("release", f"expire:{first.usage_id}"),
    ]


def test_expired_period_reservation_releases_counter_before_replacement(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 1)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    _reserve(
        connection,
        key="period-expiring",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
        now=started_at,
    )

    replacement = _reserve(
        connection,
        key="period-replacement",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
        now=started_at + timedelta(minutes=20),
    )

    assert replacement.created is True
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (1, 0)
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usages WHERE status = 'released'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usages WHERE status = 'pending'"
    ).fetchone()[0] == 1


def test_expired_idempotent_replay_returns_released_reservation(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    created = _reserve(
        connection,
        key="expired-replay",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        now=started_at,
    )

    replayed = _reserve(
        connection,
        key="expired-replay",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        now=started_at + timedelta(minutes=20),
    )

    assert replayed.usage_id == created.usage_id
    assert replayed.created is False
    assert replayed.status == "released"
    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_type = 'release'"
    ).fetchone()[0] == 1


def test_reservation_clock_must_be_timezone_aware(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        _reserve(
            connection,
            key="naive-clock",
            booking_id=booking_ids[0],
            partner_id=partner_id,
            rule_id=rule_id,
            now=datetime(2026, 11, 14, 13, 0, 0),
        )

    assert connection.execute("SELECT COUNT(*) FROM affiliate_usages").fetchone()[0] == 0


def test_fractional_second_reservation_keeps_the_full_twenty_minute_window(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    started_at = datetime(
        2026, 11, 14, 13, 0, 0, 999999, tzinfo=timezone.utc
    )

    reservation = _reserve(
        connection,
        key="fractional-window",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        now=started_at,
    )

    assert reservation.expires_at == "2026-11-14 13:20:00.999999"
    with pytest.raises(AffiliateUsageLimitExceeded):
        _reserve(
            connection,
            key="fractional-too-early",
            booking_id=booking_ids[1],
            partner_id=partner_id,
            rule_id=rule_id,
            guest=_guest_hash("fractional-second-guest"),
            now=started_at + timedelta(minutes=20) - timedelta(microseconds=1),
        )


def test_parallel_replacements_at_expiry_release_once_and_keep_period_bounded(tmp_path):
    path, seed, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = seed.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 1)
        """,
        (partner_id, rule_id),
    ).lastrowid
    seed.commit()
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    expired = _reserve(
        seed,
        key="period-race-expired",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
        now=started_at,
    )
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt(index):
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            reservation = _reserve(
                connection,
                key=f"period-race-replacement-{index}",
                booking_id=booking_ids[index + 1],
                partner_id=partner_id,
                rule_id=rule_id,
                guest=_guest_hash(f"period-race-guest-{index}"),
                period_id=period_id,
                now=started_at + timedelta(minutes=20),
            )
            outcome = ("created", reservation.usage_id)
        except AffiliateUsageLimitExceeded as exc:
            outcome = ("limited", exc.limit)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcome[0] for outcome in outcomes) == ["created", "limited"]
    assert ("limited", "total") in outcomes
    verification = _connect(path)
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'release'",
        (expired.usage_id,),
    ).fetchone()[0] == 1
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usages WHERE status = 'released'"
    ).fetchone()[0] == 1
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usages WHERE status = 'pending'"
    ).fetchone()[0] == 1
    counters = verification.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (1, 0)
    verification.close()


def test_legacy_pending_row_without_expiry_uses_created_at_window(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    legacy = _reserve(
        connection,
        key="legacy-null-expiry",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("legacy-guest"),
        now=started_at,
    )
    connection.execute(
        """
        UPDATE affiliate_usages
           SET expires_at = NULL, created_at = '2026-11-14 13:00:00'
         WHERE id = ?
        """,
        (legacy.usage_id,),
    )
    connection.commit()

    replacement = _reserve(
        connection,
        key="legacy-null-replacement",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("replacement-guest"),
        now=started_at + timedelta(minutes=20),
    )

    assert replacement.created is True
    legacy_row = connection.execute(
        "SELECT status, expires_at FROM affiliate_usages WHERE id = ?",
        (legacy.usage_id,),
    ).fetchone()
    assert legacy_row["status"] == "released"
    assert legacy_row["expires_at"] == "2026-11-14 13:20:00.000"


def test_successful_period_usage_finalizes_counters_and_is_idempotent(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    reservation = _reserve(
        connection,
        key="finalize-period",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
        now=started_at,
    )

    finalized = finalize_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key="simplepay-success-1",
        now=started_at + timedelta(minutes=1),
    )
    replayed = finalize_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key="simplepay-success-1",
        now=started_at + timedelta(minutes=2),
    )
    alternate_replay = finalize_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key="simplepay-success-1-duplicate",
        now=started_at + timedelta(minutes=3),
    )

    assert finalized.changed is True
    assert finalized.status == "final"
    assert replayed.changed is False
    assert alternate_replay.changed is False
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 1)
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_type = 'finalize'"
    ).fetchone()[0] == 2


def test_all_accepted_callback_keys_remain_bound_to_the_final_usage(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=3, guest_limit=3
    )
    first = _reserve(
        connection,
        key="callback-binding-first",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )
    second = _reserve(
        connection,
        key="callback-binding-second",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("callback-binding-second"),
    )

    finalize_affiliate_usage(
        connection, usage_id=first.usage_id, event_key="callback-key-primary"
    )
    replay = finalize_affiliate_usage(
        connection, usage_id=first.usage_id, event_key="callback-key-alternate"
    )

    assert replay.changed is False
    for event_key in ("callback-key-primary", "callback-key-alternate"):
        with pytest.raises(AffiliateUsageConflict, match="payload mismatch"):
            finalize_affiliate_usage(
                connection, usage_id=second.usage_id, event_key=event_key
            )
    assert connection.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (second.usage_id,)
    ).fetchone()[0] == "pending"
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'finalize'",
        (first.usage_id,),
    ).fetchone()[0] == 2


def test_delayed_success_can_finalize_a_still_pending_reservation(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    reservation = _reserve(
        connection,
        key="delayed-success",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        now=started_at,
    )

    finalized = finalize_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key="delayed-simplepay-success",
        now=started_at + timedelta(minutes=21),
    )

    assert finalized.changed is True
    assert connection.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (reservation.usage_id,)
    ).fetchone()[0] == "final"


def test_released_usage_cannot_be_finalized(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    expired = _reserve(
        connection,
        key="released-before-success",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("expired-before-success"),
        now=started_at,
    )
    _reserve(
        connection,
        key="replacement-before-success",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("replacement-before-success"),
        now=started_at + timedelta(minutes=20),
    )

    with pytest.raises(AffiliateUsageConflict, match="released"):
        finalize_affiliate_usage(
            connection,
            usage_id=expired.usage_id,
            event_key="late-after-release",
            now=started_at + timedelta(minutes=21),
        )

    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_type = 'finalize'"
    ).fetchone()[0] == 0


def test_finalize_event_failure_rolls_back_status_and_period_counters(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    reservation = _reserve(
        connection,
        key="finalize-rollback",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )
    connection.execute(
        """
        CREATE TRIGGER reject_finalize_event
        BEFORE INSERT ON affiliate_usage_events
        WHEN NEW.event_type = 'finalize'
        BEGIN
            SELECT RAISE(ABORT, 'forced finalize event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced finalize event failure"):
        finalize_affiliate_usage(
            connection,
            usage_id=reservation.usage_id,
            event_key="rejected-finalize",
        )

    usage = connection.execute(
        "SELECT status, finalized_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()
    assert tuple(usage) == ("pending", None)
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (1, 0)


def test_parallel_success_callbacks_finalize_once(tmp_path):
    path, seed, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = seed.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    seed.commit()
    reservation = _reserve(
        seed,
        key="parallel-finalize",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt(index):
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            result = finalize_affiliate_usage(
                connection,
                usage_id=reservation.usage_id,
                event_key=f"parallel-success-{index}",
            )
            outcome = ("ok", result.changed)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == [("ok", False), ("ok", True)]
    verification = _connect(path)
    counters = verification.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 1)
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE event_type = 'finalize'"
    ).fetchone()[0] == 2
    verification.close()


def test_finalize_and_exact_expiry_replacement_serialize_coherently(tmp_path):
    path, seed, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = seed.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 1)
        """,
        (partner_id, rule_id),
    ).lastrowid
    seed.commit()
    started_at = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    original = _reserve(
        seed,
        key="finalize-expiry-original",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
        now=started_at,
    )
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def finalize_original():
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            result = finalize_affiliate_usage(
                connection,
                usage_id=original.usage_id,
                event_key="finalize-expiry-success",
                now=started_at + timedelta(minutes=20),
            )
            outcome = ("finalize", "changed" if result.changed else "replayed")
        except AffiliateUsageConflict:
            outcome = ("finalize", "conflict")
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    def reserve_replacement():
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            replacement = _reserve(
                connection,
                key="finalize-expiry-replacement",
                booking_id=booking_ids[1],
                partner_id=partner_id,
                rule_id=rule_id,
                guest=_guest_hash("finalize-expiry-replacement"),
                period_id=period_id,
                now=started_at + timedelta(minutes=20),
            )
            outcome = ("reserve", "created", replacement.usage_id)
        except AffiliateUsageLimitExceeded as exc:
            outcome = ("reserve", "limited", exc.limit)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=finalize_original),
        threading.Thread(target=reserve_replacement),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert all(outcome[0] != "error" for outcome in outcomes)
    verification = _connect(path)
    original_row = verification.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (original.usage_id,)
    ).fetchone()
    counters = verification.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    lifecycle_events = verification.execute(
        "SELECT event_type FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type IN ('release', 'finalize')",
        (original.usage_id,),
    ).fetchall()

    if original_row["status"] == "final":
        assert ("finalize", "changed") in outcomes
        assert any(outcome[:2] == ("reserve", "limited") for outcome in outcomes)
        assert tuple(counters) == (0, 1)
        assert [row["event_type"] for row in lifecycle_events] == ["finalize"]
    else:
        assert original_row["status"] == "released"
        assert ("finalize", "conflict") in outcomes
        assert any(outcome[:2] == ("reserve", "created") for outcome in outcomes)
        assert tuple(counters) == (1, 0)
        assert [row["event_type"] for row in lifecycle_events] == ["release"]
    verification.close()


@pytest.mark.parametrize("failure_kind", ["failed", "cancelled", "timeout"])
def test_payment_failure_paths_release_period_budget_once(tmp_path, failure_kind):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    reservation = _reserve(
        connection,
        key=f"release-{failure_kind}",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )

    released = release_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key=f"payment-{failure_kind}-1",
    )
    replayed = release_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key=f"payment-{failure_kind}-1",
    )
    alternate = release_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key=f"payment-{failure_kind}-duplicate",
    )

    assert released.changed is True
    assert replayed.changed is False
    assert alternate.changed is False
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 0)
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'release'",
        (reservation.usage_id,),
    ).fetchone()[0] == 2


def test_release_callback_keys_cannot_be_reused_for_another_usage(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=3, guest_limit=3
    )
    first = _reserve(
        connection,
        key="release-binding-first",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )
    second = _reserve(
        connection,
        key="release-binding-second",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("release-binding-second"),
    )
    release_affiliate_usage(
        connection, usage_id=first.usage_id, event_key="release-key-primary"
    )
    release_affiliate_usage(
        connection, usage_id=first.usage_id, event_key="release-key-alternate"
    )

    for event_key in ("release-key-primary", "release-key-alternate"):
        with pytest.raises(AffiliateUsageConflict, match="payload mismatch"):
            release_affiliate_usage(
                connection, usage_id=second.usage_id, event_key=event_key
            )
    assert connection.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (second.usage_id,)
    ).fetchone()[0] == "pending"


def test_final_usage_cannot_be_released(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    reservation = _reserve(
        connection,
        key="final-before-release",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )
    finalize_affiliate_usage(
        connection, usage_id=reservation.usage_id, event_key="final-before-release-success"
    )

    with pytest.raises(AffiliateUsageConflict, match="final"):
        release_affiliate_usage(
            connection,
            usage_id=reservation.usage_id,
            event_key="final-before-release-failure",
        )


def test_release_event_failure_rolls_back_status_and_period_counter(tmp_path):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    reservation = _reserve(
        connection,
        key="release-rollback",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )
    connection.execute(
        """
        CREATE TRIGGER reject_manual_release_event
        BEFORE INSERT ON affiliate_usage_events
        WHEN NEW.event_key = 'rejected-release'
        BEGIN
            SELECT RAISE(ABORT, 'forced release event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced release event failure"):
        release_affiliate_usage(
            connection,
            usage_id=reservation.usage_id,
            event_key="rejected-release",
        )

    usage = connection.execute(
        "SELECT status, released_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()
    assert tuple(usage) == ("pending", None)
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (1, 0)


def test_parallel_release_callbacks_return_budget_once(tmp_path):
    path, seed, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = seed.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    seed.commit()
    reservation = _reserve(
        seed,
        key="parallel-release",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt(index):
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            result = release_affiliate_usage(
                connection,
                usage_id=reservation.usage_id,
                event_key=f"parallel-release-{index}",
            )
            outcome = ("ok", result.changed)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == [("ok", False), ("ok", True)]
    verification = _connect(path)
    counters = verification.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 0)
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'release'",
        (reservation.usage_id,),
    ).fetchone()[0] == 2
    verification.close()


def _finalized_period_usage(tmp_path, *, key="return-period"):
    path, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=5, guest_limit=None, period_type="monthly"
    )
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
        ) VALUES (?, ?, '2026-11', '2026-11-01', '2026-12-01', 3)
        """,
        (partner_id, rule_id),
    ).lastrowid
    connection.commit()
    reservation = _reserve(
        connection,
        key=key,
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
        period_id=period_id,
    )
    finalize_affiliate_usage(
        connection,
        usage_id=reservation.usage_id,
        event_key=f"{key}-success",
    )
    return path, connection, booking_ids, partner_id, rule_id, period_id, reservation


def test_returned_period_usage_decrements_finalized_once_and_binds_keys(tmp_path):
    _, connection, _, _, _, period_id, reservation = _finalized_period_usage(tmp_path)

    returned = return_affiliate_usage(
        connection, usage_id=reservation.usage_id, event_key="refund-primary"
    )
    replayed = return_affiliate_usage(
        connection, usage_id=reservation.usage_id, event_key="refund-primary"
    )
    alternate = return_affiliate_usage(
        connection, usage_id=reservation.usage_id, event_key="refund-alternate"
    )

    assert returned.changed is True
    assert replayed.changed is False
    assert alternate.changed is False
    usage = connection.execute(
        "SELECT status, returned_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()
    assert usage["status"] == "returned"
    assert usage["returned_at"] is not None
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 0)
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'return'",
        (reservation.usage_id,),
    ).fetchone()[0] == 2


def test_return_callback_keys_cannot_be_reused_for_another_usage(tmp_path):
    _, connection, booking_ids, partner_id, rule_id, period_id, first = _finalized_period_usage(
        tmp_path, key="return-binding-first"
    )
    second = _reserve(
        connection,
        key="return-binding-second",
        booking_id=booking_ids[1],
        partner_id=partner_id,
        rule_id=rule_id,
        guest=_guest_hash("return-binding-second"),
        period_id=period_id,
    )
    finalize_affiliate_usage(
        connection, usage_id=second.usage_id, event_key="return-binding-second-success"
    )
    return_affiliate_usage(
        connection, usage_id=first.usage_id, event_key="return-key-primary"
    )
    return_affiliate_usage(
        connection, usage_id=first.usage_id, event_key="return-key-alternate"
    )

    for event_key in ("return-key-primary", "return-key-alternate"):
        with pytest.raises(AffiliateUsageConflict, match="payload mismatch"):
            return_affiliate_usage(
                connection, usage_id=second.usage_id, event_key=event_key
            )
    assert connection.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (second.usage_id,)
    ).fetchone()[0] == "final"


@pytest.mark.parametrize("source_status", ["pending", "released"])
def test_nonfinal_usage_cannot_be_returned(tmp_path, source_status):
    _, connection, booking_ids, partner_id, rule_id = _database(
        tmp_path, total_limit=1, guest_limit=1
    )
    reservation = _reserve(
        connection,
        key=f"return-from-{source_status}",
        booking_id=booking_ids[0],
        partner_id=partner_id,
        rule_id=rule_id,
    )
    if source_status == "released":
        release_affiliate_usage(
            connection,
            usage_id=reservation.usage_id,
            event_key="release-before-return",
        )

    with pytest.raises(AffiliateUsageConflict, match=source_status):
        return_affiliate_usage(
            connection,
            usage_id=reservation.usage_id,
            event_key=f"invalid-return-{source_status}",
        )


def test_return_fails_closed_for_missing_finalize_event_or_counter_drift(tmp_path):
    _, connection, _, _, _, period_id, reservation = _finalized_period_usage(tmp_path)
    connection.execute(
        "DELETE FROM affiliate_usage_events WHERE usage_id = ? AND event_type = 'finalize'",
        (reservation.usage_id,),
    )
    connection.commit()

    with pytest.raises(AffiliateUsageConfigurationError, match="finalization event"):
        return_affiliate_usage(
            connection, usage_id=reservation.usage_id, event_key="missing-finalize"
        )

    connection.execute(
        """
        INSERT INTO affiliate_usage_events (usage_id, event_key, event_type)
        VALUES (?, 'restored-finalize', 'finalize')
        """,
        (reservation.usage_id,),
    )
    connection.execute(
        "UPDATE affiliate_budget_periods SET finalized_usage = 2 WHERE id = ?",
        (period_id,),
    )
    connection.commit()
    with pytest.raises(AffiliateUsageConfigurationError, match="budget counters"):
        return_affiliate_usage(
            connection, usage_id=reservation.usage_id, event_key="drifted-return"
        )
    assert connection.execute(
        "SELECT status FROM affiliate_usages WHERE id = ?", (reservation.usage_id,)
    ).fetchone()[0] == "final"


def test_returned_replays_require_the_complete_finalize_return_audit_chain(tmp_path):
    _, connection, _, _, _, _, reservation = _finalized_period_usage(tmp_path)
    return_affiliate_usage(
        connection, usage_id=reservation.usage_id, event_key="return-chain-primary"
    )
    connection.execute(
        "DELETE FROM affiliate_usage_events WHERE usage_id = ? AND event_type = 'finalize'",
        (reservation.usage_id,),
    )
    connection.commit()

    for event_key in ("return-chain-primary", "return-chain-alternate"):
        with pytest.raises(
            AffiliateUsageConfigurationError, match="finalize/return audit chain"
        ):
            return_affiliate_usage(
                connection, usage_id=reservation.usage_id, event_key=event_key
            )
    assert connection.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'return'",
        (reservation.usage_id,),
    ).fetchone()[0] == 1

    connection.execute(
        """
        INSERT INTO affiliate_usage_events (usage_id, event_key, event_type)
        VALUES (?, 'return-chain-restored-finalize', 'finalize')
        """,
        (reservation.usage_id,),
    )
    connection.execute(
        "DELETE FROM affiliate_usage_events WHERE usage_id = ? AND event_type = 'return'",
        (reservation.usage_id,),
    )
    connection.commit()
    with pytest.raises(
        AffiliateUsageConfigurationError, match="finalize/return audit chain"
    ):
        return_affiliate_usage(
            connection,
            usage_id=reservation.usage_id,
            event_key="return-chain-missing-return",
        )


def test_return_event_failure_rolls_back_status_and_period_counter(tmp_path):
    _, connection, _, _, _, period_id, reservation = _finalized_period_usage(tmp_path)
    connection.execute(
        """
        CREATE TRIGGER reject_return_event
        BEFORE INSERT ON affiliate_usage_events
        WHEN NEW.event_type = 'return'
        BEGIN
            SELECT RAISE(ABORT, 'forced return event failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced return event failure"):
        return_affiliate_usage(
            connection, usage_id=reservation.usage_id, event_key="rejected-return"
        )

    usage = connection.execute(
        "SELECT status, returned_at FROM affiliate_usages WHERE id = ?",
        (reservation.usage_id,),
    ).fetchone()
    assert tuple(usage) == ("final", None)
    counters = connection.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 1)


def test_parallel_return_callbacks_return_finalized_budget_once(tmp_path):
    path, seed, _, _, _, period_id, reservation = _finalized_period_usage(tmp_path)
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def attempt(index):
        connection = _connect(path)
        try:
            barrier.wait(timeout=5)
            result = return_affiliate_usage(
                connection,
                usage_id=reservation.usage_id,
                event_key=f"parallel-return-{index}",
            )
            outcome = ("ok", result.changed)
        except Exception as exc:  # Surface unexpected thread failures in the test.
            outcome = ("error", repr(exc))
        finally:
            connection.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == [("ok", False), ("ok", True)]
    verification = _connect(path)
    counters = verification.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (period_id,),
    ).fetchone()
    assert tuple(counters) == (0, 0)
    assert verification.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events "
        "WHERE usage_id = ? AND event_type = 'return'",
        (reservation.usage_id,),
    ).fetchone()[0] == 2
    verification.close()
