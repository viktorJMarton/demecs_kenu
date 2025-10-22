from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from .db import get_db
from .auth import login_required
from .events import broadcast_tour_update, broadcast_booking_update, broadcast_system_message
from flask import g
import datetime

bp = Blueprint('admin', __name__, url_prefix='/admin')

# ============== TÚRÁK KEZELÉSE ==============

@bp.route('/')
@login_required
def dashboard():
    """Admin főoldal - statisztikák"""
    db = get_db()
    
    # Statisztikák lekérése
    stats = {}
    stats['total_tours'] = db.execute('SELECT COUNT(*) FROM tours WHERE is_active = 1').fetchone()[0]
    stats['total_bookings'] = db.execute('SELECT COUNT(*) FROM bookings').fetchone()[0]
    stats['paid_bookings'] = db.execute('SELECT COUNT(*) FROM bookings WHERE payment_status = "paid"').fetchone()[0]
    stats['pending_bookings'] = db.execute('SELECT COUNT(*) FROM bookings WHERE payment_status = "pending"').fetchone()[0]
    
    # Bevétel számítás
    revenue = db.execute('SELECT SUM(total_price) FROM bookings WHERE payment_status = "paid"').fetchone()[0]
    stats['total_revenue'] = revenue if revenue else 0
    
    # Legközelebbi túrák
    upcoming_tours = db.execute('''
        SELECT t.*, COUNT(b.id) as booking_count
        FROM tours t
        LEFT JOIN bookings b ON t.id = b.tour_id AND b.payment_status IN ('paid', 'pending')
        WHERE t.date >= date('now') AND t.is_active = 1
        GROUP BY t.id
        ORDER BY t.date
        LIMIT 5
    ''').fetchall()
    
    return render_template('admin/dashboard.html', stats=stats, upcoming_tours=upcoming_tours)

@bp.route('/tours')
@login_required
def tours():
    """Túrák listázása"""
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
    
    tours = db.execute(query, params).fetchall()
    return render_template('admin/tours.html', tours=tours, search=search, date_from=date_from, date_to=date_to)

@bp.route('/tours/add', methods=['GET', 'POST'])
@login_required
def add_tour():
    """Új túra hozzáadása"""
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
        
        # Esemény küldése az új túráról
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
        return redirect(url_for('admin.tours'))
    
    return render_template('admin/tour_form.html', tour=None)

@bp.route('/tours/edit/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def edit_tour(tour_id):
    """Túra szerkesztése"""
    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()
    
    if not tour:
        flash('Túra nem található!', 'error')
        return redirect(url_for('admin.tours'))
    
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
        
        # Ellenőrizzük a létszám változást (túlfoglalás elkerülése)
        old_max = tour['max_participants']
        if max_participants < old_max:
            # Ellenőrizzük a jelenlegi foglalásokat
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
        
        # Esemény küldése a túra frissítéséről
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
        return redirect(url_for('admin.tours'))
    
    return render_template('admin/tour_form.html', tour=tour)

@bp.route('/tours/delete/<int:tour_id>', methods=['POST'])
@login_required
def delete_tour(tour_id):
    """Túra törlése (inaktiválás)"""
    db = get_db()
    
    # Ellenőrizzük, vannak-e aktív foglalások
    active_bookings = db.execute('''
        SELECT COUNT(*) FROM bookings 
        WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
    ''', (tour_id,)).fetchone()[0]
    
    if active_bookings > 0:
        flash(f'A túrát nem lehet törölni, mert {active_bookings} aktív foglalás tartozik hozzá!', 'error')
        broadcast_system_message(f'Túra törlési kísérlet sikertelen: {active_bookings} aktív foglalás', 'warning')
    else:
        # Túra adatok lekérése az eseményhez
        tour = db.execute('SELECT title FROM tours WHERE id = ?', (tour_id,)).fetchone()
        
        db.execute('UPDATE tours SET is_active = 0 WHERE id = ?', (tour_id,))
        db.commit()
        
        # Esemény küldése a túra törléséről
        broadcast_tour_update(tour_id, 'deleted', {
            'id': tour_id,
            'title': tour['title'] if tour else 'Ismeretlen túra'
        })
        
        broadcast_system_message(f'Túra törölve: {tour["title"] if tour else "Ismeretlen túra"}', 'info')
        
        flash('Túra sikeresen törölve!', 'success')
    
    return redirect(url_for('admin.tours'))

# ============== FOGLALÁSOK KEZELÉSE ==============

@bp.route('/bookings')
@login_required
def bookings():
    """Foglalások listázása"""
    db = get_db()
    
    # Szűrő paraméterek
    tour_filter = request.args.get('tour', '')
    status_filter = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '')
    
    query = '''
        SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        WHERE 1=1
    '''
    params = []
    
    if tour_filter:
        query += ' AND b.tour_id = ?'
        params.append(tour_filter)
    
    if status_filter:
        query += ' AND b.payment_status = ?'
        params.append(status_filter)
    
    if date_from:
        query += ' AND date(b.booking_date) >= ?'
        params.append(date_from)
    
    if date_to:
        query += ' AND date(b.booking_date) <= ?'
        params.append(date_to)
    
    if search:
        query += ' AND (b.customer_name LIKE ? OR b.customer_email LIKE ? OR b.order_ref LIKE ?)'
        search_param = f'%{search}%'
        params.extend([search_param, search_param, search_param])
    
    query += ' ORDER BY b.booking_date DESC'
    
    bookings = db.execute(query, params).fetchall()
    
    # Túrák listája a szűrőhöz
    tours_list = db.execute('SELECT id, title FROM tours WHERE is_active = 1 ORDER BY title').fetchall()
    
    return render_template('admin/bookings.html', 
                         bookings=bookings, 
                         tours_list=tours_list,
                         tour_filter=tour_filter,
                         status_filter=status_filter,
                         date_from=date_from,
                         date_to=date_to,
                         search=search)

