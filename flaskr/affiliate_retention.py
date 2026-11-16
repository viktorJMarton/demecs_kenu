"""Bounded, privacy-preserving retention for affiliate click details."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import logging
import math
from zoneinfo import ZoneInfo


MAX_RETENTION_BATCH_SIZE = 500
_BUDAPEST = ZoneInfo("Europe/Budapest")
_SKETCH_BITS = 4096
_SKETCH_BYTES = _SKETCH_BITS // 8
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AffiliateClickAggregationResult:
    aggregated_months: tuple[str, ...]
    deleted_detail_rows: int
    has_more: bool
    detail_cutoff: str


@contextmanager
def _atomic_write(db):
    nested = db.in_transaction
    savepoint = "affiliate_click_retention"
    if nested:
        db.execute(f"SAVEPOINT {savepoint}")
    else:
        db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        if nested:
            db.execute(f"ROLLBACK TO {savepoint}")
            db.execute(f"RELEASE {savepoint}")
        else:
            db.rollback()
        raise
    else:
        if nested:
            db.execute(f"RELEASE {savepoint}")
        else:
            db.commit()


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        value = datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _retention_cutoff(now: datetime | None) -> str:
    current = _as_utc(now)
    try:
        cutoff = current.replace(year=current.year - 2)
    except ValueError:
        cutoff = current.replace(year=current.year - 2, day=28)
    return cutoff.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


def _stored_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise ValueError("stored click timestamp is invalid")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _month_bucket(value: object) -> tuple[str, str, str]:
    local = _stored_utc(value).astimezone(_BUDAPEST)
    start = datetime(local.year, local.month, 1, tzinfo=_BUDAPEST)
    if local.month == 12:
        end = datetime(local.year + 1, 1, 1, tzinfo=_BUDAPEST)
    else:
        end = datetime(local.year, local.month + 1, 1, tzinfo=_BUDAPEST)
    return (
        start.date().isoformat(),
        start.astimezone(timezone.utc).replace(tzinfo=None).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        ),
        end.astimezone(timezone.utc).replace(tzinfo=None).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        ),
    )


def _dimension(value: object) -> str:
    return "" if value is None else str(value).strip()


def _empty_sketch() -> bytearray:
    return bytearray(_SKETCH_BYTES)


def _add_to_sketch(
    sketch: bytearray,
    *,
    partner_id: int,
    month_start: str,
    scope: str,
    visitor_id: str,
) -> None:
    digest = hashlib.sha256(
        f"{partner_id}|{month_start}|{scope}|{visitor_id}".encode("utf-8")
    ).digest()
    bit = int.from_bytes(digest[:8], "big") % _SKETCH_BITS
    sketch[bit // 8] |= 1 << (bit % 8)


def _merge_sketches(existing: bytes, incoming: bytearray) -> bytes:
    if len(existing) not in (0, _SKETCH_BYTES):
        raise RuntimeError("affiliate monthly visitor sketch is incompatible")
    base = bytearray(existing) if existing else _empty_sketch()
    return bytes(left | right for left, right in zip(base, incoming, strict=True))


def _sketch_estimate(sketch: bytes) -> int:
    set_bits = sum(byte.bit_count() for byte in sketch)
    if set_bits == 0:
        return 0
    empty = _SKETCH_BITS - set_bits
    if empty == 0:
        # Linear counting cannot distinguish cardinalities after saturation.
        # Freeze at a monotonic cap just above the last measurable state so an
        # added/merged visitor can never lower the reported estimate.
        last_measurable = -_SKETCH_BITS * math.log(1 / _SKETCH_BITS)
        return int(round(last_measurable)) + 1
    return int(round(-_SKETCH_BITS * math.log(empty / _SKETCH_BITS)))


def merge_monthly_visitor_estimate(
    existing_sketch: bytes,
    *,
    partner_scope: int,
    month_start: str,
    scope: str,
    visitor_ids,
) -> int:
    """Merge live visitor IDs into one anonymous archived sketch and estimate."""

    incoming = _empty_sketch()
    for visitor_id in visitor_ids:
        _add_to_sketch(
            incoming,
            partner_id=partner_scope,
            month_start=month_start,
            scope=scope,
            visitor_id=str(visitor_id),
        )
    return _sketch_estimate(_merge_sketches(existing_sketch, incoming))


def _normalized_timestamp(column: str) -> str:
    return (
        f"CASE WHEN instr({column}, '.') = 0 THEN {column} || '.000000' "
        f"ELSE {column} || substr('000000', 1, "
        f"6 - (length({column}) - instr({column}, '.'))) END"
    )


def _candidate_rows(db, cutoff: str, batch_size: int):
    normalized = _normalized_timestamp("clicked_at")
    return db.execute(
        f"""
        SELECT id, partner_id, visitor_id, clicked_at, is_bot, is_duplicate,
               utm_source, utm_medium, utm_campaign, landing_page
          FROM affiliate_click_events
         WHERE clicked_at GLOB '????-??-?? ??:??:??*'
           AND ({normalized}) < ?
         ORDER BY ({normalized}), id
         LIMIT ?
        """,
        (cutoff, batch_size),
    ).fetchall()


def _has_candidates(db, cutoff: str) -> bool:
    normalized = _normalized_timestamp("clicked_at")
    return bool(
        db.execute(
            f"""
            SELECT EXISTS(
                SELECT 1 FROM affiliate_click_events
                 WHERE clicked_at GLOB '????-??-?? ??:??:??*'
                   AND ({normalized}) < ?
            )
            """,
            (cutoff,),
        ).fetchone()[0]
    )


def _new_rollup(
    month_start: str,
    bucket_start: str,
    bucket_end: str,
    partner_id: int,
    level: str,
    source: str = "",
    medium: str = "",
    campaign: str = "",
    landing: str = "",
) -> dict[str, object]:
    return {
        "month_start": month_start,
        "bucket_start": bucket_start,
        "bucket_end": bucket_end,
        "partner_id": partner_id,
        "level": level,
        "source": source,
        "medium": medium,
        "campaign": campaign,
        "landing": landing,
        "total": 0,
        "bot": 0,
        "duplicate": 0,
        "valid": 0,
        "sketch": _empty_sketch(),
    }


def _rollup_key(rollup: dict[str, object]) -> tuple[object, ...]:
    return (
        rollup["month_start"], rollup["partner_id"], rollup["level"],
        rollup["source"], rollup["medium"], rollup["campaign"],
        rollup["landing"],
    )


def _upsert_rollup(db, rollup: dict[str, object]) -> None:
    key = _rollup_key(rollup)
    existing = db.execute(
        """SELECT total_clicks, bot_clicks, duplicate_clicks, valid_clicks,
                  visitor_sketch
             FROM affiliate_click_monthly_aggregates
            WHERE month_start = ? AND partner_id = ? AND aggregate_level = ?
              AND utm_source = ? AND utm_medium = ? AND utm_campaign = ?
              AND landing_page = ?""",
        key,
    ).fetchone()
    if rollup["level"] == "detail":
        merged_sketch = b""
    else:
        existing_sketch = b"" if existing is None else bytes(existing["visitor_sketch"])
        merged_sketch = _merge_sketches(existing_sketch, rollup["sketch"])
    totals = (
        int(rollup["total"]) + (0 if existing is None else int(existing["total_clicks"])),
        int(rollup["bot"]) + (0 if existing is None else int(existing["bot_clicks"])),
        int(rollup["duplicate"]) + (
            0 if existing is None else int(existing["duplicate_clicks"])
        ),
        int(rollup["valid"]) + (0 if existing is None else int(existing["valid_clicks"])),
    )
    db.execute(
        """
        INSERT INTO affiliate_click_monthly_aggregates (
            month_start, bucket_start_at, bucket_end_at, partner_id,
            aggregate_level, utm_source, utm_medium, utm_campaign, landing_page,
            total_clicks, bot_clicks, duplicate_clicks, valid_clicks,
            estimated_unique_visitors, visitor_sketch
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (
            month_start, partner_id, aggregate_level,
            utm_source, utm_medium, utm_campaign, landing_page
        ) DO UPDATE SET
            total_clicks = excluded.total_clicks,
            bot_clicks = excluded.bot_clicks,
            duplicate_clicks = excluded.duplicate_clicks,
            valid_clicks = excluded.valid_clicks,
            estimated_unique_visitors = excluded.estimated_unique_visitors,
            visitor_sketch = excluded.visitor_sketch,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            rollup["month_start"], rollup["bucket_start"], rollup["bucket_end"],
            rollup["partner_id"], rollup["level"], rollup["source"],
            rollup["medium"], rollup["campaign"], rollup["landing"],
            *totals,
            0 if rollup["level"] == "detail" else _sketch_estimate(merged_sketch),
            merged_sketch,
        ),
    )


