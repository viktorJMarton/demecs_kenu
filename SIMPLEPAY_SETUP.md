# SimplePay Payment Integration - Setup Guide

## Bevezetés

Ez a projekt SimplePay 2.x API-t használó fizetési rendszert integrál a túrafoglalási rendszerbe. 
Az implementáció a SimplePay hivatalos dokumentációja (PaymentService_SimplePay_2.x_Payment_HU) alapján készült.

## Előfeltételek

1. **SimplePay Merchant Account**
   - Regisztráció az OTP SimplePay rendszerében
   - Merchant ID és Secret Key megszerzése
   - Test és Live környezet hozzáférés

2. **HTTPS kötelező**
   - SimplePay csak HTTPS kapcsolaton keresztül működik
   - Development környezetben használhatsz ngrok-ot vagy localhost tunnel-t

## Timeout Beállítások (SimplePay PDF szerint)

- **Webes vásárlás (IPEW)**: 20 perc ✅ (implementálva)
- **Fizikai eladóhely (IPPS)**: 10 perc
- **Számlák**: 60-180 nap (típustól függően)
- **Alapértelmezett**: 5 perc (ha nincs megadva)

## Telepítés és Konfiguráció

### 1. Környezeti Változók Beállítása

Másold le a `.env.example` fájlt `.env` néven:

```bash
cp .env.example .env
```

Szerkeszd a `.env` fájlt és add meg a SimplePay adatokat:

```env
SIMPLEPAY_MERCHANT_ID=your_actual_merchant_id
SIMPLEPAY_SECRET_KEY=your_actual_secret_key
SIMPLEPAY_SANDBOX=true  # false az éles környezethez
```

### 2. Adatbázis Migráció

Futtasd le az adatbázis inicializálást a payment_transactions táblával:

```bash
flask --app flaskr init-db
```

Vagy ha már létezik az adatbázis, add hozzá a payment_transactions táblát:

```sql
-- Lásd schema.sql payment_transactions táblát
```

### 3. Python Függőségek

Telepítsd a szükséges csomagokat:

```bash
pip install requests python-dotenv
```

## Használat

### Fizetési Folyamat

1. **Túra kiválasztása** - Felhasználó kiválaszt egy túrát
2. **Foglalási űrlap kitöltése** - Név, email, telefon, résztvevők száma, számlázási adatok
3. **POST /payment/start** - Fizetés indítása
4. **Átirányítás SimplePay-re** - Felhasználó a SimplePay oldalon fizet
5. **IPN értesítés** - SimplePay POST /payment/ipn-re értesít a tranzakció státuszáról
6. **Visszairányítás** - Felhasználó visszajön a success/fail/cancel oldalra

### API Endpoints

```
POST   /payment/start          - Fizetés indítása
POST   /payment/ipn            - IPN notification (SimplePay server-to-server)
GET    /payment/success        - Sikeres fizetés oldal
GET    /payment/fail           - Sikertelen fizetés oldal
GET    /payment/cancel         - Megszakított fizetés oldal
GET    /payment/timeout        - Időtúllépés oldal
GET    /payment/status/<ref>   - Fizetési státusz lekérdezés (AJAX)
```

### Példa Booking Form

```html
<form action="{{ url_for('payment.start_payment') }}" method="POST">
  <input type="hidden" name="tour_id" value="{{ tour.id }}">
  
  <input type="text" name="customer_name" placeholder="Teljes név" required>
  <input type="email" name="customer_email" placeholder="Email" required>
  <input type="tel" name="customer_phone" placeholder="Telefonszám" required>
  <input type="number" name="participants_count" value="1" min="1" required>
  
  <!-- Számlázási adatok -->
  <input type="text" name="invoice_name" placeholder="Számlázási név">
  <input type="text" name="invoice_city" placeholder="Város" required>
  <input type="text" name="invoice_zip" placeholder="Irányítószám" required>
  <input type="text" name="invoice_address" placeholder="Cím" required>
  
  <button type="submit">Fizetés</button>
</form>
```

## SimplePay Test Adatok

### Test Kártyaszámok (Sandbox környezet)

**Sikeres teszt tranzakció:**
```
Kártyaszám: 4908 3660 9990 0425
Lejárat: bármilyen jövőbeli dátum (pl: 12/30)
CVC: bármilyen 3 számjegy (pl: 123)
```

**Sikertelen teszt tranzakció:**
```
Kártyaszám: 4908 3660 9990 0177
Lejárat: bármilyen jövőbeli dátum
CVC: bármilyen 3 számjegy
```

## Logging és Monitoring

A SimplePay service részletes logokat ír:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Fontos log pontok:
- Payment start request/response
- IPN notification adatok
- Signature verification eredménye
- Tranzakció státusz változások

## Élesítés Előtti Checklist

- [ ] HTTPS konfiguráció éles szerverhez
- [ ] Éles SimplePay API kulcsok beállítása
- [ ] `SIMPLEPAY_SANDBOX=false` beállítása
- [ ] IPN URL nyilvánosan elérhető és HTTPS
- [ ] BACK URL-ek (success, fail, cancel, timeout) működnek
- [ ] Email értesítések konfigurálva (opcionális)
- [ ] Error handling és logging beállítva
- [ ] Adatvédelmi nyilatkozat frissítve
- [ ] SimplePay logó és feltételek a checkout oldalon

## Troubleshooting

### "Signature verification failed"
- Ellenőrizd hogy a SECRET_KEY helyes
- Ellenőrizd hogy az adatok sorrendje megegyezik a dokumentációban leírtakkal
- Debug logban nézd meg a signature base stringet

### "IPN nem érkezik meg"
- Ellenőrizd hogy a /payment/ipn URL nyilvánosan elérhető
- Ellenőrizd hogy HTTPS-en fut
- SimplePay admin felületen ellenőrizd az IPN URL-t

### "Payment URL nem jön vissza"
- Ellenőrizd a START request response-t a logban
- Ellenőrizd hogy a Merchant ID és Secret Key helyes
- Sandbox/Live környezet megfelelő

## Biztonsági Megfontolások

1. **SECRET_KEY védelme** - Soha ne committolj a titkos kulcsot a git-be
2. **IPN signature ellenőrzés** - Mindig ellenőrizd az IPN signature-t
3. **HTTPS használat** - Kötelező éles környezetben
4. **SQL injection védelem** - Paraméteres query-k használata
5. **XSS védelem** - Input sanitization
6. **CSRF védelem** - Flask-WTF használata form-okhoz

## További Információk

- [SimplePay API Dokumentáció](https://simplepay.hu/fejlesztoknek/)
- [SimplePay Admin Felület](https://admin.simplepay.hu/)
- SimplePay Támogatás: fejleszto@simplepay.hu

## Licensz

Proprietary - OTP SimplePay felhasználási feltételek szerint
