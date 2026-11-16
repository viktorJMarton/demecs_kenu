# Affiliate modul – végrehajtási fejlesztési terv

Ez a terv az affiliate modul jövőbeni megvalósításának követendő munkaterve. A termékdöntések forrása az [affiliate-modul-beszelgetes-es-dontesek.md](affiliate-modul-beszelgetes-es-dontesek.md) fájl. Ha a két dokumentum között eltérés lenne, a megrendelő legutóbbi, kifejezett döntése az irányadó.

## Cél

A meglévő Flask–SQLite–Jinja–SimplePay alkalmazásba olyan saját partneri ajánlói rendszert kell építeni, amely:

- adminfelületen beállítható;
- kedvezményt és jutalékot számol;
- biztonságosan korlátozza a felhasználást;
- követi a forgalmi forrást és a foglalási eredményeket;
- kézi partnerelszámolást támogat;
- a meglévő adminfelület megjelenését követi;
- partnerportál és automatikus kifizetés nélkül működik.

## Kötelező műszaki alapelvek

1. A frontend által küldött árat vagy kedvezményt soha nem tekintjük hitelesnek; a backend számol újra mindent.
2. A foglaláson változtathatatlanul megőrizzük az eredeti árat, a kedvezményt, a fizetendő árat, a szabályváltozatot és a jutalékot.
3. A keretellenőrzés és a keretfoglalás egyetlen adatbázis-műveleti egységben történik.
4. Minden fizetési visszahívás és keret-visszaadás ismételhető anélkül, hogy kétszer módosítaná az adatokat.
5. A régi partneri szabályokat nem írjuk felül és nem töröljük; módosításkor új változat készül.
6. A jelenlegi, nem commitolt felhasználói módosításokat meg kell őrizni.
7. Minden fejlesztési szakasz csak a saját ellenőrzési feltételeinek teljesülése után tekinthető késznek.

## Javasolt adatmodell

A végleges neveket a meglévő adatbázis elnevezési szokásaihoz kell igazítani.

### `affiliate_partners`

- partnerazonosító;
- generált, egyedi `ref` kód;
- név, cégnév és kapcsolattartási adatok;
- számlázási adatok és adószám;
- belső megjegyzés;
- aktív állapot;
- létrehozási és módosítási idő.

### `affiliate_rule_versions`

- partnerazonosító és változatszám;
- kedvezmény típusa és értéke;
- kedvezmény számítási módja;
- legnagyobb kedvezményösszeg;
- jutalék típusa és értéke;
- hozzárendelési idő és munkamenet-korlátozás;
- érvényesség kezdete és vége;
- teljes és vendégenkénti korlát;
- foglalás- vagy résztvevőalapú mértékegység;
- keretidőszak típusa;
- létrehozási idő és archivált állapot.

### `affiliate_rule_scopes`

- szabályváltozat;
- érvényességi típus: minden túra, túra vagy helyszín;
- kapcsolódó túra- vagy helyszínazonosító.

### `affiliate_budget_periods`

- partner és szabályváltozat;
- időszak kezdete és vége;
- beállított keret;
- végleges és ideiglenesen lefoglalt felhasználás;
- időszak állapota.

### `affiliate_attributions`

- véletlenszerű látogatói azonosító;
- partner és szabályváltozat;
- kattintás ideje és lejárata;
- hivatkozó oldal és UTM-adatok;
- céloldal;
- utolsó kattintásos hozzárendelési adatok.

### `affiliate_click_events`

- partner, szabályváltozat és látogatói azonosító;
- időpont, hivatkozó oldal és UTM-adatok;
- céloldal;
- robot- vagy ismétlésszűrés eredménye;
- szükséges technikai metaadatok személyes adatok indokolatlan tárolása nélkül.

### `affiliate_usages`

