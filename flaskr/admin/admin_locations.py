"""Admin interface for managing tour location galleries."""

from __future__ import annotations

import os
from typing import Dict, List

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)
import io
from werkzeug.utils import secure_filename

from ..auth import login_required
from ..db import get_db
from ..image_utils import process_and_save_image
import shutil

bp = Blueprint("admin_locations", __name__, url_prefix="/admin/locations")

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
}


def ensure_location_images_table(db) -> None:
    """Create supporting table on demand."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS location_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            alt_text TEXT,
            sort_order INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (location_id) REFERENCES tour_locations(id)
        );
        CREATE INDEX IF NOT EXISTS idx_location_images_location_id
            ON location_images(location_id);
        """
    )


def _uploads_root() -> str:
    root = current_app.config.get("UPLOADS_ROOT")
    if not root:
        root = os.path.abspath(os.path.join(current_app.root_path, "..", "public", "uploads"))
    os.makedirs(root, exist_ok=True)
    return root


def _location_upload_dir(location_id: int) -> str:
    path = os.path.join(_uploads_root(), "locations", str(location_id))
    os.makedirs(path, exist_ok=True)
    return path


def _fetch_locations_with_images(db):
    locations = db.execute(
        """
        SELECT tl.*,
               COUNT(t.id)            AS tours_count,
               SUM(CASE WHEN t.is_active = 1 THEN 1 ELSE 0 END) AS active_tours
          FROM tour_locations tl
     LEFT JOIN tours t ON t.tour_location_id = tl.id
      GROUP BY tl.id
      ORDER BY tl.name
        """
    ).fetchall()

    location_dicts: List[Dict] = [dict(loc) for loc in locations]
    location_ids = [loc["id"] for loc in location_dicts]
    images_map: Dict[int, List[Dict]] = {loc_id: [] for loc_id in location_ids}

    if location_ids:
        placeholders = ",".join(["?"] * len(location_ids))
        image_rows = db.execute(
            f"""
            SELECT id, location_id, filename, file_path, alt_text, sort_order, uploaded_at
              FROM location_images
             WHERE location_id IN ({placeholders})
             ORDER BY sort_order, id
            """,
            location_ids,
        ).fetchall()
        for row in image_rows:
            images_map[row["location_id"]].append(dict(row))

    for loc in location_dicts:
        loc["images"] = images_map.get(loc["id"], [])

    return location_dicts


@bp.route("/", methods=["GET"])
@login_required
def index():
    db = get_db()
    ensure_location_images_table(db)
    locations = _fetch_locations_with_images(db)
    return render_template("admin/locations.html", locations=locations)


