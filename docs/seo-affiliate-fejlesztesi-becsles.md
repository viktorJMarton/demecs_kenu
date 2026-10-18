# SEO- és affiliate marketing fejlesztési becslés

**Projekt:** Demecs Vízitúra / Kajak-Kenu  
**Becslés készült:** 2026. szeptember 1.  
**Technológiai környezet:** Flask, SQLite, Jinja, TailwindCSS/DaisyUI, SimplePay

## Kiindulási állapot

A becslés a jelenlegi kódbázis és adatbázis áttekintése alapján készült. A rendszer jelenleg:

- 18 aktív túrát;
- 8 helyszínt;
- 8 szerkeszthető tartalmi szekciót;
- saját adminfelületet;
- SimplePay fizetési integrációt kezel.

A SEO és a Google Analytics egy része már megtalálható a rendszerben:

- dinamikus `robots.txt`;
- dinamikus `sitemap.xml`;
- title és description metaadatok;
- Open Graph és Twitter metaadatok;
- canonical URL;
- JSON-LD strukturált adat;
- környezeti változóból bekapcsolható GA4;
- szerveroldali árképzés a SimplePay fizetés indítása előtt.

A becslés fejlesztői munkaórát jelent, és tartalmazza a tervezést, implementációt, automatizált teszteket, dokumentációt és élesítési támogatást.

## 1. SEO-optimalizálás

| Részfeladat | Becsült idő |
|---|---:|
| Technikai SEO-audit, kulcsszókutatás, versenytárselemzés | 6–9 óra |
| Beszédes, slug-alapú, külön indexelhető túra- és helyszínoldalak | 10–15 óra |
| Dinamikus title, description, canonical, Open Graph és közösségi metaadatok | 5–8 óra |
| Event, TouristAttraction/SportsActivityLocation, Organization és breadcrumb strukturált adatok | 4–6 óra |
| Robots.txt és sitemap továbbfejlesztése, admin/API/fizetési oldalak indexelési szabályai | 3–5 óra |
| A 18 aktív túra, 8 helyszín és főoldali tartalmak keresőoptimalizálása | 12–20 óra |
| Belső linkstruktúra, képek alt szövegei, heading-hierarchia | 5–8 óra |
| GA4 és teljes consent banner/Consent Mode v2 bevezetése | 8–12 óra |
| GA4-események: túranézet, foglalásindítás, fizetés, purchase, affiliate konverzió | 7–11 óra |
| Google Search Console bekötése, sitemap beküldése és ellenőrzése | 2–4 óra |
| Core Web Vitals, Lighthouse és mobil teljesítmény javítása | 5–8 óra |
| SEO-, strukturáltadat-, analytics- és regressziós tesztelés | 6–9 óra |
| **SEO összesen** | **73–115 óra** |

### SEO-megvalósítás

A SEO teljes körű, kulcsrakész feladatként készül:

- technikai SEO;
- kulcsszókutatás;
- tartalmi optimalizálás;
- külön indexelhető túra- és helyszínoldalak;
- strukturált adatok;
- sitemap- és robots-szabályok;
- GA4 és konverziós események;
- cookie consent és Consent Mode v2;
- Search Console beállítás;
- teljesítménymérés és ellenőrzés.

A megrendelőnek nem kell kódot vagy konfigurációs fájlt módosítania. Google-fiók- és esetleg DNS-hozzáférés biztosítására viszont szükség lehet.

### SEO-források

