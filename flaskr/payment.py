"""
Payment Blueprint - SimplePay fizetési integráció
Kezeli a fizetési folyamatot és a SimplePay callback-eket
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for, 
    current_app, flash, jsonify, session
)
from flaskr.db import get_db
from flaskr.services.simplepay_service import SimplePayService
import json
import logging
from datetime import datetime
import os

bp = Blueprint('payment', __name__, url_prefix='/payment')
logger = logging.getLogger(__name__)


def get_simplepay_service():
    """SimplePay service példány létrehozása környezeti változókból"""
    merchant_id = os.environ.get('SIMPLEPAY_MERCHANT_ID', 'MERCHANT_ID_PLACEHOLDER')
    secret_key = os.environ.get('SIMPLEPAY_SECRET_KEY', 'SECRET_KEY_PLACEHOLDER')
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
    - invoice_*: Számlázási adatok
    """
    try:
        db = get_db()
        
        # Form adatok kinyerése
        tour_id = request.form.get('tour_id', type=int)
        customer_name = request.form.get('customer_name', '')
        customer_email = request.form.get('customer_email', '')
        customer_phone = request.form.get('customer_phone', '')
        participants_count = request.form.get('participants_count', 1, type=int)
        
        # Számlázási adatok
        invoice_data = {
            'name': request.form.get('invoice_name', customer_name),
            'country': request.form.get('invoice_country', 'hu'),
            'state': request.form.get('invoice_state', ''),
            'city': request.form.get('invoice_city', ''),
            'zip': request.form.get('invoice_zip', ''),
            'address': request.form.get('invoice_address', ''),
            'company': request.form.get('invoice_company', '')
        }
        
        # Validáció
        if not all([tour_id, customer_name, customer_email, customer_phone]):
            flash('Kérjük töltse ki az összes kötelező mezőt!', 'error')
            return redirect(url_for('main.index'))
        
        # Túra lekérdezése
        tour = db.execute(
            'SELECT * FROM tours WHERE id = ? AND is_active = 1',
            (tour_id,)
        ).fetchone()
        
        if not tour:
            flash('A kiválasztott túra nem található!', 'error')
            return redirect(url_for('main.index'))
        
        # Összeg számítása
        total_price = tour['price'] * participants_count
        
        # Foglalás létrehozása pending státusszal
        cursor = db.execute(
            '''INSERT INTO bookings (
                tour_id, order_ref, customer_name, customer_email, customer_phone,
                participants_count, total_price, payment_status, payment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                tour_id,
                'TEMP-' + datetime.now().strftime('%Y%m%d%H%M%S'),  # Ideiglenes, frissítjük
                customer_name,
                customer_email,
                customer_phone,
                participants_count,
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
            language='HU'
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
                'initiated',
                json.dumps(payment_data, ensure_ascii=False)
            )
        )
        db.commit()
        
        # Fizetés indítása SimplePay-nél
        success, payment_url, response_data = simplepay.start_payment(payment_data)
        
        # Response mentése
        db.execute(
            'UPDATE payment_transactions SET response_data = ?, updated_at = CURRENT_TIMESTAMP WHERE order_ref = ?',
            (json.dumps(response_data, ensure_ascii=False), order_ref)
        )
        db.commit()
        
        if success and payment_url:
            logger.info(f"Payment started successfully for booking {booking_id}, redirecting to SimplePay")
            # Átirányítás SimplePay fizetési oldalára
            return redirect(payment_url)
        else:
            # Hiba esetén
            error_msg = response_data.get('errorCodes', ['Ismeretlen hiba'])
            logger.error(f"Payment start failed for booking {booking_id}: {error_msg}")
            
            # Státusz frissítése
            db.execute(
                'UPDATE payment_transactions SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE order_ref = ?',
                ('fail', str(error_msg), order_ref)
            )
            db.execute(
                'UPDATE bookings SET payment_status = ? WHERE id = ?',
                ('failed', booking_id)
            )
            db.commit()
            
            flash(f'A fizetés indítása sikertelen: {", ".join(error_msg)}', 'error')
            return redirect(url_for('main.index'))
            
    except Exception as e:
        logger.error(f"Error in start_payment: {str(e)}", exc_info=True)
        flash('Hiba történt a fizetés indítása során!', 'error')
        return redirect(url_for('main.index'))


@bp.route('/ipn', methods=['POST'])
def ipn():
    """
    IPN (Instant Payment Notification) endpoint
    SimplePay server-to-server értesítés a fizetés státuszáról
    """
    try:
        # IPN adatok fogadása (JSON vagy form data)
        if request.is_json:
            ipn_data = request.get_json()
        else:
            ipn_data = request.form.to_dict()
        
        logger.info(f"IPN received: {json.dumps(ipn_data, ensure_ascii=False)}")
        
        # SimplePay service inicializálása
        simplepay = get_simplepay_service()
        
        # IPN feldolgozása és signature ellenőrzés
        success, status, verified_data = simplepay.process_ipn(ipn_data)
        
        if not success:
            logger.error(f"IPN verification failed: {status}")
            return jsonify({'receiveDate': datetime.now().isoformat()}), 400
        
        # Order referencia
        order_ref = ipn_data.get('orderRef', '')
        transaction_id = ipn_data.get('transactionId', '')
        
        db = get_db()
        
        # Payment transaction frissítése
        db.execute(
            '''UPDATE payment_transactions 
               SET status = ?, simplepay_transaction_id = ?, ipn_data = ?, updated_at = CURRENT_TIMESTAMP, paid_at = CURRENT_TIMESTAMP
               WHERE order_ref = ?''',
            (status.lower(), transaction_id, json.dumps(ipn_data, ensure_ascii=False), order_ref)
        )
        
        # Booking státusz frissítése
        if status == 'SUCCESS':
            db.execute(
                '''UPDATE bookings 
                   SET payment_status = 'paid', transaction_id = ?, payment_date = CURRENT_TIMESTAMP
                   WHERE order_ref = ?''',
                (transaction_id, order_ref)
            )
            logger.info(f"Payment successful for order {order_ref}")
        elif status in ['FAIL', 'TIMEOUT', 'CANCELLED']:
            db.execute(
                'UPDATE bookings SET payment_status = ? WHERE order_ref = ?',
                (status.lower(), order_ref)
            )
            logger.info(f"Payment {status.lower()} for order {order_ref}")
        
        db.commit()
        
        # SimplePay-nek kötelező válasz
        return jsonify({'receiveDate': datetime.now().isoformat()}), 200
        
    except Exception as e:
        logger.error(f"Error in IPN handler: {str(e)}", exc_info=True)
        return jsonify({'receiveDate': datetime.now().isoformat(), 'error': str(e)}), 500


@bp.route('/success')
def payment_success():
    """Sikeres fizetés után visszairányítási oldal"""
    # Query paraméterekből order ref
    order_ref = request.args.get('r', '')
    
    if order_ref:
        db = get_db()
        booking = db.execute(
            '''SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time
               FROM bookings b
               JOIN tours t ON b.tour_id = t.id
               WHERE b.order_ref = ?''',
            (order_ref,)
        ).fetchone()
        
        return render_template('payment/success.html', booking=booking, order_ref=order_ref)
    
    return render_template('payment/success.html', booking=None, order_ref=order_ref)


@bp.route('/fail')
def payment_fail():
    """Sikertelen fizetés után visszairányítási oldal"""
    order_ref = request.args.get('r', '')
    return render_template('payment/fail.html', order_ref=order_ref)


@bp.route('/cancel')
def payment_cancel():
    """Megszakított fizetés után visszairányítási oldal"""
    order_ref = request.args.get('r', '')
    
    if order_ref:
        # Booking státusz frissítése
        db = get_db()
        db.execute(
            'UPDATE bookings SET payment_status = ? WHERE order_ref = ?',
            ('cancelled', order_ref)
        )
        db.execute(
            'UPDATE payment_transactions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE order_ref = ?',
            ('cancelled', order_ref)
        )
        db.commit()
    
    return render_template('payment/cancel.html', order_ref=order_ref)


@bp.route('/timeout')
def payment_timeout():
    """Időtúllépés után visszairányítási oldal"""
    order_ref = request.args.get('r', '')
    
    if order_ref:
        # Booking státusz frissítése
        db = get_db()
        db.execute(
            'UPDATE bookings SET payment_status = ? WHERE order_ref = ?',
            ('timeout', order_ref)
        )
        db.execute(
            'UPDATE payment_transactions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE order_ref = ?',
            ('timeout', order_ref)
        )
        db.commit()
    
    return render_template('payment/timeout.html', order_ref=order_ref)


@bp.route('/status/<order_ref>')
def payment_status(order_ref):
    """
    Fizetés státusz lekérdezése (AJAX endpoint)
    """
    try:
        db = get_db()
        
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
                'transaction_id': transaction['simplepay_transaction_id'],
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
