"""Read-only partner settlement previews built from locked booking snapshots."""

from contextlib import contextmanager
from dataclasses import astuple, dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from json import dumps
from uuid import uuid4
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


class SettlementConflict(ValueError):
    """The requested settlement transition is unavailable."""


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


@contextmanager
def _settlement_transaction(db):
    # Acquire the write lock before reading eligibility or settlement state.
    if db.in_transaction:
        raise RuntimeError("settlement requires an independent transaction")
    with db:
        db.execute("BEGIN IMMEDIATE")
        yield


def prepare_affiliate_settlement(
    db, partner_id: int, period_start: date, period_end: date, *, admin_identifier: str,
    expected: str,
) -> int:
    """Reserve eligible bookings and store their amounts in one transaction."""
    with _settlement_transaction(db):
        preview = preview_affiliate_settlement(db, partner_id, period_start, period_end)
        if expected != preview_confirmation(preview, partner_id, period_start, period_end):
            raise SettlementConflict("settlement preview has changed")
        if not preview.items:
            raise SettlementConflict("no eligible bookings")
        partner = db.execute(
            """
            SELECT name, billing_name, billing_country, billing_zip, billing_city,
                   billing_address, tax_number
              FROM affiliate_partners WHERE id = ?
            """,
            (partner_id,),
        ).fetchone()
        locality = " ".join(filter(None, (partner["billing_zip"], partner["billing_city"])))
        address = ", ".join(filter(None, (locality, partner["billing_address"])))
        if address and partner["billing_country"]:
            address = f'{partner["billing_country"]}, {address}'
        settlement_id = db.execute(
            """
            INSERT INTO affiliate_settlements (
                settlement_ref, partner_id, period_start, period_end,
                original_amount_total, discount_amount_total, paid_amount_total,
                commission_amount_total, partner_name_snapshot,
                partner_billing_name_snapshot, partner_billing_address_snapshot,
                partner_tax_number_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex, partner_id, period_start.isoformat(), period_end.isoformat(),
                preview.original_amount_total, preview.discount_amount_total,
                preview.paid_amount_total, preview.commission_amount_total,
                partner["name"], partner["billing_name"], address or None, partner["tax_number"],
            ),
        ).lastrowid
        db.executemany(
            """
            INSERT INTO affiliate_settlement_items (
                settlement_id, booking_id, partner_id, rule_version_id, original_amount,
                discount_amount, paid_amount, commission_amount, commission_type, commission_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (settlement_id, item.booking_id, partner_id, item.rule_version_id,
                 item.original_amount, item.discount_amount, item.paid_amount,
                 item.commission_amount, item.commission_type, item.commission_value)
                for item in preview.items
            ),
        )
        _audit_transition(db, settlement_id, partner_id, admin_identifier, "settlement_prepared", None, "prepared")
        return settlement_id


def _items_totals(db, settlement_id):
    return tuple(db.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(original_amount), 0), COALESCE(SUM(discount_amount), 0),
               COALESCE(SUM(paid_amount), 0), COALESCE(SUM(commission_amount), 0)
          FROM affiliate_settlement_items WHERE settlement_id = ?
        """,
        (settlement_id,),
    ).fetchone())


_INVALID_ITEMS = """
    SELECT i.booking_id
      FROM affiliate_settlement_items i JOIN bookings b ON b.id = i.booking_id
     WHERE i.settlement_id = ?
       AND (b.payment_status IS NOT 'paid' OR b.cancellation_date IS NOT NULL
            OR b.affiliate_commission_status IS NOT 'earned' OR b.affiliate_snapshot_locked IS NOT 1)
"""


def refresh_prepared_affiliate_settlement(db, settlement_id: int, *, admin_identifier: str, expected: str) -> None:
    """Remove invalidated bookings from a draft before re-confirming it."""
    with _settlement_transaction(db):
        settlement = _require_status(db, settlement_id, "prepared")
        _verify_confirmation(db, settlement, "refresh", expected)
        removed = db.execute(
            "DELETE FROM affiliate_settlement_items WHERE settlement_id = ? AND booking_id IN (" + _INVALID_ITEMS + ")",
            (settlement_id, settlement_id),
        ).rowcount
        if removed:
            _, *totals = _items_totals(db, settlement_id)
            db.execute(
                """
                UPDATE affiliate_settlements
                   SET original_amount_total = ?, discount_amount_total = ?, paid_amount_total = ?,
                       commission_amount_total = ?, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (*totals, settlement_id),
            )
            _audit_transition(db, settlement_id, settlement["partner_id"], admin_identifier,
                              "settlement_refreshed", "prepared", "prepared")


