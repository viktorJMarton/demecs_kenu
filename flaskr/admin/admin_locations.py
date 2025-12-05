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
)
import io
from werkzeug.utils import secure_filename

from ..auth import login_required
from ..db import get_db

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

        # If HEIC/HEIF: try to convert server-side to JPEG
        if ext in ('.heic', '.heif'):
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
                # Import Pillow lazily after registering HEIF opener
                from PIL import Image
            except Exception:
                rejected.append((filename, 'HEIC konverzióhoz hiányzó függőség'))
                continue

                file.stream.seek(0)
                raw = file.read()
                img_buf = io.BytesIO(raw)
                img = Image.open(img_buf)
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                base, _ = os.path.splitext(filename)
                final_name = f"{base}.jpg"
                counter = 1
                while os.path.exists(os.path.join(upload_dir, final_name)):
                    final_name = f"{base}_{counter}.jpg"
                    counter += 1

                abs_path = os.path.join(upload_dir, final_name)
                img.save(abs_path, format='JPEG', quality=90)

                rel_path = os.path.join('locations', str(location_id), final_name).replace('\\', '/')
                db.execute(
                    "INSERT INTO location_images (location_id, filename, file_path, alt_text) VALUES (?, ?, ?, ?)",
                    (location_id, final_name, rel_path, alt_text or None),
                )
                saved += 1
                continue
            except Exception:
                rejected.append((filename, 'HEIC konverzió sikertelen'))
                continue

        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            rejected.append((filename, 'Nem támogatott kiterjesztés'))
            continue
        if file.mimetype not in ALLOWED_IMAGE_MIME_TYPES:
            rejected.append((filename, f'Nem támogatott MIME típus: {file.mimetype}'))
            continue

        base, _ = os.path.splitext(filename)
        final_name = filename
        counter = 1
        while os.path.exists(os.path.join(upload_dir, final_name)):
            final_name = f"{base}_{counter}{ext}"
            counter += 1

        file.save(os.path.join(upload_dir, final_name))
        rel_path = os.path.join("locations", str(location_id), final_name).replace("\\", "/")
        db.execute(
            "INSERT INTO location_images (location_id, filename, file_path, alt_text) VALUES (?, ?, ?, ?)",
            (location_id, final_name, rel_path, alt_text or None),
        )
        saved += 1

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
