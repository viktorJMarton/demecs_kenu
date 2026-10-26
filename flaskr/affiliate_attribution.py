"""Public referral-query entry point for affiliate attribution."""

import re

from flask import g, request

from .db import get_db


_REF_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")


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
            }


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
