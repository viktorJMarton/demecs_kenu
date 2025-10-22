# 🔐 Admin Authentikációs Rendszer - Teszt Útmutató

## 📋 Bejelentkezési adatok

### Teszt admin felhasználók:
1. **Fő admin:**
   - Felhasználónév: `admin`
   - Jelszó: `admin123`

2. **Kajak admin:**
   - Felhasználónév: `kajak_admin` 
   - Jelszó: `kajak2025`

## 🚀 Tesztelési lépések

### 1. Alkalmazás indítása
```bash
export FLASK_APP=flaskr
flask run
```

### 2. Admin felület elérése
- **Bejelentkezés nélkül**: `http://localhost:5000/admin` → Átirányít login oldalra
- **Login oldal**: `http://localhost:5000/auth/login`
- **Dashboard (bejelentkezés után)**: `http://localhost:5000/admin`

### 3. Tesztelendő funkciók

#### ✅ Bejelentkezés
1. Nyisd meg: `http://localhost:5000/admin`
2. Automatikus átirányítás a login oldalra
3. Bejelentkezés: `admin` / `admin123`
4. Sikeres átirányítás az admin dashboard-ra

#### ✅ Session kezelés
- Böngésző újratöltése → bejelentkezve marad
- 24 órás session időtartam
- Tab bezárása/megnyitása → bejelentkezve marad

#### ✅ Admin funkciók
- Dashboard elérése ✓
- Túrák kezelése ✓
- Foglalások kezelése ✓
- API endpoints ✓

#### ✅ Profil kezelés
- Profil oldal: `http://localhost:5000/auth/profile`
- Jelszó változtatás: `http://localhost:5000/auth/change-password`
- Jelszó erősség ellenőrzés
- Jelszó egyezés validáció

#### ✅ Kijelentkezés
1. Admin navbar → Felhasználó menü → "Kijelentkezés"
2. Session törlése
3. Átirányítás főoldalra
4. Admin oldal újbóli elérése → login szükséges

#### ✅ URL védelem
- `/admin/*` bármely oldal → login required
- Eredeti URL megjegyzése és visszatérés
- Flash üzenetek megfelelő megjelenítése

### 4. UI/UX tesztek

#### Bejelentkezési oldal
- Modern, responsive design
- Teszt adatok gyors kitöltése (kattintás)
- Auto-hide flash üzenetek
- "Vissza a főoldalra" link

#### Admin navbar
- Bejelentkezett felhasználó neve
- Avatar első betűvel
- Dropdown menü profil opcikkal
- Kijelentkezés gomb kiemelése

#### Védett oldalak
- Minden admin oldal védett
- Megfelelő átirányítás
- Flash üzenetek működése

## 🛡️ Biztonsági funkciók

### ✅ Password Hashing
- Werkzeug Security használata
- Bcrypt alapú hash-elés
- Soha nem tárolt plain text jelszó

### ✅ Session biztonság
- Secure session cookie-k
- 24 órás érvényesség
- Session törlés kijelentkezéskor

### ✅ Input validáció
- Kötelező mezők ellenőrzése
- Jelszó hossz minimum 6 karakter
- Username és password sanitizálás

### ✅ CSRF védelem
- Flask beépített CSRF token
- POST request-ek védelme
- Form based attacks elleni védelem

## 🔧 Hibaelhárítás

### "Session not found" hiba
```bash
# Secret key konfiguráció ellenőrzése
# Flask restart
```

### "Import error" hiba  
```bash
# Auth modul regisztrálásának ellenőrzése main.py-ban
# Blueprint import-ok ellenőrzése
```

### Login loop
```bash
# g.user értékének ellenőrzése
# Session data vizsgálata
# Browser cookie-k törlése
```

## 📱 Responsive tesztelés

- **Desktop**: Teljes menü, dropdown működés
- **Tablet**: Collapse menü, megfelelő méretezés  
- **Mobile**: Hamburger menü, touch-friendly gombok

## ⚡ Teljesítmény

- Session store: Memória (fejlesztési)
- Password hash: Optimalizált bcrypt
- Minimális middleware overhead
- Lazy loading auth check

---

## 🎯 Eredmény

✅ **Teljes admin authentikáció rendszer**
✅ **Session alapú bejelentkezés**  
✅ **Védett admin felület**
✅ **Modern UI/UX**
✅ **Biztonsági funkciók**
✅ **Responsive design**

**Admin felület már csak bejelentkezés után elérhető! 🔐**