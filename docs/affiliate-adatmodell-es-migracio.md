# Affiliate adatmodell és migráció

Ez a dokumentum a `WORK-0001` / `DB-01..DB-05` végrehajtási leltára és adatbázis-szerződése. A termékszabályok forrása továbbra is az `affiliate-modul-beszelgetes-es-dontesek.md`.

## Meglévő adatbázis és írási pontok

A projekt pluralizált `snake_case` táblaneveket, `INTEGER PRIMARY KEY AUTOINCREMENT` kulcsokat, `*_id` idegen kulcsokat, egész forintban tárolt pénzösszegeket, `CHECK`-kel védett szöveges státuszokat és `created_at` / `updated_at` időbélyegeket használ.

Meglévő fő kapcsolatok:

- `bookings.tour_id -> tours.id`;
- `payment_transactions.booking_id -> bookings.id`;
- `bookings.order_ref` és `payment_transactions.order_ref` egyedi;
- a kompatibilitási, fizetendő végösszeg továbbra is `bookings.total_price`.

Booking/payment írási pontok:

- `flaskr/payment.py`: foglalás- és tranzakciólétrehozás, SimplePay-indítás, visszatérési és IPN-státuszok;
- `flaskr/admin/admin_bookings.py`: regisztrált admin státusz- és lemondási útvonal;
- `flaskr/fake_booking.py`: kézi tesztíró;
- `flaskr/admin.py`: régi, jelenleg nem regisztrált admin írási útvonal, amelyet kompatibilisen kell tartani vagy később kivezetni.

A `flaskr/schema.sql` destruktív friss-adatbázis inicializáló, nem használható meglévő adatbázis migrálására. Az additív migráció forrása a `flaskr/affiliate_migration.py`.

## Végleges affiliate táblák

### `affiliate_partners`

Stabil, kis- és nagybetűtől függetlenül egyedi `ref_code`; név, cég-, kapcsolattartási és számlázási adatok bankszámlaadat nélkül; belső megjegyzés; `is_active`; időbélyegek.

### `affiliate_rule_versions`

Partnerenként növekvő `version_number`; `draft | active | archived` státusz; kedvezmény típusa (`percentage | fixed | free_participants | tracking`), értéke és alapja; kedvezményplafon; jutaléktípus (`none | percentage | fixed`) és érték; attribúciós idő/munkamenet; érvényesség; teljes és vendégenkénti limit; `booking | participant` egység; `lifetime | monthly | yearly | manual` keretidőszak. Partnerenként egyszerre legfeljebb egy aktív változat lehet.

### `affiliate_rule_scopes`

Egy szabályváltozat hatóköre `all`, `tour` vagy `location`. Adatbázis-ellenőrzés biztosítja, hogy csak a típushoz tartozó célazonosító legyen kitöltve, a részleges egyedi indexek pedig tiltják a duplikált scope-ot.

### `affiliate_budget_periods`

Partner, szabályváltozat és egyedi `period_key`; időhatárok; opcionális limit; lefoglalt és végleges felhasználás; `open | closed` státusz. A számlálók nem lehetnek negatívak és összegük nem lépheti túl a beállított limitet.

### `affiliate_attributions` és `affiliate_click_events`

Az attribúció látogatói tokenenként az aktuális utolsó érvényes kattintást tartja. A click eventek külön, egyedi `event_key` mellett őrzik a nyers történetet, forrás/referrer/UTM/céloldal mezőkkel és robot-/ismétlésjelzőkkel. Nyers IP-cím vagy e-mail nem kerül ide.

### `affiliate_usages` és `affiliate_usage_events`

Foglalásonként egy usage sor, egyedi idempotencia-kulccsal; partner, szabály, keretidőszak, biztonságosan származtatott vendégkulcs és mennyiség. Állapotok: `pending | final | released | returned`. A transition eventek egyedi eseménykulcsa megakadályozza ugyanazon callback, felszabadítás vagy visszaadás kétszeri alkalmazását.

