"""End-to-end referral click, cookie and attribution integration coverage."""

from flaskr.db import get_db


def _insert_partner_rule(
    app,
    ref_code,
    *,
    version=1,
    partner_id=None,
    days=30,
    valid_until=None,
):
    with app.app_context():
        db = get_db()
        if partner_id is None:
            partner_id = db.execute(
                "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
                (ref_code, ref_code),
            ).lastrowid
        else:
            db.execute(
                "UPDATE affiliate_rule_versions SET status = 'archived' "
                "WHERE partner_id = ? AND status = 'active'",
                (partner_id,),
            )
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type,
                attribution_window_days, valid_until
            ) VALUES (?, ?, 'active', 'tracking', ?, ?)
            """,
            (partner_id, version, days, valid_until),
        ).lastrowid
        db.commit()
        return partner_id, rule_id


def test_complete_click_cookie_overwrite_expiry_and_version_pin_flow(client, app):
    partner_a, rule_a_v1 = _insert_partner_rule(
        app, "AFF-FLOW0001", days=2
    )
    partner_b, rule_b_v1 = _insert_partner_rule(
        app, "AFF-FLOW0002", days=5
    )
    disabled_partner, _ = _insert_partner_rule(app, "AFF-DISABLED1")
    with app.app_context():
        db = get_db()
        with db:
            db.execute("UPDATE affiliate_partners SET is_active = 0 WHERE id = ?", (disabled_partner,))
    _insert_partner_rule(
        app,
        "AFF-EXPIRED1",
        valid_until="2000-01-01 00:00:00",
    )

    invalid = client.get("/?ref=bad%20code")
    expired = client.get("/?ref=AFF-EXPIRED1")
    disabled = client.get("/?ref=AFF-DISABLED1")
    assert not any(
        value.startswith("affiliate_visitor=")
        for response in (invalid, expired, disabled)
        for value in response.headers.getlist("Set-Cookie")
    )

    first_click = client.get(
        "/?ref=AFF-FLOW0001&utm_source=integration&utm_campaign=first"
    )
    assert any(
        value.startswith("affiliate_visitor=")
        for value in first_click.headers.getlist("Set-Cookie")
    )

    with app.app_context():
        db = get_db()
        attribution = db.execute("SELECT * FROM affiliate_attributions").fetchone()
        visitor_id = attribution["visitor_id"]
        assert attribution["partner_id"] == partner_a
        assert attribution["rule_version_id"] == rule_a_v1
        assert attribution["utm_source"] == "integration"
        assert db.execute(
            "SELECT julianday(expires_at) > julianday(clicked_at) "
            "FROM affiliate_attributions WHERE id = ?",
            (attribution["id"],),
        ).fetchone()[0] == 1

    prior_cookie = client.get_cookie("affiliate_visitor").value
    for code in ("unknown", "AFF-EXPIRED1", "AFF-DISABLED1"):
        assert client.get(f"/?ref={code}").status_code == 200
        assert client.get_cookie("affiliate_visitor").value == prior_cookie
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT rule_version_id FROM affiliate_attributions").fetchone()[0] == rule_a_v1
        assert db.execute("SELECT COUNT(*) FROM affiliate_click_events").fetchone()[0] == 1

    _, rule_a_v2 = _insert_partner_rule(
        app,
        "AFF-FLOW0001",
        version=2,
        partner_id=partner_a,
        days=7,
    )
    with app.app_context():
        pinned = get_db().execute(
            "SELECT rule_version_id FROM affiliate_attributions WHERE visitor_id = ?",
            (visitor_id,),
        ).fetchone()
        assert pinned["rule_version_id"] == rule_a_v1

    client.get("/?ref=AFF-FLOW0002&utm_campaign=overwrite")
    with app.app_context():
        overwritten = get_db().execute(
            "SELECT * FROM affiliate_attributions WHERE visitor_id = ?",
            (visitor_id,),
        ).fetchone()
        assert overwritten["partner_id"] == partner_b
        assert overwritten["rule_version_id"] == rule_b_v1
        assert overwritten["utm_campaign"] == "overwrite"

    client.get("/?ref=AFF-FLOW0001&utm_campaign=version-two")
    with app.app_context():
        db = get_db()
        final = db.execute(
            "SELECT * FROM affiliate_attributions WHERE visitor_id = ?",
            (visitor_id,),
        ).fetchone()
        assert final["partner_id"] == partner_a
        assert final["rule_version_id"] == rule_a_v2
        assert final["utm_campaign"] == "version-two"
        assert db.execute("SELECT COUNT(*) FROM affiliate_attributions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM affiliate_click_events").fetchone()[0] == 3
