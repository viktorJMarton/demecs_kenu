"""Payment-start attribution resolution integration coverage."""

import sqlite3

import pytest

from flaskr.db import get_db
from flaskr.payment import resolve_payment_affiliate_context


class FakeSimplePay:
    def __init__(self):
        self.prepared = None

    def generate_order_ref(self, booking_id):
        return f"TEST-ORDER-{booking_id}"

    def prepare_payment_data(self, **kwargs):
        self.prepared = kwargs
        return {"orderRef": kwargs["order_ref"], "total": kwargs["amount"]}

    def start_payment(self, payment_data):
        return True, "https://simplepay.invalid/pay", {"transactionId": "TEST-TX"}


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
    fake = FakeSimplePay()
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: fake)

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    assert response.headers["Location"] == "https://simplepay.invalid/pay"
    assert fake.prepared["amount"] == 25_000
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
        assert booking["affiliate_partner_id"] == partner_id
        assert booking["affiliate_rule_version_id"] == rule_id
        assert booking["affiliate_attribution_id"] == attribution["id"]
        assert booking["affiliate_ref_code_snapshot"] == "AFF-PAYMENT1"
        assert booking["affiliate_rule_version_snapshot"] == 4
        assert booking["affiliate_original_price"] == 25_000
        assert booking["affiliate_payable_price"] == 25_000
        assert booking["affiliate_utm_source"] == "server"
        assert booking["affiliate_utm_campaign"] == "trusted"


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
    monkeypatch.setattr(
        "flaskr.payment.get_simplepay_service", lambda: FakeSimplePay()
    )

    response = client.post("/payment/start", data=_payment_form(tour_id))

    assert response.status_code == 302
    with app.app_context():
        booking = get_db().execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        assert booking["total_price"] == 25_000
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_rule_version_id"] is None
        assert booking["affiliate_attribution_id"] is None
        assert booking["affiliate_discount_amount"] == 0


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
    with app.app_context():
        booking = get_db().execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        assert booking["total_price"] == 22_500
        assert booking["affiliate_original_price"] == 25_000
        assert booking["affiliate_discount_amount"] == 2_500
        assert booking["affiliate_payable_price"] == 22_500


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
    with app.app_context():
        booking = get_db().execute(
            "SELECT * FROM bookings WHERE customer_email = 'guest@example.test'"
        ).fetchone()
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_discount_amount"] == 0


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
    with app.app_context():
        booking = get_db().execute(
            """
            SELECT * FROM bookings
             WHERE customer_email = 'guest@example.test' AND order_ref != 'LIMIT-SEED'
            """
        ).fetchone()
        assert booking["affiliate_partner_id"] is None
        assert booking["affiliate_discount_amount"] == 0


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
