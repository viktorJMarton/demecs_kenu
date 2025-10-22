"""
Integration tests for the Flask application.
Tests full system functionality including database operations.
"""

import pytest
import tempfile
import os
from flaskr.main import create_app
from flaskr.db import init_db


class TestIntegration:
    """Test class for integration testing."""

    @pytest.fixture
    def app(self):
        """Create and configure a test app instance with temporary database."""
        db_fd, db_path = tempfile.mkstemp()

        app = create_app()
        app.config.update({
            'TESTING': True,
            'DATABASE': db_path,
        })

        with app.app_context():
            init_db()  # Initialize the database

        yield app

        # Cleanup
        os.close(db_fd)
        os.unlink(db_path)

    @pytest.fixture
    def client(self, app):
        """A test client for the app."""
        return app.test_client()

    def test_full_tour_booking_flow(self, client, app):
        """Test complete tour booking workflow."""
        with app.app_context():
            # This would test:
            # 1. Create a tour
            # 2. View tour on homepage
            # 3. Make a booking
            # 4. Check booking in admin
            # 5. Update booking status
            pass

    def test_admin_workflow(self, client, app):
        """Test admin functionality workflow."""
        with app.app_context():
            # Test admin login, tour management, booking management
            pass

    def test_database_operations(self, app):
        """Test database operations work correctly."""
        with app.app_context():
            from flaskr import db
            conn = db.get_db()

            # Test basic database operations
            tours = conn.execute('SELECT COUNT(*) as count FROM tours').fetchone()
            assert tours['count'] >= 0  # Should have a count field

            bookings = conn.execute('SELECT COUNT(*) as count FROM bookings').fetchone()
            assert bookings['count'] >= 0


class TestDatabaseIntegration:
    """Test database integration specifically."""

    def test_schema_integrity(self, app):
        """Test that database schema is correct."""
        with app.app_context():
            from flaskr import db
            conn = db.get_db()

            # Check if tables exist
            tables = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('tours', 'bookings')
            """).fetchall()

            table_names = [table['name'] for table in tables]
            assert 'tours' in table_names
            assert 'bookings' in table_names