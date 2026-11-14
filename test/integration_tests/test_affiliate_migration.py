import sqlite3

import pytest

from flaskr.affiliate_migration import BOOKING_COLUMNS, migrate_affiliate_schema


LEGACY_SCHEMA = """
CREATE TABLE tour_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE tours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    date DATE NOT NULL,
    time TIME NOT NULL,
    price INTEGER NOT NULL,
    tour_location_id INTEGER
);
CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_id INTEGER NOT NULL,
    order_ref TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    participants_count INTEGER DEFAULT 1,
    total_price INTEGER NOT NULL,
    payment_status TEXT DEFAULT 'pending',
    booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tour_id) REFERENCES tours (id)
);
CREATE TABLE payment_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    order_ref TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'init',
    amount INTEGER NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings (id)
);
CREATE TABLE tour_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    FOREIGN KEY (tour_id) REFERENCES tours (id)
);
CREATE TABLE location_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    FOREIGN KEY (location_id) REFERENCES tour_locations (id)
);
CREATE TABLE page_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL
);
INSERT INTO tour_locations (id, name) VALUES (1, 'Tisza-tó');
INSERT INTO tours (id, title, date, time, price, tour_location_id)
VALUES (1, 'Örökölt túra', '2027-05-01', '09:00', 10000, 1);
INSERT INTO bookings (
    id, tour_id, order_ref, customer_name, customer_email,
    participants_count, total_price, payment_status
) VALUES (1, 1, 'LEGACY-1', 'Teszt Elek', 'teszt@example.com', 2, 20000, 'paid');
INSERT INTO payment_transactions (id, booking_id, order_ref, status, amount)
VALUES (1, 1, 'LEGACY-1', 'success', 20000);
INSERT INTO tour_images (id, tour_id, filename) VALUES (1, 1, 'tour.webp');
INSERT INTO location_images (id, location_id, filename) VALUES (1, 1, 'location.webp');
INSERT INTO page_sections (id, slug, content) VALUES (1, 'hero', '{"headline":"Teszt"}');
"""


def legacy_connection(path):
    connection = sqlite3.connect(path)
    connection.executescript(LEGACY_SCHEMA)
    return connection


