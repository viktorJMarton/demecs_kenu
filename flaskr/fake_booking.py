import sys
import os
import json
import datetime
from urllib.parse import urlencode

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flaskr import create_app
from flaskr.db import get_db
from flaskr.payment import get_simplepay_service

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False

def run_fake_booking():
    with app.app_context():
        db = get_db()
        
        # 1. Keresünk egy létező aktív túrát
        tour = db.execute("SELECT id FROM tours WHERE is_active = 1 AND date > date('now') LIMIT 1").fetchone()
        if not tour:
            print("Nincs aktív túra az adatbázisban.")
            return
            
        tour_id = tour['id']
        order_ref = f"ORDER-FAKE-{int(datetime.datetime.now().timestamp())}"
        
        print(f"[*] Kamu foglalás létrehozása: {order_ref}")
        
        # 2. Beszúrjuk a foglalást a DB-be
        cursor = db.execute('''
            INSERT INTO bookings (
                tour_id, customer_name, customer_email, customer_phone,
                participants_count, total_price, payment_status, order_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (tour_id, 'Kamu Tesztelő', 'martonviktor666@gmail.com', '+36301234567', 1, 5000, 'pending', order_ref))
        booking_id = cursor.lastrowid
        
        # 3. Beszúrjuk a payment_transactions-be
        db.execute('''
            INSERT INTO payment_transactions (booking_id, order_ref, status, amount, currency)
            VALUES (?, ?, ?, ?, ?)
        ''', (booking_id, order_ref, 'init', 5000, 'HUF'))
        
        db.commit()
        
        # 4. Generálunk egy sikeres IPN payload-ot
        simplepay = get_simplepay_service()
        ipn_data = {
            "salt": "fakesalt12345678",
            "orderRef": order_ref,
            "method": "CARD",
            "merchant": simplepay.merchant_id,
            "finishDate": datetime.datetime.now().isoformat(),
            "paymentDate": datetime.datetime.now().isoformat(),
            "transactionId": 999999999,
            "status": "FINISHED" # SimplePay uses FINISHED or SUCCESS depending on the endpoint. For IPN, FINISHED is normal.
        }
        
        print("[*] Szimuláljuk a sikeres IPN hívást (belső függvények meghívása)...")
        from flaskr.payment import _force_booking_paid, _send_booking_confirmation_notification
        
        # Frissítjük a DB-t paid-re, ahogy az IPN tenné
        _force_booking_paid(db, order_ref, 999999999)
        db.commit()
        
        # Lekérjük a friss adatokat
        from flaskr.payment import _fetch_booking_with_tour
        booking_row = _fetch_booking_with_tour(db, order_ref)
        
        # Kiküldjük az emailt, ahogy az IPN tenné
        print("[*] Email küldés indítása...")
        _send_booking_confirmation_notification(db, booking_row)
                
        print("[*] Végigvitel kész!")

if __name__ == "__main__":
    run_fake_booking()
