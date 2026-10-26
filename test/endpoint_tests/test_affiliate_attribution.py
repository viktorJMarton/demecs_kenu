"""Global referral query entry-point coverage."""

from flask import g

from flaskr.affiliate_attribution import (
    get_eligible_rule_for_partner,
    normalize_ref_code,
    process_referral_query,
)
from flaskr.db import get_db


def test_ref_code_normalization_is_bounded_and_canonical():
    assert normalize_ref_code("  aff-code_01 ") == "AFF-CODE_01"
    assert normalize_ref_code("x") is None
    assert normalize_ref_code("bad code") is None
    assert normalize_ref_code("A" * 65) is None


def test_active_ref_is_available_request_locally_without_database_writes(app):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ("AFF-GLOBAL01", "Globális partner"),
        ).lastrowid
        db.commit()

        with app.test_request_context("/?ref=aff-global01"):
            process_referral_query()
            assert g.affiliate_ref_candidate == {
                "partner_id": partner_id,
                "ref_code": "AFF-GLOBAL01",
            }

        assert db.execute("SELECT COUNT(*) FROM affiliate_attributions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM affiliate_click_events").fetchone()[0] == 0


def test_invalid_unknown_and_inactive_refs_are_silent_and_stateless(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO affiliate_partners (ref_code, name, is_active) VALUES (?, ?, 0)",
            ("AFF-INACTIVE1", "Inaktív partner"),
        )
        db.commit()

        for path in ("/?ref=%20bad%20code", "/?ref=AFF-UNKNOWN1", "/?ref=AFF-INACTIVE1"):
            with app.test_request_context(path):
                process_referral_query()
                assert g.affiliate_ref_candidate is None

        assert db.execute("SELECT COUNT(*) FROM affiliate_attributions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM affiliate_click_events").fetchone()[0] == 0


def test_click_candidate_pins_the_current_eligible_rule_version(app):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ("AFF-RULEPIN01", "Verziós partner"),
        ).lastrowid
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type,
                valid_from, valid_until, total_usage_limit
            ) VALUES (?, 3, 'active', 'tracking', datetime('now', '-1 day'),
                      datetime('now', '+1 day'), 10)
            """,
            (partner_id,),
        ).lastrowid
        db.commit()

        with app.test_request_context("/?ref=AFF-RULEPIN01"):
            process_referral_query()
            assert g.affiliate_rule_candidate == {
                "partner_id": partner_id,
                "ref_code": "AFF-RULEPIN01",
                "rule_version_id": rule_id,
                "version_number": 3,
                "attribution_window_days": 30,
                "session_only": False,
                "tracking": {
                    "referrer": None,
                    "utm_source": None,
                    "utm_medium": None,
                    "utm_campaign": None,
                    "utm_content": None,
                    "utm_term": None,
                    "landing_page": "/",
                },
            }


def test_expired_future_inactive_and_exhausted_rules_are_not_eligible(app):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ("AFF-NORULE001", "Nincs szabály"),
        ).lastrowid
        db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type, valid_from
            ) VALUES (?, 1, 'active', 'tracking', '2099-01-01 00:00:00')
            """,
            (partner_id,),
        )
        db.commit()
        assert get_eligible_rule_for_partner(db, partner_id) is None

        db.execute("DELETE FROM affiliate_rule_versions WHERE partner_id = ?", (partner_id,))
        db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type, valid_until
            ) VALUES (?, 2, 'active', 'tracking', '2000-01-01 00:00:00')
            """,
            (partner_id,),
        )
        db.commit()
        assert get_eligible_rule_for_partner(db, partner_id) is None

        db.execute("DELETE FROM affiliate_rule_versions WHERE partner_id = ?", (partner_id,))
        db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type, total_usage_limit
            ) VALUES (?, 5, 'active', 'tracking', 0)
            """,
            (partner_id,),
        )
        db.commit()
        assert get_eligible_rule_for_partner(db, partner_id) is None


