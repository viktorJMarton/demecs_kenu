# Affiliate modul – beszélgetési összefoglaló és döntési napló

Ez a dokumentum az affiliate modul megtervezése során feltett kérdéseket, a megrendelő válaszait és az ezekből következő végleges működési döntéseket rögzíti. A fejlesztés során ez a fájl termékoldali döntési forrásként használandó.

## Kiinduló igény

Az adminfelületen különböző partnerekhez lehessen affiliate, vagyis partneri ajánlói hivatkozást beállítani. A rendszer kövesse a hivatkozás használatát, korlátozhassa annak felhasználását, kedvezményt adhasson a foglaló vendégnek, valamint biztosítson kimutatásokat a kézzel végzett partnerelszámoláshoz.

Az adminfelület megjelenése és működése maradjon egységes a jelenlegi konfigurátoroldalakkal.

## Kérdések, válaszok és döntések

### 1. Felhasználási korlátok

**Kérdés:** Összesített, vendégenkénti vagy mindkét felhasználási korlátra szükség van?

**Válasz:** Ezeket az adminfelületen lehessen beállítani a hivatkozásokhoz.

**Döntés:** Partnerhivatkozásonként külön beállítható:

- teljes felhasználási korlát;
- vendégenkénti felhasználási korlát;
- mindkettő esetén korlátlan működés.

Az adminfelület mutassa az aktuális felhasználást és a fennmaradó keretet.

### 2. A vendég azonosítása

**Kérdés:** E-mail, e-mail és telefonszám, böngészősüti vagy e-mail és süti együtt azonosítsa a vendéget?

**Válasz:** 4 – e-mail-cím böngészősütivel kiegészítve.

**Döntés:** A hiteles vendégenkénti korlátozás alapja a foglaláskor megadott, egységesített e-mail-cím. A böngészősüti az ajánlói hozzárendelés megőrzését segíti.

### 3. Érvényességi kör

**Kérdés:** Minden túrára, egy túrára, több túrára, helyszínre vagy ezek közül admin által választható módon legyen érvényes?

**Válasz:** 5 – az admin választhasson a lehetőségek közül.

**Döntés:** Az ajánlat érvényes lehet:

- minden túrára;
- egy kiválasztott túrára;
- több kiválasztott túrára;
- egy helyszín összes túrájára.

### 4. A hozzárendelés időtartama

**Kérdés:** Munkamenethez, globális időhöz vagy partnerenként beállítható időhöz kössük?

**Válasz:** 4 – partnerenként beállítható időtartam, valamint csak az aktuális munkamenetre szóló lehetőség.

**Döntés:** Partnerenként napokban megadható időtartam készül, 30 napos alapértékkel. Választható kizárólag az adott böngészési munkamenetre szóló működés.

### 5. Több partnerhivatkozás megnyitása

**Kérdés:** Az első vagy a legutolsó kattintás számítson?

**Válasz:** 1 – a legutolsó kattintás.

**Döntés:** Mindig a legutóbb megnyitott érvényes partnerhivatkozás kapja a későbbi foglalást.

### 6. A kedvezmény számítási alapja

**Kérdés:** A teljes foglalásra, egy résztvevőre, megadott számú résztvevőre vagy admin által választható módon vonatkozzon?

**Válasz:** 4 – az admin választhasson.

**Döntés:** A kedvezmény vonatkozhat a teljes foglalási összegre, egy résztvevőre vagy az admin által megadott számú résztvevőre. Beállítható legnagyobb kedvezményösszeg.

### 7. Kedvezménytípusok

**Kérdés:** Százalékos, fix összegű, ingyenes résztvevős vagy kedvezmény nélküli mérési hivatkozás is legyen?

**Válasz:** 4 – mindegyik legyen elérhető.

**Döntés:** Beállítható:

- százalékos kedvezmény;
- fix összegű kedvezmény;
- egy vagy több résztvevő díjának elengedése;
- kedvezmény nélküli, kizárólag követésre szolgáló hivatkozás.

### 8. Mikor fogyjon a keret?

**Kérdés:** Kattintáskor, foglaláskor, sikeres fizetéskor vagy ideiglenes keretfoglalással működjön?

**Válasz:** 4 – fizetéskor ideiglenes keretfoglalás, sikeres fizetéskor véglegesítés.

**Döntés:** A fizetés indításakor a rendszer ideiglenesen lefoglalja a szükséges keretet. Sikeres SimplePay-visszaigazoláskor véglegesíti, sikertelen, megszakított vagy időtúllépéses fizetésnél felszabadítja.

