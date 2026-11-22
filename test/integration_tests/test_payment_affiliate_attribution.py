"""Payment-start attribution resolution integration coverage."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from types import SimpleNamespace

import pytest
from flask import render_template

from flaskr.affiliate_attribution import VISITOR_COOKIE_NAME
from flaskr.affiliate_reporting import get_affiliate_report_metrics
from flaskr.affiliate_settlement import (
    close_affiliate_settlement,
    mark_affiliate_settlement_paid,
    prepare_affiliate_settlement,
    preview_affiliate_settlement,
    preview_confirmation,
    settlement_confirmation,
)
from flaskr.db import get_db
from flaskr.payment import _apply_back_status, resolve_payment_affiliate_context
from flaskr.services.simplepay_service import SimplePayService


class FakeSimplePay:
    def __init__(self, total_offset=0):
        self.prepared = None
        self.prepared_payload = None
        self.start_calls = 0
        self.total_offset = total_offset

    def generate_order_ref(self, booking_id):
        return f"TEST-ORDER-{booking_id}"

    def prepare_payment_data(self, **kwargs):
        self.prepared = kwargs
        self.prepared_payload = {
            "orderRef": kwargs["order_ref"],
            "total": str(kwargs["amount"] + self.total_offset),
        }
        return self.prepared_payload

    def start_payment(self, payment_data):
        self.start_calls += 1
        return True, "https://simplepay.invalid/pay", {"transactionId": "TEST-TX"}


class RejectedSimplePay(FakeSimplePay):
    def start_payment(self, payment_data):
        self.start_calls += 1
        return False, None, {"errorCodes": ["Ismeretlen hiba"]}


class RaisingSimplePay(FakeSimplePay):
    def start_payment(self, payment_data):
        self.start_calls += 1
        raise RuntimeError("simulated gateway failure")


class PrepareRaisingSimplePay(FakeSimplePay):
    def prepare_payment_data(self, **kwargs):
        self.prepared = kwargs
        raise RuntimeError("simulated payload preparation failure")


@pytest.fixture(autouse=True)
def cleanup_payment_affiliate_rows(app):
    yield
    with app.app_context():
        db = get_db()
        test_settlements = """SELECT s.id FROM affiliate_settlements s
            JOIN affiliate_partners p ON p.id = s.partner_id WHERE p.ref_code = 'AFF-PAYMENT1'"""
        test_bookings = "SELECT id FROM bookings WHERE customer_email = 'guest@example.test'"
        db.execute(f"DELETE FROM affiliate_audit_log WHERE booking_id IN ({test_bookings}) OR settlement_id IN ({test_settlements})")
        db.execute(f"DELETE FROM affiliate_settlement_items WHERE settlement_id IN ({test_settlements})")
        db.execute(f"DELETE FROM affiliate_settlements WHERE id IN ({test_settlements})")
        db.execute("DELETE FROM affiliate_usage_events")
        db.execute("DELETE FROM affiliate_usages")
        db.execute("DELETE FROM affiliate_budget_periods")
        db.execute(
            "DELETE FROM payment_transactions WHERE booking_id IN "
            "(SELECT id FROM bookings WHERE customer_email = 'guest@example.test')"
        )
        db.execute("DELETE FROM bookings WHERE customer_email = 'guest@example.test'")
        db.execute("DELETE FROM affiliate_click_events")
        db.execute("DELETE FROM affiliate_attributions")
        db.execute("DELETE FROM affiliate_rule_scopes")
        db.execute("DELETE FROM affiliate_rule_versions")
        db.execute("DELETE FROM affiliate_partners")
        db.execute("DELETE FROM tours WHERE title = 'Affiliate payment tour'")
        db.commit()


def _seed_affiliate_tour(app):
    with app.app_context():
        db = get_db()
        tour_id = db.execute(
            """
            INSERT INTO tours (title, date, time, price, is_active)
            VALUES ('Affiliate payment tour', '2099-06-01', '10:00', 12500, 1)
            """
        ).lastrowid
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES (?, ?)",
            ("AFF-PAYMENT1", "Payment partner"),
        ).lastrowid
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type
            ) VALUES (?, 4, 'active', 'tracking')
            """,
            (partner_id,),
        ).lastrowid
        db.execute(
            "INSERT INTO affiliate_rule_scopes (rule_version_id, scope_type) "
            "VALUES (?, 'all')",
            (rule_id,),
        )
        db.commit()
        return tour_id, partner_id, rule_id


