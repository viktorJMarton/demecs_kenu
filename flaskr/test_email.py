import sys
import os
import smtplib
from email.message import EmailMessage

# Flask app betöltése a szolgáltatások eléréséhez
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flaskr import create_app
from flaskr.services.email_service import get_email_service

def test_smtp_connection(svc):
    print("\n[1] SMTP kapcsolat tesztelése...")
    try:
        with smtplib.SMTP(svc._config.smtp_host, svc._config.smtp_port, timeout=10) as server:
            if svc._config.use_tls:
                server.starttls()
            server.login(svc._config.smtp_username, svc._config.smtp_password)
            print("  ✅ Sikeres bejelentkezés az SMTP szerverre!")
            return True
    except Exception as e:
        print(f"  ❌ SMTP hiba: {e}")
        return False

def test_plain_text(svc, target_email):
    print(f"\n[2] Egyszerű szöveges email küldése a(z) {target_email} címre...")
    msg = EmailMessage()
    msg['Subject'] = 'Debug Teszt: Sima szöveg'
    msg['From'] = svc._config.sender
    msg['To'] = target_email
    msg.set_content('Ez egy sima szöveges email. Ha ez átmegy, az SMTP rendben van, és nincsenek blokkolva a sima levelek.')
    
    try:
        svc._send(msg)
        print("  ✅ Elküldve!")
    except Exception as e:
        print(f"  ❌ Hiba küldés közben: {e}")

def test_basic_html(svc, target_email):
    print(f"\n[3] Alap HTML email küldése a(z) {target_email} címre...")
    msg = EmailMessage()
    msg['Subject'] = 'Debug Teszt: Alap HTML'
    msg['From'] = svc._config.sender
    msg['To'] = target_email
    msg.set_content('Sima szöveges változat')
    msg.add_alternative('<html><body><h1>Alap HTML</h1><p>Ez egy nagyon alap HTML levél semmi formázással.</p></body></html>', subtype='html')
    
    try:
        svc._send(msg)
        print("  ✅ Elküldve!")
    except Exception as e:
        print(f"  ❌ Hiba küldés közben: {e}")

def test_full_booking_confirmation(svc, target_email):
    print(f"\n[4] Teljes éles Visszaigazoló Sablon (send_booking_confirmation) küldése...")
    # Létrehozunk egy kamu foglalást
    dummy_booking = {
        'customer_email': target_email,
        'customer_name': 'Teszt Elek',
        'customer_phone': '+36301234567',
        'tour_title': 'Debug Szigetköz Teszt',
        'tour_date': '2026-07-01',
        'tour_time': '10:00',
        'participants': 2,
        'order_ref': 'ORDER-DEBUG-12345',
        'total_price': 15000,
        'currency': 'HUF'
    }
    
    try:
        # Meghívjuk a tényleges éles metódust
        svc.send_booking_confirmation(dummy_booking)
        print("  ✅ A send_booking_confirmation sikeresen lefutott, a levél kiment a Google SMTP-re!")
    except Exception as e:
        print(f"  ❌ Hiba a teljes sablon küldésekor: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Használat: docker exec -it kajak-kenu_kajak-kenu_1 python3 /app/scripts/test_email.py <cel_email_cim>")
        sys.exit(1)
        
    target = sys.argv[1]
    
    app = create_app()
    with app.app_context():
        svc = get_email_service()
        
        print(f"E-mail szolgáltatás inicializálva. Feladó: {svc._config.sender}")
        
        if test_smtp_connection(svc):
            test_plain_text(svc, target)
            test_basic_html(svc, target)
            test_full_booking_confirmation(svc, target)
        
        print("\n[!] Ha a script lefutott, de a levelek nem érkeznek meg (Spamba sem),")
        print("    akkor a Google szervere némán eldobja őket a tartalmuk miatt.")