def table_names(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def schema_signature(connection):
    return connection.execute(
        """
        SELECT type, name, tbl_name, COALESCE(sql, '')
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()


def test_zero_byte_database_builds_complete_supported_schema(tmp_path):
    connection = sqlite3.connect(tmp_path / "empty.sqlite")

    migrate_affiliate_schema(connection)

    assert {"tours", "bookings", "payment_transactions", "affiliate_partners"} <= table_names(connection)
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_existing_database_is_preserved_and_second_run_is_idempotent(tmp_path):
    connection = legacy_connection(tmp_path / "legacy.sqlite")
    legacy_tables = (
        "tour_locations", "tours", "bookings", "payment_transactions",
        "tour_images", "location_images", "page_sections",
    )
    original_columns = {
        table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        for table in legacy_tables
    }
    before = {
        table: connection.execute(
            f"SELECT {', '.join(original_columns[table])} FROM {table} ORDER BY id"
        ).fetchall()
        for table in legacy_tables
    }

    migrate_affiliate_schema(connection)
    first_tables = table_names(connection)
    first_schema = schema_signature(connection)
    first_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(bookings)")
    }
    migrate_affiliate_schema(connection)

    after = {
        table: connection.execute(
            f"SELECT {', '.join(original_columns[table])} FROM {table} ORDER BY id"
        ).fetchall()
        for table in legacy_tables
    }
    assert after == before
    assert {name for name, _ in BOOKING_COLUMNS} <= first_columns
    assert table_names(connection) == first_tables
    assert schema_signature(connection) == first_schema
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert connection.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
        ("2026-10-18-affiliate-v1",),
    ).fetchone()[0] == 1


def test_incompatible_partial_schema_rolls_back_new_objects(tmp_path):
    connection = legacy_connection(tmp_path / "partial.sqlite")
    usage_id = connection.execute(
        "CREATE TABLE affiliate_partners (id INTEGER PRIMARY KEY, is_active INTEGER)"
    )
    connection.commit()

    with pytest.raises(RuntimeError, match="affiliate_partners.*missing columns"):
        migrate_affiliate_schema(connection)

    assert table_names(connection) == {
        "tour_locations", "tours", "bookings", "payment_transactions", "tour_images",
        "location_images", "page_sections", "affiliate_partners",
    }
    assert "schema_migrations" not in table_names(connection)


def _insert_partner_rule(connection):
    partner_id = connection.execute(
        "INSERT INTO affiliate_partners (ref_code, name) VALUES ('Partner-ABC', 'Partner')"
    ).lastrowid
    rule_id = connection.execute(
        """
        INSERT INTO affiliate_rule_versions (
            partner_id, version_number, status, discount_type
        ) VALUES (?, 1, 'active', 'tracking')
        """,
        (partner_id,),
    ).lastrowid
    return partner_id, rule_id


def test_database_constraints_block_duplicate_usage_and_settlement(tmp_path):
    connection = legacy_connection(tmp_path / "constraints.sqlite")
    migrate_affiliate_schema(connection)
    partner_id, rule_id = _insert_partner_rule(connection)
    period_id = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key
        ) VALUES (?, ?, 'lifetime')
        """,
        (partner_id, rule_id),
    ).lastrowid
    usage_values = ("reserve-1", 1, partner_id, rule_id, period_id, "guest-hmac", 1)
    usage_id = connection.execute(
        """
        INSERT INTO affiliate_usages (
            idempotency_key, booking_id, partner_id, rule_version_id,
            budget_period_id, guest_key_hash, quantity
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        usage_values,
    ).lastrowid

    connection.execute(
        """
        INSERT INTO bookings (
            tour_id, order_ref, customer_name, customer_email,
            participants_count, total_price, payment_status
        ) VALUES (1, 'LEGACY-2', 'Második Teszt', 'masodik@example.com', 1, 10000, 'paid')
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_usages (
                idempotency_key, booking_id, partner_id, rule_version_id,
                budget_period_id, guest_key_hash, quantity
            ) VALUES ('reserve-1', 2, ?, ?, ?, 'guest-2-hmac', 1)
            """,
            (partner_id, rule_id, period_id),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_usages (
                idempotency_key, booking_id, partner_id, rule_version_id,
                budget_period_id, guest_key_hash, quantity
            ) VALUES ('reserve-2', 1, ?, ?, ?, 'guest-hmac', 1)
            """,
            (partner_id, rule_id, period_id),
        )

    connection.execute(
        "INSERT INTO affiliate_usage_events (usage_id, event_key, event_type) VALUES (?, 'event-1', 'reserve')",
        (usage_id,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO affiliate_usage_events (usage_id, event_key, event_type) VALUES (?, 'event-1', 'finalize')",
            (usage_id,),
        )

    first_settlement = connection.execute(
        """
        INSERT INTO affiliate_settlements (
            settlement_ref, partner_id, period_start, period_end, partner_name_snapshot
        ) VALUES ('SET-1', ?, '2026-01-01', '2026-01-31', 'Partner')
        """,
        (partner_id,),
    ).lastrowid
    second_settlement = connection.execute(
        """
        INSERT INTO affiliate_settlements (
            settlement_ref, partner_id, period_start, period_end, partner_name_snapshot
        ) VALUES ('SET-2', ?, '2026-02-01', '2026-02-28', 'Partner')
        """,
        (partner_id,),
    ).lastrowid
    item = (first_settlement, 1, partner_id, rule_id, 20000, 0, 20000, 1000, 'fixed', 1000)
    connection.execute(
        """
        INSERT INTO affiliate_settlement_items (
            settlement_id, booking_id, partner_id, rule_version_id, original_amount,
            discount_amount, paid_amount, commission_amount, commission_type, commission_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        item,
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_settlement_items (
                settlement_id, booking_id, partner_id, rule_version_id, original_amount,
                discount_amount, paid_amount, commission_amount, commission_type, commission_value
            ) VALUES (?, 1, ?, ?, 20000, 0, 20000, 1000, 'fixed', 1000)
            """,
            (second_settlement, partner_id, rule_id),
        )


def test_foreign_keys_and_locked_booking_snapshot_are_enforced(tmp_path):
    connection = legacy_connection(tmp_path / "foreign-keys.sqlite")
    migrate_affiliate_schema(connection)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO affiliate_rule_versions (partner_id, version_number, discount_type) VALUES (999, 1, 'tracking')"
        )

    partner_id, rule_id = _insert_partner_rule(connection)
    connection.execute(
        """
        UPDATE bookings SET
            affiliate_partner_id = ?, affiliate_rule_version_id = ?,
            affiliate_original_price = 20000, affiliate_discount_amount = 1000,
            affiliate_payable_price = 19000, affiliate_snapshot_locked = 1
        WHERE id = 1
        """,
        (partner_id, rule_id),
    )
    with pytest.raises(sqlite3.IntegrityError, match="snapshot is immutable"):
        connection.execute(
            "UPDATE bookings SET affiliate_discount_amount = 2000 WHERE id = 1"
        )

    connection.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = 1")
    assert connection.execute(
        "SELECT payment_status FROM bookings WHERE id = 1"
    ).fetchone()[0] == "refunded"


def test_partner_rule_and_budget_pairs_cannot_be_mixed(tmp_path):
    connection = legacy_connection(tmp_path / "pairs.sqlite")
    migrate_affiliate_schema(connection)
    first_partner, first_rule = _insert_partner_rule(connection)
    second_partner = connection.execute(
        "INSERT INTO affiliate_partners (ref_code, name) VALUES ('SECOND', 'Második')"
    ).lastrowid
    second_rule = connection.execute(
        """
        INSERT INTO affiliate_rule_versions (
            partner_id, version_number, status, discount_type
        ) VALUES (?, 1, 'active', 'tracking')
        """,
        (second_partner,),
    ).lastrowid
    second_period = connection.execute(
        """
        INSERT INTO affiliate_budget_periods (
            partner_id, rule_version_id, period_key
        ) VALUES (?, ?, 'lifetime')
        """,
        (second_partner, second_rule),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_attributions (
                visitor_id, partner_id, rule_version_id
            ) VALUES ('visitor-1', ?, ?)
            """,
            (first_partner, second_rule),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_usages (
                idempotency_key, booking_id, partner_id, rule_version_id,
                budget_period_id, guest_key_hash, quantity
            ) VALUES ('mixed-budget', 1, ?, ?, ?, 'guest-hmac', 1)
            """,
            (first_partner, first_rule, second_period),
        )


def test_referral_rule_and_scope_uniqueness_constraints(tmp_path):
    connection = legacy_connection(tmp_path / "unique.sqlite")
    migrate_affiliate_schema(connection)
    partner_id, rule_id = _insert_partner_rule(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES ('partner-abc', 'Duplikált')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type
            ) VALUES (?, 2, 'active', 'tracking')
            """,
            (partner_id,),
        )

    connection.execute(
        "INSERT INTO affiliate_rule_scopes (rule_version_id, scope_type) VALUES (?, 'all')",
        (rule_id,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO affiliate_rule_scopes (rule_version_id, scope_type) VALUES (?, 'all')",
            (rule_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO affiliate_rule_scopes (
                rule_version_id, scope_type, tour_id
            ) VALUES (?, 'location', 1)
            """,
            (rule_id,),
        )