def _payment_form(tour_id):
    return {
        "tour_id": str(tour_id),
        "customer_name": "Teszt Vendég",
        "customer_email": "guest@example.test",
        "customer_phone": "+36301234567",
        "participants_count": "2",
        "lifejacket_sizes[]": ["70-90 kg", "50-70 kg"],
        "invoice_name": "Teszt Vendég",
        "invoice_country": "hu",
        "invoice_city": "Budapest",
        "invoice_zip": "1111",
        "invoice_address": "Teszt utca 1.",
        "affiliate_partner_id": "999999",
        "affiliate_rule_version_id": "999999",
        "affiliate_discount_amount": "999999",
        "total_price": "1",
    }


def test_payment_start_uses_server_attribution_and_server_price(
    client, app, monkeypatch
):
    tour_id, partner_id, rule_id = _seed_affiliate_tour(app)
    click = client.get(
        "/?ref=AFF-PAYMENT1&utm_source=server&utm_campaign=trusted"
    )
    assert click.status_code == 200
    preview = client.post(
        "/payment/price-preview",
        json={
            "tour_id": tour_id,
            "participants_count": 2,
            "customer_email": "guest@example.test",
        },
    )
    assert preview.get_json() == {
        "original_amount": 25_000,
        "discount_amount": 0,
        "payable_amount": 25_000,
        "show_partner_discount": True,
    }
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert response.headers["Location"] == "https://simplepay.invalid/pay"
    assert fake.prepared["amount"] == 25_000
    assert fake.prepared_payload["total"] == "25000"
    assert fake.start_calls == 1
    with app.app_context():
        db = get_db()
        attribution = db.execute("SELECT * FROM affiliate_attributions").fetchone()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["total_price"] == 25_000
        assert transaction["amount"] == 25_000
        assert json.loads(transaction["request_data"])["start"]["total"] == "25000"
        assert booking["affiliate_partner_id"] == partner_id
        assert booking["affiliate_rule_version_id"] == rule_id
        assert booking["affiliate_attribution_id"] == attribution["id"]
        assert booking["affiliate_ref_code_snapshot"] == "AFF-PAYMENT1"
        assert booking["affiliate_rule_version_snapshot"] == 4
        assert booking["affiliate_original_price"] == 25_000
        assert booking["affiliate_payable_price"] == 25_000
        assert booking["affiliate_utm_source"] == "server"
        assert booking["affiliate_utm_campaign"] == "trusted"


def test_non_affiliate_checkout_remains_unchanged(client, app, monkeypatch):
    tour_id, _, _ = _seed_affiliate_tour(app)
    preview = client.post(
        "/payment/price-preview",
        json={
            "tour_id": tour_id,
            "participants_count": 2,
            "customer_email": "guest@example.test",
        },
    )
    assert preview.get_json() == {
        "original_amount": 25_000,
        "discount_amount": 0,
        "payable_amount": 25_000,
        "show_partner_discount": False,
    }
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert response.headers["Location"] == "https://simplepay.invalid/pay"
    assert fake.prepared_payload["total"] == "25000"
    assert fake.start_calls == 1
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["total_price"] == 25_000
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_attribution_id"] is None
        assert transaction["amount"] == 25_000
        assert json.loads(transaction["request_data"])["start"]["total"] == "25000"


def test_expired_server_attribution_and_forged_client_fields_are_ignored(
    client, app, monkeypatch
):
    tour_id, _, _ = _seed_affiliate_tour(app)
    client.get("/?ref=AFF-PAYMENT1")
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE affiliate_attributions SET expires_at = '2000-01-01 00:00:00'"
        )
        db.commit()
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.prepared_payload["total"] == "25000"
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["total_price"] == 25_000
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_rule_version_id"] is None
        assert booking["affiliate_attribution_id"] is None
        assert booking["affiliate_discount_amount"] == 0
        assert transaction["status"] == "pending"
        assert transaction["amount"] == 25_000


def test_payment_affiliate_context_uses_normalized_email_hash(client, app):
    _seed_affiliate_tour(app)
    client.get("/?ref=AFF-PAYMENT1")

    with app.app_context():
        db = get_db()
        visitor_id = db.execute(
            "SELECT visitor_id FROM affiliate_attributions"
        ).fetchone()["visitor_id"]
        first = resolve_payment_affiliate_context(
            db, visitor_id, "  GUEST@Example.Test "
        )
        second = resolve_payment_affiliate_context(
            db, visitor_id, "guest@example.test"
        )

        assert first is not None and second is not None
        assert first.guest_key_hash == second.guest_key_hash
        assert len(first.guest_key_hash) == 64
        assert "guest" not in first.guest_key_hash


