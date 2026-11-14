# Image optimization & maintenance

This project includes a small image pipeline and helper scripts to keep images optimized and avoid broken references.

Available scripts (run from project root):

- `python scripts/check_missing_images.py` - scans DB `page_sections` and image tables for image paths that don't exist under `public/uploads` and prints a report.
- `python scripts/generate_thumbnails.py` - generates `_thumb.webp` thumbnails for images and places them next to originals.
- `python scripts/migrate_to_webp.py` - converts `.jpg/.jpeg` images to `.webp`, updates DB `file_path`/`filename` columns and backs up originals under `public/uploads_backup_pre_webp`.
- `python scripts/optimize_images.py` - resizes/optimizes large images (max 1920px) and reduces file size.
- `python scripts/fix_page_section_image_extensions.py` - attempts to replace `.jpg` references in `page_sections` JSON (e.g. `info_cards`) by available `_thumb.webp` or `.webp` variants. **Creates DB backup** `kajak_kenu.db.before_fix_images`.

Best practices
- Run `generate_thumbnails.py` after uploads and `migrate_to_webp.py` periodically for older images.
- Always backup the DB before running destructive scripts (an automated backup is included in the `migrate_to_webp.py` flow).
- Use the Admin UI to re-upload missing images; the `check_missing_images.py` script helps find them.

Server tuning (already applied)
- Preload of critical assets (`style.css`, `logo.svg`) added to `flaskr/templates/base.html`.
- Static caching updated in `nginx/default.conf` to provide long `max-age` for fingerprintable assets and add `immutable`.
- Gzip types expanded for fonts.

CI
- A new GitHub workflow `lighthouse-audit.yml` runs Lighthouse (requires secret `SITE_URL`) and uploads the report as an artifact.

Rollback
- If you need to roll back any DB changes made by scripts, restore one of the DB backups present in repo root (e.g. `kajak_kenu.db.before_webp_YYYYMMDDHHMMSS` or `kajak_kenu.db.before_fix_images`).
