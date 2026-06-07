import os
import re
import hmac
import hashlib
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, redirect, url_for, send_from_directory, abort, request, make_response
from flask_wtf.csrf import CSRFProtect, generate_csrf
from .db import get_db
from .services import content_service
from .services.email_service import get_email_service, EmailServiceError
from .extensions import cache
from dotenv import load_dotenv

# Környezeti változók betöltése
load_dotenv()

_SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]?")


def first_sentences_filter(value, count=4):
    if not value:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    sentences = [segment.strip() for segment in _SENTENCE_PATTERN.findall(text) if segment.strip()]
    if not sentences:
        return text
    clipped = ' '.join(sentences[: max(1, int(count))]).strip()
    if len(sentences) > count:
        clipped = clipped.rstrip('.!?\u2026 ') + '…'
    return clipped

def thumbnail_filter(filename):
    """
    Converts a filename (e.g. image.jpg) to its thumbnail version (image_thumb.webp).
    Does not check for existence to avoid I/O overhead; assumes generate_thumbnails.py runs.
    """
    if not filename:
        return ''
    if filename.startswith(('http://', 'https://')):
        return filename
        
    # Handle paths that might already include directories
    base = os.path.basename(filename)
    dir_part = os.path.dirname(filename)
    
    name, _ = os.path.splitext(base)
    # Avoid double thumbing
    if name.endswith('_thumb'):
        return filename
        
    thumb_filename = f"{name}_thumb.webp"
    
    if dir_part:
        return os.path.join(dir_part, thumb_filename)
    return thumb_filename

def _load_secret_key(test_config):
    """Return a strong SECRET_KEY or raise if missing."""
    if test_config and 'SECRET_KEY' in test_config:
        return test_config['SECRET_KEY']
    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        raise RuntimeError(
            'SECRET_KEY environment variable is required. '
            'Generate a random 32+ byte value and store it in your .env file.'
        )
    if len(secret_key) < 32:
        raise RuntimeError('SECRET_KEY must be at least 32 characters long.')
    return secret_key


def generate_tour_token(secret_key, tour_id, order_ref):
    """Generate HMAC-SHA256 token for email tour info links.

    The token is tied to (tour_id, order_ref) so it cannot be guessed.
    """
    message = f"tour-info:{tour_id}:{order_ref}"
    return hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_tour_token(secret_key, tour_id, order_ref, token):
    """Verify an HMAC token for the tour info link."""
    expected = generate_tour_token(secret_key, tour_id, order_ref)
    return hmac.compare_digest(expected, token)