def test_public_price_preview_shows_only_neutral_discount_breakdown(client, app):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE affiliate_rule_versions "
            "SET discount_type = 'percentage', discount_value = 10, "
            "commission_type = 'percentage', commission_value = 25 WHERE id = ?",
            (rule_id,),
        )
        db.commit()
    client.get("/?ref=AFF-PAYMENT1")

    response = client.post(
        "/payment/price-preview",
        json={
            "tour_id": tour_id,
            "participants_count": 2,
            "customer_email": "guest@example.test",
            "affiliate_partner_id": 999999,
        },
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    assert "Cookie" in response.headers["Vary"]
    assert response.get_json() == {
        "original_amount": 25_000,
        "discount_amount": 2_500,
        "payable_amount": 22_500,
        "show_partner_discount": True,
    }
    public_payload = response.get_data(as_text=True).lower()
    assert "payment partner" not in public_payload
    assert "commission" not in public_payload
    assert "ref_code" not in public_payload

    invalid = client.post(
        "/payment/price-preview",
        json={
            "tour_id": tour_id,
            "participants_count": 1.5,
            "customer_email": "guest@example.test",
        },
    )
    assert invalid.status_code == 400
    assert invalid.get_json() == {"error": "invalid_request"}


def test_booking_form_uses_neutral_public_price_labels(client):
    response = client.get("/booking/form")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Eredeti ár" in html
    assert "Partnerkedvezmény" in html
    assert "Fizetendő összeg" in html
    assert "jutalék" not in html.lower()


def test_success_page_does_not_serialize_private_affiliate_fields(app):
    booking = {
        "id": 77,
        "order_ref": "PUBLIC-ORDER-77",
        "tour_title": "Public tour",
        "tour_date": "2099-06-01",
        "tour_time": "10:00",
        "participants_count": 2,
        "customer_name": "Teszt Vendég",
        "customer_email": "guest@example.test",
        "total_price": 22_500,
        "affiliate_attribution_id": 88,
        "affiliate_original_price": 25_000,
        "affiliate_discount_amount": 2_500,
        "affiliate_commission_amount": 987_654_321,
        "affiliate_partner_name": "SECRET PARTNER NAME",
    }
    with app.test_request_context():
        html = render_template(
            "payment/success.html",
            booking=booking,
            order_ref=booking["order_ref"],
            transaction_id="PUBLIC-TX-77",
        )

    assert "Eredeti ár" in html
    assert "Partnerkedvezmény" in html
    assert "SECRET PARTNER NAME" not in html
    assert "987654321" not in html
    assert "affiliate_commission" not in html


def test_payment_recalculates_discount_from_pinned_server_rule(
    client, app, monkeypatch
):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE affiliate_rule_versions "
            "SET discount_type = 'percentage', discount_value = 10 WHERE id = ?",
            (rule_id,),
        )
        db.commit()
    client.get("/?ref=AFF-PAYMENT1")
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.prepared["amount"] == 22_500
    assert fake.prepared_payload["total"] == "22500"
    assert fake.start_calls == 1
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["total_price"] == 22_500
        assert booking["affiliate_original_price"] == 25_000
        assert booking["affiliate_discount_amount"] == 2_500
        assert booking["affiliate_payable_price"] == 22_500
        assert transaction["status"] == "pending"
        assert transaction["amount"] == 22_500
        assert json.loads(transaction["request_data"])["start"]["total"] == "22500"


def test_payment_blocks_simplepay_start_when_payload_total_differs(
    client, app, monkeypatch
):
    tour_id, _, _ = _seed_affiliate_tour(app)
    fake = FakeSimplePay(total_offset=1)
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.prepared["amount"] == 25_000
    assert fake.prepared_payload["total"] == "25001"
    assert fake.start_calls == 0
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["total_price"] == 25_000
        assert booking["payment_status"] == "failed"
        assert transaction["amount"] == 25_000
        assert transaction["status"] == "fail"
        assert "amounts differ" in transaction["error_message"]


