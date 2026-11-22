"""
Payment Blueprint - SimplePay fizetési integráció
Kezeli a fizetési folyamatot és a SimplePay callback-eket
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, abort, g, current_app, make_response
)
from flaskr.db import get_db
from flaskr.affiliate_attribution import VISITOR_COOKIE_NAME, normalize_visitor_id
from flaskr.services.simplepay_service import SimplePayService
from flaskr.services.email_service import get_email_service, EmailServiceError
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from secrets import token_hex
from typing import Any, Dict, List, Optional, Tuple

from flaskr.affiliate_calculation import derive_guest_key
from flaskr.affiliate_checkout import (
    AffiliateCheckoutConfigurationError,
    calculate_checkout_affiliate,
    ensure_checkout_budget_period,
)
from flaskr.affiliate_commission_lifecycle import (
    AffiliateCommissionLifecycleError,
    finalize_booking_commission,
)
from flaskr.affiliate_usage import (
    AffiliateUsageLimitExceeded,
    RESERVATION_WINDOW,
    finalize_affiliate_usage,
    release_affiliate_usage,
    reserve_affiliate_usage,
)

bp = Blueprint('payment', __name__, url_prefix='/payment')
logger = logging.getLogger(__name__)

LIFEJACKET_SIZE_OPTIONS = [
    "90+ kg",
    "70-90 kg",
    "50-70 kg",
    "30-50 kg",
    "20-30 kg",
    "10-20 kg",
    "5-10 kg",
    "0-5 kg",
]


# SimplePay hibakódok emberi nyelvű üzenetei
# A konkrét hibakódok SimplePay dokumentációjában találhatók
SIMPLEPAY_ERROR_MESSAGES = {
    '1000': 'Általános hiba történt',
    '1001': 'Hiányzó vagy érvénytelen paraméter',
    '1002': 'Érvénytelen aláírás (signature)',
    '1003': 'Érvénytelen merchant azonosító',
    '1004': 'Érvénytelen tranzakció',
    '1005': 'Sikertelen tranzakció',
    '2001': 'Időtúllépés történt',
    '5321': 'Merchant hitelesítési hiba - ellenőrizd a MERCHANT_ID és SECRET_KEY értékét a .env fájlban',
    '8888': 'Teszt tranzakció (sandbox környezet)',
}


class PaymentAmountMismatch(RuntimeError):
    """Raised before SimplePay START when persisted and outbound totals differ."""


def _whole_huf(value: Any, *, source: str) -> int:
    """Parse an unsigned whole-forint amount without accepting booleans/floats."""
    if isinstance(value, bool):
        raise PaymentAmountMismatch(f"Invalid {source} amount")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        amount = int(value)
    else:
        raise PaymentAmountMismatch(f"Invalid {source} amount")
    if amount < 0:
        raise PaymentAmountMismatch(f"Invalid {source} amount")
    return amount


def _provider_amount_matches(value: Any, expected: int) -> bool:
    if type(value) not in (int, str):
        return False
    try:
        return Decimal(value) == expected
    except InvalidOperation:
        return False

def assert_payment_amounts_match(
    db,
    booking_id: int,
    order_ref: str,
    payment_data: Dict[str, Any],
) -> int:
    """Fail closed unless booking, transaction and SimplePay START totals match."""
    row = db.execute(
        '''SELECT b.total_price AS booking_amount,
                  pt.amount AS transaction_amount
             FROM bookings b
             JOIN payment_transactions pt ON pt.booking_id = b.id
            WHERE b.id = ? AND b.order_ref = ? AND pt.order_ref = ?''',
        (booking_id, order_ref, order_ref),
    ).fetchone()
    if row is None:
        raise PaymentAmountMismatch("Payment amount records are incomplete")
    if payment_data.get('orderRef') != order_ref:
        raise PaymentAmountMismatch("SimplePay order reference mismatch")

    booking_amount = _whole_huf(row['booking_amount'], source='booking')
    transaction_amount = _whole_huf(row['transaction_amount'], source='transaction')
    simplepay_amount = _whole_huf(payment_data.get('total'), source='SimplePay')
    if len({booking_amount, transaction_amount, simplepay_amount}) != 1:
        raise PaymentAmountMismatch("Booking, transaction and SimplePay amounts differ")
    return simplepay_amount


def _dump_json(data: Dict[str, Any]) -> str:
    """Serialize dictionaries for DB storage using UTF-8 safe settings."""
    return json.dumps(data, ensure_ascii=False)


def _merge_json_blob(existing: Optional[str], key: str, payload: Dict[str, Any]) -> str:
    """Merge structured payloads under a dedicated key without losing earlier data."""
    container: Dict[str, Any] = {}
    if existing:
        try:
            container = json.loads(existing)
        except (TypeError, ValueError):
            logger.warning("Existing JSON blob for key %s could not be parsed, overwriting", key)
            container = {}
    container[key] = payload
    return _dump_json(container)


def _store_response_payload(db, order_ref: str, key: str, payload: Dict[str, Any]) -> None:
    """Persist signed SimplePay payloads in payment_transactions.response_data."""
    if not order_ref or not payload:
        return
    row = db.execute(
        'SELECT response_data FROM payment_transactions WHERE order_ref = ?',
        (order_ref,)
    ).fetchone()
    if row is None:
        logger.warning("Payment transaction not found when storing %s payload for %s", key, order_ref)
        return
    merged = _merge_json_blob(row['response_data'], key, payload)
    db.execute(
        '''UPDATE payment_transactions
           SET response_data = ?, updated_at = CURRENT_TIMESTAMP
           WHERE order_ref = ?''',
        (merged, order_ref)
    )


def _booking_email_already_sent(db, order_ref: Optional[str]) -> bool:
    if not order_ref:
        return False
    row = db.execute(
        'SELECT response_data FROM payment_transactions WHERE order_ref = ?',
        (order_ref,),
    ).fetchone()
    if not row or not row['response_data']:
        return False
    try:
        payload = json.loads(row['response_data'])
    except (TypeError, ValueError):
        return False
    notifications = payload.get('notifications')
    return isinstance(notifications, dict) and notifications.get('booking_confirmation_sent') is True


def _mark_booking_email_sent(db, order_ref: Optional[str]) -> None:
    if not order_ref:
        return
    row = db.execute(
        'SELECT response_data FROM payment_transactions WHERE order_ref = ?',
        (order_ref,),
    ).fetchone()
    existing = row['response_data'] if row else None
    merged = _merge_json_blob(existing, 'notifications', {'booking_confirmation_sent': True})
    db.execute(
        '''UPDATE payment_transactions
           SET response_data = ?, updated_at = CURRENT_TIMESTAMP
           WHERE order_ref = ?''',
        (merged, order_ref),
    )


def _fetch_booking_with_tour(db, order_ref: Optional[str]):
    if not order_ref:
        return None
    return db.execute(
        '''SELECT b.*, 
                  t.title as tour_title, 
                  t.date as tour_date, 
                  t.time as tour_time,
                  t.tour_latitude as tour_lat_final,
                  t.tour_longitude as tour_lng_final
             FROM bookings b
             JOIN tours t ON b.tour_id = t.id
            WHERE b.order_ref = ?''',
        (order_ref,),
    ).fetchone()


def _send_booking_confirmation_notification(db, booking_row) -> None:
    if not booking_row:
        logger.debug("_send_booking_confirmation_notification: no booking_row, skipping")
        return
    order_ref = booking_row['order_ref']
    if _booking_email_already_sent(db, order_ref):
        logger.info("Booking confirmation email already sent for %s, skipping", order_ref)
        return
    customer_email = (dict(booking_row).get('customer_email') or '').strip()
    logger.info("Attempting to send booking confirmation email for %s to %s", order_ref, customer_email)
    try:
        get_email_service().send_booking_confirmation(dict(booking_row))
    except EmailServiceError as exc:
        current_app.logger.warning('Booking confirmation email failed for %s: %s', order_ref, exc)
        return
    except Exception as exc:
        current_app.logger.error('Unexpected error sending booking confirmation for %s: %s', order_ref, exc, exc_info=True)
        return
    logger.info("Booking confirmation email sent successfully for %s to %s", order_ref, customer_email)
    _mark_booking_email_sent(db, order_ref)
    db.commit()


def _send_email_background(app, booking_dict: Dict[str, Any]) -> None:
    """E-mail kiküldése háttérszálban, hogy az IPN handler azonnal 200-at tudjon visszaadni.

    A SimplePay 5 másodpercen belül választ vár az IPN endpointtól.
    Az e-mail küldés szinkron módon ezt túlléphetné, ezért daemon szálban futtatjuk.
    """
    with app.app_context():
        from flaskr.db import get_db as _get_db
        try:
            db = _get_db()
            order_ref = booking_dict.get('order_ref')
            if _booking_email_already_sent(db, order_ref):
                logger.info("Background email: already sent for %s, skipping", order_ref)
                return
            get_email_service().send_booking_confirmation(booking_dict)
            _mark_booking_email_sent(db, order_ref)
            db.commit()
            logger.info("Background email sent successfully for %s", order_ref)
        except EmailServiceError as exc:
            logger.warning('Background email failed for %s: %s', booking_dict.get('order_ref'), exc)
        except Exception as exc:
            logger.error('Unexpected error in background email for %s: %s',
                         booking_dict.get('order_ref'), exc, exc_info=True)


class ReleasedAffiliatePayment(RuntimeError):
    """A confirmed payment arrived after its usage reservation was released."""


class PaymentCallbackMismatch(ValueError):
    """A verified gateway event does not identify the stored payment."""


_GATEWAY_PAYMENT_STATES = {
    'SUCCESS': ('paid', 'success'),
    'FINISHED': ('paid', 'success'),
    'FAIL': ('failed', 'fail'),
    'FAILED': ('failed', 'fail'),
    'NOTAUTHORIZED': ('failed', 'fail'),
    'TIMEOUT': ('failed', 'timeout'),
    'CANCELLED': ('cancelled', 'cancelled'),
    'CANCEL': ('cancelled', 'cancelled'),
}


def _apply_back_status(
    db, order_ref: Optional[str], status: Optional[str], transaction_id: Optional[str],
    *, payload: Optional[Dict[str, Any]] = None, is_ipn: bool = False, browser_return: bool = False,
) -> bool:
    """Apply a verified gateway event within the caller's payment transaction."""
    if not order_ref or not isinstance(status, str):
        return False
    status = status.upper()
    states = _GATEWAY_PAYMENT_STATES.get(status)
    if states is None:
        return False
    booking_status, tx_status = states
    succeeded = booking_status == 'paid'

    # Serialize callbacks before reading the payment and its linked snapshot.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    booking = db.execute(
        """
        SELECT b.id, b.payment_status, b.payment_date, b.cancellation_date, b.total_price,
               b.transaction_id AS booking_transaction_id,
               b.affiliate_partner_id, b.affiliate_rule_version_id,
               b.affiliate_snapshot_locked, b.affiliate_payable_price,
               b.affiliate_commission_status, b.affiliate_usage_status,
               pt.transaction_id AS payment_transaction_id,
               pt.amount, pt.currency, pt.paid_at
          FROM bookings b
          JOIN payment_transactions pt ON pt.booking_id = b.id AND pt.order_ref = b.order_ref
         WHERE b.order_ref = ?
        """,
        (order_ref,),
    ).fetchone()
    if booking is None:
        if succeeded:
            raise PaymentCallbackMismatch('successful event has no matching booking and transaction')
        return False

    was_paid = (
        booking['payment_status'] == 'paid'
        or booking['payment_date'] is not None
        or booking['paid_at'] is not None
    )
    if (
        booking['payment_status'] == 'refunded'
        or booking['affiliate_commission_status'] == 'reversed'
        or (booking['payment_status'] == 'cancelled' and (was_paid or booking['cancellation_date'] is not None))
        or (was_paid and not succeeded)
    ):
        return False

    known_ids = {
        str(value) for value in (
            booking['booking_transaction_id'], booking['payment_transaction_id']
        ) if value not in (None, '')
    }
    if transaction_id is not None and (
        type(transaction_id) not in (str, int) or not str(transaction_id).strip()
    ):
        raise PaymentCallbackMismatch('invalid transaction identifier')
    if transaction_id is not None:
        known_ids.add(str(transaction_id))
    if len(known_ids) > 1 or (succeeded and not known_ids):
        raise PaymentCallbackMismatch('gateway transaction identifier does not match')
    matched_id = next(iter(known_ids), None)

    if succeeded and booking['affiliate_partner_id'] is not None:
        if (
            booking['affiliate_snapshot_locked'] != 1
            or booking['affiliate_payable_price'] != booking['amount']
            or booking['total_price'] != booking['amount']
        ):
            raise AffiliateCommissionLifecycleError(
                'payment amount does not match the locked affiliate snapshot'
            )

    payload = payload or {}
    if succeeded:
        total = payload.get('total', booking['amount'])
        # Query answers can encode a whole-forint amount as a JSON decimal.
        if (
            payload.get('currency', booking['currency']) != booking['currency']
            or not _provider_amount_matches(total, booking['amount'])
        ):
            raise PaymentCallbackMismatch('gateway amount or currency does not match')

    if succeeded and booking['affiliate_partner_id'] is not None and (browser_return or status == 'SUCCESS'):
        # Browser authorization is recorded without finalizing the affiliate
        # reservation. Only the server-side FINISHED event can earn commission.
        return browser_return and status == 'SUCCESS'

    db.execute(
        """
        UPDATE bookings
           SET payment_status = ?, transaction_id = COALESCE(?, transaction_id),
               payment_date = CASE WHEN ? THEN COALESCE(payment_date, CURRENT_TIMESTAMP)
                                   ELSE payment_date END
         WHERE id = ?
        """,
        (booking_status, matched_id, succeeded, booking['id']),
    )
    db.execute(
        """
        UPDATE payment_transactions
           SET status = ?, transaction_id = COALESCE(?, transaction_id),
               ipn_data = COALESCE(?, ipn_data), updated_at = CURRENT_TIMESTAMP,
               paid_at = CASE WHEN ? THEN COALESCE(paid_at, CURRENT_TIMESTAMP) ELSE paid_at END
         WHERE order_ref = ?
        """,
        (
            tx_status, matched_id, _merge_json_blob(None, 'ipn', payload) if is_ipn else None,
            succeeded, order_ref,
        ),
    )
    if succeeded:
        _finalize_affiliate_payment(db, booking, order_ref)
    else:
        _release_payment_usage(db, booking['id'])
    return True


