"""Endpoint coverage for the affiliate admin entry point."""

import html
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from flaskr.db import get_db
from flaskr.admin.admin_affiliates import (
    _rule_form_data,
    _scope_form_data,
    get_active_partner_by_ref,
    load_rule_scope,
    replace_rule_scopes,
    save_rule_version,
)


@pytest.fixture
def authenticated_client(client, monkeypatch):
    """Authenticate without reading the server's production admin settings."""
    monkeypatch.setattr(
        "flaskr.auth.find_user_by_username",
        lambda username: {
            "username": username,
            "password_hash": "test-only-not-used",
        },
    )
    with client.session_transaction() as session:
        session["username"] = "test_admin"
    return client


@pytest.fixture
def affiliate_report_cleanup(app):
    """Remove report-only rows even when an assertion aborts a test."""

    yield
    with app.app_context():
        db = get_db()
        partner_ids = [
            row["id"]
            for row in db.execute(
                """SELECT id FROM affiliate_partners
                   WHERE ref_code LIKE 'REPORT%' OR ref_code LIKE 'PAGE-%'"""
            ).fetchall()
        ]
        if not partner_ids:
            return
        placeholders = ", ".join("?" for _ in partner_ids)
        db.execute(
            f"""DELETE FROM payment_transactions
                WHERE booking_id IN (
                    SELECT id FROM bookings
                    WHERE affiliate_partner_id IN ({placeholders})
                )""",
            partner_ids,
        )
        db.execute(
            f"DELETE FROM bookings WHERE affiliate_partner_id IN ({placeholders})",
            partner_ids,
        )
        db.execute(
            f"DELETE FROM affiliate_click_events WHERE partner_id IN ({placeholders})",
            partner_ids,
        )
        db.execute(
            f"DELETE FROM affiliate_rule_versions WHERE partner_id IN ({placeholders})",
            partner_ids,
        )
        db.execute(
            f"DELETE FROM affiliate_partners WHERE id IN ({placeholders})",
            partner_ids,
        )
        db.commit()


def test_affiliate_admin_requires_login(client):
    response = client.get("/admin/affiliates/")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_authenticated_admin_can_open_affiliate_module(authenticated_client):
    response = authenticated_client.get("/admin/affiliates/")

    assert response.status_code == 200
    assert "Affiliate partnerek" in response.get_data(as_text=True)


def test_admin_navigation_contains_affiliate_link(authenticated_client):
    response = authenticated_client.get("/admin/affiliates/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count('href="/admin/affiliates/"') == 2
    assert 'class="active"' in html


def test_affiliate_report_requires_login(client):
    response = client.get("/admin/affiliates/reports")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_affiliate_report_has_empty_state_and_navigation(authenticated_client):
    response = authenticated_client.get("/admin/affiliates/reports")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Még nincs megjeleníthető partner" in page
    assert page.count('href="/admin/affiliates/reports"') == 2
    assert 'class="active"' in page


def test_affiliate_report_renders_partner_snapshot_totals(
    authenticated_client, app, affiliate_report_cleanup
):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES ('REPORT25', 'Riport Partner')"
        ).lastrowid
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type, commission_type
            ) VALUES (?, 1, 'active', 'tracking', 'percentage')
            """,
            (partner_id,),
        ).lastrowid
        db.executemany(
            """
            INSERT INTO affiliate_click_events (
                event_key, partner_id, rule_version_id, visitor_id,
                is_bot, is_duplicate, utm_source, utm_medium,
                utm_campaign, landing_page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ("report-valid", partner_id, rule_id, "report-v1", 0, 0,
                 "google", "cpc", "spring", "/tours"),
                ("report-duplicate", partner_id, rule_id, "report-v1", 0, 1,
                 "google", "cpc", "spring", "/tours"),
                ("report-bot", partner_id, rule_id, "report-bot", 1, 0,
                 "<script>alert(1)</script>", "referral", "bot", "/robots"),
            ),
        )
        booking_id = db.execute(
            """
            INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email,
                participants_count, total_price, payment_status,
                affiliate_partner_id, affiliate_rule_version_id,
                affiliate_original_price, affiliate_discount_amount,
                affiliate_payable_price
            ) VALUES (
                1, 'REPORT-PAID', 'Teszt Elek', 'report@example.invalid',
                3, 25500, 'paid', ?, ?, 30000, 4500, 25500
            )
            """,
            (partner_id, rule_id),
        ).lastrowid
        db.execute(
            """INSERT INTO payment_transactions (
                   booking_id, order_ref, amount, status
               ) VALUES (?, 'REPORT-PAID', 25500, 'success')""",
            (booking_id,),
        )
        db.commit()

    response = authenticated_client.get("/admin/affiliates/reports")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Riport Partner" in page
    assert "3 összes" in page
    assert "1 érvényes" in page
    assert "1 becsült egyedi" in page
    assert "1 bot" in page
    assert "1 nem bot ismétlés" in page
    assert "Kattintási metrikák módszertana" in page
    assert "Kattintások forrás szerint" in page
    assert "google" in page
    assert "cpc" in page
    assert "spring" in page
    assert "/tours" in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert "Foglalási funnel" in page
    assert "Megkezdett fizetés" in page
    assert "100,00%" in page
    assert "Pénzügyi és résztvevő összesítő" in page
    assert "Résztvevők" in page
    assert "Foglaláskori snapshot" in page
    assert "30 000 Ft" in page
    assert "4 500 Ft" in page
    assert "25 500 Ft" in page