def test_simplepay_rejection_leaves_consistent_discounted_failure_state(
    client, app, monkeypatch
):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE affiliate_rule_versions "
            "SET discount_type = 'percentage', discount_value = 10 WHERE id = ?",
            (rule_id,),
        )
        db.commit()
    client.get("/?ref=AFF-PAYMENT1")
    fake = RejectedSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.start_calls == 1
    assert fake.prepared_payload["total"] == "22500"
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["payment_status"] == "failed"
        assert booking["total_price"] == 22_500
        assert booking["affiliate_payable_price"] == 22_500
        assert transaction["status"] == "fail"
        assert transaction["amount"] == 22_500
        assert json.loads(transaction["request_data"])["start"]["total"] == "22500"
        assert transaction["error_message"] == "Ismeretlen hiba"


def test_gateway_exception_marks_existing_financial_rows_failed(
    client, app, monkeypatch
):
    tour_id, _, _ = _seed_affiliate_tour(app)
    fake = RaisingSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.start_calls == 1
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["payment_status"] == "failed"
        assert booking["total_price"] == 25_000
        assert transaction["status"] == "fail"
        assert transaction["amount"] == 25_000
        assert json.loads(transaction["request_data"])["start"]["total"] == "25000"
        assert transaction["error_message"] == "Payment start exception"


def test_payload_preparation_exception_does_not_leave_pending_booking(
    client, app, monkeypatch
):
    tour_id, _, _ = _seed_affiliate_tour(app)
    fake = PrepareRaisingSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.start_calls == 0
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["payment_status"] == "failed"
        assert booking["total_price"] == 25_000
        assert transaction is None


def test_payment_drops_affiliate_when_scope_is_no_longer_eligible(
    client, app, monkeypatch
):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    client.get("/?ref=AFF-PAYMENT1")
    with app.app_context():
        db = get_db()
        other_tour_id = db.execute(
            """
            INSERT INTO tours (title, date, time, price, is_active)
            VALUES ('Other affiliate tour', '2099-06-02', '10:00', 12500, 1)
            """
        ).lastrowid
        db.execute("DELETE FROM affiliate_rule_scopes WHERE rule_version_id = ?", (rule_id,))
        db.execute(
            """
            INSERT INTO affiliate_rule_scopes (rule_version_id, scope_type, tour_id)
            VALUES (?, 'tour', ?)
            """,
            (rule_id, other_tour_id),
        )
        db.commit()
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.prepared["amount"] == 25_000
    assert fake.prepared_payload["total"] == "25000"
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_discount_amount"] == 0
        assert booking["total_price"] == 25_000
        assert transaction["amount"] == 25_000
        assert transaction["status"] == "pending"
        assert json.loads(transaction["request_data"])["start"]["total"] == "25000"


def test_payment_rechecks_usage_limit_after_the_click(client, app, monkeypatch):
    tour_id, partner_id, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE affiliate_rule_versions SET total_usage_limit = 1 WHERE id = ?",
            (rule_id,),
        )
        db.commit()
    client.get("/?ref=AFF-PAYMENT1")
    with app.app_context():
        db = get_db()
        booking_id = db.execute(
            """
            INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email,
                participants_count, total_price
            ) VALUES (?, 'LIMIT-SEED', 'Limit Seed', 'guest@example.test', 1, 12500)
            """,
            (tour_id,),
        ).lastrowid
        db.execute(
            """
            INSERT INTO affiliate_usages (
                idempotency_key, booking_id, partner_id, rule_version_id,
                guest_key_hash, quantity, status
            ) VALUES ('limit-seed', ?, ?, ?, ?, 1, 'pending')
            """,
            (booking_id, partner_id, rule_id, "a" * 64),
        )
        db.commit()
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert fake.prepared["amount"] == 25_000
    assert fake.prepared_payload["total"] == "25000"
    with app.app_context():
        db = get_db()
        booking = db.execute(
            """
            SELECT * FROM bookings
             WHERE customer_email = 'guest@example.test' AND order_ref != 'LIMIT-SEED'
            """
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM payment_transactions WHERE booking_id = ?",
            (booking["id"],),
        ).fetchone()
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_discount_amount"] == 0
        assert booking["total_price"] == 25_000
        assert transaction["status"] == "pending"
        assert transaction["amount"] == 25_000


