"""Affiliate partner administration views."""

from flask import Blueprint, abort, render_template, request

from ..auth import login_required
from ..db import get_db


bp = Blueprint("admin_affiliates", __name__, url_prefix="/admin/affiliates")


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
