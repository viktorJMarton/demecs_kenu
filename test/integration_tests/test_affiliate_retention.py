from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from flaskr.affiliate_reporting import (
    get_affiliate_click_breakdown,
    get_affiliate_partner_summaries,
    get_affiliate_report_metrics,
    get_affiliate_source_options,
)
from flaskr.affiliate_retention import (
    _SKETCH_BYTES,
    _merge_sketches,
    _sketch_estimate,
    aggregate_expired_affiliate_clicks,
)
from flaskr.db import get_db


_BUDAPEST = ZoneInfo("Europe/Budapest")


def _seed_click(db, *, key, partner_id, rule_id, visitor, clicked_at, source,
                medium, campaign, landing, is_bot=0, is_duplicate=0):
    db.execute(
        """
        INSERT INTO affiliate_click_events (
            event_key, partner_id, rule_version_id, visitor_id, clicked_at,
            utm_source, utm_medium, utm_campaign, landing_page,
            is_bot, is_duplicate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key, partner_id, rule_id, visitor, clicked_at, source, medium,
            campaign, landing, is_bot, is_duplicate,
        ),
    )


@pytest.fixture
def retention_data(app):
    with app.app_context():
        db = get_db()
        suffix = uuid4().hex
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            (f"RET-{suffix}", "Retention Partner"),
        ).lastrowid
        rule_id = db.execute(
            """INSERT INTO affiliate_rule_versions (
                   partner_id, version_number, status, discount_type, commission_type
               ) VALUES (?, 1, 'active', 'tracking', 'none')""",
            (partner_id,),
        ).lastrowid
        rows = (
            ("sep-valid", "v1", "2024-09-10 10:00:00", "google", "cpc", "autumn", "/a", 0, 0),
            ("sep-duplicate", "v1", "2024-09-10 10:01:00", "google", "cpc", "autumn", "/a", 0, 1),
            ("sep-bot", "bot", "2024-09-11 10:00:00", "newsletter", "email", "autumn", "/b", 1, 0),
            ("oct-google", "v2", "2024-10-05 10:00:00", "google", "organic", "october", "/c", 0, 0),
            ("oct-news", "v3", "2024-10-06 10:00:00", "newsletter", "email", "october", "/b", 0, 0),
            ("nov-expired", "v5", "2024-11-15 11:59:59.999999", "google", "social", "november", "/d", 0, 0),
            ("nov-retained", "v5", "2024-11-15 12:00:00.000000", "google", "social", "november", "/d", 0, 0),
        )
        for label, visitor, clicked_at, source, medium, campaign, landing, bot, duplicate in rows:
            _seed_click(
                db,
                key=f"{label}-{suffix}",
                partner_id=partner_id,
                rule_id=rule_id,
                visitor=visitor,
                clicked_at=clicked_at,
                source=source,
                medium=medium,
                campaign=campaign,
                landing=landing,
                is_bot=bot,
                is_duplicate=duplicate,
            )
        db.commit()
        try:
            yield db, partner_id, rule_id, suffix
        finally:
            db.execute(
                "DELETE FROM affiliate_click_events WHERE partner_id = ?",
                (partner_id,),
            )
            db.execute(
                "DELETE FROM affiliate_click_monthly_aggregates WHERE partner_id = ?",
                (partner_id,),
            )
            db.execute(
                "DELETE FROM affiliate_rule_versions WHERE partner_id = ?",
                (partner_id,),
            )
            db.execute("DELETE FROM affiliate_partners WHERE id = ?", (partner_id,))
            db.commit()


def _report_snapshot(db, partner_id):
    filters = {
        "partner_id": partner_id,
        "start_at": datetime(2024, 9, 1, tzinfo=_BUDAPEST),
        "end_at": datetime(2024, 12, 1, tzinfo=_BUDAPEST),
    }
    metrics = get_affiliate_report_metrics(db, **filters)
    google = get_affiliate_report_metrics(db, source="google", **filters)
    summary = get_affiliate_partner_summaries(
        db, limit=25, offset=0, **filters
    )[0]
    breakdowns = {
        dimension: [row.__dict__ for row in get_affiliate_click_breakdown(
            db, dimension=dimension, limit=10, **filters
        )]
        for dimension in ("source", "medium", "campaign", "landing")
    }
    return metrics, google, summary, breakdowns


def test_bounded_monthly_aggregation_is_idempotent_and_preserves_reports(
    retention_data,
):
    db, partner_id, _, _ = retention_data
    before = _report_snapshot(db, partner_id)
    report_window = {
        "start_at": datetime(2024, 9, 1, tzinfo=_BUDAPEST),
        "end_at": datetime(2024, 12, 1, tzinfo=_BUDAPEST),
    }
    before_global = get_affiliate_report_metrics(db, **report_window)
    booking_count = db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)

    first = aggregate_expired_affiliate_clicks(db, now=now, batch_size=3)
    second = aggregate_expired_affiliate_clicks(db, now=now, batch_size=3)
    aggregate_rows = db.execute(
        """SELECT * FROM affiliate_click_monthly_aggregates
            WHERE partner_id = ? ORDER BY month_start, aggregate_level, id""",
        (partner_id,),
    ).fetchall()
    third = aggregate_expired_affiliate_clicks(db, now=now, batch_size=3)
    after = _report_snapshot(db, partner_id)
    after_global = get_affiliate_report_metrics(db, **report_window)

    assert first.aggregated_months == ("2024-09-01",)
    assert first.deleted_detail_rows == 3
    assert first.has_more is True
    assert second.aggregated_months == ("2024-10-01", "2024-11-01")
    assert second.deleted_detail_rows == 3
    assert second.has_more is False
    assert third.aggregated_months == ()
    assert third.deleted_detail_rows == 0
    assert third.has_more is False
    assert before == after
    assert before_global == after_global
    with pytest.raises(ValueError, match="complete Budapest months"):
        get_affiliate_report_metrics(
            db,
            partner_id=partner_id,
            start_at=datetime(2024, 9, 15, tzinfo=_BUDAPEST),
            end_at=datetime(2024, 9, 16, tzinfo=_BUDAPEST),
        )
    assert db.execute(
        "SELECT COUNT(*) FROM affiliate_click_events WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()[0] == 1
    assert db.execute(
        """SELECT clicked_at FROM affiliate_click_events
            WHERE partner_id = ?""",
        (partner_id,),
    ).fetchone()["clicked_at"] == datetime(2024, 11, 15, 12, 0)
    assert db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == booking_count
    assert {row["aggregate_level"] for row in aggregate_rows} == {
        "overall", "source", "detail"
    }
    assert db.execute(
        """SELECT COUNT(*) FROM affiliate_click_monthly_aggregates
            WHERE partner_id = 0 AND aggregate_level = 'global'"""
    ).fetchone()[0] > 0
    assert all("visitor" not in row.keys() and "referrer" not in row.keys()
               for row in aggregate_rows)
    assert "google" in get_affiliate_source_options(db)
    assert "newsletter" in get_affiliate_source_options(db)


def test_late_expired_rows_are_added_once_to_existing_month(retention_data):
    db, partner_id, rule_id, suffix = retention_data
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    aggregate_expired_affiliate_clicks(db, now=now, batch_size=20)
    before = get_affiliate_report_metrics(db, partner_id=partner_id)
    _seed_click(
        db,
        key=f"late-{suffix}",
        partner_id=partner_id,
        rule_id=rule_id,
        visitor="v1",
        clicked_at="2024-09-20 12:00:00",
        source="google",
        medium="cpc",
        campaign="late",
        landing="/late",
    )
    db.commit()

    added = aggregate_expired_affiliate_clicks(db, now=now, batch_size=1)
    rerun = aggregate_expired_affiliate_clicks(db, now=now, batch_size=1)
    after = get_affiliate_report_metrics(db, partner_id=partner_id)

    assert added.aggregated_months == ("2024-09-01",)
    assert added.deleted_detail_rows == 1
    assert rerun.aggregated_months == ()
    assert after.total_clicks == before.total_clicks + 1
    assert after.valid_clicks == before.valid_clicks + 1
    assert after.estimated_unique_visitors == before.estimated_unique_visitors


@pytest.mark.parametrize("batch_size", [0, 501, True, 1.5])
def test_retention_rejects_unbounded_batches(retention_data, batch_size):
    db, _, _, _ = retention_data
    with pytest.raises(ValueError, match="between 1 and 500"):
        aggregate_expired_affiliate_clicks(db, batch_size=batch_size)


def test_retention_requires_timezone_aware_clock(retention_data):
    db, _, _, _ = retention_data
    with pytest.raises(ValueError, match="timezone-aware"):
        aggregate_expired_affiliate_clicks(
            db, now=datetime(2026, 11, 15), batch_size=1
        )


def test_retention_cli_is_registered_and_reports_counts(app):
    result = app.test_cli_runner().invoke(
        args=["aggregate-affiliate-clicks", "--batch-size", "1"]
    )

    assert result.exit_code == 0
    assert "months=" in result.output
    assert "deleted=" in result.output
    assert "has_more=" in result.output


def test_bitmap_estimator_is_monotonic_at_saturation_and_or_merge():
    empty = bytes(_SKETCH_BYTES)
    one_empty_bit = bytes([0b11111110]) + bytes([0xFF]) * (_SKETCH_BYTES - 1)
    full = bytes([0xFF]) * _SKETCH_BYTES
    incoming_last_bit = bytearray(_SKETCH_BYTES)
    incoming_last_bit[0] = 0b00000001

    empty_estimate = _sketch_estimate(empty)
    one_empty_estimate = _sketch_estimate(one_empty_bit)
    full_estimate = _sketch_estimate(full)
    merged = _merge_sketches(one_empty_bit, incoming_last_bit)

    assert empty_estimate == 0
    assert one_empty_estimate > 0
    assert merged == full
    assert _sketch_estimate(merged) == full_estimate
    assert full_estimate >= one_empty_estimate
