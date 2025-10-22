"""
Endpoint tests for Flask routes and API endpoints.
Tests HTTP requests and responses for various endpoints.
"""

import pytest
from flaskr.main import create_app


class TestEndpoints:
    """Test class for endpoint testing."""

    @pytest.fixture
    def app(self):
        """Create and configure a test app instance."""
        app = create_app()
        app.config.update({
            'TESTING': True,
            'DATABASE': ':memory:',  # Use in-memory database for tests
        })
        return app

    @pytest.fixture
    def client(self, app):
        """A test client for the app."""
        return app.test_client()

    def test_home_page(self, client, app):
        """Test the home page endpoint."""
        with app.app_context():
            from flaskr.db import init_db
            init_db()  # Ensure database is initialized
        response = client.get('/')
        assert response.status_code == 200
        assert b'<title>KAJAK_KENU</title>' in response.data  # Check for expected content

    def test_admin_dashboard_requires_login(self, client):
        """Test that admin dashboard requires authentication."""
        response = client.get('/admin/')
        assert response.status_code == 302  # Redirect to login

    def test_api_template_endpoint(self, client):
        """Test API template endpoint."""
        response = client.get('/api/template/tour-reservation')
        assert response.status_code == 200
        assert b'tour-name-display' in response.data


# Example of testing with authentication
class TestAuthenticatedEndpoints:
    """Test endpoints that require authentication."""

    @pytest.fixture
    def authenticated_client(self, client):
        """Create a client with authenticated session."""
        # This would need to be implemented based on your auth system
        # For now, just return the client
        return client

    def test_admin_dashboard_authenticated(self, authenticated_client):
        """Test admin dashboard with authentication."""
        # This test would need proper authentication setup
        pass