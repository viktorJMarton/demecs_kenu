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