- foglalás, partner, szabályváltozat és keretidőszak;
- normalizált vagy biztonságosan származtatott vendégazonosító;
- lefoglalt felhasználási mennyiség;
- állapot: ideiglenes, végleges, felszabadított vagy visszaadott;
- létrehozási, lejárati és véglegesítési idő;
- egyedi kulcsok az ismételt feldolgozás kivédésére.

### Foglalási adatok bővítése

A `bookings` táblán vagy kapcsolódó pénzügyi táblán megőrzendő:

- partner- és szabályváltozat-azonosító;
- eredeti foglalási összeg;
- kedvezmény összege;
- ténylegesen fizetendő összeg;
- jutalék típusa, mértéke és kiszámított összege;
- forrás- és kampányadatok;
- affiliate használati állapot.

### `affiliate_settlements` és `affiliate_settlement_items`

- partner és elszámolási időszak;
- előkészített, lezárt vagy kifizetett állapot;
- lezárási és kifizetési idő;
- adminisztrátori megjegyzés;
- elszámolás összesített értékei;
- elszámolásba vont foglalások változtathatatlan tételei.

### `affiliate_audit_log`

- művelet típusa;
- érintett partner, szabály, foglalás vagy elszámolás;
- adminisztrátori azonosító;
- korábbi és új állapot szükséges kivonata;
- esemény időpontja.

## Megvalósítási szakaszok

### 1. Adatmodell és adatbázis-módosítás – 4–6 óra

Feladatok:

- végleges tábla- és mezőnevek kialakítása;
- biztonságosan újrafuttatható migráció készítése;
- idegen kulcsok, egyedi kulcsok és lekérdezési indexek létrehozása;
- a foglalási pénzügyi állapot mezőinek hozzáadása;
- próba-migráció készítése a jelenlegi adatbázis másolatán.

Késznek tekinthető, ha:

- a migráció adatvesztés nélkül lefut a jelenlegi adatbázison;
- második futtatás nem okoz hibát vagy duplikációt;
- az alkalmazás affiliate adatok nélkül is változatlanul elindul.

### 2. Partneri beállítófelület – 6–10 óra

Feladatok:

- új admin blueprint vagy a meglévő adminmodul megfelelő bővítése;
- partnerlista, létrehozás, szerkesztés, ki- és bekapcsolás;
- automatikus `ref` kód és hivatkozásmásoló gomb;
- dinamikus kedvezmény-, jutalék-, korlát- és érvényességi mezők;
- túra- és helyszínkiválasztás;
- szabályváltozatok és változástörténet megjelenítése;
- szerveroldali ellenőrzés és CSRF-védelem;
- a jelenlegi adminoldalakhoz illeszkedő DaisyUI/Tailwind megjelenés.

Késznek tekinthető, ha az admin minden jóváhagyott szabályt be tud állítani, és egy már használt szabály módosítása új változatot hoz létre.

### 3. Ajánlói kód, süti, UTM-mérés és hozzárendelés – 5–8 óra

Feladatok:

- a `ref` URL-paraméter globális feldolgozása;
- aktív állapot, dátum, keret és kód ellenőrzése;
- biztonságos, lejáró böngészősüti;
- utolsó kattintásos hozzárendelés;
- kattintáskori szabályváltozat rögzítése;
- hivatkozó oldal és UTM-adatok mentése;
- adminisztrátori UTM-hivatkozáskészítő;
- hibás és lejárt kód csendes figyelmen kívül hagyása.

Késznek tekinthető, ha egy érvényes hivatkozás hozzárendelése megmarad a beállított ideig, az új érvényes kattintás felülírja, az érvénytelen kód pedig nem módosítja.

### 4. Kedvezményszámítás és felhasználási korlátok – 8–12 óra

Feladatok:

- százalékos, fix összegű, ingyenes résztvevős és csak mérési szabály;
- teljes foglalásra, egy vagy több résztvevőre vonatkozó számítás;
- legnagyobb kedvezményösszeg;
- egész forintra történő matematikai kerekítés;
- túra- és helyszínjogosultság;
- teljes és vendégenkénti korlát;
- foglalás- és résztvevőalapú számlálás;
- életciklusos, havi, éves és kézi keretidőszak;
- külön, tisztán tesztelhető szolgáltatásréteg.

