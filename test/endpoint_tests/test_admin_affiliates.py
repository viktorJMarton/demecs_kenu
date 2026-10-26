"""Endpoint coverage for the affiliate admin entry point."""

import re

import pytest

from flaskr.db import get_db


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