def _finalize_affiliate_payment(db, booking, order_ref: str) -> None:
    if booking['affiliate_partner_id'] is None:
        return
    usage = db.execute(
        'SELECT id, partner_id, rule_version_id, status FROM affiliate_usages WHERE booking_id = ?',
        (booking['id'],),
    ).fetchone()
    if usage is not None:
        if (
            usage['partner_id'] != booking['affiliate_partner_id']
            or usage['rule_version_id'] != booking['affiliate_rule_version_id']
        ):
            raise AffiliateCommissionLifecycleError(
                'usage reservation does not match the locked affiliate snapshot'
            )
        if usage['status'] == 'released':
            raise ReleasedAffiliatePayment(order_ref)
        finalize_affiliate_usage(db, usage_id=usage['id'], event_key=f"payment-success:{usage['id']}")
        if booking['affiliate_usage_status'] != 'final':
            db.execute(
                "UPDATE bookings SET affiliate_usage_status = 'final' WHERE id = ?",
                (booking['id'],),
            )
    finalize_booking_commission(db, order_ref)


def _release_payment_usage(db, booking_id: int) -> None:
    usage = db.execute(
        "SELECT id, status FROM affiliate_usages WHERE booking_id = ?",
        (booking_id,),
    ).fetchone()
    if usage is None or usage['status'] not in ('pending', 'released'):
        return
    if usage['status'] == 'pending':
        release_affiliate_usage(
            db, usage_id=usage['id'], event_key=f"payment-release:{usage['id']}",
        )
    db.execute(
        "UPDATE bookings SET affiliate_usage_status = 'released' WHERE id = ?",
        (booking_id,),
    )