@bp.route('/bookings/<int:booking_id>')
@login_required
def booking_detail(booking_id):
    """Foglalás részletei"""
    db = get_db()
    booking = db.execute('''
        SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time,
               t.location, t.meeting_point, t.duration, t.difficulty
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()
    
    if not booking:
        flash('Foglalás nem található!', 'error')
        return redirect(url_for('admin.bookings'))
    
    return render_template('admin/booking_detail.html', booking=booking)

@bp.route('/bookings/<int:booking_id>/update-status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    """Foglalás státusz frissítése"""
    new_status = request.form['status']
    admin_notes = request.form.get('admin_notes', '')
    
    db = get_db()
    
    # Státusz frissítése
    if new_status == 'paid':
        db.execute('''
            UPDATE bookings 
            SET payment_status = ?, payment_date = CURRENT_TIMESTAMP, admin_notes = ?
            WHERE id = ?
        ''', (new_status, admin_notes, booking_id))
    elif new_status == 'cancelled':
        db.execute('''
            UPDATE bookings 
            SET payment_status = ?, cancellation_date = CURRENT_TIMESTAMP, admin_notes = ?
            WHERE id = ?
        ''', (new_status, admin_notes, booking_id))
    else:
        db.execute('''
            UPDATE bookings 
            SET payment_status = ?, admin_notes = ?
            WHERE id = ?
        ''', (new_status, admin_notes, booking_id))
    
    db.commit()
    
    # Foglalás adatok lekérése az eseményhez
    booking = db.execute('''
        SELECT b.*, t.id as tour_id, t.title as tour_title
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()
    
    if booking:
        # Esemény küldése a foglalás frissítéséről
        broadcast_booking_update(booking_id, booking['tour_id'], 'updated', {
            'id': booking_id,
            'tour_id': booking['tour_id'],
            'customer_name': booking['customer_name'],
            'payment_status': new_status,
            'participants_count': booking['participants_count']
        })
        
        broadcast_system_message(f'Foglalás státusz frissítve: {booking["tour_title"]} - {new_status}', 'info')
    
    flash('Foglalás státusza frissítve!', 'success')
    return redirect(url_for('admin.booking_detail', booking_id=booking_id))

# ============== API ENDPOINTS ==============

@bp.route('/api/tours')
@login_required
def api_tours():
    """API endpoint a túrák lekéréséhez"""
    db = get_db()
    tours = db.execute('''
        SELECT id, title, date, time, max_participants,
               COUNT(b.id) as booking_count
        FROM tours t
        LEFT JOIN bookings b ON t.id = b.tour_id AND b.payment_status IN ('paid', 'pending')
        WHERE t.is_active = 1 AND t.date >= date('now')
        GROUP BY t.id
        ORDER BY t.date
    ''').fetchall()
    
    return jsonify([dict(tour) for tour in tours])

@bp.route('/api/bookings/stats')
@login_required
def api_booking_stats():
    """API endpoint a foglalási statisztikákhoz"""
    db = get_db()
    
    stats = {}
    
    # Státusz szerinti bontás
    status_stats = db.execute('''
        SELECT payment_status, COUNT(*) as count, SUM(total_price) as revenue
        FROM bookings
        GROUP BY payment_status
    ''').fetchall()
    
    stats['by_status'] = {row['payment_status']: {'count': row['count'], 'revenue': row['revenue']} for row in status_stats}
    
    # Havi bontás
    monthly_stats = db.execute('''
        SELECT strftime('%Y-%m', booking_date) as month, 
               COUNT(*) as bookings, 
               SUM(total_price) as revenue
        FROM bookings
        WHERE booking_date >= date('now', '-12 months')
        GROUP BY month
        ORDER BY month
    ''').fetchall()
    
    stats['monthly'] = [dict(row) for row in monthly_stats]
    
    return jsonify(stats)
