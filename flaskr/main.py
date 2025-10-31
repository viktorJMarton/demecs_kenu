import os
from flask import Flask, render_template, jsonify, redirect, url_for, send_from_directory, abort, request
from .db import get_db

def create_app():
    # Resolve absolute paths to ensure Jinja finds templates regardless of CWD/import quirks.
    package_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(package_dir, "templates")
    static_dir = os.path.join(package_dir, "static")

    app = Flask(__name__, template_folder=templates_dir, static_folder=static_dir)
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config['DATABASE'] = 'kajak_kenu.db'
    
    # Session beállítások dev tunnel környezethez
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 óra
    
    # Database init
    from . import db
    db.init_app(app)
    
    # Register blueprints
    from . import auth, events
    app.register_blueprint(auth.bp)
    app.register_blueprint(events.bp)
    
    # Payment blueprint
    from . import payment
    app.register_blueprint(payment.bp)
    
    # Admin modulok import és regisztráció (refactored structure)
    from .admin.admin_dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from .admin.admin_tours import bp as tours_bp
    app.register_blueprint(tours_bp)
    
    from .admin.admin_bookings import bp as bookings_bp
    app.register_blueprint(bookings_bp)
    
    # Public uploads serving (from project-level public/uploads)
    uploads_root = os.path.abspath(os.path.join(app.root_path, '..', 'public', 'uploads'))
    app.config['UPLOADS_ROOT'] = uploads_root
    os.makedirs(uploads_root, exist_ok=True)
    
    @app.route('/')
    def index():
        """Main page - list active tours with images."""
        db_conn = get_db()
        tours = db_conn.execute('''
            SELECT t.*, COUNT(b.id) as booking_count,
                   SUM(CASE WHEN b.payment_status IN ('paid', 'pending') THEN b.participants_count ELSE 0 END) as participants
            FROM tours t
            LEFT JOIN bookings b ON t.id = b.tour_id
            WHERE t.is_active = 1
            GROUP BY t.id ORDER BY t.date DESC
        ''').fetchall()
        
        # Load images for each tour
        tours_with_images = []
        for tour in tours:
            tour_dict = dict(tour)
            
            # Fetch images for this tour
            images = db_conn.execute('''
                SELECT id, filename, file_path, alt_text, sort_order
                FROM tour_images
                WHERE tour_id = ?
                ORDER BY sort_order, id
            ''', (tour['id'],)).fetchall()
            
            tour_dict['images'] = [dict(img) for img in images]
            tours_with_images.append(tour_dict)
        
        return render_template('index.html', tours=tours_with_images)
    
    @app.route('/tour/<int:tour_id>')
    def tour_detail(tour_id):
        """Server-side rendered tour details for modal."""
        db_conn = get_db()
        
        # Get tour data
        tour = db_conn.execute(
            'SELECT * FROM tours WHERE id = ? AND is_active = 1', 
            (tour_id,)
        ).fetchone()
        
        if not tour:
            abort(404)
        
        # Get tour images
        images = db_conn.execute('''
            SELECT id, filename, file_path, alt_text, sort_order
            FROM tour_images
            WHERE tour_id = ?
            ORDER BY sort_order, id
        ''', (tour_id,)).fetchall()
        
        # Get bookings for this tour
        bookings = db_conn.execute('''
            SELECT COUNT(*) as booking_count,
                   SUM(CASE WHEN payment_status IN ('paid', 'pending') THEN participants_count ELSE 0 END) as participants
            FROM bookings
            WHERE tour_id = ?
        ''', (tour_id,)).fetchone()
        
        tour_dict = dict(tour)
        tour_dict['images'] = [dict(img) for img in images]
        tour_dict['booking_count'] = bookings['booking_count'] or 0
        tour_dict['participants'] = bookings['participants'] or 0
        
        return render_template('partials/tour_details.html', tour=tour_dict)
    
    @app.route('/api/tours')
    def api_tours():
        """API endpoint for AJAX tour filtering."""
        date_filter = request.args.get('date')
        
        db_conn = get_db()
        query = '''
            SELECT t.*, COUNT(b.id) as booking_count,
                   SUM(CASE WHEN b.payment_status IN ('paid', 'pending') THEN b.participants_count ELSE 0 END) as participants
            FROM tours t
            LEFT JOIN bookings b ON t.id = b.tour_id
            WHERE t.is_active = 1
        '''
        params = []
        
        if date_filter:
            query += ' AND DATE(t.date) = ?'
            params.append(date_filter)
        
        query += ' GROUP BY t.id ORDER BY t.date'
        
        tours = db_conn.execute(query, params).fetchall()
        
        # Add images to each tour
        tours_data = []
        for tour in tours:
            tour_dict = dict(tour)
            
            # Get images for this tour
            images = db_conn.execute('''
                SELECT id, filename, file_path, alt_text, sort_order
                FROM tour_images
                WHERE tour_id = ?
                ORDER BY sort_order, id
            ''', (tour['id'],)).fetchall()
            
            tour_dict['images'] = [dict(img) for img in images]
            tours_data.append(tour_dict)
        
        return jsonify(tours_data)
    
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        """Serve uploaded files."""
        uploads_dir = os.path.join(app.root_path, '..', 'public', 'uploads')
        return send_from_directory(uploads_dir, filename)
    
    return app
