"""
Admin Bookings Blueprint - Booking management.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from collections import Counter
from datetime import datetime
import json
from ..auth import login_required
from ..db import get_db
from ..events import broadcast_booking_update, broadcast_system_message
from ..services.email_service import get_email_service, EmailServiceError

STATUS_FILTER_CONDITIONS = {
    'paid': ('(b.payment_status = ? OR pt.status = ?)', ['paid', 'success']),
    'pending': ('(b.payment_status = ? OR pt.status IN (?, ?, ?))', ['pending', 'pending', 'init', 'refund_pending']),
    'failed': ('(b.payment_status = ? OR pt.status = ?)', ['failed', 'fail']),
    'cancelled': ('(b.payment_status = ? OR pt.status = ?)', ['cancelled', 'cancelled']),
    'refunded': ('(b.payment_status = ? OR pt.status = ?)', ['refunded', 'refunded']),
}

STATUS_MAPPING = {
    'success': 'paid',
    'fail': 'failed',
    'cancelled': 'cancelled',
    'timeout': 'timeout',
    'refunded': 'refunded',
    'pending': 'pending',
    'init': 'pending',
    'refund_pending': 'pending',
}


def _booking_happened(booking_row) -> bool:
    """Return True if the booking's tour datetime is in the past."""
    if not booking_row:
        return False

    date_val = booking_row.get('tour_date') or booking_row.get('date')
    if not date_val:
        return False

    time_val = booking_row.get('tour_time') or booking_row.get('time') or '00:00'
    try:
        scheduled = datetime.strptime(f"{date_val} {time_val}", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            scheduled = datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            return False

    return scheduled <= datetime.now()


def _normalize_display_status(transaction_status, booking_status):
    if transaction_status:
        mapped = STATUS_MAPPING.get(transaction_status.lower())
        if mapped:
            return mapped
        return transaction_status.lower()
    return (booking_status or 'pending').lower()

bp = Blueprint('admin_bookings', __name__, url_prefix='/admin')


@bp.route('/bookings')
@login_required
def bookings():
    """List all bookings with filters."""
    db = get_db()
    
    # Filter parameters
    tour_filter = request.args.get('tour', '')
    status_filter = request.args.get('status', '').lower()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '')
    
    query = '''
        SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time,
               pt.status as transaction_status, pt.transaction_id, pt.simplepay_payment_url
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        LEFT JOIN payment_transactions pt ON pt.booking_id = b.id
        WHERE 1=1
    '''
    params = []
    
    if tour_filter:
        query += ' AND b.tour_id = ?'
        params.append(tour_filter)
    
    if status_filter and status_filter in STATUS_FILTER_CONDITIONS:
        condition, values = STATUS_FILTER_CONDITIONS[status_filter]
        query += f' AND {condition}'
        params.extend(values)
    
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
    
    raw_bookings = db.execute(query, params).fetchall()
    bookings_list = []
    for row in raw_bookings:
        booking = dict(row)
        booking['display_status'] = _normalize_display_status(
            booking.get('transaction_status'),
            booking.get('payment_status')
        )
        bookings_list.append(booking)
    
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
               t.location, t.meeting_point, t.duration, t.difficulty,
               pt.status as transaction_status, pt.transaction_id, pt.simplepay_payment_url
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        LEFT JOIN payment_transactions pt ON pt.booking_id = b.id
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()
    
    if not booking:
        flash('Foglalás nem található!', 'error')
        return redirect(url_for('admin_bookings.bookings'))
    
    booking = dict(booking)
    booking['display_status'] = _normalize_display_status(
        booking.get('transaction_status'),
        booking.get('payment_status')
    )

    lifejacket_sizes = []
    lifejacket_counts = []
    lifejacket_key = 'lifejacket_sizes'

    if lifejacket_key not in booking:
        current_app.logger.warning(
            "lifejacket_sizes column is missing from bookings result set. Did you run the latest migrations?"
        )
    else:
        lifejacket_data = booking.get(lifejacket_key)
        if lifejacket_data:
            try:
                lifejacket_sizes = json.loads(lifejacket_data)
                if isinstance(lifejacket_sizes, list):
                    lifejacket_counts = sorted(Counter(lifejacket_sizes).items(), key=lambda item: item[0])
            except (TypeError, json.JSONDecodeError):
                lifejacket_sizes = []
                lifejacket_counts = []

    return render_template(
        'admin/booking_detail.html',
        booking=booking,
        lifejacket_sizes=lifejacket_sizes,
        lifejacket_counts=lifejacket_counts
    )


@bp.route('/bookings/<int:booking_id>/update-status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    """Update booking payment status."""
    new_status = request.form['status']
    admin_notes = request.form.get('admin_notes', '')

    db = get_db()

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
        # also mark any related payment transaction as cancelled so the UI reflects the change
        db.execute('''
            UPDATE payment_transactions
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE booking_id = ?
        ''', ('cancelled', booking_id))
    else:
        db.execute('''
            UPDATE bookings 
            SET payment_status = ?, admin_notes = ?
            WHERE id = ?
        ''', (new_status, admin_notes, booking_id))

    db.commit()

    booking_row = db.execute('''
        SELECT b.*, t.id as tour_id, t.title as tour_title, t.date as tour_date, t.time as tour_time
        FROM bookings b
        JOIN tours t ON b.tour_id = t.id
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()

    if booking_row:
        booking_dict = dict(booking_row)
        broadcast_booking_update(booking_id, booking_dict['tour_id'], 'updated', {
            'id': booking_id,
            'tour_id': booking_dict['tour_id'],
            'payment_status': new_status,
            'participants_count': booking_dict['participants_count']
        })

        broadcast_system_message(
            f'Foglalás státusz frissítve: {booking_dict["tour_title"]} - {new_status}',
            'info'
        )

        # If admin cancelled the booking, send a cancellation email to the customer
        if new_status == 'cancelled':
            try:
                notify_customer = not _booking_happened(booking_dict)
                get_email_service().send_booking_cancellation(
                    booking=booking_dict,
                    tour={
                        'title': booking_dict.get('tour_title'),
                        'date': booking_dict.get('tour_date'),
                        'time': booking_dict.get('tour_time')
                    },
                    cancel_reason=admin_notes or None,
                    notify_customer=notify_customer,
                )
            except EmailServiceError as exc:
                current_app.logger.warning('Cancellation email send failed for booking %s: %s', booking_id, exc)
                flash('Foglalás lemondva, de az értesítő e-mail küldése sikertelen volt.', 'warning')
            except Exception as exc:  # defensive
                current_app.logger.exception('Unexpected error sending cancellation email for booking %s: %s', booking_id, exc)
                flash('Foglalás lemondva, de váratlan hiba történt az e-mail küldésekor.', 'warning')
            else:
                if notify_customer:
                    flash('Lemondó e-mail elküldve a vendégnek.', 'success')
                else:
                    flash('A túra már lezajlott, ezért nem küldtünk értesítést a vendégnek.', 'info')

    flash('Foglalás státusza frissítve!', 'success')
    return redirect(url_for('admin_bookings.booking_detail', booking_id=booking_id))
