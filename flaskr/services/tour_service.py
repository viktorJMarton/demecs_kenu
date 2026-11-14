"""
Tour service - Business logic for tour management.
"""

from datetime import datetime
from typing import List, Optional
from ..db import get_db
from ..models import Tour, TourLocation
from ..events import broadcast_tour_update, broadcast_system_message


def _has_tour_already_run(date_str: Optional[str], time_str: Optional[str]) -> bool:
    """Return True when the stored tour date/time is already in the past."""
    if not date_str:
        return False

    time_component = time_str or "00:00"
    try:
        scheduled_dt = datetime.strptime(f"{date_str} {time_component}", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            scheduled_dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return False

    return scheduled_dt <= datetime.now()


def get_all_tours(search: str = "", date_from: str = "", date_to: str = "", active_only: bool = True) -> List[Tour]:
    """Get all tours with optional filters."""
    db = get_db()
    
    query = '''
        SELECT t.*, COUNT(b.id) as booking_count,
               SUM(CASE WHEN b.payment_status IN ('paid', 'pending') THEN b.participants_count ELSE 0 END) as participants
        FROM tours t
        LEFT JOIN bookings b ON t.id = b.tour_id
        WHERE 1=1
    '''
    params = []
    
    if active_only:
        query += ' AND t.is_active = 1'
    
    if search:
        query += ' AND (t.title LIKE ? OR t.description LIKE ? OR t.location LIKE ?)'
        search_param = f'%{search}%'
        params.extend([search_param, search_param, search_param])
    
    if date_from:
        query += ' AND t.date >= ?'
        params.append(date_from)
    
    if date_to:
        query += ' AND t.date <= ?'
        params.append(date_to)
    
    query += ' GROUP BY t.id ORDER BY t.date DESC'
    
    rows = db.execute(query, params).fetchall()
    return [Tour.from_db_row(row) for row in rows]


def get_tour_by_id(tour_id: int) -> Optional[Tour]:
    """Get a single tour by ID."""
    db = get_db()
    row = db.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()
    return Tour.from_db_row(row) if row else None


def get_upcoming_tours(limit: int = 5) -> List[Tour]:
    """Get upcoming active tours."""
    db = get_db()
    rows = db.execute('''
        SELECT t.*, COUNT(b.id) as booking_count
        FROM tours t
        LEFT JOIN bookings b ON t.id = b.tour_id AND b.payment_status IN ('paid', 'pending')
        WHERE t.date >= date('now') AND t.is_active = 1
        GROUP BY t.id
        ORDER BY t.date
        LIMIT ?
    ''', (limit,)).fetchall()
    return [Tour.from_db_row(row) for row in rows]


def create_tour(tour_data: dict) -> int:
    """Create a new tour."""
    db = get_db()
    cursor = db.execute('''
    INSERT INTO tours (title, description, date, time, duration, max_participants,
             price, difficulty, location, tour_location_id, distance, meeting_point,
             equipment_included, what_to_bring, tour_latitude, tour_longitude)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        tour_data['title'],
        tour_data['description'],
        tour_data['date'],
        tour_data['time'],
        tour_data['duration'],
        tour_data['max_participants'],
        tour_data['price'],
        tour_data['difficulty'],
        tour_data['location'],
        tour_data.get('tour_location_id'),
        tour_data.get('distance'),
        tour_data['meeting_point'],
        tour_data['equipment_included'],
        tour_data.get('what_to_bring', ''),
        tour_data.get('tour_latitude'),
        tour_data.get('tour_longitude')
    ))
    
    new_tour_id = cursor.lastrowid
    db.commit()
    
    # Broadcast event
    broadcast_tour_update(new_tour_id, 'created', {
        'id': new_tour_id,
        'title': tour_data['title'],
        'date': tour_data['date'],
        'time': tour_data['time'],
        'price': tour_data['price'],
        'max_participants': tour_data['max_participants'],
        'difficulty': tour_data['difficulty'],
        'location': tour_data['location']
    })
    
    broadcast_system_message(f'Új túra hozzáadva: {tour_data["title"]}', 'success')
    
    return new_tour_id


def update_tour(tour_id: int, tour_data: dict) -> bool:
    """Update an existing tour."""
    db = get_db()
    
    # Check for overbooking
    old_tour = get_tour_by_id(tour_id)
    if not old_tour:
        return False
    
    new_max = tour_data['max_participants']
    if new_max < old_tour.max_participants:
        current_bookings = db.execute('''
            SELECT COUNT(*) as count FROM bookings
            WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
        ''', (tour_id,)).fetchone()['count']
        
        if current_bookings > new_max:
            broadcast_system_message(
                f'Túlfoglalás riasztás: {tour_data["title"]} - {current_bookings}/{new_max} fő',
                'error'
            )
    
    db.execute('''
    UPDATE tours SET title = ?, description = ?, date = ?, time = ?,
               duration = ?, max_participants = ?, price = ?, difficulty = ?,
               location = ?, tour_location_id = ?, distance = ?, meeting_point = ?,
               equipment_included = ?, what_to_bring = ?, tour_latitude = ?,
               tour_longitude = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        tour_data['title'],
        tour_data['description'],
        tour_data['date'],
        tour_data['time'],
        tour_data['duration'],
        tour_data['max_participants'],
        tour_data['price'],
        tour_data['difficulty'],
        tour_data['location'],
        tour_data.get('tour_location_id'),
        tour_data.get('distance'),
        tour_data['meeting_point'],
        tour_data['equipment_included'],
        tour_data.get('what_to_bring', ''),
        tour_data.get('tour_latitude'),
        tour_data.get('tour_longitude'),
        tour_id
    ))
    db.commit()
    
    # Broadcast event
    broadcast_tour_update(tour_id, 'updated', {
        'id': tour_id,
        'title': tour_data['title'],
        'date': tour_data['date'],
        'time': tour_data['time'],
        'price': tour_data['price'],
        'max_participants': tour_data['max_participants'],
        'difficulty': tour_data['difficulty'],
        'location': tour_data['location']
    })
    
    broadcast_system_message(f'Túra frissítve: {tour_data["title"]}', 'info')
    
    return True