def aggregate_expired_affiliate_clicks(
    db,
    *,
    now: datetime | None = None,
    batch_size: int = 250,
) -> AffiliateClickAggregationResult:
    """Replace one row-bounded batch older than exactly 24 months with rollups."""

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= MAX_RETENTION_BATCH_SIZE
    ):
        raise ValueError(
            f"batch_size must be an integer between 1 and {MAX_RETENTION_BATCH_SIZE}"
        )
    cutoff = _retention_cutoff(now)
    months: set[str] = set()
    deleted_rows = 0

    with _atomic_write(db):
        rows = _candidate_rows(db, cutoff, batch_size)
        rollups: dict[tuple[object, ...], dict[str, object]] = {}
        for row in rows:
            month_start, bucket_start, bucket_end = _month_bucket(row["clicked_at"])
            months.add(month_start)
            source = _dimension(row["utm_source"])
            dimensions = (
                (0, "global", "", "", "", ""),
                (0, "global", source, "", "", ""),
                (int(row["partner_id"]), "overall", "", "", "", ""),
                (int(row["partner_id"]), "source", source, "", "", ""),
                (
                    int(row["partner_id"]), "detail", source,
                    _dimension(row["utm_medium"]),
                    _dimension(row["utm_campaign"]),
                    _dimension(row["landing_page"]),
                ),
            )
            for rollup_partner, level, item_source, medium, campaign, landing in dimensions:
                candidate = _new_rollup(
                    month_start, bucket_start, bucket_end, rollup_partner,
                    level, item_source, medium, campaign, landing,
                )
                key = _rollup_key(candidate)
                rollup = rollups.setdefault(key, candidate)
                rollup["total"] = int(rollup["total"]) + 1
                if row["is_bot"]:
                    rollup["bot"] = int(rollup["bot"]) + 1
                elif row["is_duplicate"]:
                    rollup["duplicate"] = int(rollup["duplicate"]) + 1
                else:
                    rollup["valid"] = int(rollup["valid"]) + 1
                if not row["is_bot"] and level in {"global", "overall", "source"}:
                    if level == "global":
                        scope = "global" if not item_source else f"global-source:{item_source}"
                    else:
                        scope = level if level == "overall" else f"source:{item_source}"
                    _add_to_sketch(
                        rollup["sketch"], partner_id=rollup_partner,
                        month_start=month_start, scope=scope,
                        visitor_id=str(row["visitor_id"]),
                    )
        for rollup in rollups.values():
            _upsert_rollup(db, rollup)
        if rows:
            placeholders = ", ".join("?" for _ in rows)
            deleted = db.execute(
                f"DELETE FROM affiliate_click_events WHERE id IN ({placeholders})",
                tuple(row["id"] for row in rows),
            )
            deleted_rows = int(deleted.rowcount)
            if deleted_rows != len(rows):
                raise RuntimeError("affiliate click retention delete count mismatch")
        has_more = _has_candidates(db, cutoff)

    result = AffiliateClickAggregationResult(
        aggregated_months=tuple(sorted(months)),
        deleted_detail_rows=deleted_rows,
        has_more=has_more,
        detail_cutoff=cutoff,
    )
    logger.info(
        "affiliate click retention aggregated_months=%d deleted_detail_rows=%d "
        "has_more=%s detail_cutoff=%s",
        len(result.aggregated_months), result.deleted_detail_rows,
        result.has_more, result.detail_cutoff,
    )
    return result
