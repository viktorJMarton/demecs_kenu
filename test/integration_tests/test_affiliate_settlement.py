"""Settlement preview integration tests against the migrated SQLite schema."""

import csv
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
from pathlib import Path

import pytest

from flaskr.affiliate_migration import migrate_affiliate_schema
from flaskr.affiliate_commission_lifecycle import reverse_booking_affiliate
from flaskr.affiliate_settlement import (
    SettlementConflict,
    close_affiliate_settlement,
    mark_affiliate_settlement_paid,
    prepare_affiliate_settlement,
    preview_affiliate_settlement,
    preview_confirmation,
    settlement_confirmation,
    refresh_prepared_affiliate_settlement,
)


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


@pytest.fixture
def settlement_db(tmp_path):
    path = tmp_path / "settlements.sqlite"
    db = connect(path)
    db.executescript(Path("flaskr/schema.sql").read_text(encoding="utf-8"))
    migrate_affiliate_schema(db)
    db.execute("INSERT INTO affiliate_partners (id, ref_code, name) VALUES (1, 'PARTNER1', 'Partner'), (2, 'PARTNER2', 'Other')")
    db.execute(
        "INSERT INTO affiliate_rule_versions (id, partner_id, version_number, discount_type) "
        "VALUES (1, 1, 1, 'fixed'), (2, 2, 1, 'fixed')"
    )

    def booking(ref, paid_at, *, partner=1, status="paid", commission="earned", locked=1, cancelled=None, amount=1000):
        return db.execute(
            """
            INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email, total_price, payment_date,
                payment_status, affiliate_partner_id, affiliate_rule_version_id,
                affiliate_original_price, affiliate_discount_amount, affiliate_payable_price,
                affiliate_commission_type, affiliate_commission_value, affiliate_commission_amount,
                affiliate_commission_status, affiliate_snapshot_locked, cancellation_date
            ) VALUES (1, ?, 'Guest', 'fixture@example.invalid', 8000, ?, ?, ?, ?,
                      10000, 2000, 8000, 'fixed', ?, ?, ?, ?, ?)
            """,
            (ref, paid_at, status, partner, partner, amount, amount, commission, locked, cancelled),
        ).lastrowid

    yield db, booking, path
    db.close()


def test_settlement_preview_uses_locked_unsettled_paid_items_and_budapest_dates(settlement_db):
    db, booking, _ = settlement_db
    # The spring clock-change day is 23 hours long, from 23:00 to 22:00 UTC.
    day = date(2026, 3, 29)
    first = booking("open-boundary", "2026-03-28 23:00:00")
    second = booking("same-second", "2026-03-28 23:00:00", amount=500)
    third = booking("closing-second", "2026-03-29 21:59:59", amount=700)
    booking("too-early", "2026-03-28 22:59:59")
    booking("too-late", "2026-03-29 22:00:00")
    booking("other-partner", "2026-03-29 12:00:00", partner=2)
    booking("refunded", "2026-03-29 12:00:00", status="refunded")
    booking("cancelled", "2026-03-29 12:00:00", cancelled="2026-03-30 12:00:00")
    booking("reversed", "2026-03-29 12:00:00", commission="reversed")
    booking("unlocked", "2026-03-29 12:00:00", locked=0)
    prepared_booking = booking("already-prepared", "2026-03-29 12:00:00")
    header = db.execute(
        """
        INSERT INTO affiliate_settlements (
            settlement_ref, partner_id, period_start, period_end, partner_name_snapshot
        ) VALUES ('PREPARED', 1, '2026-03-29', '2026-03-29', 'Partner')
        """
    ).lastrowid
    db.execute(
        """
        INSERT INTO affiliate_settlement_items (
            settlement_id, booking_id, partner_id, rule_version_id, original_amount,
            discount_amount, paid_amount, commission_amount, commission_type, commission_value
        ) VALUES (?, ?, 1, 1, 10000, 2000, 8000, 1000, 'fixed', 1000)
        """,
        (header, prepared_booking),
    )
    db.commit()

    writes = db.total_changes
    result = preview_affiliate_settlement(db, 1, day, day)
    assert [item.booking_id for item in result.items] == [first, second, third]
    assert [item.commission_amount for item in result.items] == [1000, 500, 700]
    assert (
        result.original_amount_total, result.discount_amount_total,
        result.paid_amount_total, result.commission_amount_total,
    ) == (30000, 6000, 24000, 2200)
    assert preview_affiliate_settlement(db, 1, day, day) == result
    empty = preview_affiliate_settlement(db, 99, day, day)
    assert empty.items == () and empty.commission_amount_total == 0
    assert db.total_changes == writes

    with pytest.raises(ValueError):
        preview_affiliate_settlement(db, True, day, day)
    with pytest.raises(ValueError):
        preview_affiliate_settlement(db, 1, day, date(2026, 3, 28))

