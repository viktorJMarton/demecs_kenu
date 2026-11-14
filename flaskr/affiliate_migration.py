"""Idempotent SQLite migration for the affiliate module data foundation.

This module intentionally does not use ``schema.sql`` for existing databases:
that file is a destructive fresh-install schema.  The migration below only adds
missing objects and can be run repeatedly on both empty and populated databases.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path


AFFILIATE_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ref_code TEXT NOT NULL COLLATE NOCASE UNIQUE,
        name TEXT NOT NULL,
        company_name TEXT,
        contact_name TEXT,
        contact_email TEXT,
        contact_phone TEXT,
        billing_name TEXT,
        billing_country TEXT NOT NULL DEFAULT 'hu',
        billing_zip TEXT,
        billing_city TEXT,
        billing_address TEXT,
        tax_number TEXT,
        internal_notes TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_rule_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER NOT NULL,
        version_number INTEGER NOT NULL CHECK (version_number > 0),
        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
        discount_type TEXT NOT NULL CHECK (
            discount_type IN ('percentage', 'fixed', 'free_participants', 'tracking')
        ),
        discount_value INTEGER NOT NULL DEFAULT 0 CHECK (discount_value >= 0),
        discount_basis TEXT NOT NULL DEFAULT 'booking_total' CHECK (
            discount_basis IN ('booking_total', 'participants')
        ),
        discount_participant_count INTEGER CHECK (discount_participant_count > 0),
        max_discount_amount INTEGER CHECK (max_discount_amount >= 0),
        commission_type TEXT NOT NULL DEFAULT 'none' CHECK (
            commission_type IN ('none', 'percentage', 'fixed')
        ),
        commission_value INTEGER NOT NULL DEFAULT 0 CHECK (commission_value >= 0),
        attribution_window_days INTEGER NOT NULL DEFAULT 30 CHECK (attribution_window_days >= 0),
        session_only INTEGER NOT NULL DEFAULT 0 CHECK (session_only IN (0, 1)),
        valid_from TIMESTAMP,
        valid_until TIMESTAMP,
        total_usage_limit INTEGER CHECK (total_usage_limit >= 0),
        guest_usage_limit INTEGER CHECK (guest_usage_limit >= 0),
        usage_unit TEXT NOT NULL DEFAULT 'booking' CHECK (
            usage_unit IN ('booking', 'participant')
        ),
        budget_period_type TEXT NOT NULL DEFAULT 'lifetime' CHECK (
            budget_period_type IN ('lifetime', 'monthly', 'yearly', 'manual')
        ),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (partner_id, version_number),
        UNIQUE (id, partner_id),
        CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from),
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_rule_scopes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_version_id INTEGER NOT NULL,
        scope_type TEXT NOT NULL CHECK (scope_type IN ('all', 'tour', 'location')),
        tour_id INTEGER,
        tour_location_id INTEGER,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (
            (scope_type = 'all' AND tour_id IS NULL AND tour_location_id IS NULL) OR
            (scope_type = 'tour' AND tour_id IS NOT NULL AND tour_location_id IS NULL) OR
            (scope_type = 'location' AND tour_id IS NULL AND tour_location_id IS NOT NULL)
        ),
        FOREIGN KEY (rule_version_id) REFERENCES affiliate_rule_versions (id) ON DELETE CASCADE,
        FOREIGN KEY (tour_id) REFERENCES tours (id) ON DELETE RESTRICT,
        FOREIGN KEY (tour_location_id) REFERENCES tour_locations (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_budget_periods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER NOT NULL,
        rule_version_id INTEGER NOT NULL,
        period_key TEXT NOT NULL,
        starts_at TIMESTAMP,
        ends_at TIMESTAMP,
        usage_limit INTEGER CHECK (usage_limit >= 0),
        reserved_usage INTEGER NOT NULL DEFAULT 0 CHECK (reserved_usage >= 0),
        finalized_usage INTEGER NOT NULL DEFAULT 0 CHECK (finalized_usage >= 0),
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (rule_version_id, period_key),
        UNIQUE (id, rule_version_id, partner_id),
        CHECK (usage_limit IS NULL OR reserved_usage + finalized_usage <= usage_limit),
        CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at),
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT,
        FOREIGN KEY (rule_version_id, partner_id)
            REFERENCES affiliate_rule_versions (id, partner_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_attributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_id TEXT NOT NULL UNIQUE,
        partner_id INTEGER NOT NULL,
        rule_version_id INTEGER NOT NULL,
        clicked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        referrer TEXT,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_content TEXT,
        utm_term TEXT,
        landing_page TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT,
        FOREIGN KEY (rule_version_id, partner_id)
            REFERENCES affiliate_rule_versions (id, partner_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_click_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL UNIQUE,
        partner_id INTEGER NOT NULL,
        rule_version_id INTEGER NOT NULL,
        visitor_id TEXT NOT NULL,
        clicked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        referrer TEXT,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_content TEXT,
        utm_term TEXT,
        landing_page TEXT,
        is_bot INTEGER NOT NULL DEFAULT 0 CHECK (is_bot IN (0, 1)),
        is_duplicate INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate IN (0, 1)),
        user_agent_hash TEXT,
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT,
        FOREIGN KEY (rule_version_id, partner_id)
            REFERENCES affiliate_rule_versions (id, partner_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_usages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idempotency_key TEXT NOT NULL UNIQUE,
        booking_id INTEGER NOT NULL UNIQUE,
        partner_id INTEGER NOT NULL,
        rule_version_id INTEGER NOT NULL,
        budget_period_id INTEGER,
        guest_key_hash TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        status TEXT NOT NULL DEFAULT 'pending' CHECK (
            status IN ('pending', 'final', 'released', 'returned')
        ),
        expires_at TIMESTAMP,
        finalized_at TIMESTAMP,
        released_at TIMESTAMP,
        returned_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (booking_id) REFERENCES bookings (id) ON DELETE RESTRICT,
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT,
        FOREIGN KEY (rule_version_id, partner_id)
            REFERENCES affiliate_rule_versions (id, partner_id) ON DELETE RESTRICT,
        FOREIGN KEY (budget_period_id, rule_version_id, partner_id)
            REFERENCES affiliate_budget_periods (id, rule_version_id, partner_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_usage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usage_id INTEGER NOT NULL,
        event_key TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL CHECK (
            event_type IN ('reserve', 'finalize', 'release', 'return')
        ),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usage_id) REFERENCES affiliate_usages (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        settlement_ref TEXT NOT NULL UNIQUE,
        partner_id INTEGER NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        status TEXT NOT NULL DEFAULT 'prepared' CHECK (
            status IN ('prepared', 'closed', 'paid')
        ),
        original_amount_total INTEGER NOT NULL DEFAULT 0 CHECK (original_amount_total >= 0),
        discount_amount_total INTEGER NOT NULL DEFAULT 0 CHECK (discount_amount_total >= 0),
        paid_amount_total INTEGER NOT NULL DEFAULT 0 CHECK (paid_amount_total >= 0),
        commission_amount_total INTEGER NOT NULL DEFAULT 0 CHECK (commission_amount_total >= 0),
        partner_name_snapshot TEXT NOT NULL,
        partner_billing_name_snapshot TEXT,
        partner_billing_address_snapshot TEXT,
        partner_tax_number_snapshot TEXT,
        admin_notes TEXT,
        closed_at TIMESTAMP,
        paid_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (id, partner_id),
        CHECK (period_end >= period_start),
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_settlement_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        settlement_id INTEGER NOT NULL,
        booking_id INTEGER NOT NULL UNIQUE,
        partner_id INTEGER NOT NULL,
        rule_version_id INTEGER NOT NULL,
        original_amount INTEGER NOT NULL CHECK (original_amount >= 0),
        discount_amount INTEGER NOT NULL CHECK (discount_amount >= 0),
        paid_amount INTEGER NOT NULL CHECK (paid_amount >= 0),
        commission_amount INTEGER NOT NULL CHECK (commission_amount >= 0),
        commission_type TEXT NOT NULL CHECK (commission_type IN ('none', 'percentage', 'fixed')),
        commission_value INTEGER NOT NULL DEFAULT 0 CHECK (commission_value >= 0),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (settlement_id, partner_id)
            REFERENCES affiliate_settlements (id, partner_id) ON DELETE RESTRICT,
        FOREIGN KEY (booking_id) REFERENCES bookings (id) ON DELETE RESTRICT,
        FOREIGN KEY (rule_version_id, partner_id)
            REFERENCES affiliate_rule_versions (id, partner_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS affiliate_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        partner_id INTEGER,
        rule_version_id INTEGER,
        booking_id INTEGER,
        settlement_id INTEGER,
        admin_identifier TEXT,
        previous_state TEXT,
        new_state TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (partner_id) REFERENCES affiliate_partners (id) ON DELETE RESTRICT,
        FOREIGN KEY (rule_version_id) REFERENCES affiliate_rule_versions (id) ON DELETE RESTRICT,
        FOREIGN KEY (booking_id) REFERENCES bookings (id) ON DELETE RESTRICT,
        FOREIGN KEY (settlement_id) REFERENCES affiliate_settlements (id) ON DELETE RESTRICT
    )
    """,
)