Késznek tekinthető, ha minden szabálytípus szerveroldali egységtesztekkel igazolt, és a végösszeg soha nem lehet negatív.

### 5. Foglalási folyamat és SimplePay-be illesztés – 6–10 óra

Feladatok:

- partneri hozzárendelés beolvasása a fizetés indításakor;
- vendég e-mail-címének egységesítése;
- jogosultság és kedvezmény ismételt ellenőrzése;
- eredeti ár, kedvezmény és végösszeg rögzítése;
- SimplePay indítása kizárólag a szerveren kiszámított végösszeggel;
- foglalási felületen eredeti ár, `Partnerkedvezmény` és végösszeg megjelenítése;
- partner nevének és jutalékának elrejtése a nyilvános felületen.

Késznek tekinthető, ha a foglalás, a tranzakció és a SimplePay-kérés összege minden esetben egyezik.

### 6. Keretfoglalás, lemondás és visszatérítés – 5–8 óra

Feladatok:

- feltételes, adatbázis-szintű ideiglenes keretfoglalás;
- a SimplePay 20 perces fizetési idejéhez igazodó lejárat;
- sikeres fizetéskor véglegesítés;
- sikertelen, megszakított vagy időtúllépéses fizetéskor felszabadítás;
- lemondás és visszatérítés esetén automatikus keret-visszaadás;
- beragadt ideiglenes foglalások takarítása;
- ismételt visszahívások és párhuzamos kérések védelme.

Késznek tekinthető, ha konkurens tesztben sem léphető túl a keret, és ugyanaz az esemény nem módosíthatja kétszer.

### 7. Adminisztrátori kimutatások – 7–12 óra

Feladatok:

- partnerenkénti összesítő oldal;
- összes és becsült egyedi kattintás;
- robot- és ismétlésszűrés;
- forrás-, közeg-, kampány- és céloldalbontás;
- megkezdett fizetés, sikeres és lemondott foglalás;
- résztvevőszám, konverzió, eredeti bevétel, kedvezmény és tényleges bevétel;
- dátum-, partner- és forrásszűrés;
- 24 hónap utáni havi összesítő folyamat.

Késznek tekinthető, ha a kimutatások ellenőrzött mintaadatokból a várt eredményt adják, és csak bejelentkezett adminisztrátor éri el őket.

### 8. Partnerjutalék és kézi elszámolás – 7–11 óra

Feladatok:

- százalékos és fix jutalék számítása;
- jutalék rögzítése sikeres fizetéskor;
- jutalék érvénytelenítése lemondáskor vagy visszatérítéskor;
- partner- és dátumtartomány-alapú elszámolás előnézete;
- csak sikeres, nem lemondott és még el nem számolt tételek bevonása;
- lezárás és kézzel kifizetettnek jelölés;
- dupla elszámolás elleni adatbázis-korlát;
- lezárt elszámolások változtathatatlan megőrzése.

Késznek tekinthető, ha egy foglalás legfeljebb egy kifizetett elszámolásban szerepelhet, és a lezárt összeg későbbi szabálymódosítástól nem változik.

A százalékos jutalék alapja a kedvezmény utáni, ténylegesen fizetendő
forintösszeg. A számítás egész forintban történik; pontos fél forint esetén
felfelé kerekítünk. A fix jutalék foglalásonként értendő, a `none` mód összege
mindig nulla. A számítás önmagában sem partnerkifizetést, sem SimplePay-műveletet
nem indít.

### 9. CSV- és TXT-kimenetek – 2–4 óra

Feladatok:

- képernyőn megjelenő és nyomtatható elszámolás;
- UTF-8 kódolású CSV-kimenet;
- ember által olvasható TXT-kimenet;
- magyar ékezetek, tizedesek és sortörések ellenőrzése;
- fájlnévben partner és elszámolási időszak használata.