### `affiliate_settlements` és `affiliate_settlement_items`

Egyedi elszámolási referencia, partner/időszak, `prepared | closed | paid` státusz, partner számlázási snapshot és egész forintos összesítések. A settlement item `booking_id` mezője globálisan egyedi, ezért egy foglalás nem számolható el kétszer.

### `affiliate_audit_log`

Eseménytípus, érintett entitásazonosítók, adminazonosító, korábbi/új állapot JSON-szövege és időbélyeg.

## Foglalási pénzügyi snapshot

A `bookings.total_price` megmarad a SimplePay felé is használt fizetendő összegnek. Az additív affiliate mezők:

- partner-, szabályváltozat- és attribúcióazonosító;
- referral-kód- és szabályverzió-snapshot;
- eredeti ár, kedvezmény és affiliate fizetendő ár;
- kedvezménytípus és -érték;
- jutaléktípus, -érték, -összeg és státusz;
- referrer, UTM source/medium/campaign/content/term és landing path;
- usage státusz;
- `affiliate_snapshot_locked`.

Ha a snapshot zárolt, adatbázis-trigger tiltja a partner-, szabály-, ár-, kedvezmény-, jutalék- és forrásmezők módosítását, valamint a zárolás feloldását. A fizetési és usage státuszok ettől még szabályos lifecycle-tranzakcióban változhatnak.

## Migráció és tranzakció

Az alkalmazás minden SQLite-kapcsolaton bekapcsolja a foreign key ellenőrzést és 5000 ms busy timeoutot állít. A migráció:

1. ellenőrzi a `bookings`, `tours` és `tour_locations` alapsémát;
2. `BEGIN IMMEDIATE` tranzakciót indít;
3. `CREATE ... IF NOT EXISTS` utasításokkal létrehozza a táblákat, indexeket és triggert;
4. `PRAGMA table_info(bookings)` alapján csak a hiányzó booking oszlopokat adja hozzá;
5. lefuttatja a `foreign_key_check` és `integrity_check` ellenőrzést;
6. egyszer rögzíti a `2026-10-18-affiliate-v1` migrációverziót;
7. hibánál teljes rollbacket végez.

Nulla bájtos SQLite-fájlon a migráció előbb létrehozza a projekt friss alapsémáját, majd ugyanabban a támogatott folyamatban felépíti az affiliate sémát. Részlegesen meglévő, hiányos alapsémán világos előfeltételhibával áll le; inkompatibilis részleges affiliate táblát pedig még a migrációverzió rögzítése előtt elutasít.

## Futtatás és visszaállítás

Meglévő adatbázison a támogatott parancs:

```bash
.venv/bin/python scripts/migrate_affiliate.py --database /pontos/elérési/út/kajak_kenu.db
```

A script migráció előtt SQLite backup API-val időbélyeges, külön adatbázisfájlt készít. Sikertelen migrációnál a tranzakció visszagördül, a mentés megmarad. Visszaállítás előtt az alkalmazást le kell állítani, a hibás adatbázist külön meg kell őrizni, majd a mentést az eredeti pontos útvonalra visszamásolni és `PRAGMA integrity_check` / `PRAGMA foreign_key_check` ellenőrzéssel validálni.

## Kötelező későbbi tranzakciós határok

- Keretfoglalás: `BEGIN IMMEDIATE`, jogosultság és limitek újraellenőrzése, feltételes keretszámláló-frissítés, booking + usage + usage event létrehozása, majd commit a külső SimplePay hívás előtt.
- Véglegesítés/felszabadítás/visszaadás: egyedi event key, várt előző állapotra feltételes update, keretszámlálók és booking/pénzügyi státusz egy tranzakcióban.
- Elszámolás lezárása: jogosult bookingok és immutable itemek egy tranzakcióban; a `booking_id` unique constraint a végső duplaelszámolás-védelem.
