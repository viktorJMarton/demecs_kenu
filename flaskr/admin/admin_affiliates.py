"""Affiliate partner administration views."""

import re
import secrets
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import urlencode

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
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_UTM_FIELDS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
)
_RULE_DEFAULTS = {
    "status": "draft",
    "discount_type": "percentage",
    "discount_value": "",
    "discount_participant_count": "",
    "max_discount_amount": "",
    "commission_type": "none",
    "commission_value": "",
    "total_usage_limit": "",
    "guest_usage_limit": "",
    "usage_unit": "booking",
    "budget_period_type": "lifetime",
    "valid_from": "",
    "valid_until": "",
    "attribution_window_days": "30",
    "session_only": False,
}


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


def _utm_form_data(source: Mapping[str, str]) -> dict[str, str]:
    """Return only bounded, printable UTM values accepted by attribution."""
    return {
        field: _CONTROL_PATTERN.sub("", source.get(field, "")).strip()[:200]
        for field in _UTM_FIELDS
    }


def build_referral_url(base_url: str, ref_code: str, utm_data: Mapping[str, str]) -> str:
    """Build a reversible URL from the fixed public base, ref code and UTM fields."""
    query = [("ref", ref_code)]
    query.extend((field, utm_data.get(field, "")) for field in _UTM_FIELDS if utm_data.get(field))
    return f"{base_url}?{urlencode(query)}"


def _rule_form_data(source: Mapping[str, str]) -> dict[str, str | bool]:
    """Keep only fields relevant to the selected rule modes."""
    data: dict[str, str | bool] = {
        key: source.get(key, default).strip() if isinstance(default, str) else default
        for key, default in _RULE_DEFAULTS.items()
    }
    data["session_only"] = source.get("session_only") == "1"

    discount_type = data["discount_type"]
    if discount_type not in {"percentage", "fixed"}:
        data["discount_value"] = ""
    if discount_type != "free_participants":
        data["discount_participant_count"] = ""
    if discount_type != "percentage":
        data["max_discount_amount"] = ""

    if data["commission_type"] not in {"percentage", "fixed"}:
        data["commission_value"] = ""

    has_limit = bool(data["total_usage_limit"] or data["guest_usage_limit"])
    if not has_limit:
        data["usage_unit"] = "booking"
        data["budget_period_type"] = "lifetime"

    if data["session_only"]:
        data["attribution_window_days"] = "0"
    return data


def _scope_form_data(source) -> dict[str, str | list[int]]:
    """Normalize one scope mode and its relevant selected identifiers."""
    mode = source.get("scope_mode", "all")
    if mode not in {"all", "tour", "location"}:
        mode = "all"

    def selected_ids(field: str) -> list[int]:
        values = source.getlist(field) if hasattr(source, "getlist") else source.get(field, [])
        if isinstance(values, str):
            values = [values]
        result = []
        for value in values:
            try:
                item_id = int(value)
            except (TypeError, ValueError):
                continue
            if item_id > 0 and item_id not in result:
                result.append(item_id)
        return result

    return {
        "scope_mode": mode,
        "tour_ids": selected_ids("tour_ids") if mode == "tour" else [],
        "location_ids": selected_ids("location_ids") if mode == "location" else [],
    }


def replace_rule_scopes(db, rule_version_id: int, scope_data) -> None:
    """Replace a draft rule's scopes without committing the caller's transaction."""
    db.execute(
        "DELETE FROM affiliate_rule_scopes WHERE rule_version_id = ?",
        (rule_version_id,),
    )
    mode = scope_data["scope_mode"]
    if mode == "all":
        db.execute(
            "INSERT INTO affiliate_rule_scopes (rule_version_id, scope_type) VALUES (?, 'all')",
            (rule_version_id,),
        )
        return

    id_field = "tour_ids" if mode == "tour" else "location_ids"
    column = "tour_id" if mode == "tour" else "tour_location_id"
    db.executemany(
        f"INSERT INTO affiliate_rule_scopes (rule_version_id, scope_type, {column}) "
        "VALUES (?, ?, ?)",
        [(rule_version_id, mode, item_id) for item_id in scope_data[id_field]],
    )


