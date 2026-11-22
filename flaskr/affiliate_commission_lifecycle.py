"""Atomic lifecycle transitions for immutable booking commission snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from .affiliate_usage import release_affiliate_usage, return_affiliate_usage


class AffiliateCommissionLifecycleError(RuntimeError):
    """Raised when persisted commission state cannot be finalized safely."""


@dataclass(frozen=True)
class CommissionFinalizationResult:
    booking_id: int
    status: str
    amount_huf: int
    changed: bool


def finalize_booking_commission(db, order_ref: str):
    """Mark one paid booking's locked commission earned exactly once.

    The caller owns the surrounding transaction.  The compare-and-set update
    and audit insert therefore commit or roll back together with the payment
    success transition.
    """

    if not isinstance(order_ref, str) or not order_ref.strip():
        raise ValueError("order_ref must be a non-empty string")
    booking = db.execute(
        """
        SELECT id, payment_status, affiliate_partner_id,
               affiliate_rule_version_id, affiliate_commission_type,
               affiliate_commission_amount, affiliate_commission_status,
               affiliate_snapshot_locked
          FROM bookings
         WHERE order_ref = ?
        """,
        (order_ref,),
    ).fetchone()
    if booking is None:
        return None

    amount = int(booking["affiliate_commission_amount"] or 0)
    status = booking["affiliate_commission_status"]
    if booking["affiliate_partner_id"] is None or booking["affiliate_commission_type"] == "none":
        return CommissionFinalizationResult(booking["id"], status, amount, False)
    if status in {"earned", "settled", "reversed"}:
        return CommissionFinalizationResult(booking["id"], status, amount, False)
    if status != "pending":
        raise AffiliateCommissionLifecycleError(
            f"cannot finalize commission in {status} status"
        )
    if booking["payment_status"] != "paid":
        raise AffiliateCommissionLifecycleError(
            "commission can only be finalized for a paid booking"
        )
    if booking["affiliate_snapshot_locked"] != 1:
        raise AffiliateCommissionLifecycleError(
            "commission snapshot must be locked before finalization"
        )

    updated = db.execute(
        """
        UPDATE bookings
           SET affiliate_commission_status = 'earned'
         WHERE id = ?
           AND payment_status = 'paid'
           AND affiliate_snapshot_locked = 1
           AND affiliate_commission_status = 'pending'
        """,
        (booking["id"],),
    )
    if updated.rowcount != 1:
        current = db.execute(
            """SELECT affiliate_commission_status
                 FROM bookings WHERE id = ?""",
            (booking["id"],),
        ).fetchone()
        current_status = current["affiliate_commission_status"] if current else "missing"
        if current_status in {"earned", "settled", "reversed"}:
            return CommissionFinalizationResult(
                booking["id"], current_status, amount, False
            )
        raise AffiliateCommissionLifecycleError(
            "commission finalization lost its compare-and-set race"
        )

    db.execute(
        """
        INSERT INTO affiliate_audit_log (
            event_type, partner_id, rule_version_id, booking_id,
            previous_state, new_state
        ) VALUES ('commission_earned', ?, ?, ?, 'pending', 'earned')
        """,
        (
            booking["affiliate_partner_id"],
            booking["affiliate_rule_version_id"],
            booking["id"],
        ),
    )
    return CommissionFinalizationResult(booking["id"], "earned", amount, True)


def reverse_booking_affiliate(db, booking_id: int, admin_identifier: str) -> None:
    """Void commission and return capacity within the caller's transaction."""
    booking = db.execute(
        """
        SELECT b.affiliate_partner_id, b.affiliate_rule_version_id,
               b.affiliate_commission_status, b.payment_status, item.settlement_id
          FROM bookings b
          LEFT JOIN affiliate_settlement_items item ON item.booking_id = b.id
         WHERE b.id = ?
        """,
        (booking_id,),
    ).fetchone()
    if booking is None or booking["affiliate_partner_id"] is None:
        return

    if booking["payment_status"] not in {"cancelled", "refunded"}:
        raise AffiliateCommissionLifecycleError("commission reversal requires a cancelled or refunded booking")

    usage = db.execute(
        "SELECT id, partner_id, rule_version_id, status FROM affiliate_usages WHERE booking_id = ?",
        (booking_id,),
    ).fetchone()
    if usage is not None:
        if (
            usage["partner_id"] != booking["affiliate_partner_id"]
            or usage["rule_version_id"] != booking["affiliate_rule_version_id"]
        ):
            raise AffiliateCommissionLifecycleError("usage does not match the booking snapshot")
        usage_id = usage["id"]
        status = usage["status"]
        if status == "final":
            status = return_affiliate_usage(
                db, usage_id=usage_id, event_key=f"booking-reversal:{usage_id}",
            ).status
        elif status == "pending":
            status = release_affiliate_usage(
                db, usage_id=usage_id, event_key=f"booking-release:{usage_id}",
            ).status
        db.execute("UPDATE bookings SET affiliate_usage_status = ? WHERE id = ?", (status, booking_id))

    previous = booking["affiliate_commission_status"]
    if previous not in {"pending", "earned", "settled"}:
        return
    updated = db.execute(
        """UPDATE bookings SET affiliate_commission_status = 'reversed'
            WHERE id = ? AND affiliate_commission_status = ?""",
        (booking_id, previous),
    )
    if updated.rowcount != 1:
        raise AffiliateCommissionLifecycleError("commission reversal lost its previous state")
    db.execute(
        """
        INSERT INTO affiliate_audit_log (
            event_type, partner_id, rule_version_id, booking_id,
            settlement_id, admin_identifier, previous_state, new_state
        ) VALUES ('commission_reversed', ?, ?, ?, ?, ?, ?, 'reversed')
        """,
        (
            booking["affiliate_partner_id"], booking["affiliate_rule_version_id"],
            booking_id, booking["settlement_id"], admin_identifier, previous,
        ),
    )