def _insert_cookie_rule(app, ref_code, *, days, session_only):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            (ref_code, "Cookie partner"),
        ).lastrowid
        db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type,
                attribution_window_days, session_only
            ) VALUES (?, 1, 'active', 'tracking', ?, ?)
            """,
            (partner_id, days, session_only),
        )
        db.commit()


def test_persistent_visitor_cookie_has_security_attributes(client, app):
    _insert_cookie_rule(app, "AFF-COOKIE001", days=2, session_only=0)
    previous = app.config["SESSION_COOKIE_SECURE"]
    app.config["SESSION_COOKIE_SECURE"] = True
    try:
        response = client.get("/?ref=AFF-COOKIE001")
    finally:
        app.config["SESSION_COOKIE_SECURE"] = previous

    cookie = response.headers.getlist("Set-Cookie")
    affiliate_cookie = next(value for value in cookie if value.startswith("affiliate_visitor="))
    assert "Max-Age=172800" in affiliate_cookie
    assert "Secure" in affiliate_cookie
    assert "HttpOnly" in affiliate_cookie
    assert "SameSite=Lax" in affiliate_cookie
    assert "Cookie partner" not in affiliate_cookie


def test_session_only_rule_creates_session_cookie(client, app):
    _insert_cookie_rule(app, "AFF-SESSION01", days=30, session_only=1)

    response = client.get("/?ref=AFF-SESSION01")

    affiliate_cookie = next(
        value
        for value in response.headers.getlist("Set-Cookie")
        if value.startswith("affiliate_visitor=")
    )
    assert "Max-Age" not in affiliate_cookie
    assert "Expires" not in affiliate_cookie
    assert "HttpOnly" in affiliate_cookie


def test_last_eligible_click_replaces_previous_attribution(app):
    visitor_id = "V" * 43
    with app.app_context():
        db = get_db()
        targets = []
        for index in (1, 2):
            partner_id = db.execute(
                "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
                (f"AFF-LASTCLK0{index}", f"Partner {index}"),
            ).lastrowid
            rule_id = db.execute(
                """
                INSERT INTO affiliate_rule_versions (
                    partner_id, version_number, status, discount_type,
                    attribution_window_days
                ) VALUES (?, 1, 'active', 'tracking', 7)
                """,
                (partner_id,),
            ).lastrowid
            targets.append((partner_id, rule_id))
        db.commit()

        for index in (1, 2):
            with app.test_request_context(
                f"/?ref=AFF-LASTCLK0{index}",
                headers={"Cookie": f"affiliate_visitor={visitor_id}"},
            ):
                process_referral_query()

        rows = db.execute(
            "SELECT * FROM affiliate_attributions WHERE visitor_id = ?", (visitor_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["visitor_id"] == visitor_id
        assert rows[0]["partner_id"] == targets[1][0]
        assert rows[0]["rule_version_id"] == targets[1][1]
        assert rows[0]["expires_at"] is not None


def test_click_metadata_is_allowlisted_bounded_and_sanitized(app):
    _insert_cookie_rule(app, "AFF-METADATA1", days=3, session_only=0)
    visitor_id = "M" * 43
    long_campaign = "x" * 250
    with app.app_context():
        with app.test_request_context(
            "/tours/42?ref=AFF-METADATA1&utm_source=%20newsletter%00"
            f"&utm_campaign={long_campaign}&customer_email=private@example.test",
            headers={
                "Cookie": f"affiliate_visitor={visitor_id}",
                "Referer": "https://partner.example/path\x00ignored",
            },
        ):
            process_referral_query()

        row = get_db().execute(
            "SELECT * FROM affiliate_attributions WHERE visitor_id = ?", (visitor_id,)
        ).fetchone()
        assert row["utm_source"] == "newsletter"
        assert row["utm_campaign"] == "x" * 200
        assert row["referrer"] == "https://partner.example/pathignored"
        assert row["landing_page"] == "/tours/42"
        assert "private@example.test" not in tuple(value or "" for value in row)
