"""
Admin Tours Blueprint - Tour management (CRUD operations) + image uploads.
"""

import os
import sqlite3
import io
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from ..auth import login_required
from ..db import get_db
from ..events import broadcast_tour_update, broadcast_system_message
from ..image_utils import process_and_save_image
from ..extensions import cache

bp = Blueprint('admin_tours', __name__, url_prefix='/admin')


# --- Helpers ---
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
ALLOWED_IMAGE_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
    'image/bmp'
}


def ensure_tour_images_table(db):
    """Create tour_images table if it doesn't exist (safe to call multiple times)."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS tour_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tour_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            alt_text TEXT,
            sort_order INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tour_id) REFERENCES tours(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tour_images_tour_id ON tour_images(tour_id);
        """
    )


def _uploads_root():
    """Absolute path to the public uploads root folder."""
    # Default to project-level /public/uploads if not configured
    root = current_app.config.get('UPLOADS_ROOT')
    if not root:
        # app.root_path -> .../flaskr; go one up to repo root and into public/uploads
        root = os.path.abspath(os.path.join(current_app.root_path, '..', 'public', 'uploads'))
    os.makedirs(root, exist_ok=True)
    return root


def _tour_upload_dir(tour_id: int) -> str:
    path = os.path.join(_uploads_root(), 'tours', str(tour_id))
    os.makedirs(path, exist_ok=True)
    return path


def _has_tour_happened(date_value: str | None, time_value: str | None) -> bool:
    """Return True when the given tour date/time is in the past."""
    if not date_value:
        return False

    time_component = time_value or "00:00"
    try:
        scheduled = datetime.strptime(f"{date_value} {time_component}", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            scheduled = datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            return False

    return scheduled <= datetime.now()


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


def _get_tour_locations(db):
    return db.execute('SELECT * FROM tour_locations ORDER BY name').fetchall()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@bp.route('/locations', methods=['POST'])
@login_required
def create_location():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    latitude = _safe_float(data.get('latitude'))
    longitude = _safe_float(data.get('longitude'))

    errors = {}
    if not name:
        errors['name'] = 'A helyszín neve kötelező.'
    if latitude is None:
        errors['latitude'] = 'Érvényes szélességi koordináta szükséges.'
    if longitude is None:
        errors['longitude'] = 'Érvényes hosszúsági koordináta szükséges.'

    if errors:
        return jsonify({'errors': errors}), 400

    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO tour_locations (name, latitude, longitude) VALUES (?, ?, ?)',
            (name, latitude, longitude)
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({'errors': {'name': 'Már létezik ilyen nevű helyszín.'}}), 409

    location = {
        'id': cursor.lastrowid,
        'name': name,
        'latitude': latitude,
        'longitude': longitude
    }
    return jsonify(location), 201


@bp.route('/tours/add', methods=['GET', 'POST'])
@login_required
def add_tour():
    """Add a new tour."""
    db = get_db()
    tour_locations = _get_tour_locations(db)

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
        tour_location_id = _safe_int(request.form.get('tour_location_id'))
        distance = float(request.form['distance']) if request.form['distance'] else None
        meeting_point = request.form['meeting_point']
        equipment_included = request.form['equipment_included']
        what_to_bring = request.form.get('what_to_bring', '')
        tour_latitude = float(request.form['tour_latitude']) if request.form['tour_latitude'] else None
        tour_longitude = float(request.form['tour_longitude']) if request.form['tour_longitude'] else None
        
        cursor = db.execute('''
            INSERT INTO tours (title, description, date, time, duration, max_participants, 
                             price, difficulty, location, tour_location_id, distance, meeting_point, 
                                                         equipment_included, what_to_bring, tour_latitude, tour_longitude)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ''', (title, description, date, time, duration, max_participants, price, 
          difficulty, location, tour_location_id, distance, meeting_point, equipment_included,
                    what_to_bring, tour_latitude, tour_longitude))
        
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
        
        cache.clear() # Invalidate cache
        flash('Túra sikeresen hozzáadva!', 'success')
        return redirect(url_for('admin_tours.tours'))
    
    return render_template('admin/tour_form.html', tour=None, tour_locations=tour_locations)


@bp.route('/tours/edit/<int:tour_id>', methods=['GET', 'POST'])
@login_required
def edit_tour(tour_id):
    """Edit an existing tour."""
    db = get_db()
    tour_locations = _get_tour_locations(db)
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
        what_to_bring = request.form.get('what_to_bring', '')
        tour_latitude = float(request.form['tour_latitude']) if request.form['tour_latitude'] else None
        tour_longitude = float(request.form['tour_longitude']) if request.form['tour_longitude'] else None
        tour_location_id = _safe_int(request.form.get('tour_location_id'))

        old_max = tour['max_participants']
        if max_participants < old_max:
            current_bookings = db.execute('''
                SELECT COUNT(*) FROM bookings 
                WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
            ''', (tour_id,)).fetchone()[0]
            if current_bookings > max_participants:
                flash(
                    f'Figyelem! A maximális létszám ({max_participants}) kevesebb mint a jelenlegi foglalások száma ({current_bookings}). Túlfoglalás alakult ki!',
                    'warning'
                )
                broadcast_system_message(
                    f'Túlfoglalás riasztás: {title} - {current_bookings}/{max_participants} fő',
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
            title, description, date, time, duration, max_participants, price,
            difficulty, location, tour_location_id, distance, meeting_point,
            equipment_included, what_to_bring, tour_latitude, tour_longitude, tour_id
        ))
        db.commit()

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
        cache.clear() # Invalidate cache
        flash('Túra sikeresen frissítve!', 'success')
        return redirect(url_for('admin_tours.tours'))
    
    # Ensure images table exists and load images for UI
    ensure_tour_images_table(db)
    images = db.execute(
        'SELECT * FROM tour_images WHERE tour_id = ? ORDER BY sort_order, id',
        (tour_id,)
    ).fetchall()

    return render_template('admin/tour_form.html', tour=tour, images=images, tour_locations=tour_locations)