def test_affiliate_report_paginates_large_partner_set(
    authenticated_client, app, affiliate_report_cleanup
):
    with app.app_context():
        db = get_db()
        db.executemany(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ((f"PAGE-{index:02d}", f"Partner {index:02d}") for index in range(27)),
        )
        db.commit()

    first_page = authenticated_client.get("/admin/affiliates/reports")
    second_page = authenticated_client.get("/admin/affiliates/reports?page=2")

    first_html = first_page.get_data(as_text=True)
    second_html = second_page.get_data(as_text=True)
    assert first_page.status_code == second_page.status_code == 200
    assert "1 / 2. oldal" in first_html
    assert "Partner 00" in first_html
    assert "Partner 25" not in first_html
    assert "2 / 2. oldal" in second_html
    assert "Partner 25" in second_html
    assert "Partner 26" in second_html


def test_partner_list_has_empty_state(authenticated_client):
    response = authenticated_client.get("/admin/affiliates/")

    assert response.status_code == 200
    assert "Még nincs affiliate partner" in response.get_data(as_text=True)


def test_partner_list_search_and_detail(authenticated_client, app):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO affiliate_partners (
                ref_code, name, company_name, contact_name, contact_email,
                billing_city, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DUNA25",
                "Duna Partner",
                "Duna Kft.",
                "Teszt Elek",
                "partner@example.test",
                "Győr",
                1,
            ),
        )
        partner_id = cursor.lastrowid
        db.commit()

    response = authenticated_client.get("/admin/affiliates/?search=duna25")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Duna Partner" in html
    assert "partner@example.test" in html
    assert f'/admin/affiliates/{partner_id}' in html

    no_match = authenticated_client.get("/admin/affiliates/?search=nincs-ilyen")
    assert "Nincs találat" in no_match.get_data(as_text=True)

    detail = authenticated_client.get(f"/admin/affiliates/{partner_id}")
    detail_html = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert "Duna Kft." in detail_html
    assert "Győr" in detail_html
    assert "még nem tartozik szabályverzió" in detail_html


def test_missing_partner_detail_returns_404(authenticated_client):
    response = authenticated_client.get("/admin/affiliates/999999")

    assert response.status_code == 404


def test_partner_create_form_requires_login(client):
    response = client.get("/admin/affiliates/new")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_partner_create_form_displays_field_errors(authenticated_client, app):
    response = authenticated_client.post(
        "/admin/affiliates/new",
        data={"name": "", "contact_email": "hibas", "billing_country": "HUN"},
    )

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "A partner neve kötelező" in html
    assert "érvényes e-mail-címet" in html
    assert "Kétbetűs országkód" in html
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM affiliate_partners").fetchone()[0] == 0


