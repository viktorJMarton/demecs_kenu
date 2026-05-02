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
    
    sort_dir = request.args.get('sort_dir', 'asc').lower()
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'

    if date_to:
        query += ' AND t.date <= ?'
        params.append(date_to)
    
    query += f' GROUP BY t.id ORDER BY t.date {sort_dir.upper()}, t.time {sort_dir.upper()}'

    today = datetime.now().date()
    tours_list = db.execute(query, params).fetchall()

    # Status filter (computed value, not stored in DB)
    status_filter = request.args.get('status_filter', '')
    if status_filter:
        from datetime import date as date_type

        def get_status(tour):
            tour_date = tour['date']
            if isinstance(tour_date, str):
                try:
                    tour_date = date_type.fromisoformat(tour_date)
                except ValueError:
                    return 'ismeretlen'
            if tour_date < today:
                return 'lezajlott'
            participants = tour['participants'] or 0
            max_p = tour['max_participants']
            if participants >= max_p:
                return 'megtelt'
            if participants > max_p * 0.8:
                return 'majdnem'
            return 'elerheto'

        tours_list = [t for t in tours_list if get_status(t) == status_filter]

    return render_template(
        'admin/tours.html',
        tours=tours_list,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_dir=sort_dir,
        status_filter=status_filter,
        today=today
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
        
        cache.clear()
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
        cache.clear()
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
        cache.clear()
        flash('A lezajlott túra inaktiválva, a foglalások archiváltan megmaradnak.', 'success')
    else:
        broadcast_system_message(f'Túra törölve: {tour["title"]}', 'info')
        cache.clear()
        flash('Túra sikeresen törölve!', 'success')

    return redirect(url_for('admin_tours.tours'))


@bp.route('/tours/duplicate/<int:tour_id>', methods=['POST'])
@login_required
def duplicate_tour(tour_id):
    """Duplicate a tour (creates a copy and duplicates associated images).

    If request is AJAX (X-Requested-With), returns JSON with the new tour data.
    Otherwise redirects back to the tour list.
    """
    import re
    import shutil

    db = get_db()
    tour = db.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()
    if not tour:
        flash('A másolandó túra nem található.', 'error')
        return redirect(url_for('admin_tours.tours'))

    orig_title = tour['title'] or 'Túra'
    like_pattern = f"{orig_title} másolata%"
    rows = db.execute('SELECT title FROM tours WHERE title LIKE ?', (like_pattern,)).fetchall()

    # Determine next index for the copied title
    max_n = 0
    for row in rows:
        m = re.search(r"\[(\d+)\]\s*$", row['title'])
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except ValueError:
                continue
        else:
            # Treat a bare "... másolata" as n=1
            if row['title'].strip() == f"{orig_title} másolata":
                if 1 > max_n:
                    max_n = 1

    new_n = max_n + 1
    new_title = f"{orig_title} másolata [{new_n}]"

    # Copy tour row (only core fields, do not copy bookings)
    cols = (
        'title', 'description', 'date', 'time', 'duration', 'max_participants',
        'price', 'difficulty', 'location', 'tour_location_id', 'distance', 'meeting_point',
        'equipment_included', 'what_to_bring', 'cancellation_policy', 'image_url',
        'tour_latitude', 'tour_longitude', 'is_active'
    )

    # Use a single SQL INSERT ... SELECT to duplicate the row server-side and avoid
    # Python-side dict access issues (sqlite3.Row has no .get()). This also keeps
    # the operation atomic and efficient.
    cols_str = ', '.join(cols)

    insert_sql = f"INSERT INTO tours ({cols_str}) SELECT ?, description, date, time, duration, max_participants, price, difficulty, location, tour_location_id, distance, meeting_point, equipment_included, what_to_bring, cancellation_policy, image_url, tour_latitude, tour_longitude, is_active FROM tours WHERE id = ?"

    cursor = db.execute(insert_sql, (new_title, tour_id))
    new_tour_id = cursor.lastrowid
    db.commit()

    # Duplicate images (if any)
    ensure_tour_images_table(db)
    images = db.execute('SELECT id, filename, file_path, alt_text, sort_order FROM tour_images WHERE tour_id = ?', (tour_id,)).fetchall()
    if images:
        src_root = _uploads_root()
        dest_dir = _tour_upload_dir(new_tour_id)
        for img in images:
            src_path = os.path.join(src_root, img['file_path'])
            if not os.path.exists(src_path):
                # skip missing files
                continue
            base = os.path.basename(img['filename'])
            dest_path = os.path.join(dest_dir, base)
            # Avoid overwriting existing files; add suffix if needed
            copy_index = 1
            final_name = base
            while os.path.exists(dest_path):
                name_only, ext = os.path.splitext(base)
                final_name = f"{name_only}_copy{copy_index}{ext}"
                dest_path = os.path.join(dest_dir, final_name)
                copy_index += 1
            try:
                shutil.copy2(src_path, dest_path)
                # Attempt to copy thumbnail variants (e.g. name_thumb.webp) and rename them to match the new file name
                try:
                    src_dir = os.path.dirname(src_path)
                    name_no_ext = os.path.splitext(base)[0]
                    src_thumb = os.path.join(src_dir, f"{name_no_ext}_thumb.webp")
                    if os.path.exists(src_thumb):
                        final_thumb_name = f"{os.path.splitext(final_name)[0]}_thumb.webp"
                        dest_thumb_path = os.path.join(dest_dir, final_thumb_name)
                        shutil.copy2(src_thumb, dest_thumb_path)
                        current_app.logger.info(f"Copied thumbnail {src_thumb} -> {dest_thumb_path}")
                except Exception as e2:
                    current_app.logger.warning(f"Failed to copy thumbnail for {src_path}: {e2}")
                rel = os.path.join('tours', str(new_tour_id), final_name).replace('\\', '/')
                db.execute(
                    'INSERT INTO tour_images (tour_id, filename, file_path, alt_text, sort_order) VALUES (?, ?, ?, ?, ?)',
                    (new_tour_id, final_name, rel, img['alt_text'] if 'alt_text' in img.keys() else None, img['sort_order'] if 'sort_order' in img.keys() else 0)
                )
            except Exception as e:
                current_app.logger.error(f"Failed to copy image {src_path} -> {dest_path}: {e}")
        db.commit()

        # Ensure thumbnails exist for the new images. Some admin views rely on
        # <name>_thumb.webp to be present. If a thumbnail wasn't copied above,
        # generate one from the newly copied image.
        try:
            from PIL import Image
        except Exception:
            Image = None

        if Image is not None:
            for file in os.listdir(dest_dir):
                # process only image files (skip thumbs)
                if not file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    continue
                name, ext = os.path.splitext(file)
                if name.endswith('_thumb'):
                    continue
                thumb_name = f"{name}_thumb.webp"
                thumb_path = os.path.join(dest_dir, thumb_name)
                src_img_path = os.path.join(dest_dir, file)
                # If thumbnail exists, skip
                if os.path.exists(thumb_path):
                    continue
                try:
                    with Image.open(src_img_path) as im:
                        if im.mode in ('RGBA', 'P', 'CMYK'):
                            im = im.convert('RGB')
                        # create a thumbnail with width 400
                        width, height = im.size
                        if width > 400:
                            ratio = 400 / float(width)
                            new_h = int(height * ratio)
                            im.thumbnail((400, new_h), Image.Resampling.LANCZOS)
                        im.save(thumb_path, format='WEBP', quality=80)
                        current_app.logger.info(f"Generated thumbnail for {src_img_path} -> {thumb_path}")
                except Exception as e:
                    current_app.logger.warning(f"Failed to generate thumbnail for {src_img_path}: {e}")

    # Broadcast and feedback
    broadcast_tour_update(new_tour_id, 'created', {
        'id': new_tour_id,
        'title': new_title,
        'date': tour['date'],
        'time': tour['time'],
        'price': tour['price'],
        'max_participants': tour['max_participants'],
        'difficulty': tour['difficulty'],
        'location': tour['location']
    })

    broadcast_system_message(f'Túra másolva: {orig_title} → {new_title}', 'success')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'id': new_tour_id,
            'title': new_title,
            'date': tour['date'],
            'time': tour['time'],
            'price': tour['price'],
            'max_participants': tour['max_participants'],
            'difficulty': tour['difficulty'],
            'location': tour['location']
        }), 201

    flash('Túra sikeresen másolva!', 'success')
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
        cache.clear()
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
    cache.clear()
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
    cache.clear()

    return jsonify({'success': True})