@bp.route('/tours/delete/<int:tour_id>', methods=['POST'])
@login_required
def delete_tour(tour_id):
    """Delete (deactivate) a tour."""
    db = get_db()
    tour = db.execute('SELECT id, title, date, time FROM tours WHERE id = ?', (tour_id,)).fetchone()
    if not tour:
        flash('A megadott túra nem található.', 'error')
        return redirect(url_for('admin_tours.tours'))

    already_happened = _has_tour_happened(tour['date'], tour['time'])

    if not already_happened:
        active_bookings = db.execute('''
            SELECT COUNT(*) FROM bookings 
            WHERE tour_id = ? AND payment_status IN ('paid', 'pending')
        ''', (tour_id,)).fetchone()[0]

        if active_bookings > 0:
            flash(
                f'A túrát nem lehet törölni, mert {active_bookings} aktív foglalás tartozik hozzá!',
                'error'
            )
            broadcast_system_message(
                f'Túra törlési kísérlet sikertelen: {active_bookings} aktív foglalás',
                'warning'
            )
            return redirect(url_for('admin_tours.tours'))

    db.execute('UPDATE tours SET is_active = 0 WHERE id = ?', (tour_id,))
    db.commit()

    broadcast_tour_update(tour_id, 'deleted', {
        'id': tour_id,
        'title': tour['title'] if tour else 'Ismeretlen túra'
    })

    if already_happened:
        broadcast_system_message(
            f'Túra archiválva (már lezajlott): {tour["title"]}',
            'info'
        )
        flash('A lezajlott túra inaktiválva, a foglalások archiváltan megmaradnak.', 'success')
    else:
        broadcast_system_message(f'Túra törölve: {tour["title"]}', 'info')
        flash('Túra sikeresen törölve!', 'success')

    cache.clear() # Invalidate cache
    return redirect(url_for('admin_tours.tours'))


