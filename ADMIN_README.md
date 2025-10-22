# 🚀 Kajak-Kenu Admin Rendszer

## 📋 Áttekintés

Komplett admin felület a kajak-kenu túrák és foglalások kezeléséhez, SimplePay fizetési integráció támogatással.

## 🛠️ Telepítés és indítás

### 1. Adatbázis inicializálása
```bash
python init_db.py
```

### 2. Flask alkalmazás indítása
```bash
export FLASK_APP=flaskr
export FLASK_ENV=development
flask run
```

### 3. Admin felület elérése
- **Admin Dashboard**: http://localhost:5000/admin
- **Főoldal**: http://localhost:5000
- **Fizetés teszt**: http://localhost:5000/payment-test

## 🎯 Funkciók

### 📊 Dashboard
- **Statisztikák**: Túrák száma, foglalások, bevétel
- **Legközelebbi túrák**: Áttekintés a közelgő túrákról
- **Gyors műveletek**: Linkek a legfontosabb funkciókhoz

### 🗺️ Túrák kezelése (`/admin/tours`)
- ✅ **Túrák listázása** szűrési opciókkal
- ✅ **Új túra hozzáadása** teljes adatokkal
- ✅ **Túra szerkesztése** élő előnézettel
- ✅ **Túra törlése** (inaktiválás) biztonsági ellenőrzéssel
- 📋 **Részletes adatok**: dátum, idő, ár, nehézség, helyszín

### 📅 Foglalások kezelése (`/admin/bookings`)
- ✅ **Foglalások listázása** fejlett szűrőkkel
- ✅ **Részletes foglalás nézet** minden adattal
- ✅ **Státusz kezelés**: függőben → fizetve → lemondva stb.
- 📊 **Statisztikák**: bevétel, státusz szerinti bontás
- 🔍 **Keresés**: név, email, rendelésszám alapján

### 💳 Fizetési integráció
- ✅ **SimplePay integrációs** teljes PDF implementáció alapján
- ✅ **Sandbox tesztelés** működő endpoint-okkal
- ✅ **Callback kezelés** minden fizetési státuszhoz
- ✅ **IPN támogatás** valós idejű értesítésekhez

## 📁 Adatbázis séma

### `tours` tábla
```sql
- id, title, description, date, time, duration
- max_participants, price, difficulty, location, distance
- meeting_point, equipment_included, what_to_bring
- is_active, created_at, updated_at
```

### `bookings` tábla
```sql
- id, tour_id, order_ref, customer_name, customer_email, customer_phone
- participants_count, total_price, payment_status, payment_method
- customer_notes, special_requirements, emergency_contact
- booking_date, payment_date, cancellation_date, admin_notes
```

## 🎨 UI/UX jellemzők

- **Responsive design** - minden eszközön optimális
- **DaisyUI komponensek** - modern és egységes megjelenés
- **Toast értesítések** - felhasználóbarát visszajelzések
- **Modal ablakok** - megerősítő dialógusok
- **Élő előnézet** - túra szerkesztésnél
- **Fejlett szűrők** - gyors adatkeresés

## 🔧 API Endpoints

### Admin API-k
- `GET /admin/api/tours` - Túrák JSON listája
- `GET /admin/api/bookings/stats` - Foglalási statisztikák

### Fizetési API-k
- `POST /pay` - Fizetés indítása
- `GET /payment-success` - Sikeres fizetés
- `GET /payment-fail` - Sikertelen fizetés
- `POST /payment-ipn` - SimplePay IPN callback

### Nyilvános API-k
- `GET /api/tour/<id>` - Túra részletek (frontend számára)

## 🛡️ Biztonsági funkciók

- **CSRF védelem** - session alapú token
- **SQL injection védelem** - paraméteres lekérdezések
- **Signature ellenőrzés** - SimplePay kommunikációban
- **Input validáció** - minden form mezőre
- **Státusz ellenőrzés** - törlés előtt aktív foglalások

## 📱 Mobil optimalizáció

- **Reszponzív layout** - minden képernyőmérethez
- **Touch-friendly** vezérlők
- **Kompakt táblázatok** - görgetés támogatással
- **Modal tervezés** - mobil barát

## 🚀 Gyors műveletek

### Új túra hozzáadása
1. Admin → Túrák → "Új túra"
2. Kitöltés (cím, dátum, ár kötelező)
3. Élő előnézet ellenőrzése
4. Mentés

### Foglalás kezelése
1. Admin → Foglalások
2. Szűrés túra/státusz szerint
3. Kattintás a foglalásra → részletek
4. Státusz frissítése egy kattintással

### Fizetés tesztelése
1. Navigálás: /payment-test
2. Összeg és email megadása
3. "Fizetés indítása" → SimplePay redirect
4. Sandbox fizetés szimulálása

## 🔄 Státusz kezelés

### Túra státuszok
- **Aktív**: Látható és foglalható
- **Inaktív**: Archivált, nem látható

### Foglalási státuszok
- **pending**: Várakozik fizetésre
- **paid**: Sikeres fizetés
- **failed**: Sikertelen fizetés
- **cancelled**: Lemondva
- **refunded**: Visszatérítve

## 📈 Jövőbeli fejlesztések

- [ ] Email értesítések automatizálása
- [ ] PDF számla generálás
- [ ] Térkép integráció túra helyszínekhez
- [ ] Képfeltöltés túrákhoz
- [ ] Exportálás CSV/Excel formátumban
- [ ] Felhasználó authentikáció
- [ ] Többnyelvű támogatás

---

## 🆘 Hibaelhárítás

### Adatbázis hiba
```bash
# Újra inicializálás
rm kajak_kenu.db
python init_db.py
```

### Import hibák
```bash
# Függőségek telepítése
pip install flask requests
```

### SimplePay teszt hibák
- Ellenőrizd a merchant ID-t és secret key-t
- Sandbox környezet használata kötelező teszteléshez

---

**Készítve**: Flask + DaisyUI + TailwindCSS  
**Adatbázis**: SQLite  
**Fizetés**: SimplePay Payment Service 2.x