def load_rule_scope(db, rule_version_id: int) -> dict[str, str | list[int]]:
    """Return persisted scopes in the same shape accepted by the admin form."""
    rows = db.execute(
        """
        SELECT scope_type, tour_id, tour_location_id
          FROM affiliate_rule_scopes
         WHERE rule_version_id = ?
         ORDER BY id
        """,
        (rule_version_id,),
    ).fetchall()
    if not rows or rows[0]["scope_type"] == "all":
        return {"scope_mode": "all", "tour_ids": [], "location_ids": []}
    mode = rows[0]["scope_type"]
    return {
        "scope_mode": mode,
        "tour_ids": [row["tour_id"] for row in rows if row["scope_type"] == "tour"],
        "location_ids": [
            row["tour_location_id"] for row in rows if row["scope_type"] == "location"
        ],
    }


def _optional_int(value: str):
    return None if value == "" else int(value)


def _rule_form_errors(db, form_data, scope_data) -> dict[str, str]:
    """Validate every server-authoritative rule and scope input."""
    errors = {}
    allowed = {
        "status": {"draft", "active"},
        "discount_type": {"percentage", "fixed", "free_participants", "tracking"},
        "commission_type": {"none", "percentage", "fixed"},
        "usage_unit": {"booking", "participant"},
        "budget_period_type": {"lifetime", "monthly", "yearly", "manual"},
    }
    for field, values in allowed.items():
        if form_data[field] not in values:
            errors[field] = "Érvénytelen választás."

    def integer(field, *, minimum=0, maximum=None, required=False):
        raw = form_data[field]
        if raw == "":
            if required:
                errors[field] = "Ez az érték kötelező."
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors[field] = "Egész szám szükséges."
            return None
        if value < minimum or (maximum is not None and value > maximum):
            errors[field] = "Az érték kívül esik a megengedett tartományon."
        return value

    discount_type = form_data["discount_type"]
    if discount_type in {"percentage", "fixed"}:
        integer(
            "discount_value",
            minimum=1,
            maximum=100 if discount_type == "percentage" else None,
            required=True,
        )
    if discount_type == "free_participants":
        integer("discount_participant_count", minimum=1, required=True)
    integer("max_discount_amount", minimum=0)

    commission_type = form_data["commission_type"]
    if commission_type in {"percentage", "fixed"}:
        integer(
            "commission_value",
            minimum=1,
            maximum=100 if commission_type == "percentage" else None,
            required=True,
        )

    total_limit = integer("total_usage_limit", minimum=0)
    guest_limit = integer("guest_usage_limit", minimum=0)
    if total_limit is not None and guest_limit is not None and guest_limit > total_limit:
        errors["guest_usage_limit"] = "A vendéglimit nem lehet nagyobb a teljes limitnél."
    integer("attribution_window_days", minimum=0, maximum=3650, required=True)

    parsed_dates = {}
    for field in ("valid_from", "valid_until"):
        raw = form_data[field]
        if not raw:
            parsed_dates[field] = None
            continue
        try:
            parsed_dates[field] = datetime.fromisoformat(raw)
        except ValueError:
            errors[field] = "Érvénytelen dátum és idő."
    if (
        parsed_dates.get("valid_from")
        and parsed_dates.get("valid_until")
        and parsed_dates["valid_until"] <= parsed_dates["valid_from"]
    ):
        errors["valid_until"] = "A záró időpontnak későbbinek kell lennie."

    mode = scope_data["scope_mode"]
    selected_field = "tour_ids" if mode == "tour" else "location_ids"
    selected_ids = scope_data[selected_field] if mode in {"tour", "location"} else []
    if mode in {"tour", "location"} and not selected_ids:
        errors["scope"] = "Válassz legalább egy elemet a hatókörhöz."
    if selected_ids:
        table = "tours" if mode == "tour" else "tour_locations"
        placeholders = ", ".join("?" for _ in selected_ids)
        existing = {
            row[0]
            for row in db.execute(
                f"SELECT id FROM {table} WHERE id IN ({placeholders})", selected_ids
            ).fetchall()
        }
        if existing != set(selected_ids):
            errors["scope"] = "A kiválasztott hatókör érvénytelen elemet tartalmaz."
    return errors