### 9. Lemondás és visszatérítés

**Kérdés:** A felhasználási keret maradjon felhasználva vagy álljon vissza?

**Válasz:** 2 – mindig álljon vissza.

**Döntés:** Lemondás vagy visszatérítés esetén a partner teljes kerete és a vendégenkénti keret automatikusan visszaáll. Ugyanaz az esemény nem adhatja vissza kétszer a keretet.

### 10. Partnerkifizetés

**Kérdés:** Készüljön automatikus kifizetés?

**Válasz:** A partnerkifizetések teljesen kézzel történnek majd az analitikák alapján; automatikus fizetési rendszer nem készül.

**Döntés:** A rendszer kiszámolja és kimutatja a jutalékot, de pénzmozgást nem indít.

### 11. Jutalék és elszámolási állapot

**Kérdés:** Százalékos vagy fix jutalék, valamint kifizetettségi jelölés is legyen?

**Válasz:** 4 – százalékos vagy fix jutalék, továbbá kézi kifizetettségi jelölés.

**Döntés:** Partnerenként százalékos, foglalásonkénti fix vagy jutalék nélküli működés választható. Az elszámolás előkészíthető, lezárható és kézzel kifizetettnek jelölhető.

### 12. A százalékos jutalék alapja

**Kérdés:** Kedvezmény előtti vagy ténylegesen kifizetett összegből számoljuk?

**Válasz:** 2 – a kedvezmény utáni, ténylegesen kifizetett összegből.

**Döntés:** A sikeres fizetéskor kiszámított jutalék változtathatatlan pénzügyi állapotként kerül a foglaláshoz.

### 13. Partneradatok

**Kérdés:** Milyen partneradatokat tároljon a rendszer?

**Válasz:** 4 – teljes kapcsolattartási és számlázási adatok, bankszámlaadatok nélkül.

**Döntés:** Tárolható név, cégnév, kapcsolattartó, e-mail, telefon, számlázási név és cím, adószám, megjegyzés és állapot. Bankszámlaadat nem tárolható.

### 14. Hivatkozások száma partnerenként

**Kérdés:** Egy vagy több hivatkozás tartozhasson egy partnerhez?

**Válasz:** 1 – egy.

**Döntés:** Egy partnerhez egy ajánlói kód tartozik. A különböző kampányok ugyanennek a kódnak UTM-paraméterezett változatai.

### 15. URL-formátum és kód

**Kérdés:** Külön `/partner/...` oldal vagy URL-paraméter készüljön?

**Válasz:** Ne készüljön külön erőforrás-URL; URL-paraméterekkel működjön.

**Pontosításra adott válasz:** Igen, megfelel a `?ref=GENERÁLT_KÓD` megoldás.

**Döntés:** A paraméter neve rögzítetten `ref`. A rendszer egyedi, nem könnyen kitalálható kódot készít.

### 16. Időbeli érvényesség

**Kérdés:** Aktív kapcsoló, kezdő- és záróidőpont, automatikus lejárat és újraaktiválás készüljön?

**Válasz:** 4 – mindegyik.

**Döntés:** Kézi ki- és bekapcsolás, választható kezdő- és záróidőpont, automatikus lejárat és későbbi újraaktiválás készül.

### 17. Forgalmi forrás mérése

**Felvetés:** Mérjük meg, honnan érkezett a felhasználó.

**Pontosításra adott válasz:** Igen, legyen automatikus hivatkozóoldal-mérés, UTM-paraméterek és adminisztrátori URL-készítő.

**Döntés:** Mérendő a hivatkozó oldal, UTM-forrás, közeg, kampány, tartalmi változat és céloldal.

### 18. Adminisztrátori kimutatás

**Kérdés:** Megfelel-e a teljes kattintási, foglalási, bevételi, jutalék- és konverziós kimutatás?

**Válasz:** Igen.

**Döntés:** A kimutatás tartalmaz kattintást, becsült egyedi látogatót, forrást, megkezdett fizetést, foglalást, résztvevőszámot, bevételt, kedvezményt, jutalékot, konverziót, szűrést és exportot.

### 19. Már használt szabály módosítása

**Kérdés:** Azonnali módosítás, zárolás vagy változatkezelés legyen?

**Válasz:** 3 – változatkezelés.

**Döntés:** Módosításkor új szabályváltozat készül. A korábbi foglalások és kattintások megőrzik a hozzájuk tartozó szabályt; a partnerkód nem változik.

### 20. Hozzáférés az analitikához

**Kérdés:** Adminisztrátor, partnerportál vagy megosztható jelentés férjen hozzá?

