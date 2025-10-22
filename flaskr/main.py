from flask import Flask, render_template, jsonify, redirect, url_for

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config['DATABASE'] = 'kajak_kenu.db'
    
    # Session beállítások dev tunnel környezethez
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 óra
    app.config['SESSION_COOKIE_SECURE'] = False  # HTTP-n is működjön
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Dev tunnel kompatibilitás
    
    from datetime import timedelta
    app.permanent_session_lifetime = timedelta(hours=24)  # 24 óra
    
    # Adatbázis inicializálás
    from . import db
    db.init_app(app)
    
    # Auth modul import és regisztráció
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    
    # Events modul import és regisztráció
    from .events import bp as events_bp
    app.register_blueprint(events_bp)
    
    # Admin modulok import és regisztráció (refactored structure)
    from .admin.admin_dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from .admin.admin_tours import bp as tours_bp
    app.register_blueprint(tours_bp)
    
    from .admin.admin_bookings import bp as bookings_bp
    app.register_blueprint(bookings_bp)

    @app.route('/')
    def index():
        """Main page - list active tours."""
        from . import db
        db_conn = db.get_db()
        tours = db_conn.execute('''
            SELECT t.*, COUNT(b.id) as booking_count,
                   SUM(CASE WHEN b.payment_status IN ('paid', 'pending') THEN b.participants_count ELSE 0 END) as participants
            FROM tours t
            LEFT JOIN bookings b ON t.id = b.tour_id
            WHERE t.is_active = 1
            GROUP BY t.id ORDER BY t.date DESC
        ''').fetchall()
        # Convert to dict for template compatibility
        tours = [{'id': row['id'], 'title': row['title'], 'desc': row['description'], 
                  'date': row['date'], 'price': row['price'], 'difficulty': row['difficulty'], 
                  'location': row['location']} for row in tours]
        return render_template('index.html', tours=tours)
    
    @app.route('/api/template/tour-reservation')
    def get_tour_reservation_template():
        """API endpoint for tour reservation template."""
        return render_template('partials/tour_reservation_view.html')

    return app