Késznek tekinthető, ha ugyanazok az összegek jelennek meg a felületen, a CSV-ben és a TXT-ben.

### 10. Automatizált tesztek és hibajavítás – 8–14 óra

Kötelező tesztcsoportok:

- kedvezménytípusok és kerekítés;
- túra- és helyszínjogosultság;
- összesített és vendégenkénti korlát;
- foglalás- és résztvevőalapú keret;
- havi, éves és kézi keretidőszak;
- utolsó kattintásos hozzárendelés;
- kattintáskori szabályváltozat;
- hibás, lejárt és kikapcsolt kód;
- SimplePay siker, hiba, megszakítás és időtúllépés;
- lemondás, visszatérítés és ismételt visszahívás;
- párhuzamos keretfoglalás;
- jutalék és dupla elszámolás;
- adminisztrátori jogosultság és CSRF;
- CSV- és TXT-kimenet;
- meglévő foglalási és fizetési folyamat regressziója.

Késznek tekinthető, ha a célzott és teljes tesztcsomag sikeresen lefut, és a meglévő SimplePay-folyamat nem romlik el.

### 11. Adatátállás, dokumentáció és élesítési ellenőrzés – 3–5 óra

Feladatok:

- adatbázis biztonsági mentése;
- migráció próbája az éles adatbázis másolatán;
- környezeti beállítások és üzemeltetési jegyzetek;
- adminisztrátori használati leírás;
- fokozatos élesítés kezdetben partnerhivatkozás nélkül;
- egy belső tesztpartnerrel teljes végponttól végpontig próba;
- naplók és pénzügyi összegek ellenőrzése;
- visszaállítási eljárás dokumentálása.

Késznek tekinthető, ha a próba-foglalás a kattintástól a lezárt elszámolásig ellenőrzötten végigfut.

## Összesített becslés

| Részfeladat | Óra |
|---|---:|
| Adatmodell és adatbázis-módosítás | 4–6 |
| Partneri beállítófelület | 6–10 |
| Ajánlói kód, süti, UTM-mérés és hozzárendelés | 5–8 |
| Kedvezményszámítás és felhasználási korlátok | 8–12 |
| Foglalási folyamat és SimplePay-be illesztés | 6–10 |
| Keretfoglalás, lemondás és visszatérítés | 5–8 |
| Adminisztrátori kimutatások | 7–12 |
| Partnerjutalék és kézi elszámolás | 7–11 |
| CSV- és TXT-kimenetek | 2–4 |
| Automatizált tesztek és hibajavítás | 8–14 |
| Adatátállás, dokumentáció és élesítési ellenőrzés | 3–5 |
| **Összesen** | **61–100** |

Tervezési középérték: **80 munkaóra**.

## Végrehajtási sorrend és állapotkövetés

| Szakasz | Állapot |
|---|---|
| 1. Adatmodell és migráció | Nincs elkezdve |
| 2. Partneri beállítófelület | Nincs elkezdve |
| 3. Hozzárendelés és forrásmérés | Nincs elkezdve |
| 4. Kedvezményszámítás és korlátok | Nincs elkezdve |
| 5. Foglalás és SimplePay | Nincs elkezdve |
| 6. Keretállapotok és visszaadások | Nincs elkezdve |
| 7. Kimutatások | Nincs elkezdve |
| 8. Jutalék és elszámolás | Nincs elkezdve |
| 9. Exportok | Nincs elkezdve |
| 10. Teljes tesztelés | Nincs elkezdve |
| 11. Élesítési ellenőrzés | Nincs elkezdve |

## Változtatási szabály

Ha fejlesztés közben új igény vagy a döntési naplótól eltérő működés merül fel:

1. először a döntési naplót kell frissíteni;
2. utána módosítani kell ezt a tervet és az érintett becslést;
3. csak ezt követően változhat az implementáció.