def _mark_failed_payment_start(db, booking_id: int, order_ref: Optional[str], message: str) -> None:
    updated = db.execute(
        """
        UPDATE bookings SET payment_status = 'failed'
         WHERE id = ? AND payment_date IS NULL AND payment_status IN ('pending', 'failed')
           AND NOT EXISTS (
               SELECT 1 FROM payment_transactions
                WHERE booking_id = bookings.id AND (status = 'success' OR paid_at IS NOT NULL)
           )
        """,
        (booking_id,),
    )
    if order_ref:
        db.execute(
            """
            UPDATE payment_transactions
               SET status = 'fail', error_message = COALESCE(error_message, ?),
                   updated_at = CURRENT_TIMESTAMP
             WHERE booking_id = ? AND order_ref = ? AND paid_at IS NULL
               AND status IN ('init', 'pending', 'fail')
               AND EXISTS (SELECT 1 FROM bookings WHERE id = ? AND payment_status = 'failed')
            """,
            (message, booking_id, order_ref, booking_id),
        )

    if updated.rowcount:
        _release_payment_usage(db, booking_id)


def _confirmed_payment_redirect(db, order_ref: Optional[str]):
    booking = _fetch_booking_with_tour(db, order_ref)
    if booking and booking['payment_status'] == 'paid':
        session['pending_order_ref'] = order_ref
        return redirect(url_for('payment.payment_success', order_ref=order_ref))
    return None


