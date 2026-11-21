"""Commission snapshot finalization and callback replay coverage."""

import base64
from types import SimpleNamespace

import pytest

from flaskr.affiliate_commission_lifecycle import (
    AffiliateCommissionLifecycleError,
    finalize_booking_commission,
)
from flaskr.db import get_db
from flaskr.affiliate_usage import reserve_affiliate_usage
from flaskr.payment import _apply_back_status
from flaskr.services.simplepay_service import SimplePayService


@pytest.fixture
def commission_booking(app):
    with app.app_context():
        db = get_db()
        partner_id = db.execute(
            "INSERT INTO affiliate_partners (ref_code, name) VALUES ('SET02', 'SET-02 Partner')"
        ).lastrowid
        rule_id = db.execute(
            """
            INSERT INTO affiliate_rule_versions (
                partner_id, version_number, status, discount_type,
                commission_type, commission_value
            ) VALUES (?, 1, 'active', 'tracking', 'percentage', 10)
            """,
            (partner_id,),
        ).lastrowid
        booking_id = db.execute(
            """
            INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email,
                participants_count, total_price, payment_status,
                affiliate_partner_id, affiliate_rule_version_id,
                affiliate_original_price, affiliate_discount_amount,
                affiliate_payable_price, affiliate_commission_type,
                affiliate_commission_value, affiliate_commission_amount,
                affiliate_commission_status, affiliate_snapshot_locked
            ) VALUES (
                1, 'SET02-ORDER', 'Teszt Elek', 'set02@example.invalid',
                2, 18000, 'pending', ?, ?, 20000, 2000, 18000,
                'percentage', 10, 1800, 'pending', 0
            )
            """,
            (partner_id, rule_id),
        ).lastrowid
        db.execute(
            """
            INSERT INTO payment_transactions (booking_id, order_ref, amount, status)
            VALUES (?, 'SET02-ORDER', 18000, 'pending')
            """,
            (booking_id,),
        )
        db.commit()
        try:
            yield db, booking_id, rule_id
        finally:
            db.execute("DELETE FROM affiliate_audit_log WHERE booking_id = ?", (booking_id,))
            db.execute(
                "DELETE FROM affiliate_usage_events WHERE usage_id IN (SELECT id FROM affiliate_usages WHERE booking_id = ?)",
                (booking_id,),
            )
            db.execute("DELETE FROM affiliate_usages WHERE booking_id = ?", (booking_id,))
            db.execute("DELETE FROM affiliate_budget_periods WHERE rule_version_id = ?", (rule_id,))
            db.execute("DELETE FROM payment_transactions WHERE booking_id = ?", (booking_id,))
            db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            db.execute("DELETE FROM affiliate_rule_versions WHERE id = ?", (rule_id,))
            db.execute("DELETE FROM affiliate_partners WHERE id = ?", (partner_id,))
            db.commit()


def test_success_callback_earns_locked_snapshot_exactly_once(commission_booking):
    db, booking_id, rule_id = commission_booking

    db.execute(
        "UPDATE bookings SET affiliate_snapshot_locked = 1 WHERE id = ?",
        (booking_id,),
    )
    _apply_back_status(db, "SET02-ORDER", "SUCCESS", "SET02-TX")
    first = db.execute(
        """
        SELECT payment_status, affiliate_commission_type,
               affiliate_commission_value, affiliate_commission_amount,
               affiliate_commission_status
          FROM bookings WHERE id = ?
        """,
        (booking_id,),
    ).fetchone()
    db.execute(
        """UPDATE affiliate_rule_versions
              SET commission_type = 'fixed', commission_value = 999999
            WHERE id = ?""",
        (rule_id,),
    )
    _apply_back_status(db, "SET02-ORDER", "SUCCESS", "SET02-TX")
    db.commit()

    replayed = db.execute(
        """
        SELECT affiliate_commission_type, affiliate_commission_value,
               affiliate_commission_amount, affiliate_commission_status
          FROM bookings WHERE id = ?
        """,
        (booking_id,),
    ).fetchone()
    audit_count = db.execute(
        """SELECT COUNT(*) FROM affiliate_audit_log
             WHERE booking_id = ? AND event_type = 'commission_earned'""",
        (booking_id,),
    ).fetchone()[0]

    assert tuple(first) == ("paid", "percentage", 10, 1800, "earned")
    assert tuple(replayed) == ("percentage", 10, 1800, "earned")
    assert audit_count == 1


