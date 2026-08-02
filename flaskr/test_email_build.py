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
    print("Sending actual email to customer...", flush=True)
    svc = get_email_service()
    
    try:
        svc.send_booking_confirmation(booking)
        print("Successfully sent full booking confirmation!")
    except Exception as e:
        print("Failed with Exception:", e)
        import traceback
        traceback.print_exc()
