"""Affiliate partner administration views."""

import re
import secrets
import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..auth import login_required
from ..db import get_db


bp = Blueprint("admin_affiliates", __name__, url_prefix="/admin/affiliates")

_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_PARTNER_FIELDS = (
    "name",
    "company_name",
    "contact_name",
    "contact_email",
    "contact_phone",
    "billing_name",
    "billing_country",
    "billing_zip",
    "billing_city",
    "billing_address",
    "tax_number",
    "internal_notes",
)
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _new_ref_code() -> str:
    """Return a human-readable, cryptographically random referral code."""
    token = "".join(secrets.choice(_REF_ALPHABET) for _ in range(10))
    return f"AFF-{token}"


def _partner_form_data() -> dict[str, str]:
    data = {field: request.form.get(field, "").strip() for field in _PARTNER_FIELDS}
    data["billing_country"] = (data["billing_country"] or "hu").lower()
    return data


def _partner_form_errors(data: dict[str, str]) -> dict[str, str]:
    errors = {}
    if not data["name"]:
        errors["name"] = "A partner neve kötelező."
    elif len(data["name"]) > 200:
        errors["name"] = "A partner neve legfeljebb 200 karakter lehet."

    email = data["contact_email"]
    if email and not _EMAIL_PATTERN.fullmatch(email):
        errors["contact_email"] = "Adj meg érvényes e-mail-címet."

    if len(data["billing_country"]) != 2 or not data["billing_country"].isalpha():
        errors["billing_country"] = "Kétbetűs országkód szükséges, például HU."
    return errors


def _insert_partner(db, data: dict[str, str]) -> tuple[int, str]:
    """Insert with database-backed collision handling for the referral code."""
    columns = ", ".join(_PARTNER_FIELDS)
    placeholders = ", ".join("?" for _ in _PARTNER_FIELDS)
    values = [data[field] or None for field in _PARTNER_FIELDS]
    values[_PARTNER_FIELDS.index("billing_country")] = data["billing_country"]

    for _ in range(10):
        ref_code = _new_ref_code()
        try:
            cursor = db.execute(
                f"INSERT INTO affiliate_partners (ref_code, {columns}) "
                f"VALUES (?, {placeholders})",
                [ref_code, *values],
            )
            db.commit()
            return cursor.lastrowid, ref_code
        except sqlite3.IntegrityError as exc:
            db.rollback()
            if "affiliate_partners.ref_code" not in str(exc):
                raise

    raise RuntimeError("Nem sikerült egyedi partnerkódot generálni.")


def get_active_partner_by_ref(db, ref_code: str):
    """Resolve a referral code only while its partner is active."""
    normalized = (ref_code or "").strip()
    if not normalized:
        return None
    return db.execute(
        "SELECT * FROM affiliate_partners WHERE ref_code = ? AND is_active = 1",
        (normalized,),
    ).fetchone()


@bp.get("/")
@login_required
def index():
    """List affiliate partners with a bounded text search."""
    search = request.args.get("search", "").strip()[:100]
    query = """
        SELECT p.*,
               COUNT(rv.id) AS rule_count,
               SUM(CASE WHEN rv.status = 'active' THEN 1 ELSE 0 END) AS active_rule_count
          FROM affiliate_partners p
     LEFT JOIN affiliate_rule_versions rv ON rv.partner_id = p.id
    """
    params = []
    if search:
        query += """
         WHERE p.name LIKE ? COLLATE NOCASE
            OR p.company_name LIKE ? COLLATE NOCASE
            OR p.ref_code LIKE ? COLLATE NOCASE
            OR p.contact_email LIKE ? COLLATE NOCASE
        """
        pattern = f"%{search}%"
        params = [pattern, pattern, pattern, pattern]
    query += " GROUP BY p.id ORDER BY p.is_active DESC, p.name COLLATE NOCASE"

    partners = get_db().execute(query, params).fetchall()
    return render_template(
        "admin/affiliates/index.html",
        partners=partners,
        search=search,
    )


@bp.route("/new", methods=("GET", "POST"))
@login_required
def create():
    """Create an active affiliate partner with a generated referral code."""
    form_data = {field: "" for field in _PARTNER_FIELDS}
    form_data["billing_country"] = "hu"
    errors = {}

    if request.method == "POST":
        form_data = _partner_form_data()
        errors = _partner_form_errors(form_data)
        if not errors:
            try:
                partner_id, ref_code = _insert_partner(get_db(), form_data)
            except RuntimeError:
                errors["form"] = "A partner most nem menthető. Próbáld újra."
            else:
                flash(f"Partner létrehozva. Ref-kód: {ref_code}", "success")
                return redirect(url_for("admin_affiliates.detail", partner_id=partner_id))

    status = 400 if errors else 200
    return render_template(
        "admin/affiliates/create.html",
        form_data=form_data,
        errors=errors,
        partner=None,
    ), status


@bp.route("/<int:partner_id>/edit", methods=("GET", "POST"))
@login_required
def edit(partner_id):
    """Edit partner metadata without changing its stable referral code."""
    db = get_db()
    partner = db.execute(
        "SELECT * FROM affiliate_partners WHERE id = ?",
        (partner_id,),
    ).fetchone()
    if partner is None:
        abort(404)

    form_data = {
        field: (partner[field] if partner[field] is not None else "")
        for field in _PARTNER_FIELDS
    }
    errors = {}
    if request.method == "POST":
        form_data = _partner_form_data()
        errors = _partner_form_errors(form_data)
        if not errors:
            assignments = ", ".join(f"{field} = ?" for field in _PARTNER_FIELDS)
            values = [form_data[field] or None for field in _PARTNER_FIELDS]
            values[_PARTNER_FIELDS.index("billing_country")] = form_data["billing_country"]
            db.execute(
                f"UPDATE affiliate_partners SET {assignments}, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                [*values, partner_id],
            )
            db.commit()
            flash("A partner adatai frissültek.", "success")
            return redirect(url_for("admin_affiliates.detail", partner_id=partner_id))

    status = 400 if errors else 200
    return render_template(
        "admin/affiliates/create.html",
        form_data=form_data,
        errors=errors,
        partner=partner,
    ), status


@bp.post("/<int:partner_id>/status")
@login_required
def update_status(partner_id):
    """Idempotently activate or deactivate a partner."""
    desired = request.form.get("is_active")
    if desired not in {"0", "1"}:
        abort(400)

    db = get_db()
    cursor = db.execute(
        """
        UPDATE affiliate_partners
           SET is_active = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (int(desired), partner_id),
    )
    if cursor.rowcount == 0:
        db.rollback()
        abort(404)
    db.commit()
    state = "aktiválva" if desired == "1" else "inaktiválva"
    flash(f"A partner {state}.", "success")
    return redirect(url_for("admin_affiliates.detail", partner_id=partner_id))


@bp.get("/<int:partner_id>")
@login_required
def detail(partner_id):
    """Show one partner and its immutable rule-version history."""
    db = get_db()
    partner = db.execute(
        "SELECT * FROM affiliate_partners WHERE id = ?",
        (partner_id,),
    ).fetchone()
    if partner is None:
        abort(404)

    rules = db.execute(
        """
        SELECT id, version_number, status, discount_type, discount_value,
               commission_type, commission_value, valid_from, valid_until,
               created_at
          FROM affiliate_rule_versions
         WHERE partner_id = ?
         ORDER BY version_number DESC
        """,
        (partner_id,),
    ).fetchall()
    return render_template(
        "admin/affiliates/detail.html",
        partner=partner,
        rules=rules,
    )