def test_commission_cannot_finalize_before_paid_or_without_lock(commission_booking):
    db, booking_id, _ = commission_booking

    with pytest.raises(AffiliateCommissionLifecycleError, match="paid booking"):
        finalize_booking_commission(db, "SET02-ORDER")

    db.execute("UPDATE bookings SET payment_status = 'paid' WHERE id = ?", (booking_id,))
    with pytest.raises(AffiliateCommissionLifecycleError, match="must be locked"):
        finalize_booking_commission(db, "SET02-ORDER")


def test_missing_booking_is_an_idempotent_noop(app):
    with app.app_context():
        assert finalize_booking_commission(get_db(), "SET02-MISSING") is None


@pytest.fixture
def sandbox_gateway(monkeypatch):
    service = SimplePayService("SET02-SANDBOX", "fixture-key-never-used-externally", sandbox=True)
    assert service.base_url.startswith("https://sandbox.simplepay.hu/")
    monkeypatch.setattr("flaskr.payment.get_simplepay_service", lambda: service)
    monkeypatch.setattr("flaskr.payment._send_booking_confirmation_notification", lambda *_: None)

    class NoEmailThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr("flaskr.payment.threading", SimpleNamespace(Thread=NoEmailThread))
    return service


def _signed_ipn(client, service, **overrides):
    payload = {
        "orderRef": "SET02-ORDER", "transactionId": "SET02-TX",
        "status": "FINISHED", "merchant": service.merchant_id, "total": "18000", "currency": "HUF",
    }
    body, signature = service.encode_signed_payload({**payload, **overrides})
    return client.post("/payment/ipn", data=body, headers={"Signature": signature})


def _signed_back(client, service, route="success", **overrides):
    payload = {
        "o": "SET02-ORDER", "t": "SET02-TX", "e": "SUCCESS", "m": service.merchant_id,
    }
    body, signature = service.encode_signed_payload({**payload, **overrides})
    return client.get(
        f"/payment/{route}",
        query_string={
            "r": base64.urlsafe_b64encode(body.encode()).decode().rstrip("="),
            "s": signature,
            "order_ref": "SET02-ORDER",
        },
    )


def _set_up_callback_booking(commission_booking):
    db, booking_id, rule_id = commission_booking
    partner_id = db.execute("SELECT partner_id FROM affiliate_rule_versions WHERE id = ?", (rule_id,)).fetchone()[0]
    period_id = db.execute(
        """
        INSERT INTO affiliate_budget_periods (partner_id, rule_version_id, period_key, usage_limit)
        VALUES (?, ?, 'set02-period', 2)
        """,
        (partner_id, rule_id),
    ).lastrowid
    db.execute(
        "UPDATE bookings SET affiliate_snapshot_locked = 1, affiliate_usage_status = 'pending' WHERE id = ?",
        (booking_id,),
    )
    db.commit()
    return reserve_affiliate_usage(
        db, idempotency_key="set02-reservation", booking_id=booking_id,
        partner_id=partner_id, rule_version_id=rule_id, budget_period_id=period_id,
        guest_key_hash="a" * 64, quantity=1,
    )


def _budget_counters(db, usage):
    row = db.execute(
        "SELECT reserved_usage, finalized_usage FROM affiliate_budget_periods WHERE id = ?",
        (usage.budget_period_id,),
    ).fetchone()
    return tuple(row)


def _payment_state(db, booking_id):
    booking = db.execute(
        """SELECT payment_status, payment_date, transaction_id,
                  affiliate_commission_status, affiliate_usage_status
             FROM bookings WHERE id = ?""",
        (booking_id,),
    ).fetchone()
    tx = db.execute(
        "SELECT status, paid_at, transaction_id FROM payment_transactions WHERE booking_id = ?",
        (booking_id,),
    ).fetchone()
    return tuple(booking), tuple(tx)