BOOKING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("affiliate_partner_id", "INTEGER REFERENCES affiliate_partners (id)"),
    ("affiliate_rule_version_id", "INTEGER REFERENCES affiliate_rule_versions (id)"),
    ("affiliate_attribution_id", "INTEGER REFERENCES affiliate_attributions (id)"),
    ("affiliate_ref_code_snapshot", "TEXT"),
    ("affiliate_rule_version_snapshot", "INTEGER CHECK (affiliate_rule_version_snapshot > 0)"),
    ("affiliate_original_price", "INTEGER CHECK (affiliate_original_price >= 0)"),
    ("affiliate_discount_amount", "INTEGER NOT NULL DEFAULT 0 CHECK (affiliate_discount_amount >= 0)"),
    ("affiliate_payable_price", "INTEGER CHECK (affiliate_payable_price >= 0)"),
    ("affiliate_discount_type", "TEXT CHECK (affiliate_discount_type IN ('percentage', 'fixed', 'free_participants', 'tracking'))"),
    ("affiliate_discount_value", "INTEGER CHECK (affiliate_discount_value >= 0)"),
    ("affiliate_commission_type", "TEXT CHECK (affiliate_commission_type IN ('none', 'percentage', 'fixed'))"),
    ("affiliate_commission_value", "INTEGER CHECK (affiliate_commission_value >= 0)"),
    ("affiliate_commission_amount", "INTEGER NOT NULL DEFAULT 0 CHECK (affiliate_commission_amount >= 0)"),
    ("affiliate_commission_status", "TEXT NOT NULL DEFAULT 'none' CHECK (affiliate_commission_status IN ('none', 'pending', 'earned', 'reversed', 'settled'))"),
    ("affiliate_referrer", "TEXT"),
    ("affiliate_utm_source", "TEXT"),
    ("affiliate_utm_medium", "TEXT"),
    ("affiliate_utm_campaign", "TEXT"),
    ("affiliate_utm_content", "TEXT"),
    ("affiliate_utm_term", "TEXT"),
    ("affiliate_landing_path", "TEXT"),
    ("affiliate_usage_status", "TEXT NOT NULL DEFAULT 'none' CHECK (affiliate_usage_status IN ('none', 'pending', 'final', 'released', 'returned'))"),
    ("affiliate_snapshot_locked", "INTEGER NOT NULL DEFAULT 0 CHECK (affiliate_snapshot_locked IN (0, 1))"),
)


