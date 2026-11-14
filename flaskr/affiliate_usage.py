"""Atomic affiliate usage-budget reservations.

This module owns the persistence boundary for reserving usage.  It deliberately
does not call SimplePay or implement expiry/finalization; those lifecycle steps
belong to the following BUD work items.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import re


_GUEST_KEY_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


class AffiliateUsageError(RuntimeError):
    """Base class for reservation failures safe to handle at checkout."""


class AffiliateUsageConfigurationError(AffiliateUsageError):
    """Persisted rule/period data cannot be reserved safely."""


class AffiliateUsageConflict(AffiliateUsageError):
    """An idempotency or booking key was reused for different data."""


class AffiliateUsageLimitExceeded(AffiliateUsageError):
    """The partner or guest budget cannot accept the requested quantity."""

    def __init__(self, limit: str):
        self.limit = limit
        super().__init__(f"affiliate {limit} usage limit exceeded")


@dataclass(frozen=True)
class UsageReservation:
    usage_id: int
    created: bool
    quantity: int
    budget_period_id: int | None


def _positive_integer(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


@contextmanager
def _atomic_write(db):
    """Use a write lock, or a savepoint when the caller already owns one."""
    nested = db.in_transaction
    savepoint = "affiliate_usage_reservation"
    if nested:
        db.execute(f"SAVEPOINT {savepoint}")
    else:
        db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        if nested:
            db.execute(f"ROLLBACK TO {savepoint}")
            db.execute(f"RELEASE {savepoint}")
        else:
            db.rollback()
        raise
    else:
        if nested:
            db.execute(f"RELEASE {savepoint}")
        else:
            db.commit()


def _usage_scope(budget_period_id: int | None) -> tuple[str, tuple[int, ...]]:
    if budget_period_id is None:
        return "budget_period_id IS NULL", ()
    return "budget_period_id = ?", (budget_period_id,)


def _current_usage(
    db,
    *,
    partner_id: int,
    rule_version_id: int,
    budget_period_id: int | None,
    guest_key_hash: str | None = None,
) -> int:
    period_clause, period_parameters = _usage_scope(budget_period_id)
    guest_clause = "" if guest_key_hash is None else "AND guest_key_hash = ?"
    parameters = [partner_id, rule_version_id, *period_parameters]
    if guest_key_hash is not None:
        parameters.append(guest_key_hash)
    row = db.execute(
        f"""
        SELECT COALESCE(SUM(quantity), 0) AS used
          FROM affiliate_usages
         WHERE partner_id = ? AND rule_version_id = ?
           AND status IN ('pending', 'final')
           AND {period_clause}
           {guest_clause}
        """,
        parameters,
    ).fetchone()
    return int(row["used"])


def _existing_reservation(db, idempotency_key: str):
    return db.execute(
        "SELECT * FROM affiliate_usages WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()


def _same_reservation(
    row,
    *,
    booking_id: int,
    partner_id: int,
    rule_version_id: int,
    budget_period_id: int | None,
    guest_key_hash: str,
    quantity: int,
) -> bool:
    return (
        row["booking_id"] == booking_id
        and row["partner_id"] == partner_id
        and row["rule_version_id"] == rule_version_id
        and row["budget_period_id"] == budget_period_id
        and row["guest_key_hash"] == guest_key_hash
        and row["quantity"] == quantity
    )


def reserve_affiliate_usage(
    db,
    *,
    idempotency_key: str,
    booking_id: int,
    partner_id: int,
    rule_version_id: int,
    budget_period_id: int | None,
    guest_key_hash: str,
    quantity: int,
) -> UsageReservation:
    """Conditionally create one pending usage reservation.

    ``BEGIN IMMEDIATE`` serializes competing SQLite writers.  The insert still
    carries both limit predicates so the database operation itself is
    conditional; a stale application-side calculation cannot overbook either
    the partner or the normalized guest budget.
    """
    booking_id = _positive_integer(booking_id, "booking_id")
    partner_id = _positive_integer(partner_id, "partner_id")
    rule_version_id = _positive_integer(rule_version_id, "rule_version_id")
    quantity = _positive_integer(quantity, "quantity")
    if budget_period_id is not None:
        budget_period_id = _positive_integer(budget_period_id, "budget_period_id")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    if (
        not isinstance(guest_key_hash, str)
        or _GUEST_KEY_HASH_PATTERN.fullmatch(guest_key_hash) is None
    ):
        raise ValueError("guest_key_hash must be a lowercase SHA-256 hex digest")

    with _atomic_write(db):
        existing = _existing_reservation(db, idempotency_key)
        if existing is not None:
            if not _same_reservation(
                existing,
                booking_id=booking_id,
                partner_id=partner_id,
                rule_version_id=rule_version_id,
                budget_period_id=budget_period_id,
                guest_key_hash=guest_key_hash,
                quantity=quantity,
            ):
                raise AffiliateUsageConflict("idempotency key payload mismatch")
            return UsageReservation(
                usage_id=existing["id"],
                created=False,
                quantity=existing["quantity"],
                budget_period_id=existing["budget_period_id"],
            )

        booking_conflict = db.execute(
            "SELECT id FROM affiliate_usages WHERE booking_id = ?",
            (booking_id,),
        ).fetchone()
        if booking_conflict is not None:
            raise AffiliateUsageConflict("booking already has a usage reservation")

        rule = db.execute(
            """
            SELECT total_usage_limit, guest_usage_limit, budget_period_type
              FROM affiliate_rule_versions
             WHERE id = ? AND partner_id = ?
            """,
            (rule_version_id, partner_id),
        ).fetchone()
        if rule is None:
            raise AffiliateUsageConfigurationError("affiliate rule is unavailable")
        if rule["budget_period_type"] != "lifetime" and budget_period_id is None:
            raise AffiliateUsageConfigurationError("bounded rule requires a budget period")

        total_limit = rule["total_usage_limit"]
        guest_limit = rule["guest_usage_limit"]
        period = None
        if budget_period_id is not None:
            period = db.execute(
                """
                SELECT usage_limit, reserved_usage, finalized_usage, status
                  FROM affiliate_budget_periods
                 WHERE id = ? AND partner_id = ? AND rule_version_id = ?
                """,
                (budget_period_id, partner_id, rule_version_id),
            ).fetchone()
            if period is None or period["status"] != "open":
                raise AffiliateUsageConfigurationError("budget period is unavailable")
            if period["usage_limit"] is not None:
                total_limit = period["usage_limit"]
            actual_reserved = db.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                  FROM affiliate_usages
                 WHERE budget_period_id = ? AND status = 'pending'
                """,
                (budget_period_id,),
            ).fetchone()[0]
            actual_finalized = db.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                  FROM affiliate_usages
                 WHERE budget_period_id = ? AND status = 'final'
                """,
                (budget_period_id,),
            ).fetchone()[0]
            if (
                period["reserved_usage"] != actual_reserved
                or period["finalized_usage"] != actual_finalized
            ):
                raise AffiliateUsageConfigurationError("budget counters are inconsistent")

        period_clause, period_parameters = _usage_scope(budget_period_id)
        total_scope = (partner_id, rule_version_id, *period_parameters)
        insert = db.execute(
            f"""
            INSERT INTO affiliate_usages (
                idempotency_key, booking_id, partner_id, rule_version_id,
                budget_period_id, guest_key_hash, quantity, status
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, 'pending'
             WHERE (
                    ? IS NULL OR
                    COALESCE((
                        SELECT SUM(quantity)
                          FROM affiliate_usages
                         WHERE partner_id = ? AND rule_version_id = ?
                           AND status IN ('pending', 'final')
                           AND {period_clause}
                    ), 0) + ? <= ?
                   )
               AND (
                    ? IS NULL OR
                    COALESCE((
                        SELECT SUM(quantity)
                          FROM affiliate_usages
                         WHERE partner_id = ? AND rule_version_id = ?
                           AND status IN ('pending', 'final')
                           AND {period_clause}
                           AND guest_key_hash = ?
                    ), 0) + ? <= ?
                   )
            """,
            (
                idempotency_key,
                booking_id,
                partner_id,
                rule_version_id,
                budget_period_id,
                guest_key_hash,
                quantity,
                total_limit,
                *total_scope,
                quantity,
                total_limit,
                guest_limit,
                *total_scope,
                guest_key_hash,
                quantity,
                guest_limit,
            ),
        )
        if insert.rowcount != 1:
            total_used = _current_usage(
                db,
                partner_id=partner_id,
                rule_version_id=rule_version_id,
                budget_period_id=budget_period_id,
            )
            guest_used = _current_usage(
                db,
                partner_id=partner_id,
                rule_version_id=rule_version_id,
                budget_period_id=budget_period_id,
                guest_key_hash=guest_key_hash,
            )
            if total_limit is not None and total_used + quantity > total_limit:
                raise AffiliateUsageLimitExceeded("total")
            if guest_limit is not None and guest_used + quantity > guest_limit:
                raise AffiliateUsageLimitExceeded("guest")
            raise AffiliateUsageConfigurationError("reservation predicate rejected")

        usage_id = insert.lastrowid
        if period is not None:
            counter_update = db.execute(
                """
                UPDATE affiliate_budget_periods
                   SET reserved_usage = reserved_usage + ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'open'
                   AND (
                        usage_limit IS NULL OR
                        reserved_usage + finalized_usage + ? <= usage_limit
                   )
                """,
                (quantity, budget_period_id, quantity),
            )
            if counter_update.rowcount != 1:
                raise AffiliateUsageLimitExceeded("total")

        db.execute(
            """
            INSERT INTO affiliate_usage_events (usage_id, event_key, event_type)
            VALUES (?, ?, 'reserve')
            """,
            (usage_id, f"reserve:{idempotency_key}"),
        )
        return UsageReservation(
            usage_id=usage_id,
            created=True,
            quantity=quantity,
            budget_period_id=budget_period_id,
        )