def test_booking_financial_snapshot_is_complete_and_immutable(
    client, app, monkeypatch
):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE affiliate_rule_versions
               SET discount_type = 'percentage', discount_value = 10,
                   commission_type = 'percentage', commission_value = 20
             WHERE id = ?
            """,
            (rule_id,),
        )
        db.commit()
    client.get("/?ref=AFF-PAYMENT1&utm_medium=snapshot")
    monkeypatch.setattr(
        "flaskr.payment.get_simplepay_service", lambda: FakeSimplePay()
    )

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    with app.app_context():
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        assert booking["affiliate_original_price"] == 25_000
        assert booking["affiliate_discount_amount"] == 2_500
        assert booking["affiliate_payable_price"] == 22_500
        assert booking["affiliate_discount_type"] == "percentage"
        assert booking["affiliate_discount_value"] == 10
        assert booking["affiliate_commission_type"] == "percentage"
        assert booking["affiliate_commission_value"] == 20
        assert booking["affiliate_commission_amount"] == 4_500
        assert booking["affiliate_commission_status"] == "pending"
        assert booking["affiliate_utm_medium"] == "snapshot"
        assert booking["affiliate_snapshot_locked"] == 1

        db.execute(
            "UPDATE affiliate_rule_versions SET discount_value = 50 WHERE id = ?",
            (rule_id,),
        )
        with pytest.raises(sqlite3.IntegrityError, match="snapshot is immutable"):
            db.execute(
                "UPDATE bookings SET affiliate_discount_amount = 1 WHERE id = ?",
                (booking["id"],),
            )
        db.rollback()
        unchanged = db.execute(
            "SELECT affiliate_discount_amount FROM bookings WHERE id = ?",
            (booking["id"],),
        ).fetchone()
        assert unchanged["affiliate_discount_amount"] == 2_500


@pytest.mark.parametrize("start_outcome", ["accepted", "rejected", "exception"])
def test_late_start_reply_does_not_overwrite_confirmed_payment(client, app, monkeypatch, start_outcome):
    tour_id, _, _ = _seed_affiliate_tour(app)

    class CallbackBeforeStartReply(FakeSimplePay):
        def start_payment(self, payment_data):
            db = get_db()
            assert _apply_back_status(db, payment_data["orderRef"], "SUCCESS", "TEST-TX")
            db.commit()
            if start_outcome == "rejected":
                return False, None, {"errorCodes": ["TEST"]}
            if start_outcome == "exception":
                raise RuntimeError("simulated late START exception")
            return super().start_payment(payment_data)

    monkeypatch.setattr("flaskr.payment.get_simplepay_service", CallbackBeforeStartReply)
    response = client.post("/payment/start", data=_payment_form(tour_id))
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/payment/success?")
    with app.app_context():
        row = get_db().execute(
            """
            SELECT b.payment_status, pt.status, pt.transaction_id
              FROM bookings b JOIN payment_transactions pt ON pt.booking_id = b.id
             WHERE b.tour_id = ?
            """,
            (tour_id,),
        ).fetchone()
        assert tuple(row) == ("paid", "success", "TEST-TX")


def test_checkout_reserves_monthly_participant_usage_before_sandbox_start(client, app, monkeypatch):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE affiliate_rule_versions SET budget_period_type = 'monthly',
                usage_unit = 'participant', total_usage_limit = 3
            WHERE id = ?
            """,
            (rule_id,),
        )
        db.commit()

    class InspectCommittedReservation(FakeSimplePay):
        def start_payment(self, payment_data):
            with sqlite3.connect(app.config["DATABASE"]) as observer:
                saved = observer.execute(
                    """
                    SELECT b.affiliate_snapshot_locked, b.affiliate_usage_status, u.quantity,
                           u.expires_at, p.usage_limit, p.reserved_usage, tx.status
                      FROM bookings b
                      JOIN affiliate_usages u ON u.booking_id = b.id
                      JOIN affiliate_budget_periods p ON p.id = u.budget_period_id
                      JOIN payment_transactions tx ON tx.booking_id = b.id
                     WHERE b.order_ref = ?
                    """,
                    (payment_data["orderRef"],),
                ).fetchone()
            assert saved[:3] == (1, "pending", 2)
            assert saved[4:] == (3, 2, "init")
            assert datetime.fromisoformat(saved[3]) == self.prepared["timeout_at"].replace(tzinfo=None)
            return super().start_payment(payment_data)

    client.get("/?ref=AFF-PAYMENT1")
    fake = InspectCommittedReservation()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)
    assert client.post("/payment/start", data=_payment_form(tour_id)).headers["Location"] == "https://simplepay.invalid/pay"
    assert fake.start_calls == 1