def test_partner_creation_generates_ref_code(authenticated_client, app):
    response = authenticated_client.post(
        "/admin/affiliates/new",
        data={
            "name": "Tisza Partner",
            "company_name": "Tisza Kft.",
            "contact_email": "tisza@example.test",
            "billing_country": "HU",
            "billing_city": "Szeged",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        partner = get_db().execute(
            "SELECT * FROM affiliate_partners WHERE name = ?",
            ("Tisza Partner",),
        ).fetchone()
        assert partner is not None
        assert re.fullmatch(r"AFF-[A-HJ-NP-Z2-9]{10}", partner["ref_code"])
        assert partner["billing_country"] == "hu"
        assert partner["is_active"] == 1
        assert response.headers["Location"].endswith(f"/admin/affiliates/{partner['id']}")


def test_ref_code_collision_is_retried(authenticated_client, app, monkeypatch):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ("AFF-DUPLICATE1", "Meglévő partner"),
        )
        db.commit()

    generated_codes = iter(("AFF-DUPLICATE1", "AFF-UNIQUE2345"))
    monkeypatch.setattr(
        "flaskr.admin.admin_affiliates._new_ref_code",
        lambda: next(generated_codes),
    )

    response = authenticated_client.post(
        "/admin/affiliates/new",
        data={"name": "Új partner", "billing_country": "hu"},
    )

    assert response.status_code == 302
    with app.app_context():
        refs = {
            row["ref_code"]
            for row in get_db().execute("SELECT ref_code FROM affiliate_partners").fetchall()
        }
    assert refs == {"AFF-DUPLICATE1", "AFF-UNIQUE2345"}


def _insert_editable_partner(app, ref_code="AFF-EDITABLE1"):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO affiliate_partners (
                ref_code, name, contact_email, billing_country
            ) VALUES (?, ?, ?, ?)
            """,
            (ref_code, "Régi név", "old@example.test", "hu"),
        )
        db.commit()
        return cursor.lastrowid


def test_partner_edit_preserves_ref_code(authenticated_client, app):
    partner_id = _insert_editable_partner(app)

    response = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/edit",
        data={
            "name": "Új név",
            "contact_email": "new@example.test",
            "billing_country": "AT",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        partner = get_db().execute(
            "SELECT * FROM affiliate_partners WHERE id = ?", (partner_id,)
        ).fetchone()
        assert partner["name"] == "Új név"
        assert partner["contact_email"] == "new@example.test"
        assert partner["billing_country"] == "at"
        assert partner["ref_code"] == "AFF-EDITABLE1"


def test_invalid_partner_edit_does_not_write(authenticated_client, app):
    partner_id = _insert_editable_partner(app)

    response = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/edit",
        data={"name": "", "contact_email": "invalid", "billing_country": "hu"},
    )

    assert response.status_code == 400
    with app.app_context():
        partner = get_db().execute(
            "SELECT * FROM affiliate_partners WHERE id = ?", (partner_id,)
        ).fetchone()
        assert partner["name"] == "Régi név"
        assert partner["contact_email"] == "old@example.test"


def test_partner_status_controls_active_ref_resolution(authenticated_client, app):
    partner_id = _insert_editable_partner(app)

    disabled = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/status",
        data={"is_active": "0"},
    )
    assert disabled.status_code == 302
    with app.app_context():
        db = get_db()
        assert get_active_partner_by_ref(db, "aff-editable1") is None

    enabled = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/status",
        data={"is_active": "1"},
    )
    assert enabled.status_code == 302
    with app.app_context():
        partner = get_active_partner_by_ref(get_db(), "aff-editable1")
        assert partner is not None
        assert partner["id"] == partner_id


def test_partner_status_rejects_invalid_state(authenticated_client, app):
    partner_id = _insert_editable_partner(app)

    response = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/status",
        data={"is_active": "yes"},
    )

    assert response.status_code == 400


def test_rule_form_requires_login(client, app):
    partner_id = _insert_editable_partner(app)

    response = client.get(f"/admin/affiliates/{partner_id}/rules/new")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_rule_form_exposes_dynamic_field_groups(authenticated_client, app):
    partner_id = _insert_editable_partner(app)

    response = authenticated_client.get(f"/admin/affiliates/{partner_id}/rules/new")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-rule-controller="discount"' in html
    assert 'data-visible-for="discount:free_participants"' in html
    assert 'data-rule-controller="commission"' in html
    assert 'data-limit-dependent' in html
    assert 'data-session-only' in html


def test_rule_form_filters_irrelevant_submitted_fields(authenticated_client, app):
    partner_id = _insert_editable_partner(app)

    response = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/rules/new",
        data={
            "discount_type": "tracking",
            "discount_value": "9999",
            "discount_participant_count": "9",
            "max_discount_amount": "5000",
            "commission_type": "none",
            "commission_value": "9999",
            "usage_unit": "participant",
            "budget_period_type": "monthly",
            "attribution_window_days": "30",
            "session_only": "1",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 302
    with app.app_context():
        rule = get_db().execute("SELECT * FROM affiliate_rule_versions").fetchone()
        assert rule["discount_type"] == "tracking"
        assert rule["discount_value"] == 0
        assert rule["discount_participant_count"] is None
        assert rule["max_discount_amount"] is None
        assert rule["commission_value"] == 0
        assert rule["session_only"] == 1
        assert rule["attribution_window_days"] == 0


def test_rule_form_data_keeps_only_selected_mode_values():
    normalized = _rule_form_data(
        {
            "discount_type": "free_participants",
            "discount_value": "25",
            "discount_participant_count": "2",
            "max_discount_amount": "1000",
            "commission_type": "fixed",
            "commission_value": "1500",
            "total_usage_limit": "100",
            "guest_usage_limit": "",
            "usage_unit": "participant",
            "budget_period_type": "monthly",
            "valid_from": "2026-11-01T00:00",
            "valid_until": "2026-12-01T00:00",
            "attribution_window_days": "14",
        }
    )

    assert normalized["discount_value"] == ""
    assert normalized["discount_participant_count"] == "2"
    assert normalized["max_discount_amount"] == ""
    assert normalized["commission_value"] == "1500"
    assert normalized["usage_unit"] == "participant"
    assert normalized["budget_period_type"] == "monthly"
    assert normalized["attribution_window_days"] == "14"


def test_rule_form_lists_tours_and_locations(authenticated_client, app):
    partner_id = _insert_editable_partner(app)
    with app.app_context():
        db = get_db()
        location_id = db.execute(
            "INSERT INTO tour_locations (name) VALUES (?)", ("Dunakanyar",)
        ).lastrowid
        db.execute(
            """
            INSERT INTO tours (title, date, time, price, tour_location_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Naplemente túra", "2026-11-10", "16:00", 12000, location_id),
        )
        db.commit()

    response = authenticated_client.get(f"/admin/affiliates/{partner_id}/rules/new")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Minden túra" in html
    assert "Naplemente túra" in html
    assert "Dunakanyar" in html
    assert 'data-scope-fields="tour"' in html
    assert 'data-scope-fields="location"' in html


def test_scope_form_data_keeps_only_relevant_unique_ids():
    scope = _scope_form_data(
        {
            "scope_mode": "tour",
            "tour_ids": ["3", "3", "bad", "4"],
            "location_ids": ["8"],
        }
    )

    assert scope == {"scope_mode": "tour", "tour_ids": [3, 4], "location_ids": []}


def test_rule_scopes_round_trip_without_loss(app):
    partner_id = _insert_editable_partner(app, "AFF-SCOPE0001")
    with app.app_context():
        db = get_db()
        first_location = db.execute(
            "INSERT INTO tour_locations (name) VALUES (?)", ("Rába",)
        ).lastrowid
        second_location = db.execute(
            "INSERT INTO tour_locations (name) VALUES (?)", ("Tisza",)
        ).lastrowid
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, discount_type
            ) VALUES (?, 1, 'tracking')
            """,
            (partner_id,),
        ).lastrowid

        expected = {
            "scope_mode": "location",
            "tour_ids": [],
            "location_ids": [first_location, second_location],
        }
        replace_rule_scopes(db, rule_id, expected)
        db.commit()

        assert load_rule_scope(db, rule_id) == expected

        replace_rule_scopes(
            db,
            rule_id,
            {"scope_mode": "all", "tour_ids": [], "location_ids": []},
        )
        db.commit()
        assert load_rule_scope(db, rule_id) == {
            "scope_mode": "all",
            "tour_ids": [],
            "location_ids": [],
        }


def test_new_active_rule_archives_previous_without_rewriting_it(app):
    partner_id = _insert_editable_partner(app, "AFF-VERSION001")
    base_form = {
        "status": "active",
        "discount_type": "fixed",
        "discount_value": "1000",
        "discount_participant_count": "",
        "max_discount_amount": "",
        "commission_type": "none",
        "commission_value": "",
        "attribution_window_days": "30",
        "session_only": False,
        "valid_from": "",
        "valid_until": "",
        "total_usage_limit": "",
        "guest_usage_limit": "",
        "usage_unit": "booking",
        "budget_period_type": "lifetime",
    }
    all_scope = {"scope_mode": "all", "tour_ids": [], "location_ids": []}

    with app.app_context():
        db = get_db()
        first_id, first_version = save_rule_version(db, partner_id, base_form, all_scope)
        second_form = {**base_form, "discount_value": "2500"}
        second_id, second_version = save_rule_version(db, partner_id, second_form, all_scope)
        rules = db.execute(
            """
            SELECT id, version_number, status, discount_value
              FROM affiliate_rule_versions
             WHERE partner_id = ? ORDER BY version_number
            """,
            (partner_id,),
        ).fetchall()

    assert (first_version, second_version) == (1, 2)
    assert [row["id"] for row in rules] == [first_id, second_id]
    assert dict(rules[0]) == {
        "id": first_id,
        "version_number": 1,
        "status": "archived",
        "discount_value": 1000,
    }
    assert dict(rules[1]) == {
        "id": second_id,
        "version_number": 2,
        "status": "active",
        "discount_value": 2500,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"discount_type": "percentage", "discount_value": "101"},
        {"discount_type": "fixed", "discount_value": "not-a-number"},
        {"commission_type": "percentage", "commission_value": "150"},
        {"total_usage_limit": "2", "guest_usage_limit": "3"},
        {"valid_from": "2026-12-02T10:00", "valid_until": "2026-12-01T10:00"},
        {"scope_mode": "tour", "tour_ids": "999999"},
    ],
)
def test_rule_form_rejects_manipulated_requests(authenticated_client, app, overrides):
    partner_id = _insert_editable_partner(app)
    data = {
        "status": "draft",
        "discount_type": "tracking",
        "commission_type": "none",
        "attribution_window_days": "30",
        "scope_mode": "all",
    }
    data.update(overrides)

    response = authenticated_client.post(
        f"/admin/affiliates/{partner_id}/rules/new", data=data
    )

    assert response.status_code == 400
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM affiliate_rule_versions").fetchone()[0] == 0


def test_rule_form_post_requires_csrf_when_enabled(authenticated_client, app):
    partner_id = _insert_editable_partner(app)
    previous = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = authenticated_client.post(
            f"/admin/affiliates/{partner_id}/rules/new",
            data={
                "status": "draft",
                "discount_type": "tracking",
                "commission_type": "none",
                "attribution_window_days": "30",
                "scope_mode": "all",
            },
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = previous

    assert response.status_code == 400


def test_partner_detail_contains_copyable_full_referral_url(authenticated_client, app):
    partner_id = _insert_editable_partner(app, "AFF-COPYLINK1")

    response = authenticated_client.get(f"/admin/affiliates/{partner_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="http://localhost/?ref=AFF-COPYLINK1"' in html
    assert "Link másolása" in html
    assert "navigator.clipboard.writeText(input.value)" in html
    assert "flex-col sm:flex-row" in html


def test_partner_detail_builds_encoded_reversible_utm_url(authenticated_client, app):
    partner_id = _insert_editable_partner(app, "AFF-UTMLINK1")

    response = authenticated_client.get(
        f"/admin/affiliates/{partner_id}",
        query_string={
            "utm_source": "  hírlevél & partner\x00  ",
            "utm_medium": "social / paid",
            "utm_campaign": "őszi túra?",
            "customer_email": "must-not-appear@example.test",
        },
    )
    page = response.get_data(as_text=True)
    match = re.search(r'id="referral-url"[^>]+value="([^"]+)"', page)

    assert response.status_code == 200
    assert match is not None
    generated_url = html.unescape(match.group(1))
    query = parse_qs(urlsplit(generated_url).query)
    assert query == {
        "ref": ["AFF-UTMLINK1"],
        "utm_source": ["hírlevél & partner"],
        "utm_medium": ["social / paid"],
        "utm_campaign": ["őszi túra?"],
    }
    assert "%26" in generated_url
    assert "must-not-appear" not in page
    assert "UTM-link elkészítése" in page
