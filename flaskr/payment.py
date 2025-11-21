"""
Payment Blueprint - SimplePay fizetési integráció
Kezeli a fizetési folyamatot és a SimplePay callback-eket
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, abort, g
)
from flaskr.db import get_db
from flaskr.services.simplepay_service import SimplePayService
import json
import logging
from datetime import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

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


def _apply_back_status(db, order_ref: Optional[str], status: Optional[str], transaction_id: Optional[str]) -> None:
    """Update booking and transaction rows based on signed back redirect payloads."""
    if not order_ref or not status:
        return
    normalized = status.upper()
    tx_status = normalized.lower()
    if normalized not in {'SUCCESS', 'FAIL', 'TIMEOUT', 'CANCELLED'}:
        logger.debug("Ignoring back status %s for order %s", normalized, order_ref)
        return
    db.execute(
        '''UPDATE payment_transactions
           SET status = ?, transaction_id = COALESCE(?, transaction_id), updated_at = CURRENT_TIMESTAMP
           WHERE order_ref = ?''',
        (tx_status, transaction_id, order_ref)
    )
    if normalized == 'SUCCESS':
        db.execute(
            '''UPDATE bookings
               SET payment_status = 'paid', transaction_id = COALESCE(?, transaction_id),
                   payment_date = COALESCE(payment_date, CURRENT_TIMESTAMP)
               WHERE order_ref = ?''',
            (transaction_id, order_ref)
        )
    else:
        db.execute(
            'UPDATE bookings SET payment_status = ? WHERE order_ref = ?',
            (tx_status, order_ref)
        )


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
        except Exception as exc:
            logger.error('Failed to decode SimplePay back payload: %s', exc)
    if not order_ref:
        order_ref = request.args.get('order_ref') or request.args.get('orderRef') or session.get('pending_order_ref')
    return payload, order_ref


def _extract_query_entries(result: Dict[str, Any], order_ref: Optional[str], transaction_id: Optional[str]) -> List[Dict[str, Any]]:
    """Normalize SimplePay query responses into a list of transaction entries."""
    if not isinstance(result, dict):
        return []
    for key in ('transactions', 'results', 'data', 'items'):
        entries = result.get(key)
        if isinstance(entries, list):
            return entries
        if isinstance(entries, dict):
            return [entries]
    if order_ref or transaction_id:
        entry = dict(result)
        if order_ref and 'orderRef' not in entry:
            entry['orderRef'] = order_ref
        if transaction_id and 'transactionId' not in entry:
            entry['transactionId'] = transaction_id
        return [entry]
    return []


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
            'state': request.form.get('invoice_state', ''),
            'city': invoice_city,
            'zip': invoice_zip,
            'address': invoice_address,
            'company': request.form.get('invoice_company', '')
        }
        
        # Túra lekérdezése
        tour = db.execute(
            'SELECT * FROM tours WHERE id = ? AND is_active = 1',
            (tour_id,)
        ).fetchone()
        
        if not tour:
            flash('A kiválasztott túra nem található!', 'error')
            return redirect(url_for('index'))
        
        # Összeg számítása
        total_price = tour['price'] * participants_count
        
        # Foglalás létrehozása pending státusszal
        lifejacket_sizes_json = json.dumps(lifejacket_sizes, ensure_ascii=False)
        cursor = db.execute(
            '''INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email, customer_phone,
                participants_count, lifejacket_sizes, total_price, payment_status, payment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                tour_id,
                'TEMP-' + datetime.now().strftime('%Y%m%d%H%M%S'),  # Ideiglenes, frissítjük
                customer_name,
                customer_email,
                customer_phone,
                participants_count,
                lifejacket_sizes_json,
                total_price,
                'pending',
                'simplepay'
            )
        )
        db.commit()
        
        booking_id = cursor.lastrowid
        
        # SimplePay service inicializálása
        simplepay = get_simplepay_service()
        
        # Order referencia generálása
        order_ref = simplepay.generate_order_ref(booking_id)
        
        # Booking frissítése order ref-fel
        db.execute(
            'UPDATE bookings SET order_ref = ? WHERE id = ?',
            (order_ref, booking_id)
        )
        db.commit()
        
        # SimplePay callback URL-ek
        base_url = request.host_url.rstrip('/')
        success_url = f"{base_url}{url_for('payment.payment_success')}"
        fail_url = f"{base_url}{url_for('payment.payment_fail')}"
        cancel_url = f"{base_url}{url_for('payment.payment_cancel')}"
        timeout_url = f"{base_url}{url_for('payment.payment_timeout')}"
        
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
            language='HU',
            timeout_minutes=20  # Webes vásárlás alapértelmezett timeout
        )
        
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
        
        # Fizetés indítása SimplePay-nél
        success, payment_url, response_data = simplepay.start_payment(payment_data)
        
        # Response mentése
        if response_data:
            _store_response_payload(db, order_ref, 'start', response_data)
            db.commit()
        
        if success and payment_url:
            logger.info(f"Payment started successfully for booking {booking_id}, redirecting to SimplePay")
            # Order ref session-be mentése a visszatéréshez
            session['pending_order_ref'] = order_ref
            db.execute(
                '''UPDATE payment_transactions
                   SET status = ?, simplepay_payment_url = ?, error_message = NULL,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE order_ref = ?''',
                ('pending', payment_url, order_ref)
            )
            db.commit()
            # Átirányítás SimplePay fizetési oldalára
            return redirect(payment_url)
        else:
            # Hiba esetén
            error_codes = response_data.get('errorCodes', ['Ismeretlen hiba'])
            # Stringgé konvertálás, ha számok
            error_msg = [str(code) for code in error_codes]
            # Emberi nyelvű hibaüzenetek
            human_errors = [get_error_message(code) for code in error_msg]
            logger.error(f"Payment start failed for booking {booking_id}: {error_msg} - {human_errors}")
            
            # Státusz frissítése
            db.execute(
                '''UPDATE payment_transactions
                   SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE order_ref = ?''',
                ('fail', ', '.join(error_msg), order_ref)
            )
            db.execute(
                'UPDATE bookings SET payment_status = ? WHERE id = ?',
                ('failed', booking_id)
            )
            db.commit()
            
            flash(f'A fizetés indítása sikertelen. {" | ".join(human_errors)}', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f"Error in start_payment: {str(e)}", exc_info=True)
        flash('Hiba történt a fizetés indítása során!', 'error')
        return redirect(url_for('index'))


@bp.route('/ipn', methods=['POST'])
def ipn():
    """IPN (Instant Payment Notification) endpoint with header-based signature validation."""
    try:
        raw_body = request.get_data() or b''
        signature = request.headers.get(SimplePayService.HEADER_SIGNATURE, '')
        simplepay = get_simplepay_service()

        success, status, ipn_data = simplepay.process_ipn(raw_body, signature)
        if not success or not ipn_data:
            logger.error("IPN verification failed: %s", status)
            return jsonify({'receiveDate': datetime.now().isoformat()}), 400

        logger.info("Verified IPN payload: %s", json.dumps(ipn_data, ensure_ascii=False))

        order_ref = ipn_data.get('orderRef')
        transaction_id = ipn_data.get('transactionId')
        if not order_ref:
            logger.error("IPN payload missing orderRef")
            return jsonify({'receiveDate': datetime.now().isoformat()}), 400

        db = get_db()
        merged_ipn = _merge_json_blob(None, 'ipn', ipn_data)
        db.execute(
            '''UPDATE payment_transactions
               SET status = ?, transaction_id = ?, ipn_data = ?, updated_at = CURRENT_TIMESTAMP,
                   paid_at = CASE WHEN ? = 'SUCCESS' THEN CURRENT_TIMESTAMP ELSE paid_at END
               WHERE order_ref = ?''',
            (status.lower(), transaction_id, merged_ipn, status.upper(), order_ref)
        )

        if status.upper() == 'SUCCESS':
            db.execute(
                '''UPDATE bookings
                   SET payment_status = 'paid', transaction_id = ?, payment_date = CURRENT_TIMESTAMP
                   WHERE order_ref = ?''',
                (transaction_id, order_ref)
            )
            logger.info("Payment successful for order %s", order_ref)
        elif status.upper() in ['FAIL', 'TIMEOUT', 'CANCELLED']:
            db.execute(
                'UPDATE bookings SET payment_status = ? WHERE order_ref = ?',
                (status.lower(), order_ref)
            )
            logger.info("Payment %s for order %s", status.lower(), order_ref)

        db.commit()
        return jsonify({'receiveDate': datetime.now().isoformat()}), 200

    except Exception as e:
        logger.error("Error in IPN handler: %s", str(e), exc_info=True)
        return jsonify({'receiveDate': datetime.now().isoformat(), 'error': str(e)}), 500


@bp.route('/success')
def payment_success():
    """Sikeres fizetés után visszairányítási oldal (signed SimplePay back payload)."""
    payload, order_ref = _decode_back_request()
    db = get_db()
    booking = None

    if order_ref:
        booking = db.execute(
            '''SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time
               FROM bookings b
               JOIN tours t ON b.tour_id = t.id
               WHERE b.order_ref = ?''',
            (order_ref,)
        ).fetchone()

    if payload and order_ref:
        _store_response_payload(db, order_ref, 'back_success', payload)
        _apply_back_status(db, order_ref, payload.get('status'), payload.get('transactionId'))
        db.commit()
    elif order_ref:
        logger.warning("Success redirect for %s missing signed payload; skipping DB updates", order_ref)

    return render_template('payment/success.html', booking=booking, order_ref=order_ref)


@bp.route('/fail')
def payment_fail():
    """Sikertelen fizetés visszairányítása aláírt paraméterekkel."""
    payload, order_ref = _decode_back_request()

    if payload and order_ref:
        db = get_db()
        _store_response_payload(db, order_ref, 'back_fail', payload)
        _apply_back_status(db, order_ref, payload.get('status', 'FAIL'), payload.get('transactionId'))
        db.commit()
    elif order_ref:
        logger.warning("Fail redirect for %s missing signed payload; skipping DB updates", order_ref)

    return render_template('payment/fail.html', order_ref=order_ref)


@bp.route('/cancel')
def payment_cancel():
    """Megszakított fizetés után visszairányítás aláírt paraméterekkel."""
    payload, order_ref = _decode_back_request()

    if payload and order_ref:
        db = get_db()
        _store_response_payload(db, order_ref, 'back_cancel', payload)
        _apply_back_status(db, order_ref, payload.get('status', 'CANCELLED'), payload.get('transactionId'))
        db.commit()
    elif order_ref:
        logger.warning("Cancel redirect for %s missing signed payload; skipping DB updates", order_ref)

    return render_template('payment/cancel.html', order_ref=order_ref)


@bp.route('/timeout')
def payment_timeout():
    """Időtúllépés után visszairányítás aláírt paraméterekkel."""
    payload, order_ref = _decode_back_request()

    if payload and order_ref:
        db = get_db()
        _store_response_payload(db, order_ref, 'back_timeout', payload)
        _apply_back_status(db, order_ref, payload.get('status', 'TIMEOUT'), payload.get('transactionId'))
        db.commit()
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

    entries = _extract_query_entries(result, order_ref, transaction_id)
    db = get_db()
    synced: List[Dict[str, Any]] = []
    timestamp_key = f"query_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    for entry in entries:
        ref = entry.get('orderRef') or order_ref
        if not ref:
            continue
        _store_response_payload(db, ref, timestamp_key, entry)
        _apply_back_status(db, ref, entry.get('status'), entry.get('transactionId'))
        synced.append({
            'order_ref': ref,
            'status': entry.get('status'),
            'transaction_id': entry.get('transactionId')
        })

    if synced:
        db.commit()
    elif order_ref:
        _store_response_payload(db, order_ref, timestamp_key, result)
        db.commit()

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