def test_settlement_freezes_snapshot_and_records_payment_once(settlement_db):
    db, booking, _ = settlement_db
    day = date(2026, 3, 29)
    kept = booking("kept", "2026-03-29 12:00:00", amount=700)
    refunded = booking("removed", "2026-03-29 13:00:00")
    db.commit()
    previous = preview_affiliate_settlement(db, 1, day, day)
    settlement_id = prepare_affiliate_settlement(db, 1, day, day, admin_identifier="admin", expected=preview_confirmation(previous, 1, day, day))
    with pytest.raises(SettlementConflict):
        mark_affiliate_settlement_paid(db, settlement_id, admin_identifier="admin", note="bank transfer", expected="not a payout token")
    with db:
        db.execute("UPDATE affiliate_partners SET name = 'New name' WHERE id = 1")
        db.execute("INSERT INTO affiliate_rule_versions (partner_id, version_number, discount_type) VALUES (1, 2, 'tracking')")
        db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (refunded,))
        reverse_booking_affiliate(db, refunded, "admin")
    stale = settlement_confirmation(db, settlement_id, "prepared", "close")
    with pytest.raises(SettlementConflict, match="invalidated"):
        close_affiliate_settlement(db, settlement_id, admin_identifier="admin", expected=stale)
    refresh_token = settlement_confirmation(db, settlement_id, "prepared", "refresh")
    refresh_prepared_affiliate_settlement(db, settlement_id, admin_identifier="admin", expected=refresh_token)
    with pytest.raises(SettlementConflict, match="has changed"):
        close_affiliate_settlement(db, settlement_id, admin_identifier="admin", expected=stale)
    expected = settlement_confirmation(db, settlement_id, "prepared", "close")
    close_affiliate_settlement(db, settlement_id, admin_identifier="admin", expected=expected)
    with pytest.raises(SettlementConflict):
        close_affiliate_settlement(db, settlement_id, admin_identifier="admin", expected=expected)
    with pytest.raises(SettlementConflict):
        refresh_prepared_affiliate_settlement(db, settlement_id, admin_identifier="admin", expected=refresh_token)
    assert db.execute("SELECT affiliate_commission_status FROM bookings WHERE id = ?", (kept,)).fetchone()[0] == "earned"
    payout_token = settlement_confirmation(db, settlement_id, "closed", "paid")
    with pytest.raises(SettlementConflict, match="has changed"):
        mark_affiliate_settlement_paid(db, settlement_id, admin_identifier="admin", note="bank transfer", expected=expected)
    mark_affiliate_settlement_paid(db, settlement_id, admin_identifier="admin", note=" bank transfer ", expected=payout_token)
    assert db.execute("SELECT affiliate_commission_status FROM bookings WHERE id = ?", (kept,)).fetchone()[0] == "settled"
    with pytest.raises(SettlementConflict):
        mark_affiliate_settlement_paid(db, settlement_id, admin_identifier="admin", note="duplicate", expected=payout_token)
    with db:
        db.execute("UPDATE bookings SET payment_status = 'refunded' WHERE id = ?", (kept,))
        reverse_booking_affiliate(db, kept, "admin")
    header = db.execute("SELECT * FROM affiliate_settlements WHERE id = ?", (settlement_id,)).fetchone()
    assert (header["status"], header["admin_notes"], header["partner_name_snapshot"]) == ("paid", "bank transfer", "Partner")
    assert (header["original_amount_total"], header["paid_amount_total"], header["commission_amount_total"]) == (10000, 8000, 700)
    assert header["paid_at"] is not None and header["closed_at"] is not None
    assert [tuple(row) for row in db.execute(
        "SELECT booking_id, rule_version_id, commission_amount FROM affiliate_settlement_items WHERE settlement_id = ?",
        (settlement_id,),
    )] == [(kept, 1, 700)]
    assert [r[0] for r in db.execute(
        """SELECT event_type FROM affiliate_audit_log
           WHERE settlement_id = ? AND event_type LIKE 'settlement_%' ORDER BY id""",
        (settlement_id,),
    )] == ["settlement_prepared", "settlement_refreshed", "settlement_closed", "settlement_paid"]


def test_concurrent_preparations_cannot_share_a_booking(settlement_db):
    db, booking, path = settlement_db
    day = date(2026, 3, 29)
    booking("only-one", "2026-03-29 12:00:00")
    db.commit()
    barrier = Barrier(2, timeout=5)

    def prepare():
        conn = connect(path)
        try:
            expected = preview_affiliate_settlement(conn, 1, day, day)
            barrier.wait()
            return prepare_affiliate_settlement(conn, 1, day, day, admin_identifier="admin", expected=preview_confirmation(expected, 1, day, day))
        except SettlementConflict:
            return None
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _: prepare(), range(2)))
    assert outcomes.count(None) == 1
    assert db.execute("SELECT COUNT(*) FROM affiliate_settlements").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM affiliate_settlement_items").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"), db:
        db.execute(
            """INSERT INTO affiliate_settlement_items (
                settlement_id, booking_id, partner_id, rule_version_id, original_amount,
                discount_amount, paid_amount, commission_amount, commission_type, commission_value
            ) SELECT settlement_id, booking_id, partner_id, rule_version_id, original_amount,
                     discount_amount, paid_amount, commission_amount, commission_type, commission_value
                FROM affiliate_settlement_items"""
        )