@bp.route("/<int:location_id>/description", methods=["POST"])
@login_required
def update_location_description(location_id: int):
    db = get_db()
    exists = db.execute(
        "SELECT id FROM tour_locations WHERE id = ?",
        (location_id,),
    ).fetchone()
    if not exists:
        flash("A kiválasztott helyszín nem található.", "error")
        return redirect(url_for("admin_locations.index"))
    description = (request.form.get("description") or "").strip()
    db.execute(
        """
        UPDATE tour_locations
           SET description = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (description or None, location_id),
    )
    db.commit()
    flash("Helyszín leírás frissítve.", "success")
    return redirect(url_for("admin_locations.index", _anchor=f"location-{location_id}"))


@bp.route("/<int:location_id>/images", methods=["POST"])
@login_required
def upload_location_images(location_id: int):
    db = get_db()
    ensure_location_images_table(db)
    location = db.execute(
        "SELECT id, name FROM tour_locations WHERE id = ?",
        (location_id,),
    ).fetchone()
    if not location:
        flash("A kiválasztott helyszín nem található.", "error")
        return redirect(url_for("admin_locations.index"))

    files = request.files.getlist("images")
    if not files:
        flash("Nem választottál ki képet.", "warning")
        return redirect(url_for("admin_locations.index", _anchor=f"location-{location_id}"))

    upload_dir = _location_upload_dir(location_id)
    saved = 0
    rejected = []
    alt_text = location["name"].strip()

    for file in files:
        filename = secure_filename(getattr(file, "filename", ""))
        if not filename:
            continue
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        # Check extensions (allow HEIC/HEIF for processing)
        if ext not in ALLOWED_IMAGE_EXTENSIONS and ext not in ('.heic', '.heif'):
            rejected.append((filename, 'Nem támogatott kiterjesztés'))
            continue
            
        # Check mime type (skip check for HEIC as it varies)
        if ext not in ('.heic', '.heif') and file.mimetype not in ALLOWED_IMAGE_MIME_TYPES:
            rejected.append((filename, f'Nem támogatott MIME típus: {file.mimetype}'))
            continue

        try:
            # Process and save image (resize + compress)
            final_name = process_and_save_image(file, upload_dir, filename)
            
            rel_path = os.path.join('locations', str(location_id), final_name).replace('\\', '/')
            db.execute(
                "INSERT INTO location_images (location_id, filename, file_path, alt_text) VALUES (?, ?, ?, ?)",
                (location_id, final_name, rel_path, alt_text or None),
            )
            saved += 1
        except Exception as e:
            current_app.logger.error(f"Image processing failed for {filename}: {e}")
            rejected.append((filename, f'Hiba a feldolgozás során: {str(e)}'))
            continue

    if saved:
        db.commit()
        flash(f"{saved} kép sikeresen feltöltve.", "success")

    if rejected:
        msgs = [f"{fn}: {reason}" for fn, reason in rejected]
        flash('Néhány fájl elutasítva: ' + '; '.join(msgs), 'warning')

    if not saved and not rejected:
        flash("Nem sikerült képet feltölteni. Ellenőrizd a fájlokat.", "error")

    return redirect(url_for("admin_locations.index", _anchor=f"location-{location_id}"))


@bp.route("/<int:location_id>/images/<int:image_id>/delete", methods=["POST"])
@login_required
def delete_location_image(location_id: int, image_id: int):
    db = get_db()
    ensure_location_images_table(db)
    row = db.execute(
        "SELECT id, file_path FROM location_images WHERE id = ? AND location_id = ?",
        (image_id, location_id),
    ).fetchone()
    if not row:
        flash("A kép nem található.", "warning")
        return redirect(url_for("admin_locations.index", _anchor=f"location-{location_id}"))

    abs_path = os.path.join(_uploads_root(), row["file_path"])
    try:
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except OSError:
        # Non-fatal; continue removing the DB row.
        pass

    db.execute("DELETE FROM location_images WHERE id = ?", (image_id,))
    db.commit()
    flash("Kép törölve.", "info")
    return redirect(url_for("admin_locations.index", _anchor=f"location-{location_id}"))


@bp.route("/<int:location_id>/delete", methods=["POST"])
@login_required
def delete_location(location_id: int):
    """Delete a tour location and its images if no tours reference it."""
    db = get_db()
    # Verify location exists
    loc = db.execute(
        "SELECT id, name FROM tour_locations WHERE id = ?",
        (location_id,),
    ).fetchone()
    if not loc:
        flash("A kiválasztott helyszín nem található.", "error")
        return redirect(url_for("admin_locations.index"))

    # Prevent deletion if tours reference this location
    ref = db.execute(
        "SELECT COUNT(1) AS cnt FROM tours WHERE tour_location_id = ?",
        (location_id,),
    ).fetchone()
    if ref and ref["cnt"] > 0:
        flash("A helyszínhez kapcsolódó túrák vannak, ezért nem törölhető.", "warning")
        return redirect(url_for("admin_locations.index", _anchor=f"location-{location_id}"))

    # Remove image files from disk
    rows = db.execute(
        "SELECT file_path FROM location_images WHERE location_id = ?",
        (location_id,),
    ).fetchall()
    uploads_root = _uploads_root()
    for r in rows:
        try:
            abs_path = os.path.join(uploads_root, r["file_path"])
            if os.path.exists(abs_path):
                os.remove(abs_path)
            # Also attempt to remove thumbnail variant next to it
            base, ext = os.path.splitext(abs_path)
            thumb = f"{base}_thumb.webp"
            if os.path.exists(thumb):
                os.remove(thumb)
        except OSError:
            # non-fatal
            current_app.logger.exception("Failed removing image file during location delete")

    # Remove the uploads directory for the location if empty
    loc_dir = os.path.join(uploads_root, "locations", str(location_id))
    try:
        if os.path.isdir(loc_dir):
            # remove directory and contents if any remain
            shutil.rmtree(loc_dir)
    except OSError:
        current_app.logger.exception("Failed to remove location upload directory")

    # Delete DB rows
    db.execute("DELETE FROM location_images WHERE location_id = ?", (location_id,))
    db.execute("DELETE FROM tour_locations WHERE id = ?", (location_id,))
    db.commit()

    flash("Helyszín és összes képe törölve.", "info")
    return redirect(url_for("admin_locations.index"))


@bp.route("/<int:location_id>/images/<int:image_id>/focus", methods=["POST"])
@login_required
def update_location_image_focus(location_id: int, image_id: int):
    """Update the focal point of a location image."""
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
    ensure_location_images_table(db)
    
    db.execute(
        'UPDATE location_images SET focus_x = ?, focus_y = ? WHERE id = ? AND location_id = ?',
        (focus_x, focus_y, image_id, location_id)
    )
    db.commit()

    return jsonify({'success': True})