def test_two_concurrent_checkouts_cannot_claim_the_same_last_budget_slot(app, monkeypatch):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE affiliate_rule_versions SET discount_type = 'percentage',
                discount_value = 10, total_usage_limit = 1 WHERE id = ?
            """,
            (rule_id,),
        )
        db.commit()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", FakeSimplePay)

    def checkout():
        client = app.test_client()
        client.get("/?ref=AFF-PAYMENT1")
        return client.post("/payment/start", data=_payment_form(tour_id)).status_code

    with ThreadPoolExecutor(max_workers=2) as tasks:
        assert list(tasks.map(lambda _: checkout(), range(2))) == [302, 302]
    with app.app_context():
        db = get_db()
        rows = db.execute(
            """
            SELECT b.total_price, b.affiliate_usage_status, tx.amount, u.status
              FROM bookings b JOIN payment_transactions tx ON tx.booking_id = b.id
              LEFT JOIN affiliate_usages u ON u.booking_id = b.id
             WHERE b.tour_id = ? ORDER BY b.total_price
            """,
            (tour_id,),
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            (22_500, "pending", 22_500, "pending"), (25_000, "none", 25_000, None),
        ]


@pytest.mark.parametrize("gateway_class,expected_usage,expected_payment", [
    (RejectedSimplePay, "released", "failed"),
    (PrepareRaisingSimplePay, "released", "failed"),
    (RaisingSimplePay, "pending", "pending"),
])
def test_checkout_release_depends_on_whether_gateway_outcome_is_known(
    client, app, monkeypatch, gateway_class, expected_usage, expected_payment,
):
    tour_id, _, _ = _seed_affiliate_tour(app)
    client.get("/?ref=AFF-PAYMENT1")
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", gateway_class)

    response = client.post("/payment/start", data=_payment_form(tour_id))
    assert response.status_code == 302
    if expected_payment == "pending":
        assert response.headers["Location"].startswith("/payment/success?")
    with app.app_context():
        db = get_db()
        state = db.execute(
            """
            SELECT b.payment_status, b.affiliate_usage_status, u.status,
                   (SELECT COUNT(*) FROM affiliate_usage_events
                     WHERE usage_id = u.id AND event_type = 'release')
              FROM bookings b JOIN affiliate_usages u ON u.booking_id = b.id
             WHERE b.tour_id = ?
            """,
            (tour_id,),
        ).fetchone()
        assert tuple(state) == (
            expected_payment, expected_usage, expected_usage, int(expected_usage == "released"),
        )


@pytest.mark.parametrize("reply_code,signed,expected_rejection", [
    (200, True, True),
    (200, False, False),
    (503, True, False),
])
def test_start_only_accepts_definitive_signed_sandbox_rejections(
    monkeypatch, reply_code, signed, expected_rejection,
):
    gateway = SimplePayService("mock-sandbox", "mock-secret", sandbox=True)
    data = {"orderRef": "START-SANDBOX", "errorCodes": ["1001"]}
    body, signature = gateway.encode_signed_payload(data)

    def reply(url, **kwargs):
        assert url == "https://sandbox.simplepay.hu/payment/v2/start"
        return SimpleNamespace(
            content=body.encode(), status_code=reply_code,
            headers={"Signature": signature} if signed else {}, json=lambda: data,
        )
    monkeypatch.setattr("flaskr.services.simplepay_service.requests.post", reply)
    if expected_rejection:
        assert gateway.start_payment({"orderRef": "START-SANDBOX"}) == (False, None, data)
    else:
        with pytest.raises(RuntimeError):
            gateway.start_payment({"orderRef": "START-SANDBOX"})


def test_expired_legacy_checkout_capacity_returns_without_preview_writes(client, app, monkeypatch):
    tour_id, _, rule_id = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE affiliate_rule_versions SET discount_type = 'percentage',
                discount_value = 10, total_usage_limit = 1 WHERE id = ?
            """,
            (rule_id,),
        )
        db.commit()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", FakeSimplePay)
    client.get("/?ref=AFF-PAYMENT1")
    assert client.post("/payment/start", data=_payment_form(tour_id)).status_code == 302
    with app.app_context():
        db = get_db()
        old = datetime.now(timezone.utc) - timedelta(minutes=21)
        db.execute(
            "UPDATE affiliate_usages SET expires_at = NULL, created_at = ? WHERE rule_version_id = ?",
            (old.strftime("%Y-%m-%d %H:%M:%S.%f"), rule_id),
        )
        db.commit()

    preview = client.post("/payment/price-preview", json={
        "tour_id": tour_id, "participants_count": 2, "customer_email": "guest@example.test",
    })
    assert preview.get_json()["payable_amount"] == 22_500
    with app.app_context():
        db = get_db()
        assert tuple(db.execute(
            "SELECT status, expires_at FROM affiliate_usages WHERE rule_version_id = ?", (rule_id,),
        ).fetchone()) == ("pending", None)

    assert client.post("/payment/start", data=_payment_form(tour_id)).status_code == 302
    with app.app_context():
        db = get_db()
        rows = db.execute(
            """
            SELECT u.status, b.affiliate_usage_status, b.total_price
              FROM affiliate_usages u JOIN bookings b ON b.id = u.booking_id
             WHERE u.rule_version_id = ? ORDER BY u.id
            """,
            (rule_id,),
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("released", "released", 22_500), ("pending", "pending", 22_500),
        ]


