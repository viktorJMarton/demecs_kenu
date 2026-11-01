"""Payment-start attribution resolution integration coverage."""

import json
import sqlite3

import pytest
from flask import render_template

from flaskr.db import get_db
from flaskr.payment import resolve_payment_affiliate_context


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
        return False, None, None


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