@pytest.mark.parametrize("ipn_first", [True, False])
def test_signed_success_replays_and_late_failures_preserve_original_payment(
    app, commission_booking, sandbox_gateway, ipn_first,
):
    db, booking_id, _ = commission_booking
    usage = _set_up_callback_booking(commission_booking)
    client = app.test_client()
    first, replay = (_signed_ipn, _signed_back) if ipn_first else (_signed_back, _signed_ipn)
    assert first(client, sandbox_gateway).status_code == 200

    # A distinguishable persisted timestamp detects rewrites by callback replay.
    db.execute("UPDATE bookings SET payment_date = '2026-01-01 00:00:00' WHERE id = ?", (booking_id,))
    db.execute("UPDATE payment_transactions SET paid_at = '2026-01-01 00:00:00' WHERE booking_id = ?", (booking_id,))
    db.commit()
    paid = _payment_state(db, booking_id)
    assert paid[0][0] == "paid"
    assert paid[0][3:] == ("earned", "final")
    assert paid[1][0] == "success"
    assert _budget_counters(db, usage) == (0, 1)

    assert replay(client, sandbox_gateway).status_code == 200
    assert _signed_ipn(client, sandbox_gateway, status="TIMEOUT").status_code == 200
    assert _signed_back(client, sandbox_gateway, "fail", e="FAILED").status_code == 200
    assert _signed_ipn(client, sandbox_gateway, transactionId="WRONG-TX").status_code == 400
    assert _payment_state(db, booking_id) == paid
    assert _budget_counters(db, usage) == (0, 1)
    assert db.execute("SELECT status FROM affiliate_usages WHERE id = ?", (usage.usage_id,)).fetchone()[0] == "final"
    assert db.execute(
        "SELECT COUNT(*) FROM affiliate_usage_events WHERE usage_id = ? AND event_type = 'finalize'",
        (usage.usage_id,),
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM affiliate_audit_log WHERE booking_id = ? AND event_type = 'commission_earned'",
        (booking_id,),
    ).fetchone()[0] == 1


@pytest.mark.parametrize("status", ["cancelled", "refunded"])
def test_late_success_does_not_resurrect_reversed_booking(app, commission_booking, sandbox_gateway, status):
    db, booking_id, _ = commission_booking
    _set_up_callback_booking(commission_booking)
    client = app.test_client()
    assert _signed_ipn(client, sandbox_gateway).status_code == 200
    db.execute(
        "UPDATE bookings SET payment_status = ?, affiliate_commission_status = 'reversed' WHERE id = ?",
        (status, booking_id),
    )
    db.commit()
    reversed_state = _payment_state(db, booking_id)
    assert _signed_back(client, sandbox_gateway).status_code == 200
    assert _signed_ipn(client, sandbox_gateway).status_code == 200
    assert _payment_state(db, booking_id) == reversed_state


def test_signed_order_mismatch_and_invalid_callback_are_ignored(app, commission_booking, sandbox_gateway):
    db, booking_id, _ = commission_booking
    _set_up_callback_booking(commission_booking)
    client = app.test_client()
    pending = _payment_state(db, booking_id)

    assert _signed_back(client, sandbox_gateway, o=None).status_code == 200
    assert _signed_back(client, sandbox_gateway, o="DIFFERENT-ORDER").status_code == 200
    assert _signed_ipn(client, sandbox_gateway, merchant="DIFFERENT-MERCHANT").status_code == 400
    assert _signed_ipn(client, sandbox_gateway, total="18001").status_code == 400
    assert _signed_ipn(client, sandbox_gateway, currency="EUR").status_code == 400
    assert client.post("/payment/ipn", data="{}", headers={"Signature": "invalid"}).status_code == 400
    assert _payment_state(db, booking_id) == pending

    assert _signed_back(client, sandbox_gateway, "fail", e="FAILED").status_code == 200
    assert _payment_state(db, booking_id)[1][0] == "fail"
    assert _signed_ipn(client, sandbox_gateway).status_code == 200
    assert _payment_state(db, booking_id)[0][3:] == ("earned", "final")


def test_ipn_audit_failure_rolls_back_payment_usage_and_commission(app, commission_booking, sandbox_gateway):
    db, booking_id, _ = commission_booking
    usage = _set_up_callback_booking(commission_booking)
    db.execute(
        """CREATE TEMP TRIGGER fail_commission_earn BEFORE INSERT ON affiliate_audit_log
           WHEN NEW.event_type = 'commission_earned'
           BEGIN SELECT RAISE(ABORT, 'test audit failure'); END"""
    )
    db.commit()
    initial = _payment_state(db, booking_id)
    try:
        response = _signed_ipn(app.test_client(), sandbox_gateway)
        assert response.status_code == 500
        assert response.headers["Signature"]
        assert not db.in_transaction
        assert _payment_state(db, booking_id) == initial
        assert _budget_counters(db, usage) == (1, 0)
        assert db.execute("SELECT status FROM affiliate_usages WHERE id = ?", (usage.usage_id,)).fetchone()[0] == "pending"
        assert db.execute(
            "SELECT COUNT(*) FROM affiliate_usage_events WHERE usage_id = ? AND event_type = 'finalize'",
            (usage.usage_id,),
        ).fetchone()[0] == 0
    finally:
        db.execute("DROP TRIGGER fail_commission_earn")