def close_affiliate_settlement(db, settlement_id: int, *, admin_identifier: str, expected: str) -> None:
    """Freeze one eligible prepared settlement and settle its commissions."""
    with _settlement_transaction(db):
        settlement = _require_status(db, settlement_id, "prepared")
        _verify_confirmation(db, settlement, "close", expected)
        count, *totals = _items_totals(db, settlement_id)
        if not count or db.execute(_INVALID_ITEMS, (settlement_id,)).fetchone() is not None:
            raise SettlementConflict("settlement is empty or contains an invalidated booking")
        if totals != [settlement[key] for key in (
            "original_amount_total", "discount_amount_total", "paid_amount_total", "commission_amount_total",
        )]:
            raise SettlementConflict("settlement totals do not match its items")
        db.execute(
            """
            UPDATE bookings SET affiliate_commission_status = 'settled'
             WHERE id IN (SELECT booking_id FROM affiliate_settlement_items WHERE settlement_id = ?)
            """,
            (settlement_id,),
        )
        db.execute(
            """
            UPDATE affiliate_settlements
               SET status = 'closed', closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (settlement_id,),
        )
        _audit_transition(db, settlement_id, settlement["partner_id"], admin_identifier,
                          "settlement_closed", "prepared", "closed")


def mark_affiliate_settlement_paid(db, settlement_id: int, *, admin_identifier: str, note: str, expected: str) -> None:
    """Record a manual payout against a closed settlement."""
    if not isinstance(note, str) or not note.strip() or len(note.strip()) > 2000:
        raise ValueError("a payout note of 1 to 2000 characters is required")
    with _settlement_transaction(db):
        settlement = _require_status(db, settlement_id, "closed")
        _verify_confirmation(db, settlement, "paid", expected)
        db.execute(
            """
            UPDATE affiliate_settlements
               SET status = 'paid', paid_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, admin_notes = ?
             WHERE id = ?
            """,
            (note.strip(), settlement_id),
        )
        _audit_transition(db, settlement_id, settlement["partner_id"], admin_identifier,
                          "settlement_paid", "closed", "paid")


def _require_status(db, settlement_id, status):
    settlement = db.execute("SELECT * FROM affiliate_settlements WHERE id = ?", (settlement_id,)).fetchone()
    if settlement is None or settlement["status"] != status:
        raise SettlementConflict(f"a {status} settlement is required")
    return settlement


def _audit_transition(db, settlement_id, partner_id, admin_identifier, event, previous, current):
    db.execute(
        """
        INSERT INTO affiliate_audit_log (
            event_type, partner_id, settlement_id, admin_identifier, previous_state, new_state
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event, partner_id, settlement_id, admin_identifier, previous, current),
    )


def _confirmation(values) -> str:
    return sha256(dumps(values, separators=(",", ":")).encode("utf-8")).hexdigest()


def preview_confirmation(preview: SettlementPreview, partner_id: int, start: date, end: date) -> str:
    return _confirmation((partner_id, start.isoformat(), end.isoformat(), astuple(preview)))


def _verify_confirmation(db, settlement, operation: str, expected: str) -> None:
    if expected != settlement_confirmation(db, settlement["id"], settlement["status"], operation):
        raise SettlementConflict("settlement or confirmed action has changed")


def settlement_confirmation(db, settlement_id: int, status: str, operation: str) -> str:
    items = db.execute(
        """
        SELECT booking_id, rule_version_id, original_amount, discount_amount, paid_amount,
               commission_amount, commission_type, commission_value
          FROM affiliate_settlement_items WHERE settlement_id = ? ORDER BY id
        """,
        (settlement_id,),
    )
    return _confirmation((settlement_id, status, operation, [tuple(item) for item in items]))
