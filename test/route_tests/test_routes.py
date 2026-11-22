"""
Route tests for backend route handlers.
Tests route logic and business rules without full HTTP requests.
"""

import pytest
from unittest.mock import Mock, patch
from flaskr.main import create_app
from flaskr.admin.admin_tours import bp as tours_bp
from flaskr.admin.admin_bookings import bp as bookings_bp
from flaskr.admin.admin_dashboard import bp as dashboard_bp


class TestRouteLogic:
    """Test route handler logic."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app()
        app.config['TESTING'] = True
        return app

    def test_tour_creation_logic(self, app):
        """Test tour creation route logic."""
        with app.app_context():
            with app.test_request_context():
                # Mock the database and test route logic
                with patch('flaskr.admin.admin_tours.get_db') as mock_db:
                    mock_conn = Mock()
                    mock_db.return_value = mock_conn

                    # Test the route logic here
                    # This would test the business logic of tour creation
                    pass

    def test_booking_status_update_logic(self, app):
        """Test booking status update route logic."""
        with app.app_context():
            with app.test_request_context():
                # Mock database operations
                with patch('flaskr.admin.admin_bookings.get_db') as mock_db:
                    with patch('flaskr.admin.admin_bookings.broadcast_booking_update') as mock_broadcast:
                        mock_conn = Mock()
                        mock_db.return_value = mock_conn

                        # Mock database responses
                        mock_conn.execute.return_value.fetchone.return_value = {
                            'id': 1,
                            'tour_id': 1,
                            'customer_name': 'Test User',
                            'payment_status': 'pending'
                        }

                        # Test the route logic
                        # This would test status update business rules
                        pass


class TestRouteValidation:
    """Test route input validation."""

    def test_tour_form_validation(self, app):
        """Test tour form input validation."""
        with app.app_context():
            # Test validation logic for tour forms
            pass

    def test_booking_form_validation(self, app):
        """Test booking form input validation."""
        with app.app_context():
            # Test validation logic for booking forms
            pass


class TestRoutePermissions:
    """Test route access permissions."""

    def test_admin_route_access_control(self, app):
        """Test that admin routes check permissions."""
        with app.app_context():
            # Test login_required decorator and admin access
            pass


def test_login_recovers_from_missing_session_cookie(app, monkeypatch):
    import re
    from werkzeug.security import generate_password_hash

    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    user = {"username": "fixture_admin", "password_hash": generate_password_hash("fixture-login")}
    monkeypatch.setattr("flaskr.auth.find_user_by_username", lambda name: user if name == user["username"] else None)
    login_url = "/auth/login?next=%2Fadmin%2Fcontent"

    def token(response):
        assert response.headers["Cache-Control"] == "private, no-store"
        return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))[1]

    old_token = token(app.test_client().get(login_url))
    browser = app.test_client()
    form = {"username": "fixture_admin", "password": "fixture-login", "csrf_token": old_token}
    rejected = browser.post(login_url, data=form)
    assert rejected.status_code == 400
    assert "Add meg újra a belépési adatokat." in rejected.get_data(as_text=True)
    assert token(rejected) != old_token
    retry = browser.post(login_url, data={**form, "csrf_token": token(rejected)})
    assert retry.status_code == 302 and retry.location == "/admin/content"


def test_admin_tour_list_includes_inactive_tours_and_filters_them(client, app, monkeypatch):
    from flaskr.db import get_db

    monkeypatch.setattr("flaskr.auth.find_user_by_username", lambda username: {
        "username": username, "password_hash": "unused", "is_admin": True,
    })
    with client.session_transaction() as session:
        session["username"] = "fixture-admin"
    with app.app_context():
        db = get_db()
        with db:
            db.executemany(
                "INSERT INTO tours (title, date, time, price, is_active) VALUES (?, ?, '10:00', 10000, ?)",
                [("Dunakanyar próba inaktív", "2099-01-01", 0), ("Dunakanyar próba aktív", "2099-01-01", 1)],
            )
    query = {"search": "Dunakanyar próba"}
    listing = client.get("/admin/tours", query_string=query).get_data(as_text=True)
    assert "Dunakanyar próba inaktív" in listing and "Dunakanyar próba aktív" in listing
    inactive = client.get("/admin/tours", query_string={**query, "status_filter": "inaktiv"}).get_data(as_text=True)
    assert "Dunakanyar próba inaktív" in inactive and "Dunakanyar próba aktív" not in inactive
    assert 'class="badge badge-ghost">Inaktív</div>' in inactive
    active = client.get("/admin/tours", query_string={**query, "status_filter": "elerheto"}).get_data(as_text=True)
    assert "Dunakanyar próba aktív" in active and "Dunakanyar próba inaktív" not in active
    public = app.test_client().get("/api/tours", query_string={"date": "2099-01-01"}).get_json()
    assert {tour["title"] for tour in public} == {"Dunakanyar próba aktív"}
