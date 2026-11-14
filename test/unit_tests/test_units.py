"""
Unit tests for individual functions and classes.
Tests isolated components without external dependencies.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from flaskr.models import Tour, Booking, User
from flaskr.services.tour_service import get_all_tours, get_tour_by_id


class TestModels:
    """Test model classes."""

    def test_tour_model_creation(self):
        """Test Tour model creation and methods."""
        tour_data = {
            'id': 1,
            'title': 'Test Tour',
            'description': 'A test tour',
            'date': '2025-12-01',
            'time': '10:00',
            'price': 15000,
            'difficulty': 'Haladó',
            'location': 'Balaton',
            'meeting_point': 'Veszprém',
            'duration': '3 óra',
            'max_participants': 10,
            'is_active': 1
        }

        tour = Tour.from_db_row(tour_data)

        assert tour.id == 1
        assert tour.title == 'Test Tour'
        assert tour.price == 15000
        assert tour.is_active == True

    def test_booking_model_creation(self):
        """Test Booking model creation."""
        booking_data = {
            'id': 1,
            'tour_id': 1,
            'customer_name': 'John Doe',
            'customer_email': 'john@example.com',
            'customer_phone': '+36301234567',
            'participants_count': 2,
            'lifejacket_sizes': json.dumps(['70-90 kg', '50-70 kg']),
            'special_requests': 'Vegetarian meal',
            'payment_status': 'pending',
            'order_ref': 'ORDER123',
            'total_price': 20000,
            'booking_date': '2025-10-01 14:30:00'
        }

        booking = Booking.from_db_row(booking_data)

        assert booking.id == 1
        assert booking.customer_name == 'John Doe'
        assert booking.participants_count == 2
        assert booking.payment_status == 'pending'
        assert booking.lifejacket_sizes == ['70-90 kg', '50-70 kg']


class TestTourService:
    """Test tour service functions."""

    @patch('flaskr.services.tour_service.get_db')
    def test_get_all_tours(self, mock_get_db):
        """Test get_all_tours function."""
        mock_conn = Mock()
        mock_get_db.return_value = mock_conn

        # Mock database response
        mock_tours = [
            {'id': 1, 'title': 'Tour 1', 'description': 'Desc 1', 'date': '2025-12-01', 'time': '10:00',
             'price': 10000, 'difficulty': 'Kezdő', 'location': 'Balaton', 'is_active': 1},
            {'id': 2, 'title': 'Tour 2', 'description': 'Desc 2', 'date': '2025-12-02', 'time': '14:00',
             'price': 15000, 'difficulty': 'Haladó', 'location': 'Velencei-tó', 'is_active': 1}
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_tours

        tours = get_all_tours()

        assert len(tours) == 2
        assert tours[0].title == 'Tour 1'
        assert tours[1].title == 'Tour 2'
        mock_conn.execute.assert_called_once()

    @patch('flaskr.services.tour_service.get_db')
    def test_get_tour_by_id(self, mock_get_db):
        """Test get_tour_by_id function."""
        mock_conn = Mock()
        mock_get_db.return_value = mock_conn

        mock_tour = {'id': 1, 'title': 'Test Tour', 'description': 'Test Description',
                     'date': '2025-12-01', 'time': '10:00', 'price': 12000, 'difficulty': 'Haladó',
                     'location': 'Balaton', 'is_active': 1}
        mock_conn.execute.return_value.fetchone.return_value = mock_tour

        tour = get_tour_by_id(1)

        assert tour is not None
        assert tour.id == 1
        assert tour.title == 'Test Tour'


class TestUtilityFunctions:
    """Test utility functions."""

    def test_date_validation(self):
        """Test date validation functions."""
        # Test date parsing and validation
        pass

    def test_email_validation(self):
        """Test email validation."""
        # Test email format validation
        pass