def _decode_back_request() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (payload, order_ref) for signed SimplePay back redirects."""
    payload: Optional[Dict[str, Any]] = None
    order_ref: Optional[str] = None
    r_param = request.args.get('r')
    signature = request.args.get('s')
    if r_param and signature:
        try:
            simplepay = get_simplepay_service()
            payload = simplepay.decode_back_payload(r_param, signature)
            order_ref = payload.get('orderRef')
            if not isinstance(order_ref, str) or not order_ref.strip():
                payload = None
                order_ref = None
            elif 'merchant' in payload and payload['merchant'] != simplepay.merchant_id:
                payload = None
                order_ref = None
        except Exception as exc:
            payload = None
            logger.error('Failed to decode SimplePay back payload: %s', exc)
    if not order_ref:
        order_ref = request.args.get('order_ref') or request.args.get('orderRef') or session.get('pending_order_ref')
    return payload, order_ref


def _record_released_payment(db, order_ref: str, source: str, payload: Dict[str, Any]) -> None:
    db.rollback()
    with db:
        db.execute('BEGIN IMMEDIATE')
        _store_response_payload(db, order_ref, f'{source}_after_release', payload)
    logger.error('Confirmed SimplePay payment requires reconciliation after usage release: %s', order_ref)


def _record_back_event(db, order_ref: str, event: str, payload: Dict[str, Any]) -> None:
    with db:
        try:
            applied = _apply_back_status(
                db, order_ref, payload.get('status'), payload.get('transactionId'), payload=payload, browser_return=True,
            )
        except ReleasedAffiliatePayment:
            _record_released_payment(db, order_ref, event, payload)
            return
        except PaymentCallbackMismatch as exc:
            logger.warning('SimplePay %s rejected for %s: %s', event, order_ref, exc)
            return
        if applied:
            _store_response_payload(db, order_ref, event, payload)


def _extract_query_entries(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize SimplePay query responses into a list of transaction entries."""
    if not isinstance(result, dict):
        return []
    for key in ('transactions', 'results', 'data', 'items'):
        entries = result.get(key)
        if isinstance(entries, list):
            return entries
        if isinstance(entries, dict):
            return [entries]
    return [result] if result.get('orderRef') or result.get('transactionId') else []


def get_error_message(error_code: str) -> str:
    """SimplePay hibakód emberbarát üzenetre fordítása"""
    return SIMPLEPAY_ERROR_MESSAGES.get(str(error_code), f'Ismeretlen hiba ({error_code})')


def get_simplepay_service():
    """SimplePay service példány létrehozása környezeti változókból"""
    merchant_id = os.environ.get('SIMPLEPAY_MERCHANT_ID')
    secret_key = os.environ.get('SIMPLEPAY_SECRET_KEY')
    if not merchant_id or not secret_key:
        raise RuntimeError(
            'SimplePay credentials missing. Set SIMPLEPAY_MERCHANT_ID and SIMPLEPAY_SECRET_KEY environment variables.'
        )
    sandbox = os.environ.get('SIMPLEPAY_SANDBOX', 'true').lower() == 'true'
    
    return SimplePayService(merchant_id, secret_key, sandbox)


def resolve_active_affiliate_attribution(db, visitor_id: Optional[str]):
    """Resolve payment attribution exclusively from a validated server cookie."""
    visitor_id = normalize_visitor_id(visitor_id)
    if visitor_id is None:
        return None
    return db.execute(
        '''SELECT a.*, p.ref_code, rv.version_number
             FROM affiliate_attributions a
             JOIN affiliate_partners p
               ON p.id = a.partner_id AND p.is_active = 1
             JOIN affiliate_rule_versions rv
               ON rv.id = a.rule_version_id AND rv.partner_id = a.partner_id
            WHERE a.visitor_id = ?
              AND (a.expires_at IS NULL OR a.expires_at >= CURRENT_TIMESTAMP)
            ORDER BY a.clicked_at DESC, a.id DESC
            LIMIT 1''',
        (visitor_id,),
    ).fetchone()


@dataclass(frozen=True)
class PaymentAffiliateContext:
    """Server-resolved affiliate data safe to pass into limit calculation."""

    attribution: Any
    guest_key_hash: str


def resolve_payment_affiliate_context(
    db,
    visitor_id: Optional[str],
    customer_email: str,
) -> Optional[PaymentAffiliateContext]:
    if not current_app.config["AFFILIATE_PUBLIC_ENABLED"]:
        return None
    attribution = resolve_active_affiliate_attribution(db, visitor_id)
    if attribution is None:
        return None
    return PaymentAffiliateContext(
        attribution=attribution,
        guest_key_hash=derive_guest_key(email=customer_email),
    )


@bp.route('/price-preview', methods=['POST'])
def price_preview():
    """Return a server-calculated public price summary without affiliate secrets."""
    payload = request.get_json(silent=True) or {}
    tour_id = payload.get('tour_id')
    participants_count = payload.get('participants_count')
    def parse_integer(value):
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isascii() and value.isdigit():
            return int(value)
        raise ValueError

    try:
        tour_id = parse_integer(tour_id)
        participants_count = parse_integer(participants_count)
    except ValueError:
        return jsonify({'error': 'invalid_request'}), 400
    if tour_id < 1 or not 1 <= participants_count <= 50:
        return jsonify({'error': 'invalid_request'}), 400

    db = get_db()
    tour = db.execute(
        'SELECT * FROM tours WHERE id = ? AND is_active = 1',
        (tour_id,),
    ).fetchone()
    if tour is None:
        return jsonify({'error': 'tour_not_found'}), 404

    original_amount = int(tour['price']) * participants_count
    discount_amount = 0
    payable_amount = original_amount
    show_partner_discount = False
    customer_email = str(payload.get('customer_email') or '').strip()
    if customer_email:
        try:
            context = resolve_payment_affiliate_context(
                db,
                request.cookies.get(VISITOR_COOKIE_NAME),
                customer_email,
            )
        except ValueError:
            context = None
        if context is not None:
            try:
                calculation = calculate_checkout_affiliate(
                    db,
                    context.attribution,
                    context.guest_key_hash,
                    tour,
                    participants_count,
                )
            except (AffiliateCheckoutConfigurationError, ValueError) as exc:
                logger.warning("Affiliate price preview revalidation failed: %s", exc)
            else:
                if calculation.result.is_eligible:
                    discount_amount = calculation.result.discount_huf
                    payable_amount = calculation.result.payable_total_huf
                    show_partner_discount = True

    response = jsonify(
        original_amount=original_amount,
        discount_amount=discount_amount,
        payable_amount=payable_amount,
        show_partner_discount=show_partner_discount,
    )
    response.headers['Cache-Control'] = 'no-store, private'
    response.vary.add('Cookie')
    return response


