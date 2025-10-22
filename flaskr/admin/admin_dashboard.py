"""
Admin Dashboard Blueprint - Statistics and overview.
"""

from flask import Blueprint, render_template, jsonify
from ..auth import login_required
from ..db import get_db

bp = Blueprint('admin_dashboard', __name__, url_prefix='/admin')


@bp.route('/')
@login_required
def dashboard():
    """Admin dashboard - statistics and overview."""
    db = get_db()
    
    # Statistics
    stats = {}
    stats['total_tours'] = db.execute('SELECT COUNT(*) FROM tours WHERE is_active = 1').fetchone()[0]
    stats['total_bookings'] = db.execute('SELECT COUNT(*) FROM bookings').fetchone()[0]
    stats['paid_bookings'] = db.execute('SELECT COUNT(*) FROM bookings WHERE payment_status = "paid"').fetchone()[0]
    stats['pending_bookings'] = db.execute('SELECT COUNT(*) FROM bookings WHERE payment_status = "pending"').fetchone()[0]
    
    # Revenue calculation
    revenue = db.execute('SELECT SUM(total_price) FROM bookings WHERE payment_status = "paid"').fetchone()[0]
    stats['total_revenue'] = revenue if revenue else 0
    
    # Upcoming tours
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


@bp.route('/api/tours')
@login_required
def api_tours():
    """API endpoint for tours list."""
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
    """API endpoint for booking statistics."""
    db = get_db()
    
    stats = {}
    
    # Status breakdown
    status_stats = db.execute('''
        SELECT payment_status, COUNT(*) as count, SUM(total_price) as revenue
        FROM bookings
        GROUP BY payment_status
    ''').fetchall()
    
    stats['by_status'] = {row['payment_status']: {'count': row['count'], 'revenue': row['revenue']} for row in status_stats}
    
    # Monthly breakdown
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