def test_admin_settlement_requires_authorization_and_fresh_confirmation(app, monkeypatch, settlement_db):
    db, booking, path = settlement_db
    booking_id = booking("admin-settle", "2026-03-29 12:00:00", amount=900)
    db.execute("UPDATE affiliate_partners SET name = 'Árvízi Őrség', billing_name = ' =1+1', tax_number = '＝1+1' WHERE id = 1")
    db.commit()
    monkeypatch.setitem(app.config, "DATABASE", str(path))
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    monkeypatch.setattr("flaskr.auth.find_user_by_username", lambda username: {
        "username": username, "password_hash": "unused", "is_admin": username == "admin",
    })
    client = app.test_client()
    base = "/admin/affiliates/settlements"
    assert client.get(base).status_code == 302
    with client.session_transaction() as session:
        session["username"] = "viewer"
    assert client.get(base).status_code == 403
    with client.session_transaction() as session:
        session["username"] = "admin"

    def confirmation(response):
        assert response.status_code == 200
        return {
            key: re.search(fr'name="{key}" value="([^"]+)"', response.get_data(as_text=True))[1]
            for key in ("csrf_token", "confirmation")
        } | {"confirmed": "yes"}

    filters = {"partner_id": "1", "period_start": "2026-03-29", "period_end": "2026-03-29"}
    prepare_form = filters | confirmation(client.get(base, query_string=filters))
    assert client.post(base + "/prepare", data=filters).status_code == 400
    assert client.post(base + "/prepare", data=prepare_form | {"confirmed": ""}).status_code == 400
    assert client.post(base + "/prepare", data=prepare_form | {"period_end": "2026-03-30"}).status_code == 409
    prepared = client.post(base + "/prepare", data=prepare_form)
    assert prepared.status_code == 303
    url = prepared.location
    assert client.get(url + "/export.csv").status_code == 409
    close_form = confirmation(client.get(url))
    assert client.post(url + "/close", data=close_form | {"confirmation": "0" * 64}).status_code == 303
    assert "Elszámolás lezárása" in client.get(url).get_data(as_text=True)
    assert client.post(url + "/close", data=close_form).status_code == 303
    closed_view = client.get(url)
    pay_form = confirmation(closed_view) | {"note": "Próba átutalás"}
    assert client.post(url + "/paid", data=pay_form | {"confirmation": close_form["confirmation"]}).status_code == 303
    assert db.execute("SELECT status FROM affiliate_settlements").fetchone()[0] == "closed"
    assert client.post(url + "/paid", data=pay_form).status_code == 303
    assert "Kifizetve" in client.get(url).get_data(as_text=True)
    assert db.execute("SELECT admin_notes FROM affiliate_settlements").fetchone()[0] == "Próba átutalás"

    csv_response = client.get(url + "/export.csv")
    txt_response = client.get(url + "/export.txt")
    assert csv_response.status_code == txt_response.status_code == 200
    assert csv_response.headers["Cache-Control"] == "no-store"
    assert csv_response.headers["Content-Disposition"].endswith('Arvizi_Orseg-2026-03-29-2026-03-29-1.csv"')
    assert txt_response.headers["Content-Disposition"].endswith('Arvizi_Orseg-2026-03-29-2026-03-29-1.txt"')
    assert csv_response.data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(csv_response.data.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert all(len(row) == 7 for row in rows)
    assert ["Adat", "Partner", "Árvízi Őrség", "", "", "", ""] in rows
    assert ["Adat", "Számlázási név", "'=1+1", "", "", "", ""] in rows
    assert ["Adat", "Adószám", "'＝1+1", "", "", "", ""] in rows
    assert rows[-2][2:] == [str(booking_id), "10000", "2000", "8000", "900"]
    assert rows[-1] == ["Összesen", "", "", "10000", "2000", "8000", "900"]
    txt = txt_response.get_data(as_text=True)
    assert "Partner: Árvízi Őrség\r\n" in txt
    assert "Összesen\r\nEredeti ár (Ft): 10000\r\nKedvezmény (Ft): 2000\r\nFizetett összeg (Ft): 8000\r\nJutalék (Ft): 900\r\n" in txt
    screen = closed_view.get_data(as_text=True)
    assert "@media print" in screen and str(booking_id) in screen
    cells = re.findall(r"<td[^>]*>([0-9]+)</td>", screen)
    assert cells == rows[-2][3:] + rows[-1][3:]
    with client.session_transaction() as session:
        session["username"] = "viewer"
    assert client.get(url + "/export.csv").status_code == 403
    assert client.get(url + "/export.txt").status_code == 403