@bp.route('/start', methods=['POST'])
def start_payment():
    """
    Fizetés indítása - foglalás létrehozása és átirányítás SimplePay-re
    
    Várható POST adatok:
    - tour_id: Túra azonosító
    - customer_name: Vásárló neve
    - customer_email: Email cím
    - customer_phone: Telefonszám
    - participants_count: Résztvevők száma
    - lifejacket_sizes[]: Mentőmellény méretek résztvevőnként
    - invoice_*: Számlázási adatok
    """
    db = None
    booking_id = None
    booking_committed = False
    start_in_flight = False
    order_ref = None
    try:
        db = get_db()
        
        # Form adatok kinyerése
        tour_id = request.form.get('tour_id', type=int)
        customer_name = request.form.get('customer_name', '').strip()
        customer_email = request.form.get('customer_email', '').strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        participants_count = request.form.get('participants_count', 1, type=int)
        lifejacket_sizes = request.form.getlist('lifejacket_sizes[]') or request.form.getlist('lifejacket_sizes')
        lifejacket_sizes = [size.strip() for size in lifejacket_sizes if size.strip()]
        
        # Alapvető validáció
        validation_errors = []
        
        if not tour_id:
            validation_errors.append('Túra azonosító hiányzik')
        if not customer_name or len(customer_name) < 3:
            validation_errors.append('Név legalább 3 karakter hosszú kell legyen')
        if not customer_email or '@' not in customer_email:
            validation_errors.append('Érvényes email cím szükséges')
        if not customer_phone or len(customer_phone) < 9:
            validation_errors.append('Érvényes telefonszám szükséges')
        if participants_count < 1 or participants_count > 50:
            validation_errors.append('Résztvevők száma 1-50 között lehet')
        if len(lifejacket_sizes) != participants_count:
            validation_errors.append('Minden résztvevőhöz meg kell adni egy mentőmellény méretet')
        invalid_sizes = [size for size in lifejacket_sizes if size not in LIFEJACKET_SIZE_OPTIONS]
        if invalid_sizes:
            validation_errors.append('Érvénytelen mentőmellény méret lett megadva')
        
        if validation_errors:
            for error in validation_errors:
                flash(error, 'error')
            return redirect(url_for('index'))
        
        # Számlázási adatok
        invoice_name = request.form.get('invoice_name', customer_name).strip()
        invoice_country = request.form.get('invoice_country', 'hu').lower()
        invoice_city = request.form.get('invoice_city', '').strip()
        invoice_zip = request.form.get('invoice_zip', '').strip()
        invoice_address = request.form.get('invoice_address', '').strip()
        invoice_company = request.form.get('invoice_company', '').strip()
        invoice_state = request.form.get('invoice_state', '').strip()
        
        # Számlázási adatok validálása
        if not invoice_name:
            validation_errors.append('Számlázási név kötelező')
        if not invoice_city or len(invoice_city) < 2:
            validation_errors.append('Város megadása kötelező')
        if not invoice_zip or len(invoice_zip) < 4:
            validation_errors.append('Irányítószám megadása kötelező (min. 4 karakter)')
        if not invoice_address or len(invoice_address) < 5:
            validation_errors.append('Teljes cím megadása kötelező (min. 5 karakter)')
        
        if validation_errors:
            for error in validation_errors:
                flash(error, 'error')
            return redirect(url_for('index'))
        
        invoice_data = {
            'name': invoice_name,
            'country': invoice_country,
            'state': invoice_state,
            'city': invoice_city,
            'zip': invoice_zip,
            'address': invoice_address,
            'company': invoice_company
        }

        # Foglaláshoz kapcsolódó szöveges megjegyzések (űrlapon "Megjegyzés")
        special_requirements = request.form.get('special_requirements', '').strip()
        customer_notes = special_requirements  # admin UI/emailek "Megjegyzés" blokkja ezt használja
        if not special_requirements and customer_notes:
            special_requirements = customer_notes
        
        # Use one writer for revalidation, booking and reservation.
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        checkout_at = datetime.now(timezone.utc)
        tour = db.execute(
            'SELECT * FROM tours WHERE id = ? AND is_active = 1',
            (tour_id,)
        ).fetchone()
        
        if not tour:
            db.rollback()
            flash('A kiválasztott túra nem található!', 'error')
            return redirect(url_for('index'))
        
        # Összeg és affiliate jogosultság számítása kizárólag szerveroldali adatokból.
        original_price = tour['price'] * participants_count
        total_price = original_price
        affiliate_context = resolve_payment_affiliate_context(
            db,
            request.cookies.get(VISITOR_COOKIE_NAME),
            customer_email,
        )
        affiliate_attribution = (
            affiliate_context.attribution if affiliate_context is not None else None
        )
        affiliate_calculation = None
        if affiliate_context is not None:
            try:
                affiliate_calculation = calculate_checkout_affiliate(
                    db,
                    affiliate_context.attribution,
                    affiliate_context.guest_key_hash,
                    tour,
                    participants_count,
                    at=checkout_at,
                )
            except (AffiliateCheckoutConfigurationError, ValueError) as exc:
                logger.warning("Affiliate checkout revalidation failed: %s", exc)
                affiliate_context = None
                affiliate_attribution = None
            else:
                if affiliate_calculation.result.is_eligible:
                    total_price = affiliate_calculation.result.payable_total_huf
                else:
                    affiliate_context = None
                    affiliate_attribution = None
                    affiliate_calculation = None
        
        # Foglalás létrehozása pending státusszal
        lifejacket_sizes_json = json.dumps(lifejacket_sizes, ensure_ascii=False)
        cursor = db.execute(
            '''INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email, customer_phone,
                participants_count, lifejacket_sizes, total_price, payment_status, payment_method,
                invoice_name, invoice_country, invoice_city, invoice_zip, invoice_address,
                invoice_company, invoice_state, customer_notes, special_requirements
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                tour_id,
                'TEMP-' + token_hex(16),
                customer_name,
                customer_email,
                customer_phone,
                participants_count,
                lifejacket_sizes_json,
                total_price,
                'pending',
                'simplepay',
                invoice_name,
                invoice_country,
                invoice_city,
                invoice_zip,
                invoice_address,
                invoice_company,
                invoice_state,
                customer_notes,
                special_requirements,
            )
        )

        booking_id = cursor.lastrowid
        if affiliate_attribution is not None:
            try:
                period_id = ensure_checkout_budget_period(db, affiliate_attribution, affiliate_calculation)
                reserve_affiliate_usage(
                    db, idempotency_key=f"checkout:{booking_id}", booking_id=booking_id,
                    partner_id=affiliate_attribution['partner_id'],
                    rule_version_id=affiliate_attribution['rule_version_id'],
                    budget_period_id=period_id, guest_key_hash=affiliate_context.guest_key_hash,
                    quantity=affiliate_calculation.result.usage_quantity, now=checkout_at,
                )
            except AffiliateUsageLimitExceeded:
                # Period-specific limits can be stricter than an earlier preview.
                affiliate_attribution = None
                total_price = original_price
                db.execute(
                    "UPDATE bookings SET total_price = ? WHERE id = ?",
                    (total_price, booking_id),
                )

        if affiliate_attribution is not None:
            db.execute(
                '''UPDATE bookings
                      SET affiliate_partner_id = ?,
                          affiliate_rule_version_id = ?,
                          affiliate_attribution_id = ?,
                          affiliate_ref_code_snapshot = ?,
                          affiliate_rule_version_snapshot = ?,
                          affiliate_original_price = ?,
                          affiliate_discount_amount = ?,
                          affiliate_payable_price = ?,
                          affiliate_discount_type = ?,
                          affiliate_discount_value = ?,
                          affiliate_commission_type = ?,
                          affiliate_commission_value = ?,
                          affiliate_commission_amount = ?,
                          affiliate_commission_status = ?,
                          affiliate_usage_status = 'pending',
                          affiliate_referrer = ?,
                          affiliate_utm_source = ?,
                          affiliate_utm_medium = ?,
                          affiliate_utm_campaign = ?,
                          affiliate_utm_content = ?,
                          affiliate_utm_term = ?,
                          affiliate_landing_path = ?,
                          affiliate_snapshot_locked = 1
                    WHERE id = ?''',
                (
                    affiliate_attribution['partner_id'],
                    affiliate_attribution['rule_version_id'],
                    affiliate_attribution['id'],
                    affiliate_attribution['ref_code'],
                    affiliate_attribution['version_number'],
                    original_price,
                    affiliate_calculation.result.discount_huf,
                    total_price,
                    affiliate_calculation.rule.discount_type,
                    affiliate_calculation.rule.discount_value,
                    affiliate_calculation.rule.commission_type,
                    affiliate_calculation.rule.commission_value,
                    affiliate_calculation.commission_amount_huf,
                    (
                        'pending'
                        if affiliate_calculation.rule.commission_type != 'none'
                        else 'none'
                    ),
                    affiliate_attribution['referrer'],
                    affiliate_attribution['utm_source'],
                    affiliate_attribution['utm_medium'],
                    affiliate_attribution['utm_campaign'],
                    affiliate_attribution['utm_content'],
                    affiliate_attribution['utm_term'],
                    affiliate_attribution['landing_page'],
                    booking_id,
                ),
            )
        try:
            # SimplePay service inicializálása
            simplepay = get_simplepay_service()

            # Order referencia generálása
            order_ref = simplepay.generate_order_ref(booking_id)

            # Booking frissítése order ref-fel
            db.execute(
                'UPDATE bookings SET order_ref = ? WHERE id = ?',
                (order_ref, booking_id)
            )

            # SimplePay callback URL-ek
            base_url = os.getenv('APP_BASE_URL', request.host_url.rstrip('/')).rstrip('/')
            success_url = f"{base_url}{url_for('payment.payment_success')}"
            fail_url = f"{base_url}{url_for('payment.payment_fail')}"
            cancel_url = f"{base_url}{url_for('payment.payment_cancel')}"
            timeout_url = f"{base_url}{url_for('payment.payment_timeout')}"
            ipn_url = f"{base_url}{url_for('payment.ipn')}"

            # Fizetési adatok előkészítése
            # PDF szerint: webes vásárlás timeout 20 perc (IPEW)
            payment_data = simplepay.prepare_payment_data(
                order_ref=order_ref,
                amount=total_price,
                customer_email=customer_email,
                customer_name=customer_name,
                customer_phone=customer_phone,
                invoice_data=invoice_data,
                success_url=success_url,
                fail_url=fail_url,
                cancel_url=cancel_url,
                timeout_url=timeout_url,
                ipn_url=ipn_url,
                language='HU',
                timeout_minutes=20,
                **({'timeout_at': checkout_at + RESERVATION_WINDOW} if affiliate_attribution is not None else {}),
            )

        except Exception:
            _mark_failed_payment_start(db, booking_id, order_ref, 'Payment start exception')
            db.commit()
            raise

        # Payment transaction létrehozása
        db.execute(
            '''INSERT INTO payment_transactions (
                booking_id, order_ref, amount, currency, status, request_data
            ) VALUES (?, ?, ?, ?, ?, ?)''',
            (
                booking_id,
                order_ref,
                total_price,
                'HUF',
                'init',
                _dump_json({'start': payment_data})
            )
        )
        db.commit()
        booking_committed = True

        # Never contact SimplePay unless every server-side financial record and
        # the exact outbound START payload carry the same whole-forint total.
        try:
            assert_payment_amounts_match(db, booking_id, order_ref, payment_data)
        except PaymentAmountMismatch as exc:
            logger.error("SimplePay START blocked: %s", exc)
            _mark_failed_payment_start(db, booking_id, order_ref, str(exc))
            db.commit()
            raise
        
        # Fizetés indítása SimplePay-nél
        if affiliate_attribution is not None and datetime.now(timezone.utc) >= checkout_at + RESERVATION_WINDOW:
            raise RuntimeError('Affiliate checkout reservation expired before START')
        start_in_flight = True
        success, payment_url, response_data = simplepay.start_payment(payment_data)
        if not isinstance(response_data, dict):
            response_data = {}
        if not success and affiliate_attribution is not None and not response_data.get('errorCodes'):
            raise RuntimeError('SimplePay START outcome is unconfirmed')
        # An accepted START may be followed by a local persistence error.
        start_in_flight = bool(success and payment_url)
        
        # Response mentése
        if response_data:
            _store_response_payload(db, order_ref, 'start', response_data)
            db.commit()
        
        if success and payment_url:
            logger.info(f"Payment started successfully for booking {booking_id}, redirecting to SimplePay")
            # Order ref session-be mentése a visszatéréshez
            session['pending_order_ref'] = order_ref
            response_id = response_data.get('transactionId')
            if response_id is not None and (
                type(response_id) not in (str, int) or not str(response_id).strip()
            ):
                raise PaymentCallbackMismatch('invalid START transaction identifier')
            response_id = str(response_id) if response_id is not None else None
            updated = db.execute(
                """
                UPDATE payment_transactions
                   SET status = 'pending', simplepay_payment_url = ?, error_message = NULL,
                       transaction_id = COALESCE(transaction_id, ?), updated_at = CURRENT_TIMESTAMP
                 WHERE order_ref = ? AND status = 'init' AND paid_at IS NULL
                   AND (transaction_id IS NULL OR ? IS NULL OR transaction_id = ?)
                """,
                (payment_url, response_id, order_ref, response_id, response_id),
            )
            db.commit()
            if updated.rowcount:
                return redirect(payment_url)
            return _confirmed_payment_redirect(db, order_ref) or redirect(url_for('index'))
        else:
            # Hiba esetén
            error_codes = response_data.get('errorCodes', ['Ismeretlen hiba'])
            # Stringgé konvertálás, ha számok
            error_msg = [str(code) for code in error_codes]
            # Emberi nyelvű hibaüzenetek
            human_errors = [get_error_message(code) for code in error_msg]
            logger.error(f"Payment start failed for booking {booking_id}: {error_msg} - {human_errors}")
            
            # Státusz frissítése
            _mark_failed_payment_start(db, booking_id, order_ref, ', '.join(error_msg))
            db.commit()
            confirmed = _confirmed_payment_redirect(db, order_ref)
            if confirmed is not None:
                return confirmed

            flash(f'A fizetés indítása sikertelen. {" | ".join(human_errors)}', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f"Error in start_payment: {str(e)}", exc_info=True)
        if db is not None:
            db.rollback()
        if booking_committed:
            try:
                if start_in_flight and affiliate_attribution is not None:
                    confirmed = _confirmed_payment_redirect(db, order_ref)
                    if confirmed is not None:
                        return confirmed
                    session['pending_order_ref'] = order_ref
                    return redirect(url_for('payment.payment_success', order_ref=order_ref))
                _mark_failed_payment_start(db, booking_id, order_ref, 'Payment start exception')
                db.commit()
                confirmed = _confirmed_payment_redirect(db, order_ref)
                if confirmed is not None:
                    return confirmed
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not persist failed payment-start state for booking %s",
                    booking_id,
                )
        flash('Hiba történt a fizetés indítása során!', 'error')
        return redirect(url_for('index'))


def _signed_ipn_response(simplepay, status_code: int, payload=None):
    body, signature = simplepay.generate_ipn_response(payload)
    response = make_response(body, status_code)
    response.headers['Content-Type'] = 'application/json'
    response.headers[SimplePayService.HEADER_SIGNATURE] = signature
    return response


@bp.route('/ipn', methods=['POST'])
def ipn():
    """IPN (Instant Payment Notification) endpoint with header-based signature validation."""
    db = None
    try:
        raw_body = request.get_data() or b''
        signature = request.headers.get(SimplePayService.HEADER_SIGNATURE, '')
        simplepay = get_simplepay_service()

        success, status, ipn_data = simplepay.process_ipn(raw_body, signature)
        if not success or not ipn_data:
            logger.error("IPN verification failed: %s", status)
            return jsonify({'receiveDate': datetime.now().isoformat()}), 400

        order_ref = ipn_data.get('orderRef')
        if not isinstance(order_ref, str) or not order_ref.strip():
            return jsonify({'receiveDate': datetime.now().isoformat()}), 400
        if 'merchant' in ipn_data and ipn_data['merchant'] != simplepay.merchant_id:
            return jsonify({'receiveDate': datetime.now().isoformat()}), 400

        db = get_db()
        event = ipn_data
        if type(ipn_data.get('total')) is float:
            # Compare the signed decimal token before any binary float rounding.
            event = dict(ipn_data, total=json.loads(raw_body, parse_float=str)['total'])
        accepted = _apply_back_status(
            db, order_ref, status, ipn_data.get('transactionId'), payload=event, is_ipn=True,
        )
        booking_row = (
            _fetch_booking_with_tour(db, order_ref)
            if accepted and status.upper() in ('SUCCESS', 'FINISHED') else None
        )
        db.commit()

        if booking_row:
            app = current_app._get_current_object()
            threading.Thread(
                target=_send_email_background, args=(app, dict(booking_row)), daemon=True,
            ).start()

        return _signed_ipn_response(simplepay, 200, ipn_data)

    except ReleasedAffiliatePayment:
        _record_released_payment(db, order_ref, 'ipn', ipn_data)
        return _signed_ipn_response(simplepay, 500, ipn_data)
    except PaymentCallbackMismatch as exc:
        db.rollback()
        logger.warning('SimplePay IPN rejected for %s: %s', order_ref, exc)
        return _signed_ipn_response(simplepay, 400, ipn_data)
    except Exception as e:
        if db is not None:
            db.rollback()
        logger.error("Error in IPN handler: %s", str(e), exc_info=True)
        return _signed_ipn_response(get_simplepay_service(), 500)


@bp.route('/success')
def payment_success():
    """Sikeres fizetés után visszairányítási oldal (signed SimplePay back payload)."""
    payload, order_ref = _decode_back_request()
    db = get_db()
    if payload and order_ref:
        _record_back_event(db, order_ref, 'back_success', payload)
    elif order_ref != session.get('pending_order_ref'):
        order_ref = None

    booking_row = _fetch_booking_with_tour(db, order_ref)
    if not booking_row or booking_row['payment_status'] != 'paid':
        return render_template('payment/success.html', payment_unconfirmed=True)

    _send_booking_confirmation_notification(db, booking_row)
    return render_template(
        'payment/success.html', booking=dict(booking_row), order_ref=order_ref,
        transaction_id=booking_row['transaction_id'],
    )


@bp.route('/fail')
def payment_fail():
    """Sikertelen fizetés visszairányítása aláírt paraméterekkel."""
    payload, order_ref = _decode_back_request()

    if payload and order_ref:
        db = get_db()
        _record_back_event(db, order_ref, 'back_fail', payload)
    elif order_ref:
        logger.warning("Fail redirect for %s missing signed payload; skipping DB updates", order_ref)

    transaction_id = payload.get('transactionId') if payload else None
    return render_template('payment/fail.html', order_ref=order_ref, transaction_id=transaction_id)


@bp.route('/cancel')
def payment_cancel():
    """Megszakított fizetés után visszairányítás aláírt paraméterekkel."""
    payload, order_ref = _decode_back_request()

    if payload and order_ref:
        db = get_db()
        _record_back_event(db, order_ref, 'back_cancel', payload)
    elif order_ref:
        logger.warning("Cancel redirect for %s missing signed payload; skipping DB updates", order_ref)

    return render_template('payment/cancel.html', order_ref=order_ref)


@bp.route('/timeout')
def payment_timeout():
    """Időtúllépés után visszairányítás aláírt paraméterekkel."""
    payload, order_ref = _decode_back_request()

    if payload and order_ref:
        db = get_db()
        _record_back_event(db, order_ref, 'back_timeout', payload)
    elif order_ref:
        logger.warning("Timeout redirect for %s missing signed payload; skipping DB updates", order_ref)

    return render_template('payment/timeout.html', order_ref=order_ref)


@bp.route('/sync', methods=['POST'])
def sync_transaction():
    """Admin-only endpoint to re-sync a transaction via SimplePay query API."""
    user = getattr(g, 'user', None)
    if not user or not user.get('is_admin'):
        abort(403)

    payload = request.get_json(silent=True) or request.form
    order_ref = payload.get('order_ref') or payload.get('orderRef')
    transaction_id = payload.get('transaction_id') or payload.get('transactionId')

    if not order_ref and not transaction_id:
        return jsonify({'success': False, 'error': 'order_ref or transaction_id is required'}), 400

    simplepay = get_simplepay_service()
    try:
        result = simplepay.query_transactions(
            order_refs=[order_ref] if order_ref else None,
            transaction_ids=[transaction_id] if transaction_id else None,
        )
    except Exception as exc:
        logger.error('SimplePay query failed: %s', exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 502

    entries = _extract_query_entries(result)
    db = get_db()
    synced: List[Dict[str, Any]] = []
    timestamp_key = f"query_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ref = entry.get('orderRef')
        provider_id = entry.get('transactionId')
        if 'merchant' in entry and entry['merchant'] != simplepay.merchant_id:
            continue
        if transaction_id and str(provider_id) != str(transaction_id):
            continue
        if ref is None and type(provider_id) in (str, int):
            match = db.execute(
                'SELECT order_ref FROM payment_transactions WHERE transaction_id = ?',
                (str(provider_id),),
            ).fetchall()
            if len(match) == 1:
                ref = match[0]['order_ref']
        if not isinstance(ref, str) or not ref or (order_ref and ref != order_ref):
            continue
        with db:
            try:
                applied = _apply_back_status(db, ref, entry.get('status'), provider_id, payload=entry)
            except ReleasedAffiliatePayment:
                _record_released_payment(db, ref, 'query', entry)
                continue
            except PaymentCallbackMismatch as exc:
                logger.warning('SimplePay query event rejected for %s: %s', ref, exc)
                continue
            if not applied:
                continue
            _store_response_payload(db, ref, timestamp_key, entry)
        synced.append({
            'order_ref': ref,
            'status': entry.get('status'),
            'transaction_id': provider_id,
        })

    return jsonify({'success': True, 'synced': synced, 'raw': result})


@bp.route('/status/<order_ref>')
def payment_status(order_ref):
    """
    Fizetés státusz lekérdezése (AJAX endpoint)
    """
    try:
        db = get_db()
        
        user = getattr(g, 'user', None)
        has_permission = False
        if user and user.get('is_admin'):
            has_permission = True
        elif session.get('pending_order_ref') == order_ref:
            has_permission = True

        if not has_permission:
            abort(403)

        transaction = db.execute(
            '''SELECT pt.*, b.payment_status as booking_status
               FROM payment_transactions pt
               JOIN bookings b ON pt.booking_id = b.id
               WHERE pt.order_ref = ?''',
            (order_ref,)
        ).fetchone()
        
        if transaction:
            return jsonify({
                'success': True,
                'status': transaction['status'],
                'booking_status': transaction['booking_status'],
                'transaction_id': transaction['transaction_id'],
                'amount': transaction['amount'],
                'currency': transaction['currency']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Tranzakció nem található'
            }), 404
            
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
