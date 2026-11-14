import sqlite3
import threading

import pytest

from flaskr.affiliate_migration import migrate_affiliate_schema
from flaskr.affiliate_usage import (
    AffiliateUsageConflict,
    AffiliateUsageLimitExceeded,
    reserve_affiliate_usage,
)


def _connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


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
    guest="guest-key",
    quantity=1,
    period_id=None,
):
    return reserve_affiliate_usage(
        connection,
        idempotency_key=key,
        booking_id=booking_id,
        partner_id=partner_id,
        rule_version_id=rule_id,
        budget_period_id=period_id,
        guest_key_hash=guest,
        quantity=quantity,
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
        (1, 2, ("guest-a", "guest-b"), "total"),
        (2, 1, ("guest-a", "guest-a"), "guest"),
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