- [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [Google sitemap útmutató](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [GA4 beállítása webhelyhez](https://support.google.com/analytics/answer/14183469)
- [Google Consent Mode](https://support.google.com/analytics/answer/12329709)

## 2. Affiliate marketing modul

### Rögzített üzleti működés

#### Partner és affiliate link

- Egy partnerhez pontosan egy affiliate kód tartozik.
- Az affiliate azonosító query paraméterben érkezik.
- URL-formátum: `?ref=GENERÁLT_KÓD`.
- A rendszer automatikusan generálja az egyedi, nem könnyen kitalálható kódot.
- Az admin egy gombbal másolhatja a teljes affiliate URL-t.
- Nem készül külön `/partner/...` erőforrás-URL.
- Ugyanahhoz az affiliate kódhoz több UTM-mérési URL-változat készíthető.

#### Partneradatok

Az adminfelületen tárolható:

- partner neve;
- cégnév;
- kapcsolattartó neve;
- e-mail-cím;
- telefonszám;
- számlázási név és cím;
- adószám;
- adminisztrátori megjegyzés;
- aktív/inaktív állapot.

Bankszámlaadatot a rendszer nem tárol.

#### Attribúció

- Utolsó kattintásos attribúció.
- Az end user elsődleges azonosítása a foglaláskor megadott, normalizált e-mail-cím alapján történik.
- Az e-mail-alapú azonosítást biztonságos cookie egészíti ki.
- Az attribúciós idő linkenként konfigurálható napokban.
- Választható csak az aktuális munkamenetre szóló működés.
- Alapértelmezett attribúciós idő: 30 nap.
- A kattintáskor érvényes affiliate szabályverzió marad érvényben az attribúciós időszak végéig.
- A link teljes deaktiválása, lejárata vagy keretének elfogyása ettől függetlenül letiltja a kedvezményt.
- Érvénytelen, lejárt, inaktív vagy kimerített linket a rendszer csendben figyelmen kívül hagy.
- Érvénytelen új `ref` paraméter nem ír felül korábbi érvényes attribúciót.

#### Érvényességi kör

Az admin linkenként választhat:

- minden túrára érvényes;
- egy kiválasztott túrára érvényes;
- több kiválasztott túrára érvényes;
- egy helyszín összes túrájára érvényes.

#### Kedvezménytípusok

Linkenként beállítható:

- százalékos kedvezmény;
- fix forintösszegű kedvezmény;
- egy vagy több résztvevő árának elengedése;
- kedvezmény nélküli, kizárólag követésre szolgáló link.

A kedvezmény vonatkozhat:

- a teljes foglalási összegre;
- egy résztvevő árára;
- az admin által meghatározott számú résztvevő árára.

Opcionális maximális kedvezményösszeg is megadható.

Minden pénzösszeget matematikailag, a legközelebbi egész forintra kell kerekíteni. Ugyanaz a rögzített érték szerepel a foglalási összesítőben, az adatbázisban, a SimplePay-tranzakcióban, az analitikában és a partnerelszámolásban.

#### Felhasználási limitek

Affiliate linkenként beállítható:

- összesített felhasználási limit;
- end userenkénti felhasználási limit;
- mindkét limit esetén korlátlan működés;
- foglalásszám-alapú limit;
- résztvevőszám-alapú limit.

A keret vonatkozhat:

- a link teljes élettartamára;
- egy hónapra, automatikus havi megújulással;
- egy évre, automatikus éves megújulással;
- admin által kézzel indított keretidőszakra.

Az új keretidőszak nem törli a korábbi időszakok felhasználási adatait.

#### Fizetés és keretfoglalás

- A fizetés indításakor a rendszer ideiglenesen lefoglalja a szükséges keretet.
- Sikeres SimplePay-visszaigazoláskor a felhasználás véglegessé válik.
- Sikertelen, megszakított vagy timeoutos fizetésnél a keret felszabadul.
- A keretfoglalás igazodik a SimplePay 20 perces fizetési időkorlátjához.
- Tranzakciós védelem akadályozza meg a párhuzamos foglalások miatti limittúllépést.
- Lemondás vagy visszatérítés esetén a rendszer mindig automatikusan visszaadja a link és az end user keretét.
- A műveletek idempotensek, ezért ugyanaz a státuszfrissítés nem módosíthatja kétszer a keretet.

#### End-user megjelenítés

- Az affiliate kedvezmény automatikusan érvényesül.
- Az end user nem távolíthatja el, és nem adhat meg kézzel affiliate kódot.
- A foglalási összesítő mutatja az eredeti árat, a kedvezményt és a végösszeget.
- A kedvezmény neve semlegesen `Partnerkedvezmény`.
- A partner neve és jutaléka nem jelenik meg a publikus felületen.
- A frontend kijelzése csak tájékoztató; a backend a fizetés előtt újraszámolja az összeget.

#### Partnerjutalék

- Automatikus partnerkifizetési rendszer nem készül.
- A rendszer kiszámolja a manuálisan kifizetendő jutalékot.
- Linkenként választható százalékos, fix összegű vagy jutalék nélküli működés.
- A százalékos jutalék alapja a kedvezmény utáni, ténylegesen kifizetett összeg.
- A jutalékot sikeres fizetéskor rögzíteni kell a foglaláshoz.
- A jutalékszabály későbbi módosítása nem változtatja meg a korábbi foglalások adatait.
- Lemondás vagy visszatérítés esetén a jutalék automatikusan érvénytelenné válik.

#### Manuális elszámolás

- Az admin kiválaszt egy partnert és egy tetszőleges dátumtartományt.
- A rendszer csak a sikeresen kifizetett, nem lemondott és még el nem számolt foglalásokat gyűjti össze.
- Előnézet mutatja a foglalásokat, bevételt és jutalékot.
- Az elszámolás lezárható, majd a manuális utalás után kifizetettnek jelölhető.
- A kifizetés dátuma és adminisztrátori megjegyzés rögzíthető.
- Egy foglalás ugyanahhoz a partnerhez csak egyszer kerülhet kifizetett elszámolásba.
- A lezárt elszámolás pénzügyi adatai nem írhatók át.
- A lezárt elszámolás normál HTML-nézetben megtekinthető és nyomtatható.
- Az elszámolás CSV- és TXT-formátumban letölthető.
- A lezárt elszámolás később változatlan állapotban újra megtekinthető és exportálható.

#### Analitika

Az adminriport tartalmazza:

- összes kattintás;
- becsült egyedi látogatók;
- küldődomain/referrer;
- UTM source, medium, campaign és content;
- megkezdett fizetések;
- sikeres és lemondott foglalások;
- konverziós arány;
- résztvevők száma;
- eredeti foglalási érték;
- adott ügyfélkedvezmény;
- ténylegesen befolyt összeg;
- kiszámított partnerjutalék;
- még nem elszámolt és már kifizetett jutalék;
- lemondások és visszatérítések;
- dátumtartomány, partner és forrás szerinti szűrés;
- CSV-export.

Minden érvényes megnyitás eseményként tárolható, de a riport külön mutatja az összes és a becsült egyedi kattintást. Ismert botok, crawlerek és irreálisan gyakori ismétlések nem számítanak valós partnerforgalomnak.

A részletes kattintási adatokat a rendszer 24 hónapig őrzi meg. Ezután havi, személyhez nem köthető összesítések maradnak. A foglalási, jutalék- és partnerelszámolási pénzügyi adatokat ez nem törli.

Az affiliate analitika kizárólag a jelenlegi adminisztrátorok számára érhető el. Nem készül partnerportál vagy külön partneri authentikáció.

#### Verziókezelés és audit

- Affiliate szabály szerkesztésekor új verzió jön létre.
- A `ref` kód és a publikus link nem változik.
- Korábbi foglalások megtartják a hozzájuk tartozó kedvezmény- és jutalékszabályt.
- A kattintáskori szabályverzió az attribúciós időszakban megmarad.
- Korábbi verziók nem törölhetők, csak archiválhatók.
- Az admin megtekintheti a változástörténetet.
- A pénzügyi és keretmódosítások auditnaplóba kerülnek.

### Affiliate részletes becslés

| Részfeladat | Becsült idő |
|---|---:|
| Adatmodell és architektúra: partner, szabályverzió, attribúció, használat, kattintás, elszámolás | 7–10 óra |
| Biztonságos adatbázis-migrációk, indexek és meglévő adatbázis kompatibilitása | 5–8 óra |
| Partner- és affiliate konfigurátor az eddigi admin design szerint | 12–17 óra |
| Automatikus `ref` kódgenerálás, linkmásolás és UTM URL-generátor | 5–8 óra |
| Verziókezelés, aktiválás, időzítés és változástörténet | 9–14 óra |
| Havi, éves, életciklusos és manuálisan indított keretidőszakok | 5–8 óra |
| Query paraméter, cookie, utolsó kattintás és kattintáskori szabályrögzítés | 7–11 óra |
| Referrer- és UTM-mérés, céloldal és kampányadatok | 5–8 óra |
| Kattintásnapló, egyedi látogatók becslése, bot- és ismétlésszűrés | 6–10 óra |
| 24 hónapos megőrzés és automatikus havi aggregálás | 3–5 óra |
| Túra-, többtúrás, helyszín- és globális érvényesség | 6–9 óra |
| Kedvezményszámító motor és minden kedvezménytípus | 10–15 óra |
| Foglalás- és résztvevőalapú összesített/end-user limitek | 7–11 óra |
| Párhuzamos foglalás elleni tranzakciós keretfoglalás | 7–11 óra |
| SimplePay-integráció: eredeti ár, kedvezmény és végösszeg | 8–12 óra |
| Sikeres, sikertelen, timeoutos, lemondott és visszatérített fizetések kezelése | 6–10 óra |
| Foglalási frontend ár- és kedvezménymegjelenítése | 4–6 óra |
| Adminanalitika, szűrők, konverziók és bevételi mutatók | 12–18 óra |
| Százalékos/fix jutalék és kattintáskori pénzügyi snapshot | 5–8 óra |
| Manuális elszámolási folyamat és lezárás/kifizetés állapotok | 8–12 óra |
| HTML-, nyomtatási, CSV- és TXT-kimenetek | 4–7 óra |
| Auditnapló, jogosultság- és biztonsági ellenőrzések | 5–8 óra |
| Unit-, route-, integrációs, fizetési és konkurenciatesztek | 16–24 óra |
| Dokumentáció, éles migráció és bevezetési ellenőrzés | 7–10 óra |
| **Affiliate összesen** | **169–260 óra** |

### Affiliate technikai források

- [RSC Labs Medusa Affiliate Discount](https://github.com/RSC-Labs/medusa-affiliate-discount)
- [Medusa affiliate adatmodell és funkcionális javaslat](https://github.com/medusajs/medusa/discussions/4684)
- [Párhuzamos promócióbeváltások és limitkezelési versenyhelyzet](https://github.com/medusajs/medusa/issues/16012)

## 3. Teljes projektbecslés

| Fejlesztési terület | Munkaóra |
|---|---:|
| Teljes SEO és Analytics | 73–115 óra |
| Affiliate marketing rendszer | 169–260 óra |
| **Projekt összesen** | **242–375 óra** |

Egy fejlesztővel ez hozzávetőleg **6–9,5 teljes munkahetet** jelent, napi 8 és heti 40 munkaórával számolva.

A reális projekttervezési középérték körülbelül **309 munkaóra**, vagyis **7,5–8 fejlesztői hét**.

## 4. Feltételezések és korlátok

A becslés az alábbi feltételezések mellett érvényes:

- A jelenlegi Flask–SQLite–Jinja–SimplePay architektúra megmarad.
- Nem készül automatikus partnerkifizetési rendszer.
- Nem készül partnerportál vagy külön partneri bejelentkezés.
- Nem történik teljes vizuális újratervezés.
- Az új adminoldalak a jelenlegi DaisyUI/Tailwind konfigurátorok megjelenését követik.
- A jelenlegi, nem commitolt munkakönyvtári módosításokat a fejlesztés során meg kell őrizni és össze kell egyeztetni az új funkciókkal.
- A Google Analytics és Search Console konfigurációjához szükséges jogosultságokat a megrendelő biztosítja.
- A tartalmi SEO a jelenlegi magyar nyelvű oldalra, 18 aktív túrára és 8 helyszínre vonatkozik.
- Új nyelvek, külső CRM, számlázóprogram, automatikus banki kifizetés vagy külső affiliate hálózat integrációja nincs a becslésben.

## 5. Javasolt megvalósítási sorrend

1. Technikai specifikáció és adatmodell véglegesítése.
2. Biztonságos adatbázis-migrációk.
3. Affiliate partner- és szabálykonfigurátor.
4. Attribúció, cookie, UTM és kattintásmérés.
5. Kedvezményszámítás és felhasználási limitek.
6. SimplePay- és foglalási integráció.
7. Analitika, jutalék és manuális elszámolás.
8. Affiliate regressziós és konkurenciatesztek.
9. Indexelhető túra- és helyszínoldalak.
10. Technikai és tartalmi SEO.
11. GA4, Consent Mode és Search Console.
12. Teljes rendszerellenőrzés és fokozatos élesítés.