def test_gateway_query_requires_a_signed_sandbox_response(monkeypatch, sandbox_gateway):
    payload = {"transactions": [{"orderRef": "SET02-ORDER", "transactionId": "SET02-TX", "status": "SUCCESS"}]}
    body, signature = sandbox_gateway.encode_signed_payload(payload)
    response = SimpleNamespace(content=body.encode(), headers={}, status_code=200, json=lambda: payload)

    def sandbox_post(url, **kwargs):
        assert url == "https://sandbox.simplepay.hu/payment/v2/query"
        return response

    monkeypatch.setattr("flaskr.services.simplepay_service.requests.post", sandbox_post)
    with pytest.raises(RuntimeError, match="Invalid signature"):
        sandbox_gateway.query_transactions(order_refs=["SET02-ORDER"])
    response.headers["Signature"] = signature
    assert sandbox_gateway.query_transactions(order_refs=["SET02-ORDER"]) == payload


def test_sync_applies_only_matching_signed_query_entries(app, commission_booking, sandbox_gateway, monkeypatch):
    db, booking_id, _ = commission_booking
    _set_up_callback_booking(commission_booking)
    db.execute(
        "UPDATE payment_transactions SET transaction_id = 'SET02-TX' WHERE booking_id = ?",
        (booking_id,),
    )
    db.commit()
    client = app.test_client()
    monkeypatch.setattr("flaskr.auth.find_user_by_username", lambda _: {
        "username": "set02-admin", "password_hash": "unused", "is_admin": True,
    })
    with client.session_transaction() as session:
        session["username"] = "set02-admin"

    result = {}

    def gateway_response(url, **kwargs):
        assert url == "https://sandbox.simplepay.hu/payment/v2/query"
        body, signature = sandbox_gateway.encode_signed_payload(result)
        return SimpleNamespace(
            content=body.encode(), status_code=200, headers={"Signature": signature},
            json=lambda: result,
        )

    monkeypatch.setattr("flaskr.services.simplepay_service.requests.post", gateway_response)
    initial = _payment_state(db, booking_id)
    for entry in (
        {"status": "SUCCESS"},
        {"orderRef": "SET02-ORDER", "transactionId": "WRONG-TX", "status": "SUCCESS"},
        {"orderRef": "SET02-ORDER", "transactionId": "SET02-TX", "status": "SUCCESS", "total": "18001"},
    ):
        result["transactions"] = [entry]
        response = client.post("/payment/sync", json={"order_ref": "SET02-ORDER"})
        assert response.status_code == 200
        assert response.json["synced"] == []
        assert _payment_state(db, booking_id) == initial
        assert db.execute(
            "SELECT response_data FROM payment_transactions WHERE booking_id = ?", (booking_id,),
        ).fetchone()[0] is None

    result["transactions"] = [{"transactionId": "SET02-TX", "status": "SUCCESS"}]
    response = client.post("/payment/sync", json={"order_ref": "SET02-ORDER"})
    assert response.status_code == 200
    assert [entry["order_ref"] for entry in response.json["synced"]] == ["SET02-ORDER"]
    assert _payment_state(db, booking_id)[0][3:] == ("earned", "final")


def test_success_page_only_displays_verified_paid_booking(app, commission_booking, sandbox_gateway):
    _set_up_callback_booking(commission_booking)
    client = app.test_client()
    rejected = _signed_back(client, sandbox_gateway, o=None)
    assert "A fizetés még nincs megerősítve" in rejected.get_data(as_text=True)
    assert "set02@example.invalid" not in rejected.get_data(as_text=True)

    accepted = _signed_back(client, sandbox_gateway)
    assert "Sikeres fizetés!" in accepted.get_data(as_text=True)
    assert "set02@example.invalid" in accepted.get_data(as_text=True)

    unbound = app.test_client().get("/payment/success?order_ref=SET02-ORDER")
    assert "A fizetés még nincs megerősítve" in unbound.get_data(as_text=True)
    assert "set02@example.invalid" not in unbound.get_data(as_text=True)
