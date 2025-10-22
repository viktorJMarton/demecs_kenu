"""
Shared test configuration and fixtures for all test types.
This file provides common setup for endpoint, integration, route, and unit tests.
"""

import pytest
import tempfile
import os
import sys

# Add the parent directory to Python path so we can import flaskr
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flaskr.main import create_app
from flaskr.db import init_db


@pytest.fixture(scope='session')
def app():
    """Create and configure a test app instance for the entire test session."""
    db_fd, db_path = tempfile.mkstemp()

    app = create_app()
    app.config.update({
        'TESTING': True,
        'DATABASE': db_path,
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for easier testing
    })

    with app.app_context():
        init_db()  # Initialize database with schema

    yield app

    # Cleanup after all tests
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """A test client for the app."""
    with app.app_context():
        init_db()  # Ensure database is initialized for each test
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def db_session(app):
    """Database session for tests that need direct database access."""
    with app.app_context():
        from flaskr import db
        yield db.get_db()


# Authentication fixtures
@pytest.fixture
def auth_client(client):
    """A test client with authentication."""
    # This would need to be implemented based on your auth system
    # For now, just return the client
    return client


# Sample data fixtures
@pytest.fixture
def sample_tour_data():
    """Sample tour data for testing."""
    return {
        'title': 'Test Kajak Tour',
        'description': 'An amazing test tour on the lake',
        'date': '2025-12-25',
        'time': '10:00',
        'price': 15000,
        'difficulty': 'Közepes',
        'location': 'Balaton',
        'meeting_point': 'Balatonfüred',
        'duration': '3 óra',
        'max_participants': 8,
        'is_active': 1
    }


@pytest.fixture
def sample_booking_data():
    """Sample booking data for testing."""
    return {
        'tour_id': 1,
        'customer_name': 'Test User',
        'customer_email': 'test@example.com',
        'customer_phone': '+36301234567',
        'participants_count': 2,
        'special_requests': 'No special requests',
        'payment_status': 'pending',
        'order_ref': 'TEST123'
    }


# Custom markers for different test types
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "endpoint: mark test as an endpoint test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "route: mark test as a route test")
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


# Test configuration
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location."""
    for item in items:
        # Add markers based on test file location
        if 'endpoint_tests' in str(item.fspath):
            item.add_marker(pytest.mark.endpoint)
        elif 'integration_tests' in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif 'route_tests' in str(item.fspath):
            item.add_marker(pytest.mark.route)
        elif 'unit_tests' in str(item.fspath):
            item.add_marker(pytest.mark.unit)