def delete_tour(tour_id: int) -> tuple[bool, str]:
    """
    Delete (deactivate) a tour.
    Returns (success, message)
    """
    db = get_db()

    tour = get_tour_by_id(tour_id)
    if not tour:
        return False, 'A túra nem található.'

    tour_title = tour.title or 'Ismeretlen túra'
    already_happened = _has_tour_already_run(tour.date, tour.time)

    if not already_happened:
        active_bookings = db.execute('''
            SELECT COUNT(*) as count FROM bookings
            WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
        ''', (tour_id,)).fetchone()['count']

        if active_bookings > 0:
            broadcast_system_message(
                f'Túra törlési kísérlet sikertelen: {active_bookings} aktív foglalás',
                'warning'
            )
            return False, f'A túrát nem lehet törölni, mert {active_bookings} aktív foglalás tartozik hozzá!'
    
    # Deactivate
    db.execute('UPDATE tours SET is_active = 0 WHERE id = ?', (tour_id,))
    db.commit()
    
    # Broadcast event
    broadcast_tour_update(tour_id, 'deleted', {
        'id': tour_id,
        'title': tour_title
    })
    
    if already_happened:
        broadcast_system_message(
            f'Túra archiválva (már lezajlott): {tour_title}',
            'info'
        )
    else:
        broadcast_system_message(f'Túra törölve: {tour_title}', 'info')
    
    return True, 'Túra sikeresen törölve!'


def get_tour_stats() -> dict:
    """Get tour statistics."""
    db = get_db()
    return {
        'total_tours': db.execute('SELECT COUNT(*) as count FROM tours WHERE is_active = 1').fetchone()['count']
    }


def get_all_tour_locations() -> List[TourLocation]:
    """Return every reusable tour location."""
    db = get_db()
    rows = db.execute('SELECT * FROM tour_locations ORDER BY name').fetchall()
    return [TourLocation.from_db_row(dict(row)) for row in rows]


def get_tour_location_by_id(location_id: int) -> Optional[TourLocation]:
    db = get_db()
    row = db.execute('SELECT * FROM tour_locations WHERE id = ?', (location_id,)).fetchone()
    return TourLocation.from_db_row(dict(row)) if row else None


def create_tour_location(
    name: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    description: Optional[str] = None,
) -> int:
    db = get_db()
    cursor = db.execute('''
        INSERT INTO tour_locations (name, description, latitude, longitude)
        VALUES (?, ?, ?, ?)
    ''', (
        name.strip(),
        (description or '').strip() or None,
        latitude,
        longitude,
    ))
    db.commit()
    return cursor.lastrowid