**Válasz:** 1 – csak a jelenlegi adminisztrátorok.

**Döntés:** Nem készül partnerportál vagy külön partneri bejelentkezés.

### 21. Kézi elszámolás kimenetei

**Kérés:** A lezárt elszámolás CSV-ben legyen letölthető, a felületen is jelenjen meg, és TXT-fájlként is menthető legyen.

**Döntés:** Az elszámolás HTML-nézetben megtekinthető, nyomtatható, CSV- és TXT-fájlként letölthető.

### 22. Kerekítés

**Kérdés:** Milyen kerekítést használjunk?

**Válasz:** 1 – matematikai kerekítés a legközelebbi egész forintra.

**Döntés:** Ugyanaz a rögzített egész forintösszeg kerül a foglalásba, a SimplePay-kérésbe, a kimutatásba és az elszámolásba.

### 23. A kedvezmény kezelése a vendég felületén

**Kérdés:** Automatikus, eltávolítható vagy kézzel megadható legyen?

**Válasz:** 1 – automatikusan érvényesüljön, legyen látható, de ne legyen eltávolítható.

**Döntés:** A vendég az eredeti árat, a kedvezményt és a fizetendő összeget látja. A szerver minden esetben újraszámolja az árat.

### 24. A partner nevének megjelenítése

**Kérdés:** Látható legyen-e a partner neve?

**Válasz:** 2 – ne legyen látható.

**Döntés:** A nyilvános felületen kizárólag a semleges `Partnerkedvezmény` megnevezés jelenik meg.

### 25. Hibás vagy lejárt hivatkozás

**Kérdés:** Csendes figyelmen kívül hagyás, üzenet vagy hibaoldal készüljön?

**Válasz:** 1 – csendes figyelmen kívül hagyás.

**Döntés:** Nem készül hibaüzenet, nem jön létre új partneri süti, és a foglalás normál áron folytatódik.

### 26. Kattintások számítása

**Kérdés:** Minden kattintás, napi egy kattintás, összes és egyedi mérés, vagy ezek robotszűréssel?

**Válasz:** 4 – összes és becsült egyedi kattintás, robot- és ismétlésszűréssel.

**Döntés:** A nyers események és a kimutatásban használt, tisztított mérőszámok külön kezelendők.

### 27. Adatmegőrzés

**Kérdés:** Megfelel-e 24 hónap részletes megőrzés, utána havi összesítéssel?

**Válasz:** Igen.

**Döntés:** A kattintási részletek 24 hónap után összesítendők. A foglalási és pénzügyi adatok ettől nem törlődnek.

### 28. Mit jelent egy felhasználás?

**Kérdés:** Egy foglalás, egy résztvevő vagy partnerenként választható legyen?

**Válasz:** 3 – partnerenként választható.

**Döntés:** A korlát foglalások vagy résztvevők száma alapján működhet.

### 29. Keret újraindítása

**Kérdés:** Élettartamra szóló, havi, éves vagy kézzel újraindítható keret legyen?

**Válasz:** 5 – mindegyik, kézi új időszakkal és megtartott előzményekkel.

**Döntés:** A keretidőszakok külön nyilvántartásban maradnak, és nem törlik egymás előzményeit.

### 30. Szabálymódosítás aktív hozzárendelés közben

**Kérdés:** Ha kattintás után változik a kedvezmény, a régi vagy az új érték legyen érvényes?

**Válasz:** 2 – a kattintáskor érvényes érték maradjon.

**Döntés:** A böngészősüti a kattintáskor aktív szabályváltozatra hivatkozik. A link teljes kikapcsolása, lejárata vagy keretének elfogyása ettől függetlenül azonnal érvényesül.

## Becsléssel kapcsolatos végső döntés

Az első, hagyományos ügynökségi szemléletű 169–260 órás becslést a megrendelő túlzónak ítélte, mivel a modult AI-val támogatott fejlesztéssel, egy fejlesztő készíti.

**Jóváhagyott, AI-val támogatott becslés:**

- teljes tartomány: **61–100 munkaóra**;
- tervezési középérték: **80 munkaóra**;
- szűkebb első működő változat: **45–60 munkaóra**;
- várható időtartam: **1,5–2,5 teljes munkahetet jelent** heti 40 órával számolva.

## A döntési napló használata

- Eltérő megvalósítás csak új, kifejezett termékdöntés alapján készülhet.
- Bizonytalanság esetén ez a dokumentum és a fejlesztési terv együtt az irányadó.
- A pénzügyi, keretkezelési és fizetési szabályokat automatizált teszteknek kell védeniük.

