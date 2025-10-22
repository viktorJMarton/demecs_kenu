"""
Admin Tours Blueprint - Tour management (CRUD operations).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..auth import login_required
from ..db import get_db
from ..events import broadcast_tour_update, broadcast_system_message

bp = Blueprint('admin_tours', __name__, url_prefix='/admin')


@bp.route('/tours')
@login_required
def tours():
    """List all tours with filters."""
    db = get_db()
    search = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = '''
        SELECT t.*, COUNT(b.id) as booking_count,
               SUM(CASE WHEN b.payment_status IN ('paid', 'pending') THEN b.participants_count ELSE 0 END) as participants
        FROM tours t
        LEFT JOIN bookings b ON t.id = b.tour_id
        WHERE t.is_active = 1
    '''
    params = []
    
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
    
    tours_list = db.execute(query, params).fetchall()
    
    return render_template(
        'admin/tours.html',
        tours=tours_list,
        search=search,
        date_from=date_from,
        date_to=date_to
    )


@bp.route('/tours/add', methods=['GET', 'POST'])
@login_required
def add_tour():
    """Add a new tour."""
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        time = request.form['time']
        duration = int(request.form['duration'])
        max_participants = int(request.form['max_participants'])
        price = int(request.form['price'])
        difficulty = request.form['difficulty']
        location = request.form['location']
        distance = float(request.form['distance']) if request.form['distance'] else None
        meeting_point = request.form['meeting_point']
        equipment_included = request.form['equipment_included']
        what_to_bring = request.form['what_to_bring']
        tour_latitude = float(request.form['tour_latitude']) if request.form['tour_latitude'] else None
        tour_longitude = float(request.form['tour_longitude']) if request.form['tour_longitude'] else None
        
        db = get_db()
        cursor = db.execute('''
            INSERT INTO tours (title, description, date, time, duration, max_participants, 
                             price, difficulty, location, distance, meeting_point, 
                             equipment_included, what_to_bring, tour_latitude, tour_longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, date, time, duration, max_participants, price, 
              difficulty, location, distance, meeting_point, equipment_included, what_to_bring,
              tour_latitude, tour_longitude))
        
        new_tour_id = cursor.lastrowid
        db.commit()
        
        # Broadcast event
        broadcast_tour_update(new_tour_id, 'created', {
            'id': new_tour_id,
            'title': title,
            'date': date,
            'time': time,
            'price': price,
            'max_participants': max_participants,
            'difficulty': difficulty,
            'location': location
        })
        
        broadcast_system_message(f'Új túra hozzáadva: {title}', 'success')
        
        flash('Túra sikeresen hozzáadva!', 'success')
        return redirect(url_for('admin_tours.tours'))
    
    return render_template('admin/tour_form.html', tour=None)


@bp.route('/tours/edit/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def edit_tour(tour_id):
    """Edit an existing tour."""
    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()
    
    if not tour:
        flash('Túra nem található!', 'error')
        return redirect(url_for('admin_tours.tours'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        time = request.form['time']
        duration = int(request.form['duration'])
        max_participants = int(request.form['max_participants'])
        price = int(request.form['price'])
        difficulty = request.form['difficulty']
        location = request.form['location']
        distance = float(request.form['distance']) if request.form['distance'] else None
        meeting_point = request.form['meeting_point']
        equipment_included = request.form['equipment_included']
        what_to_bring = request.form['what_to_bring']
        tour_latitude = float(request.form['tour_latitude']) if request.form['tour_latitude'] else None
        tour_longitude = float(request.form['tour_longitude']) if request.form['tour_longitude'] else None
        
        # Check participant limit
        old_max = tour['max_participants']
        if max_participants < old_max:
            current_bookings = db.execute('''
                SELECT COUNT(*) FROM bookings 
                WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
            ''', (tour_id,)).fetchone()[0]
            
            if current_bookings > max_participants:
                flash(f'Figyelem! A maximális létszám ({max_participants}) kevesebb mint a jelenlegi foglalások száma ({current_bookings}). Túlfoglalás alakult ki!', 'warning')
                broadcast_system_message(f'Túlfoglalás riasztás: {title} - {current_bookings}/{max_participants} fő', 'error')
        
        db.execute('''
            UPDATE tours SET title = ?, description = ?, date = ?, time = ?, 
                           duration = ?, max_participants = ?, price = ?, difficulty = ?, 
                           location = ?, distance = ?, meeting_point = ?, 
                           equipment_included = ?, what_to_bring = ?, tour_latitude = ?, 
                           tour_longitude = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (title, description, date, time, duration, max_participants, price,
              difficulty, location, distance, meeting_point, equipment_included, 
              what_to_bring, tour_latitude, tour_longitude, tour_id))
        db.commit()
        
        # Broadcast event
        broadcast_tour_update(tour_id, 'updated', {
            'id': tour_id,
            'title': title,
            'date': date,
            'time': time,
            'price': price,
            'max_participants': max_participants,
            'difficulty': difficulty,
            'location': location
        })
        
        broadcast_system_message(f'Túra frissítve: {title}', 'info')
        
        flash('Túra sikeresen frissítve!', 'success')
        return redirect(url_for('admin_tours.tours'))
    
    return render_template('admin/tour_form.html', tour=tour)


@bp.route('/tours/delete/<int:tour_id>', methods=['POST'])
@login_required
def delete_tour(tour_id):
    """Delete (deactivate) a tour."""
    db = get_db()
    
    # Check for active bookings
    active_bookings = db.execute('''
        SELECT COUNT(*) FROM bookings 
        WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
    ''', (tour_id,)).fetchone()[0]
    
    if active_bookings > 0:
        flash(f'A túrát nem lehet törölni, mert {active_bookings} aktív foglalás tartozik hozzá!', 'error')
        broadcast_system_message(f'Túra törlési kísérlet sikertelen: {active_bookings} aktív foglalás', 'warning')
    else:
        # Get tour data for event
        tour = db.execute('SELECT title FROM tours WHERE id = ?', (tour_id,)).fetchone()
        
        db.execute('UPDATE tours SET is_active = 0 WHERE id = ?', (tour_id,))
        db.commit()
        
        # Broadcast event
        broadcast_tour_update(tour_id, 'deleted', {
            'id': tour_id,
            'title': tour['title'] if tour else 'Ismeretlen túra'
        })
        
        broadcast_system_message(f'Túra törölve: {tour["title"] if tour else "Ismeretlen túra"}', 'info')
        
        flash('Túra sikeresen törölve!', 'success')
    
    return redirect(url_for('admin_tours.tours'))