def create_app(test_config=None):
    app = Flask(__name__)
    app.jinja_env.filters['first_sentences'] = first_sentences_filter
    app.jinja_env.filters['thumbnail'] = thumbnail_filter
    secret_key = _load_secret_key(test_config)
    database_url = os.getenv('DATABASE_URL', 'kajak_kenu.db')
    if test_config and 'DATABASE' in test_config:
        database_url = test_config['DATABASE']

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        WTF_CSRF_SECRET_KEY=os.getenv('WTF_CSRF_SECRET_KEY', secret_key),
        DATABASE=database_url,
        PERMANENT_SESSION_LIFETIME=3600,
        SESSION_COOKIE_SAMESITE=os.getenv('SESSION_COOKIE_SAMESITE', 'Lax'),
        SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true',
        MAX_CONTENT_LENGTH=100 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    # File-based rotating logging for production
    try:
        log_dir = os.environ.get('APP_LOG_DIR', os.path.join(os.path.abspath(os.path.join(app.root_path, '..')), 'logs'))
        # default to /app/logs if running in container
        if not log_dir:
            log_dir = '/app/logs'
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'app.log')
        file_handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
        file_handler.setFormatter(formatter)
        # attach to app logger and werkzeug
        app.logger.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        logging.getLogger('werkzeug').addHandler(file_handler)
    except Exception:
        # fail safe: don't crash app if logging setup fails
        app.logger.exception('Failed to set up file logger')

    csrf = CSRFProtect()
    csrf.init_app(app)

    # Cache init (SimpleCache for speed, 5 minute default timeout)
    cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

    # Database init
    from . import db
    db.init_app(app)
    
    # Register blueprints
    from . import auth, events, payment
    app.register_blueprint(auth.bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(payment.bp)
    
    # Admin modulok import és regisztráció (refactored structure)
    from .admin.admin_dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from .admin.admin_tours import bp as tours_bp
    app.register_blueprint(tours_bp)
    
    from .admin.admin_bookings import bp as bookings_bp
    app.register_blueprint(bookings_bp)

    from .admin.admin_content import bp as content_bp
    app.register_blueprint(content_bp)

    from .admin.admin_locations import bp as locations_bp
    app.register_blueprint(locations_bp)
    
    # Public uploads serving (from project-level public/uploads)
    uploads_root = os.path.abspath(os.path.join(app.root_path, '..', 'public', 'uploads'))
    app.config['UPLOADS_ROOT'] = uploads_root
    os.makedirs(uploads_root, exist_ok=True)
    
    @app.route('/')
    @cache.cached(timeout=300)
    def index():
        """Main page - list active tours with images."""
        db_conn = get_db()
        tours = db_conn.execute('''
            SELECT t.*, COUNT(b.id) as booking_count,
                   SUM(CASE WHEN b.payment_status IN ('paid', 'pending') THEN b.participants_count ELSE 0 END) as participants
            FROM tours t
            LEFT JOIN bookings b ON t.id = b.tour_id
            WHERE t.is_active = 1 AND DATE(t.date) >= DATE('now')
            GROUP BY t.id ORDER BY t.date ASC
        ''').fetchall()
        
        # Load images for each tour (BATCH OPTIMIZED)
        tour_ids = [t['id'] for t in tours]
        images_by_tour = {tid: [] for tid in tour_ids}
        
        if tour_ids:
            placeholders = ','.join(['?'] * len(tour_ids))
            all_images = db_conn.execute(f'''
                SELECT id, tour_id, filename, file_path, alt_text, sort_order
                FROM tour_images
                WHERE tour_id IN ({placeholders})
                ORDER BY sort_order, id
            ''', tour_ids).fetchall()
            
            for img in all_images:
                images_by_tour[img['tour_id']].append(dict(img))
        
        tours_with_images = []
        for tour in tours:
            tour_dict = dict(tour)
            tour_dict['images'] = images_by_tour.get(tour['id'], [])
            tours_with_images.append(tour_dict)
        
        tour_locations = db_conn.execute('''
            WITH booking_totals AS (
                SELECT tour_id,
                       SUM(CASE WHEN payment_status IN ('paid', 'pending') THEN participants_count ELSE 0 END) AS participants
                FROM bookings
                GROUP BY tour_id
            ),
            upcoming_tours AS (
                SELECT t.id,
                       t.tour_location_id,
                       t.date,
                       t.max_participants,
                       COALESCE(bt.participants, 0) AS participants
                FROM tours t
                LEFT JOIN booking_totals bt ON bt.tour_id = t.id
                WHERE t.is_active = 1
                  AND DATE(t.date) >= DATE('now')
            ),
            location_next_dates AS (
                SELECT tour_location_id, MIN(date) as next_tour_date
                FROM upcoming_tours
                GROUP BY tour_location_id
            )
            SELECT tl.id,
                   tl.name,
                   tl.description,
                   tl.latitude,
                   tl.longitude,
                   EXISTS (
                       SELECT 1
                       FROM upcoming_tours ut
                       WHERE ut.tour_location_id = tl.id
                         AND (ut.max_participants IS NULL OR ut.max_participants - ut.participants > 0)
                   ) AS has_upcoming_slots
            FROM tour_locations tl
            LEFT JOIN location_next_dates lnd ON tl.id = lnd.tour_location_id
            ORDER BY 
                CASE WHEN lnd.next_tour_date IS NULL THEN 1 ELSE 0 END,
                lnd.next_tour_date ASC,
                tl.name ASC
        ''').fetchall()
        tour_locations = [dict(loc) for loc in tour_locations]
        # Attach location images (if any) so templates can render galleries for locations
        location_ids = [loc['id'] for loc in tour_locations]
        if location_ids:
            placeholders = ','.join(['?'] * len(location_ids))
            image_rows = db_conn.execute(
                f"""
                SELECT id, location_id, filename, file_path, alt_text, sort_order
                  FROM location_images
                 WHERE location_id IN ({placeholders})
                 ORDER BY sort_order, id
                """,
                location_ids,
            ).fetchall()
            images_map = {lid: [] for lid in location_ids}
            for row in image_rows:
                images_map[row['location_id']].append(dict(row))
            for loc in tour_locations:
                loc['images'] = images_map.get(loc['id'], [])
        else:
            for loc in tour_locations:
                loc['images'] = []
        sections_map = {section['slug']: section for section in content_service.list_sections()}

        return render_template(
            'index.html',
            tours=tours_with_images,
            tour_locations=tour_locations,
            page_sections=sections_map
        )

    @app.post('/contact')
    def submit_contact_message():
        payload = request.get_json(silent=True) or {}
        name = (payload.get('name') or '').strip()
        email = (payload.get('email') or '').strip()
        message = (payload.get('message') or '').strip()

        if not name or not email or not message:
            return jsonify({'message': 'Minden mező kitöltése kötelező.'}), 400

        try:
            email_service = get_email_service()
            email_service.send_contact_message(name=name, email=email, message=message)
        except EmailServiceError as exc:
            app.logger.error('Contact email failed: %s', exc)
            return jsonify({'message': 'Az üzenetet most nem tudtuk elküldeni. Próbáld újra később.'}), 500

        return jsonify({'message': 'Köszönjük! Hamarosan felvesszük veled a kapcsolatot.'}), 200
    
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
        
        # Fallback to location images if no tour-specific images are uploaded
        if not images:
            loc_id = tour['tour_location_id'] if 'tour_location_id' in tour.keys() else None
            if not loc_id and tour.get('location'):
                loc = db_conn.execute('SELECT id FROM tour_locations WHERE name = ?', (tour['location'],)).fetchone()
                if loc:
                    loc_id = loc['id']
            
            if loc_id:
                images = db_conn.execute('''
                    SELECT id, filename, file_path, alt_text, sort_order
                    FROM location_images
                    WHERE location_id = ?
                    ORDER BY sort_order, id
                ''', (loc_id,)).fetchall()
        
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
        
        response = make_response(render_template('partials/tour_details.html', tour=tour_dict))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    @app.route('/api/tours')
    @cache.cached(timeout=300, query_string=True)
    def api_tours():
        """API endpoint for AJAX tour filtering."""
        date_filter = request.args.get('date')
        month_filter = request.args.get('month')
        
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
        elif month_filter:
            query += ' AND STRFTIME("%Y-%m", t.date) = ?'
            params.append(month_filter)

        
        query += ' GROUP BY t.id ORDER BY t.date ASC'
        
        tours = db_conn.execute(query, params).fetchall()
        
        # Add images to each tour (BATCH OPTIMIZED)
        tour_ids = [t['id'] for t in tours]
        images_by_tour = {tid: [] for tid in tour_ids}
        
        if tour_ids:
            placeholders = ','.join(['?'] * len(tour_ids))
            all_images = db_conn.execute(f'''
                SELECT id, tour_id, filename, file_path, alt_text, sort_order
                FROM tour_images
                WHERE tour_id IN ({placeholders})
                ORDER BY sort_order, id
            ''', tour_ids).fetchall()
            
            for img in all_images:
                images_by_tour[img['tour_id']].append(dict(img))

        tours_data = []
        for tour in tours:
            tour_dict = dict(tour)
            tour_dict['images'] = images_by_tour.get(tour['id'], [])
            tours_data.append(tour_dict)
        
        return jsonify(tours_data)
    
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        """Serve uploaded files."""
        uploads_dir = os.path.join(app.root_path, '..', 'public', 'uploads')
        return send_from_directory(uploads_dir, filename)
    
    @app.route('/booking/form')
    def booking_form():
        """Render booking form partial with a fresh CSRF token and no-cache headers."""
        csrf_token_value = generate_csrf()
        html = render_template('partials/booking_form_view.html', booking_form_csrf_token=csrf_token_value)
        response = make_response(html)
        response.headers['X-CSRF-Token'] = csrf_token_value
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route('/aszf')
    def terms_page():
        """Public ÁSZF page with editable content."""
        section = content_service.get_section('terms_page')
        return render_template('aszf.html', legal_content=section.get('content', {}))

    @app.route('/adatvedelmi-nyilatkozat')
    def privacy_page():
        """Public privacy notice page with editable content."""
        section = content_service.get_section('privacy_page')
        return render_template('adatvedelmi_nyilatkozat.html', legal_content=section.get('content', {}))

    @app.route('/tour/<int:tour_id>/info')
    def tour_info(tour_id):
        """Standalone tour info page – accessible only via email token link.

        URL format: /tour/<id>/info?ref=<order_ref>&token=<hmac_token>
        If the tour date is in the past, render the 'tour_expired' page.
        """
        order_ref = request.args.get('ref', '')
        token = request.args.get('token', '')

        if not order_ref or not token:
            abort(404)

        if not verify_tour_token(app.config['SECRET_KEY'], tour_id, order_ref, token):
            abort(404)

        db_conn = get_db()
        tour = db_conn.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()
        if not tour:
            abort(404)

        # Check if tour date is in the past
        tour_date_str = tour['date']
        tour_time_str = tour['time'] or '00:00'
        try:
            tour_dt = datetime.strptime(f"{tour_date_str} {tour_time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                tour_dt = datetime.strptime(tour_date_str, "%Y-%m-%d")
            except ValueError:
                tour_dt = None

        if tour_dt and tour_dt <= datetime.now():
            return render_template('tour_expired.html', now=datetime.now())

        # Load images
        images = db_conn.execute('''
            SELECT id, filename, file_path, alt_text, sort_order,
                   COALESCE(focus_x, 50) as focus_x, COALESCE(focus_y, 50) as focus_y
            FROM tour_images WHERE tour_id = ? ORDER BY sort_order, id
        ''', (tour_id,)).fetchall()

        # Load location coords if available
        tour_dict = dict(tour)
        if tour['tour_location_id']:
            loc = db_conn.execute('SELECT latitude, longitude FROM tour_locations WHERE id = ?',
                                 (tour['tour_location_id'],)).fetchone()
            if loc:
                tour_dict['latitude'] = loc['latitude']
                tour_dict['longitude'] = loc['longitude']

        return render_template('tour_info.html', tour=tour_dict, images=[dict(i) for i in images])

    # Exempt tour_info from CSRF (it's GET-only, no form submission)
    csrf.exempt(tour_info)

    @app.route('/api/template/tour-reservation')
    def tour_reservation_template():
        """Return the tour reservation view partial for client-side rendering."""
        return render_template('partials/tour_reservation_view.html')
    
    @app.route('/robots.txt')
    def robots_txt():
        """Serve robots.txt dynamically to include sitemap URL."""
        base_url = os.getenv('APP_BASE_URL', request.url_root.rstrip('/'))
        lines = [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {base_url}/sitemap.xml"
        ]
        response = make_response("\n".join(lines))
        response.headers["Content-Type"] = "text/plain"
        return response

    @app.route('/sitemap.xml')
    def sitemap_xml():
        """Generate XML sitemap dynamically."""
        base_url = os.getenv('APP_BASE_URL', request.url_root.rstrip('/'))
        
        # Start XML
        xml = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        # Add homepage
        xml.append('  <url>')
        xml.append(f'    <loc>{base_url}/</loc>')
        xml.append('    <changefreq>daily</changefreq>')
        xml.append('    <priority>1.0</priority>')
        xml.append('  </url>')
        
        # Add legal pages
        xml.append('  <url>')
        xml.append(f'    <loc>{base_url}/aszf</loc>')
        xml.append('    <changefreq>monthly</changefreq>')
        xml.append('    <priority>0.3</priority>')
        xml.append('  </url>')
        
        xml.append('  <url>')
        xml.append(f'    <loc>{base_url}/adatvedelmi-nyilatkozat</loc>')
        xml.append('    <changefreq>monthly</changefreq>')
        xml.append('    <priority>0.3</priority>')
        xml.append('  </url>')
        
        xml.append('</urlset>')
        
        response = make_response("\n".join(xml))
        response.headers["Content-Type"] = "application/xml"
        return response

    return app