@bp.route('/tours/<int:tour_id>/images/upload', methods=['POST'])
@login_required
def upload_tour_images(tour_id):
    """Handle multi-image upload for a tour."""
    db = get_db()
    # Validate tour exists
    tour = db.execute('SELECT id, title FROM tours WHERE id = ?', (tour_id,)).fetchone()
    if not tour:
        flash('Túra nem található!', 'error')
        return redirect(url_for('admin_tours.tours'))

    ensure_tour_images_table(db)

    files = request.files.getlist('images')
    if not files:
        flash('Nincs kiválasztott kép.', 'warning')
        return redirect(url_for('admin_tours.edit_tour', tour_id=tour_id))

    saved = 0
    rejected = []
    upload_dir = _tour_upload_dir(tour_id)

    for file in files:
        if not file or not getattr(file, 'filename', ''):
            continue
        name = secure_filename(file.filename)
        ext = os.path.splitext(name)[1].lower()

        # Check extensions (allow HEIC/HEIF for processing)
        if ext not in ALLOWED_IMAGE_EXTENSIONS and ext not in ('.heic', '.heif'):
            rejected.append((name, 'Nem támogatott kiterjesztés'))
            continue
            
        # Check mime type (skip check for HEIC as it varies)
        if ext not in ('.heic', '.heif') and file.mimetype not in ALLOWED_IMAGE_MIME_TYPES:
            rejected.append((name, f'Nem támogatott MIME típus: {file.mimetype}'))
            continue

        try:
            # Process and save image (resize + compress)
            final_name = process_and_save_image(file, upload_dir, name)
            
            rel_path = os.path.join('tours', str(tour_id), final_name).replace('\\', '/')
            db.execute(
                'INSERT INTO tour_images (tour_id, filename, file_path) VALUES (?, ?, ?)',
                (tour_id, final_name, rel_path)
            )
            saved += 1
        except Exception as e:
            current_app.logger.error(f"Image processing failed for {name}: {e}")
            rejected.append((name, f'Hiba a feldolgozás során: {str(e)}'))
            continue

    # Commit saved files and report results
    if saved:
        db.commit()
        cache.clear() # Invalidate cache (images changed)
        flash(f'{saved} kép sikeresen feltöltve.', 'success')

    if rejected:
        # build a short message listing rejected files and reasons
        msgs = [f"{fn}: {reason}" for fn, reason in rejected]
        flash('Néhány fájl elutasítva: ' + '; '.join(msgs), 'warning')

    if not saved and not rejected:
        flash('Nem sikerült képet feltölteni. Ellenőrizd a fájlformátumokat.', 'error')

    return redirect(url_for('admin_tours.edit_tour', tour_id=tour_id))


@bp.route('/tours/<int:tour_id>/images/<int:image_id>/delete', methods=['POST'])
@login_required
def delete_tour_image(tour_id, image_id):
    """Delete an image for a tour (file + DB row)."""
    db = get_db()
    ensure_tour_images_table(db)
    row = db.execute(
        'SELECT id, file_path FROM tour_images WHERE id = ? AND tour_id = ?',
        (image_id, tour_id)
    ).fetchone()
    if not row:
        flash('Kép nem található.', 'warning')
        return redirect(url_for('admin_tours.edit_tour', tour_id=tour_id))

    # Remove file if exists
    abs_path = os.path.join(_uploads_root(), row['file_path'])
    try:
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception:
        # Non-fatal; continue to remove DB row
        pass

    db.execute('DELETE FROM tour_images WHERE id = ?', (image_id,))
    db.commit()
    cache.clear() # Invalidate cache
    flash('Kép törölve.', 'info')
    return redirect(url_for('admin_tours.edit_tour', tour_id=tour_id))


@bp.route('/tours/<int:tour_id>/images/<int:image_id>/focus', methods=['POST'])
@login_required
def update_tour_image_focus(tour_id, image_id):
    """Update the focal point of a tour image."""
    data = request.get_json()
    focus_x = data.get('focus_x')
    focus_y = data.get('focus_y')

    if focus_x is None or focus_y is None:
        return jsonify({'error': 'Missing coordinates'}), 400

    try:
        focus_x = int(focus_x)
        focus_y = int(focus_y)
        if not (0 <= focus_x <= 100 and 0 <= focus_y <= 100):
             return jsonify({'error': 'Coordinates must be between 0 and 100'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid coordinates'}), 400

    db = get_db()
    ensure_tour_images_table(db)
    
    db.execute(
        'UPDATE tour_images SET focus_x = ?, focus_y = ? WHERE id = ? AND tour_id = ?',
        (focus_x, focus_y, image_id, tour_id)
    )
    db.commit()
    cache.clear() # Invalidate cache

    return jsonify({'success': True})
