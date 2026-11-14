"""
Data models for the Kajak-Kenu application.
Simple data classes to represent database entities.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import json


@dataclass
class TourLocation:
    """Reusable tour location entry with optional coordinates."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_db_row(cls, row):
        if not row:
            return None
        return cls(
            id=row['id'],
            name=row['name'],
            description=row.get('description', ''),
            latitude=row.get('latitude'),
            longitude=row.get('longitude'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )


@dataclass
class Tour:
    """Tour model representing a kayak/canoe tour."""
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    date: str = ""
    time: str = ""
    duration: int = 0  # minutes
    max_participants: int = 15
    price: int = 0  # HUF
    difficulty: str = "Kezdő"  # Kezdő vagy Haladó
    location: str = ""
    tour_location_id: Optional[int] = None
    distance: Optional[float] = None  # km
    meeting_point: str = ""
    equipment_included: str = ""
    what_to_bring: str = ""
    cancellation_policy: Optional[str] = None
    image_url: Optional[str] = None
    tour_latitude: Optional[float] = None
    tour_longitude: Optional[float] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    # Computed fields (not in DB)
    booking_count: int = 0
    participants: int = 0

    @classmethod
    def from_db_row(cls, row):
        """Create Tour instance from database row."""
        if not row:
            return None
        return cls(
            id=row['id'],
            title=row['title'],
            description=row.get('description', ''),
            date=row['date'],
            time=row['time'],
            duration=row.get('duration', 0),
            max_participants=row.get('max_participants', 15),
            price=row['price'],
            difficulty=row.get('difficulty', 'Kezdő'),
            location=row.get('location', ''),
            tour_location_id=row.get('tour_location_id'),
            distance=row.get('distance'),
            meeting_point=row.get('meeting_point', ''),
            equipment_included=row.get('equipment_included', ''),
            what_to_bring=row.get('what_to_bring', ''),
            cancellation_policy=row.get('cancellation_policy'),
            image_url=row.get('image_url'),
            tour_latitude=row.get('tour_latitude'),
            tour_longitude=row.get('tour_longitude'),
            is_active=bool(row.get('is_active', 1)),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
            booking_count=row.get('booking_count', 0),
            participants=row.get('participants', 0)
        )


@dataclass
class Booking:
    """Booking model representing a tour reservation."""
    id: Optional[int] = None
    tour_id: int = 0
    order_ref: str = ""
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: Optional[str] = None
    participants_count: int = 1
    total_price: int = 0
    lifejacket_sizes: Optional[List[str]] = None
    payment_status: str = "pending"  # pending, paid, failed, cancelled, refunded
    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None
    customer_notes: Optional[str] = None
    special_requirements: Optional[str] = None
    emergency_contact: Optional[str] = None
    booking_date: Optional[str] = None
    payment_date: Optional[str] = None
    cancellation_date: Optional[str] = None
    admin_notes: Optional[str] = None
    invoice_name: Optional[str] = None
    invoice_country: Optional[str] = None
    invoice_city: Optional[str] = None
    invoice_zip: Optional[str] = None
    invoice_address: Optional[str] = None
    invoice_company: Optional[str] = None
    invoice_state: Optional[str] = None
    tour_latitude: Optional[float] = None
    tour_longitude: Optional[float] = None
    
    # Joined fields from tours table
    tour_title: Optional[str] = None
    tour_date: Optional[str] = None
    tour_time: Optional[str] = None
    tour_location: Optional[str] = None
    meeting_point: Optional[str] = None
    tour_duration: Optional[int] = None
    tour_difficulty: Optional[str] = None

    @classmethod
    def from_db_row(cls, row):
        """Create Booking instance from database row."""
        if not row:
            return None
        return cls(
            id=row['id'],
            tour_id=row['tour_id'],
            order_ref=row['order_ref'],
            customer_name=row['customer_name'],
            customer_email=row['customer_email'],
            customer_phone=row.get('customer_phone'),
            participants_count=row.get('participants_count', 1),
            lifejacket_sizes=_parse_lifejacket_sizes(row.get('lifejacket_sizes')),
            total_price=row['total_price'],
            payment_status=row.get('payment_status', 'pending'),
            payment_method=row.get('payment_method'),
            transaction_id=row.get('transaction_id'),
            customer_notes=row.get('customer_notes'),
            special_requirements=row.get('special_requirements'),
            emergency_contact=row.get('emergency_contact'),
            booking_date=row.get('booking_date'),
            payment_date=row.get('payment_date'),
            cancellation_date=row.get('cancellation_date'),
            admin_notes=row.get('admin_notes'),
            invoice_name=row.get('invoice_name'),
            invoice_country=row.get('invoice_country'),
            invoice_city=row.get('invoice_city'),
            invoice_zip=row.get('invoice_zip'),
            invoice_address=row.get('invoice_address'),
            invoice_company=row.get('invoice_company'),
            invoice_state=row.get('invoice_state'),
            tour_latitude=row.get('tour_latitude'),
            tour_longitude=row.get('tour_longitude'),
            tour_title=row.get('tour_title'),
            tour_date=row.get('tour_date'),
            tour_time=row.get('tour_time'),
            tour_location=row.get('location'),
            meeting_point=row.get('meeting_point'),
            tour_duration=row.get('duration'),
            tour_difficulty=row.get('difficulty')
        )


def _parse_lifejacket_sizes(raw_value):
    """Safely parse lifejacket sizes JSON payloads."""
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return raw_value
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return parsed
    except (TypeError, json.JSONDecodeError):
        return []
    return []


@dataclass
class User:
    """User model for admin authentication."""
    username: str
    password_hash: str
    is_admin: bool = True
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict):
        """Create User instance from dictionary."""
        return cls(
            username=data.get('username', ''),
            password_hash=data.get('password_hash', ''),
            is_admin=data.get('is_admin', True),
            created_at=data.get('created_at')
        )
