"""Commission snapshot finalization and callback replay coverage."""

import pytest

from flaskr.affiliate_commission_lifecycle import (
    AffiliateCommissionLifecycleError,
    finalize_booking_commission,
)
from flaskr.db import get_db
from flaskr.payment import _apply_back_status, _force_booking_paid


@pytest.fixture
def commission_booking(app):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES ('SET02', 'SET-02 Partner')"
        ).lastrowid
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type,
                commission_type, commission_value
            ) VALUES (?, 1, 'active', 'tracking', 'percentage', 10)
            """,
            (partner_id,),
        ).lastrowid
        booking_id = db.execute(
            """
            INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email,
                participants_count, total_price, payment_status,
                affiliate_partner_id, affiliate_rule_version_id,
                affiliate_original_price, affiliate_discount_amount,
                affiliate_payable_price, affiliate_commission_type,
                affiliate_commission_value, affiliate_commission_amount,
                affiliate_commission_status, affiliate_snapshot_locked
            ) VALUES (
                1, 'SET02-ORDER', 'Teszt Elek', 'set02@example.invalid',
                2, 18000, 'pending', ?, ?, 20000, 2000, 18000,
                'percentage', 10, 1800, 'pending', 0
            )
            """,
            (partner_id, rule_id),
        ).lastrowid
        db.execute(
            """
            INSERT INTO payment_transactions (booking_id, order_ref, amount, status)
            VALUES (?, 'SET02-ORDER', 18000, 'pending')
            """,
            (booking_id,),
        )
        db.commit()
        try:
            yield db, booking_id, rule_id
        finally:
            db.execute("DELETE FROM affiliate_audit_log WHERE booking_id = ?", (booking_id,))
            db.execute("DELETE FROM payment_transactions WHERE booking_id = ?", (booking_id,))
            db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            db.execute("DELETE FROM affiliate_rule_versions WHERE id = ?", (rule_id,))
            db.execute("DELETE FROM affiliate_partners WHERE id = ?", (partner_id,))
            db.commit()


def test_success_callback_earns_locked_snapshot_exactly_once(commission_booking):
    db, booking_id, rule_id = commission_booking

    db.execute(
        "UPDATE bookings SET affiliate_snapshot_locked = 1 WHERE id = ?",
        (booking_id,),
    )
    _apply_back_status(db, "SET02-ORDER", "SUCCESS", "SET02-TX")
    first = db.execute(
        """
        SELECT payment_status, affiliate_commission_type,
               affiliate_commission_value, affiliate_commission_amount,
               affiliate_commission_status
          FROM bookings WHERE id = ?
        """,
        (booking_id,),
    ).fetchone()
    db.execute(
        """UPDATE affiliate_rule_versions
              SET commission_type = 'fixed', commission_value = 999999
            WHERE id = ?""",
        (rule_id,),
    )
    _apply_back_status(db, "SET02-ORDER", "SUCCESS", "SET02-TX")
    _force_booking_paid(db, "SET02-ORDER", "SET02-TX")
    db.commit()

    replayed = db.execute(
        """
        SELECT affiliate_commission_type, affiliate_commission_value,
               affiliate_commission_amount, affiliate_commission_status
          FROM bookings WHERE id = ?
        """,
        (booking_id,),
    ).fetchone()
    audit_count = db.execute(
        """SELECT COUNT(*) FROM affiliate_audit_log
             WHERE booking_id = ? AND event_type = 'commission_earned'""",
        (booking_id,),
    ).fetchone()[0]

    assert tuple(first) == ("paid", "percentage", 10, 1800, "earned")
    assert tuple(replayed) == ("percentage", 10, 1800, "earned")
    assert audit_count == 1


def test_commission_cannot_finalize_before_paid_or_without_lock(commission_booking):
    db, booking_id, _ = commission_booking

    with pytest.raises(AffiliateCommissionLifecycleError, match="paid booking"):
        finalize_booking_commission(db, "SET02-ORDER")

    db.execute("UPDATE bookings SET payment_status = 'paid' WHERE id = ?", (booking_id,))
    with pytest.raises(AffiliateCommissionLifecycleError, match="must be locked"):
        finalize_booking_commission(db, "SET02-ORDER")


def test_missing_booking_is_an_idempotent_noop(app):
    with app.app_context():
        assert finalize_booking_commission(get_db(), "SET02-MISSING") is None
