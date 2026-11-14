import sys, os
sys.path.insert(0, '/app')
os.chdir('/app')
from flaskr import create_app
from flaskr.db import get_db
from flaskr.payment import _fetch_booking_with_tour
from flaskr.services.email_service import get_email_service

app = create_app()
with app.app_context():
    db = get_db()
    row = _fetch_booking_with_tour(db, 'ORDER-B21-1781952610')
    booking = dict(row)
    print("Fetched booking. Calling send_booking_confirmation...", flush=True)
    svc = get_email_service()
    
    # We will step into it manually to see where it hangs
    tour_title = booking.get("tour_title") or "Ismeretlen túra"
    order_ref = booking.get("order_ref") or "n/a"
    print("Generating tour token...", flush=True)
    
    tour_id = booking.get('tour_id')
    if tour_id and order_ref and order_ref != 'n/a':
        try:
            from flaskr.main import generate_tour_token
            secret_key = app.config['SECRET_KEY']
            token = generate_tour_token(secret_key, tour_id, order_ref)
            print("Token generated:", token, flush=True)
        except Exception as e:
            print("Token generation failed:", e, flush=True)

    print("Building HTML body...", flush=True)
    # just basic send
    customer_email = (booking.get("customer_email") or "").strip()
    print("Customer email is:", customer_email, flush=True)
    
    print("Sending via _send...", flush=True)
    try:
        svc.send_booking_confirmation(booking)
        print("Success!")
    except Exception as e:
        print("Exception:", e)