def test_monthly_checkout_reuses_prior_period_with_equivalent_timestamp_format(client, app, monkeypatch):
    tour_id, partner_id, rule_id = _seed_affiliate_tour(app)
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE affiliate_rule_versions SET budget_period_type = 'monthly',
                total_usage_limit = 9 WHERE id = ?
            """,
            (rule_id,),
        )
        period_id = db.execute(
            """
            INSERT INTO affiliate_budget_periods (
                partner_id, rule_version_id, period_key, starts_at, ends_at, usage_limit
            ) VALUES (?, ?, 'older-format', ?, ?, 1)
            """,
            (partner_id, rule_id, start.isoformat(timespec="microseconds"),
             end.isoformat(timespec="microseconds")),
        ).lastrowid
        db.commit()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", FakeSimplePay)
    client.get("/?ref=AFF-PAYMENT1")
    assert client.post("/payment/start", data=_payment_form(tour_id)).status_code == 302
    preview = client.post("/payment/price-preview", json={
        "tour_id": tour_id, "participants_count": 2, "customer_email": "guest@example.test",
    })
    assert preview.get_json()["show_partner_discount"] is False
    assert client.post("/payment/start", data=_payment_form(tour_id)).status_code == 302
    with app.app_context():
        db = get_db()
        periods = db.execute(
            "SELECT id, reserved_usage FROM affiliate_budget_periods WHERE rule_version_id = ?",
            (rule_id,),
        ).fetchall()
        assert [tuple(row) for row in periods] == [(period_id, 1)]
        assert db.execute(
            "SELECT budget_period_id FROM affiliate_usages WHERE rule_version_id = ?", (rule_id,),
        ).fetchone()[0] == period_id


def test_accepted_start_with_invalid_transaction_id_keeps_checkout_pending(client, app, monkeypatch):
    tour_id, _, _ = _seed_affiliate_tour(app)

    class AcceptedButInvalidIdentity(FakeSimplePay):
        def start_payment(self, payment_data):
            return True, "https://simplepay.invalid/pay", {"transactionId": []}

    client.get("/?ref=AFF-PAYMENT1")
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", AcceptedButInvalidIdentity)
    response = client.post("/payment/start", data=_payment_form(tour_id))
    assert response.headers["Location"].startswith("/payment/success?")
    with app.app_context():
        result = get_db().execute(
            """
            SELECT b.payment_status, b.affiliate_usage_status, u.status, tx.status
              FROM bookings b JOIN affiliate_usages u ON u.booking_id = b.id
              JOIN payment_transactions tx ON tx.booking_id = b.id
             WHERE b.tour_id = ?
            """,
            (tour_id,),
        ).fetchone()
        assert tuple(result) == ("pending", "pending", "pending", "init")

def test_release_flag_and_internal_partner_lifecycle(client, app, monkeypatch):
    tour, partner, rule = _seed_affiliate_tour(app)
    with app.app_context():
        db = get_db()
        with db:
            db.execute(
                """
                UPDATE affiliate_rule_versions SET discount_type = 'fixed', discount_value = 1000,
                       commission_type = 'percentage', commission_value = 10, total_usage_limit = 2
                 WHERE id = ?
                """,
                (rule,),
            )

    sandbox = SimplePayService("RELEASE-SANDBOX", "fixture-only", sandbox=True)
    assert sandbox.base_url.startswith("https://sandbox.simplepay.hu/")
    gateway_calls = []

    def simulate_gateway(endpoint, payload, *, require_signature):
        assert endpoint == "start" and require_signature
        gateway_calls.append((payload["orderRef"], payload["total"]))
        return 200, {
            "orderRef": payload["orderRef"], "transactionId": "TEST-E2E",
            "paymentUrl": f"{sandbox.base_url}/test",
        }

    monkeypatch.setattr(sandbox, "_post", simulate_gateway)
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: sandbox)
    monkeypatch.setattr("flaskr.payment._send_booking_confirmation_notification", lambda *_: None)
    monkeypatch.setattr("flaskr.payment._send_email_background", lambda *_: None)
    monkeypatch.setitem(app.config, "AFFILIATE_PUBLIC_ENABLED", False)
    click_url = "/?ref=AFF-PAYMENT1&utm_source=internal"
    click = client.get(click_url)
    assert click.status_code == 200 and client.get_cookie(VISITOR_COOKIE_NAME) is None
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM affiliate_click_events WHERE partner_id = ?", (partner,)).fetchone()[0] == 0

    monkeypatch.setitem(app.config, "AFFILIATE_PUBLIC_ENABLED", True)
    click = client.get(click_url)
    assert click.status_code == 200
    assert client.get_cookie(VISITOR_COOKIE_NAME) is not None
    price = {"tour_id": tour, "participants_count": 2, "customer_email": "guest@example.test"}
    enabled = client.post("/payment/price-preview", json=price).get_json()
    assert enabled["payable_amount"] == 24000

    monkeypatch.setitem(app.config, "AFFILIATE_PUBLIC_ENABLED", False)
    disabled = client.post("/payment/price-preview", json=price).get_json()
    assert disabled["payable_amount"] == 25000 and disabled["discount_amount"] == 0
    disabled_start = client.post("/payment/start", data=_payment_form(tour))
    assert disabled_start.status_code == 302
    assert int(gateway_calls[-1][1]) == 25000

    monkeypatch.setitem(app.config, "AFFILIATE_PUBLIC_ENABLED", True)
    start = client.post("/payment/start", data=_payment_form(tour))
    assert start.status_code == 302 and start.location.startswith(sandbox.base_url)
    order_ref, amount = gateway_calls[-1]
    assert int(amount) == 24000 and len(gateway_calls) == 2

    # Disabling new affiliate activity must never strand a previously started checkout.
    monkeypatch.setitem(app.config, "AFFILIATE_PUBLIC_ENABLED", False)
    body, signature = sandbox.encode_signed_payload({
        "orderRef": order_ref, "transactionId": "TEST-E2E", "status": "FINISHED",
        "merchant": sandbox.merchant_id, "currency": "HUF", "total": str(amount),
    })
    for _ in range(2):
        assert client.post("/payment/ipn", data=body, headers={"Signature": signature}).status_code == 200

    with app.app_context():
        db = get_db()
        paid = db.execute(
            """SELECT affiliate_payable_price, affiliate_commission_amount, affiliate_usage_status,
                      payment_status, affiliate_commission_status, payment_date
                 FROM bookings WHERE order_ref = ?""",
            (order_ref,),
        ).fetchone()
        assert tuple(paid)[:5] == (24000, 2400, "final", "paid", "earned")
        plain = db.execute("SELECT affiliate_partner_id FROM bookings WHERE order_ref = ?", (gateway_calls[0][0],)).fetchone()
        assert plain[0] is None
        day = paid["payment_date"].replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Budapest")).date()
        metrics = get_affiliate_report_metrics(db, partner_id=partner)
        assert (metrics.total_clicks, metrics.started_bookings, metrics.successful_bookings) == (1, 1, 1)
        assert (metrics.paid_amount_huf, metrics.discount_amount_huf, metrics.unsettled_commission_huf) == (24000, 1000, 2400)
        preview = preview_affiliate_settlement(db, partner, day, day)
        assert len(preview.items) == 1 and preview.commission_amount_total == 2400
        sid = prepare_affiliate_settlement(
            db, partner, day, day, admin_identifier="test",
            expected=preview_confirmation(preview, partner, day, day),
        )
        close_affiliate_settlement(
            db, sid, admin_identifier="test", expected=settlement_confirmation(db, sid, "prepared", "close"),
        )
        metrics = get_affiliate_report_metrics(db, partner_id=partner)
        assert (metrics.unsettled_commission_huf, metrics.settled_commission_huf) == (2400, 0)
        mark_affiliate_settlement_paid(
            db, sid, admin_identifier="test", note="Rögzített tesztkifizetés",
            expected=settlement_confirmation(db, sid, "closed", "paid"),
        )
        metrics = get_affiliate_report_metrics(db, partner_id=partner)
        assert (metrics.unsettled_commission_huf, metrics.settled_commission_huf) == (0, 2400)