def save_rule_version(db, partner_id: int, form_data, scope_data) -> tuple[int, int]:
    """Append a rule version and atomically maintain one active version."""
    try:
        db.execute("BEGIN IMMEDIATE")
        version_number = db.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) + 1
              FROM affiliate_rule_versions
             WHERE partner_id = ?
            """,
            (partner_id,),
        ).fetchone()[0]
        if form_data["status"] == "active":
            db.execute(
                """
                UPDATE affiliate_rule_versions
                   SET status = 'archived', updated_at = CURRENT_TIMESTAMP
                 WHERE partner_id = ? AND status = 'active'
                """,
                (partner_id,),
            )

        cursor = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status,
                discount_type, discount_value, discount_participant_count,
                max_discount_amount, commission_type, commission_value,
                attribution_window_days, session_only, valid_from, valid_until,
                total_usage_limit, guest_usage_limit, usage_unit, budget_period_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                partner_id,
                version_number,
                form_data["status"],
                form_data["discount_type"],
                int(form_data["discount_value"] or 0),
                _optional_int(form_data["discount_participant_count"]),
                _optional_int(form_data["max_discount_amount"]),
                form_data["commission_type"],
                int(form_data["commission_value"] or 0),
                int(form_data["attribution_window_days"] or 0),
                int(form_data["session_only"]),
                form_data["valid_from"] or None,
                form_data["valid_until"] or None,
                _optional_int(form_data["total_usage_limit"]),
                _optional_int(form_data["guest_usage_limit"]),
                form_data["usage_unit"],
                form_data["budget_period_type"],
            ),
        )
        replace_rule_scopes(db, cursor.lastrowid, scope_data)
        db.commit()
        return cursor.lastrowid, version_number
    except Exception:
        db.rollback()
        raise


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


@bp.route("/<int:partner_id>/rules/new", methods=("GET", "POST"))
@login_required
def rule_form(partner_id):
    """Render and normalize the dynamic rule fields before versioned saving."""
    partner = get_db().execute(
        "SELECT * FROM affiliate_partners WHERE id = ?",
        (partner_id,),
    ).fetchone()
    if partner is None:
        abort(404)

    db = get_db()
    form_data = dict(_RULE_DEFAULTS)
    scope_data = {"scope_mode": "all", "tour_ids": [], "location_ids": []}
    errors = {}
    if request.method == "POST":
        form_data = _rule_form_data(request.form)
        scope_data = _scope_form_data(request.form)
        errors = _rule_form_errors(db, form_data, scope_data)
        if not errors:
            try:
                _, version_number = save_rule_version(db, partner_id, form_data, scope_data)
            except (ValueError, sqlite3.IntegrityError):
                errors["form"] = "A szabály adatai nem menthetők. Ellenőrizd a megadott értékeket."
            else:
                flash(f"A v{version_number} szabályverzió létrejött.", "success")
                return redirect(url_for("admin_affiliates.detail", partner_id=partner_id))

    tours = db.execute(
        "SELECT id, title, date FROM tours ORDER BY date DESC, title COLLATE NOCASE"
    ).fetchall()
    locations = db.execute(
        "SELECT id, name FROM tour_locations ORDER BY name COLLATE NOCASE"
    ).fetchall()

    status = 400 if errors else 200
    return render_template(
        "admin/affiliates/rule_form.html",
        partner=partner,
        form_data=form_data,
        scope_data=scope_data,
        tours=tours,
        locations=locations,
        errors=errors,
    ), status


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
    utm_data = _utm_form_data(request.args)
    return render_template(
        "admin/affiliates/detail.html",
        partner=partner,
        rules=rules,
        utm_data=utm_data,
        referral_url=build_referral_url(
            url_for("index", _external=True), partner["ref_code"], utm_data
        ),
    )
