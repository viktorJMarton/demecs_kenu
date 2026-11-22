"""Settlement preview integration tests against the migrated SQLite schema."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from flaskr.affiliate_migration import migrate_affiliate_schema
from flaskr.affiliate_settlement import preview_affiliate_settlement


def test_settlement_preview_uses_locked_unsettled_paid_items_and_budapest_dates():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(Path("flaskr/schema.sql").read_text(encoding="utf-8"))
    migrate_affiliate_schema(db)
    db.execute("INSERT INTO affiliate_partners (id, ref_code, name) VALUES (1, 'PARTNER1', 'Partner'), (2, 'PARTNER2', 'Other')")
    db.execute(
        "INSERT INTO affiliate_rule_versions (id, partner_id, version_number, discount_type) "
        "VALUES (1, 1, 1, 'fixed'), (2, 2, 1, 'fixed')"
    )

    def booking(ref, paid_at, *, partner=1, status="paid", commission="earned", locked=1, cancelled=None, amount=1000):
        return db.execute(
            """
            INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email, total_price, payment_date,
                payment_status, affiliate_partner_id, affiliate_rule_version_id,
                affiliate_original_price, affiliate_discount_amount, affiliate_payable_price,
                affiliate_commission_type, affiliate_commission_value, affiliate_commission_amount,
                affiliate_commission_status, affiliate_snapshot_locked, cancellation_date
            ) VALUES (1, ?, 'Guest', 'fixture@example.invalid', 8000, ?, ?, ?, ?,
                      10000, 2000, 8000, 'fixed', ?, ?, ?, ?, ?)
            """,
            (ref, paid_at, status, partner, partner, amount, amount, commission, locked, cancelled),
        ).lastrowid

    # The spring clock-change day is 23 hours long, from 23:00 to 22:00 UTC.
    day = date(2026, 3, 29)
    first = booking("open-boundary", "2026-03-28 23:00:00")
    second = booking("same-second", "2026-03-28 23:00:00", amount=500)
    third = booking("closing-second", "2026-03-29 21:59:59", amount=700)
    booking("too-early", "2026-03-28 22:59:59")
    booking("too-late", "2026-03-29 22:00:00")
    booking("other-partner", "2026-03-29 12:00:00", partner=2)
    booking("refunded", "2026-03-29 12:00:00", status="refunded")
    booking("cancelled", "2026-03-29 12:00:00", cancelled="2026-03-30 12:00:00")
    booking("reversed", "2026-03-29 12:00:00", commission="reversed")
    booking("unlocked", "2026-03-29 12:00:00", locked=0)
    prepared_booking = booking("already-prepared", "2026-03-29 12:00:00")
    header = db.execute(
        """
        INSERT INTO affiliate_settlements (
            settlement_ref, partner_id, period_start, period_end, partner_name_snapshot
        ) VALUES ('PREPARED', 1, '2026-03-29', '2026-03-29', 'Partner')
        """
    ).lastrowid
    db.execute(
        """
        INSERT INTO affiliate_settlement_items (
            settlement_id, booking_id, partner_id, rule_version_id, original_amount,
            discount_amount, paid_amount, commission_amount, commission_type, commission_value
        ) VALUES (?, ?, 1, 1, 10000, 2000, 8000, 1000, 'fixed', 1000)
        """,
        (header, prepared_booking),
    )
    db.commit()

    writes = db.total_changes
    result = preview_affiliate_settlement(db, 1, day, day)
    assert [item.booking_id for item in result.items] == [first, second, third]
    assert [item.commission_amount for item in result.items] == [1000, 500, 700]
    assert (
        result.original_amount_total, result.discount_amount_total,
        result.paid_amount_total, result.commission_amount_total,
    ) == (30000, 6000, 24000, 2200)
    assert preview_affiliate_settlement(db, 1, day, day) == result
    empty = preview_affiliate_settlement(db, 99, day, day)
    assert empty.items == () and empty.commission_amount_total == 0
    assert db.total_changes == writes

    with pytest.raises(ValueError):
        preview_affiliate_settlement(db, True, day, day)
    with pytest.raises(ValueError):
        preview_affiliate_settlement(db, 1, day, date(2026, 3, 28))
    db.close()
