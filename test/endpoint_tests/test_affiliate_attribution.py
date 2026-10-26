"""Global referral query entry-point coverage."""

from flask import g

from flaskr.affiliate_attribution import normalize_ref_code, process_referral_query
from flaskr.db import get_db


def test_ref_code_normalization_is_bounded_and_canonical():
    assert normalize_ref_code("  aff-code_01 ") == "AFF-CODE_01"
    assert normalize_ref_code("x") is None
    assert normalize_ref_code("bad code") is None
    assert normalize_ref_code("A" * 65) is None


def test_active_ref_is_available_request_locally_without_database_writes(app):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ("AFF-GLOBAL01", "Globális partner"),
        ).lastrowid
        db.commit()

        with app.test_request_context("/?ref=aff-global01"):
            process_referral_query()
            assert g.affiliate_ref_candidate == {
                "partner_id": partner_id,
                "ref_code": "AFF-GLOBAL01",
            }

        assert db.execute("SELECT COUNT(*) FROM affiliate_attributions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM affiliate_click_events").fetchone()[0] == 0


def test_invalid_unknown_and_inactive_refs_are_silent_and_stateless(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO affiliate_partners (ref_code, name, is_active) VALUES (?, ?, 0)",
            ("AFF-INACTIVE1", "Inaktív partner"),
        )
        db.commit()

        for path in ("/?ref=%20bad%20code", "/?ref=AFF-UNKNOWN1", "/?ref=AFF-INACTIVE1"):
            with app.test_request_context(path):
                process_referral_query()
                assert g.affiliate_ref_candidate is None

        assert db.execute("SELECT COUNT(*) FROM affiliate_attributions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM affiliate_click_events").fetchone()[0] == 0
