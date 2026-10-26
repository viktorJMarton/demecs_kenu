"""Endpoint coverage for the affiliate admin entry point."""

import pytest


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