AFFILIATE_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_scope_all ON affiliate_rule_scopes (rule_version_id) WHERE scope_type = 'all'",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_scope_tour ON affiliate_rule_scopes (rule_version_id, tour_id) WHERE scope_type = 'tour'",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_scope_location ON affiliate_rule_scopes (rule_version_id, tour_location_id) WHERE scope_type = 'location'",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_rule_active ON affiliate_rule_versions (partner_id) WHERE status = 'active'",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_partners_active ON affiliate_partners (is_active)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_rule_versions_partner ON affiliate_rule_versions (partner_id, status, version_number DESC)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_budget_periods_lookup ON affiliate_budget_periods (rule_version_id, status, starts_at, ends_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_attributions_rule ON affiliate_attributions (rule_version_id, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_click_events_reporting ON affiliate_click_events (partner_id, clicked_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_click_events_visitor ON affiliate_click_events (visitor_id, clicked_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_usages_partner_status ON affiliate_usages (partner_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_usages_guest ON affiliate_usages (rule_version_id, guest_key_hash, status)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_usages_expiry ON affiliate_usages (status, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_usage_events_usage ON affiliate_usage_events (usage_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_settlements_partner ON affiliate_settlements (partner_id, status, period_start, period_end)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_settlement_items_settlement ON affiliate_settlement_items (settlement_id)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_audit_log_created ON affiliate_audit_log (created_at)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_audit_log_partner ON affiliate_audit_log (partner_id, created_at)",
)


AFFILIATE_TRIGGER_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_bookings_affiliate_snapshot_immutable
    BEFORE UPDATE ON bookings
    WHEN OLD.affiliate_snapshot_locked = 1 AND (
        NEW.affiliate_partner_id IS NOT OLD.affiliate_partner_id OR
        NEW.affiliate_rule_version_id IS NOT OLD.affiliate_rule_version_id OR
        NEW.affiliate_attribution_id IS NOT OLD.affiliate_attribution_id OR
        NEW.affiliate_ref_code_snapshot IS NOT OLD.affiliate_ref_code_snapshot OR
        NEW.affiliate_rule_version_snapshot IS NOT OLD.affiliate_rule_version_snapshot OR
        NEW.affiliate_original_price IS NOT OLD.affiliate_original_price OR
        NEW.affiliate_discount_amount IS NOT OLD.affiliate_discount_amount OR
        NEW.affiliate_payable_price IS NOT OLD.affiliate_payable_price OR
        NEW.affiliate_discount_type IS NOT OLD.affiliate_discount_type OR
        NEW.affiliate_discount_value IS NOT OLD.affiliate_discount_value OR
        NEW.affiliate_commission_type IS NOT OLD.affiliate_commission_type OR
        NEW.affiliate_commission_value IS NOT OLD.affiliate_commission_value OR
        NEW.affiliate_commission_amount IS NOT OLD.affiliate_commission_amount OR
        NEW.affiliate_referrer IS NOT OLD.affiliate_referrer OR
        NEW.affiliate_utm_source IS NOT OLD.affiliate_utm_source OR
        NEW.affiliate_utm_medium IS NOT OLD.affiliate_utm_medium OR
        NEW.affiliate_utm_campaign IS NOT OLD.affiliate_utm_campaign OR
        NEW.affiliate_utm_content IS NOT OLD.affiliate_utm_content OR
        NEW.affiliate_utm_term IS NOT OLD.affiliate_utm_term OR
        NEW.affiliate_landing_path IS NOT OLD.affiliate_landing_path OR
        NEW.affiliate_snapshot_locked = 0
    )
    BEGIN
        SELECT RAISE(ABORT, 'affiliate booking snapshot is immutable');
    END
    """,
)


BOOKING_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_bookings_affiliate_partner ON bookings (affiliate_partner_id, booking_date)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_affiliate_rule ON bookings (affiliate_rule_version_id)",
)


REQUIRED_AFFILIATE_COLUMNS: dict[str, set[str]] = {
    "affiliate_partners": {"id", "ref_code", "name", "is_active"},
    "affiliate_rule_versions": {
        "id", "partner_id", "version_number", "status", "discount_type",
        "commission_type", "usage_unit", "budget_period_type",
    },
    "affiliate_rule_scopes": {"id", "rule_version_id", "scope_type"},
    "affiliate_budget_periods": {
        "id", "partner_id", "rule_version_id", "period_key", "reserved_usage",
        "finalized_usage", "status",
    },
    "affiliate_attributions": {
        "id", "visitor_id", "partner_id", "rule_version_id", "clicked_at",
    },
    "affiliate_click_events": {
        "id", "event_key", "partner_id", "rule_version_id", "visitor_id", "clicked_at",
    },
    "affiliate_usages": {
        "id", "idempotency_key", "booking_id", "partner_id", "rule_version_id",
        "guest_key_hash", "quantity", "status",
    },
    "affiliate_usage_events": {"id", "usage_id", "event_key", "event_type"},
    "affiliate_settlements": {
        "id", "settlement_ref", "partner_id", "period_start", "period_end", "status",
    },
    "affiliate_settlement_items": {
        "id", "settlement_id", "booking_id", "partner_id", "rule_version_id",
        "commission_amount", "commission_type", "commission_value",
    },
    "affiliate_audit_log": {"id", "event_type", "created_at"},
}


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table_name}")')}


def _execute_all(connection: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        connection.execute(statement)


def _validate_existing_objects(connection: sqlite3.Connection) -> None:
    for table_name, required_columns in REQUIRED_AFFILIATE_COLUMNS.items():
        actual_columns = _column_names(connection, table_name)
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            raise RuntimeError(
                f"Existing {table_name} table is incompatible; missing columns: "
                + ", ".join(missing_columns)
            )


def migrate_affiliate_schema(connection: sqlite3.Connection) -> None:
    """Add the affiliate v1 schema without deleting or rewriting existing rows."""

    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    required_base_tables = {"bookings", "tours", "tour_locations"}
    if not any(_table_exists(connection, table) for table in required_base_tables):
        schema_path = Path(__file__).with_name("schema.sql")
        connection.executescript(schema_path.read_text(encoding="utf-8"))

    missing = sorted(
        table for table in required_base_tables if not _table_exists(connection, table)
    )
    if missing:
        raise RuntimeError(
            "Affiliate migration requires the base schema; missing tables: "
            + ", ".join(missing)
        )

    try:
        connection.execute("BEGIN IMMEDIATE")
        _execute_all(connection, AFFILIATE_TABLE_STATEMENTS)
        _validate_existing_objects(connection)
        _execute_all(connection, AFFILIATE_INDEX_STATEMENTS)

        if _table_exists(connection, "bookings"):
            existing_columns = _column_names(connection, "bookings")
            for column_name, column_definition in BOOKING_COLUMNS:
                if column_name not in existing_columns:
                    connection.execute(
                        f'ALTER TABLE bookings ADD COLUMN "{column_name}" {column_definition}'
                    )

            _execute_all(connection, BOOKING_INDEX_STATEMENTS)
            _execute_all(connection, AFFILIATE_TRIGGER_STATEMENTS)

        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise sqlite3.IntegrityError(
                f"Foreign key check failed after affiliate migration: {foreign_key_errors!r}"
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(
                f"Integrity check failed after affiliate migration: {integrity}"
            )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
            ("2026-10-18-affiliate-v1",),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
