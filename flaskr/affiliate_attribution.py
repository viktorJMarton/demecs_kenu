"""Public referral-query entry point for affiliate attribution."""

import re
import secrets

from flask import current_app, g, request

from .db import get_db


_REF_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
_VISITOR_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
VISITOR_COOKIE_NAME = "affiliate_visitor"


def normalize_ref_code(value: str | None) -> str | None:
    """Return a bounded canonical referral code or ``None`` silently."""
    normalized = (value or "").strip().upper()
    if not _REF_PATTERN.fullmatch(normalized):
        return None
    return normalized


def process_referral_query() -> None:
    """Resolve a global ``ref`` query parameter without persisting state yet."""
    g.affiliate_ref_candidate = None
    g.affiliate_rule_candidate = None
    g.affiliate_visitor_id = None
    g.set_affiliate_visitor_cookie = False
    normalized = normalize_ref_code(request.args.get("ref"))
    if normalized is None:
        return
    partner = get_db().execute(
        "SELECT id, ref_code FROM affiliate_partners WHERE ref_code = ? AND is_active = 1",
        (normalized,),
    ).fetchone()
    if partner is not None:
        g.affiliate_ref_candidate = {
            "partner_id": partner["id"],
            "ref_code": partner["ref_code"],
        }
        rule = get_eligible_rule_for_partner(get_db(), partner["id"])
        if rule is not None:
            g.affiliate_rule_candidate = {
                "partner_id": partner["id"],
                "ref_code": partner["ref_code"],
                "rule_version_id": rule["id"],
                "version_number": rule["version_number"],
                "attribution_window_days": rule["attribution_window_days"],
                "session_only": bool(rule["session_only"]),
            }
            visitor_id = request.cookies.get(VISITOR_COOKIE_NAME, "")
            if not _VISITOR_PATTERN.fullmatch(visitor_id):
                visitor_id = secrets.token_urlsafe(32)
                g.set_affiliate_visitor_cookie = True
            g.affiliate_visitor_id = visitor_id


def set_affiliate_visitor_cookie(response):
    """Attach a secure visitor identifier only after an eligible referral click."""
    if not getattr(g, "set_affiliate_visitor_cookie", False):
        return response
    rule = g.affiliate_rule_candidate
    max_age = None if rule["session_only"] else rule["attribution_window_days"] * 86400
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        g.affiliate_visitor_id,
        max_age=max_age,
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
        httponly=True,
        samesite=current_app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        path="/",
    )
    return response


def get_eligible_rule_for_partner(db, partner_id: int):
    """Select the exact active rule valid at click time with remaining total capacity."""
    return db.execute(
        """
        SELECT rv.*
          FROM affiliate_rule_versions rv
         WHERE rv.partner_id = ?
           AND rv.status = 'active'
           AND (rv.valid_from IS NULL OR rv.valid_from <= CURRENT_TIMESTAMP)
           AND (rv.valid_until IS NULL OR rv.valid_until > CURRENT_TIMESTAMP)
           AND (
                rv.total_usage_limit IS NULL OR
                COALESCE((
                    SELECT SUM(u.quantity)
                      FROM affiliate_usages u
                     WHERE u.rule_version_id = rv.id
                       AND u.status IN ('pending', 'final')
                ), 0) < rv.total_usage_limit
           )
         ORDER BY rv.version_number DESC
         LIMIT 1
        """,
        (partner_id,),
    ).fetchone()
