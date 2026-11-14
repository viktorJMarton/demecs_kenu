# Kajak-Kenu Túrafoglalás Teszt Rendszer

## 🌐 Publikus Teszt URL
**Főoldal:** https://mmpfg3nv-5000.euw.devtunnels.ms

## 📍 Főbb Oldalak

### Nyilvános Felület
- **Főoldal (túrák listája):** https://mmpfg3nv-5000.euw.devtunnels.ms/
- **Túra részletek példa:** https://mmpfg3nv-5000.euw.devtunnels.ms/tour/50

### Admin Felület
- **Admin bejelentkezés:** https://mmpfg3nv-5000.euw.devtunnels.ms/auth/login
- **Admin dashboard:** https://mmpfg3nv-5000.euw.devtunnels.ms/admin/
- **Túrák kezelése:** https://mmpfg3nv-5000.euw.devtunnels.ms/admin/tours
- **Foglalások kezelése:** https://mmpfg3nv-5000.euw.devtunnels.ms/admin/bookings

## 🔐 Bejelentkezési Adatok (Teszt)

### Admin
- **Felhasználónév:** `admin`
- **Jelszó:** `admin123`

### Másodlagos Admin
- **Felhasználónév:** `kajak_admin`
- **Jelszó:** `kajak2025`

## 💳 SimplePay Teszt Fizetés

### Teszt Kártyaszám (Sikeres tranzakció)
```
Kártyaszám: 4908 3660 9990 0425
Lejárat: bármilyen jövőbeli dátum (pl: 12/30)
CVC: bármilyen 3 számjegy (pl: 123)
```

### Teszt Kártyaszám (Sikertelen tranzakció)
```
Kártyaszám: 4908 3660 9990 0177
Lejárat: bármilyen jövőbeli dátum
CVC: bármilyen 3 számjegy
```

## 🧪 Tesztelési Folyamat

### 1. Foglalás Leadása (Felhasználói Felület)
1. Nyisd meg a főoldalt
2. Kattints a **Naptár** gombra
3. Válassz egy hónapot
4. Válassz egy túrát
5. Kattints a **Foglalás!** gombra
6. Töltsd ki a foglalási formot
7. Kattints a **Tovább a fizetéshez** gombra
8. SimplePay teszt kártyával fizess

### 2. Admin Funkciók Tesztelése
1. Jelentkezz be: https://mmpfg3nv-5000.euw.devtunnels.ms/auth/login
2. **Dashboard:** Statisztikák megtekintése
3. **Túrák kezelése:**
   - Új túra hozzáadása
   - Meglévő túra szerkesztése
   - Képek feltöltése
4. **Foglalások kezelése:**
   - Foglalások listázása
   - Foglalás részletek megtekintése
   - Foglalás státusz módosítása

## ⚠️ Fontos Megjegyzések

### Korlátok
- **DEV TUNNEL** - Ez egy fejlesztői teszt környezet
- **Adatok törlődhetnek** - Újraindítás esetén
- **Teljesítmény** - Nem optimalizált éles használatra
- **Időszakos leállás** - A szerver nem 24/7 elérhető

### Időzóna
- Minden időpont **Magyar idő (CET/CEST)**
- Foglalások timeout: **20 perc** fizetésre

### SimplePay Sandbox
- **TESZT környezet** - Valós fizetés NEM történik
- Csak teszt kártyák működnek
- IPN callbackek tesztelhetők

## 📊 Tesztelendő Funkciók

### Prioritás 1 (Kritikus)
- [ ] Foglalás folyamat végigvitele
- [ ] SimplePay fizetés sikeres tranzakció
- [ ] SimplePay fizetés sikertelen tranzakció
- [ ] Admin bejelentkezés
- [ ] Foglalások megtekintése admin felületen

### Prioritás 2 (Fontos)
- [ ] Túra részletek modal megnyitása
- [ ] Képek carousel működése
- [ ] Havi szűrés a naptárban
- [ ] Admin túra szerkesztése
- [ ] Admin képek feltöltése

### Prioritás 3 (Nice to have)
- [ ] Mobil nézet tesztelése
- [ ] Form validációk (hiányzó mezők)
- [ ] Timeout működés (várj 20 percet)
- [ ] Több résztvevő foglalása

## 🐛 Hibabejelentés

Ha hibát találsz, jelezd az alábbi információkkal:
- **Mi a hiba?** (részletes leírás)
- **Hol történt?** (URL)
- **Hogyan lehet reprodukálni?** (lépések)
- **Milyen böngésző?** (Chrome, Firefox, stb.)
- **Screenshot** (ha van)

---

**Utolsó frissítés:** 2025. november 10.
**Verzió:** 1.0 (SimplePay integráció)
