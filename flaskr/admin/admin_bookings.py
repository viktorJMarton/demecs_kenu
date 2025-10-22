"""
Admin Bookings Blueprint - Booking management.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..auth import login_required
from ..db import get_db
from ..events import broadcast_booking_update, broadcast_system_message

bp = Blueprint('admin_bookings', __name__, url_prefix='/admin')


@bp.route('/bookings')
@login_required
def bookings():
    """List all bookings with filters."""
    db = get_db()
    
    # Filter parameters
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
    
    bookings_list = db.execute(query, params).fetchall()
    
    # Get tours list for filter dropdown
    tours_list = db.execute('SELECT id, title FROM tours WHERE is_active = 1 ORDER BY title').fetchall()
    
    return render_template(
        'admin/bookings.html',
        bookings=bookings_list,
        tours_list=tours_list,
        tour_filter=tour_filter,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        search=search
    )


@bp.route('/bookings/<int:booking_id>')
@login_required
def booking_detail(booking_id):
    """Show booking details."""
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
        return redirect(url_for('admin_bookings.bookings'))
    
    return render_template('admin/booking_detail.html', booking=booking)


@bp.route('/bookings/<int:booking_id>/update-status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    """Update booking payment status."""
    new_status = request.form['status']
    admin_notes = request.form.get('admin_notes', '')
    
    db = get_db()
    
    # Update status
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
    
    # Get booking data for event
    booking = db.execute('''
        SELECT b.*, t.id as tour_id, t.title as tour_title
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()
    
    if booking:
        # Broadcast event
        broadcast_booking_update(booking_id, booking['tour_id'], 'updated', {
            'id': booking_id,
            'tour_id': booking['tour_id'],
            'customer_name': booking['customer_name'],
            'payment_status': new_status,
            'participants_count': booking['participants_count']
        })
        
        broadcast_system_message(f'Foglalás státusz frissítve: {booking["tour_title"]} - {new_status}', 'info')
    
    flash('Foglalás státusza frissítve!', 'success')
    return redirect(url_for('admin_bookings.booking_detail', booking_id=booking_id))
