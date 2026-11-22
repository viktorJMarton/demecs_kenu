# Affiliate modul üzemeltetése

## Mentés, próba-visszaállítás és migráció

A telepítést végző üzemeltető először azonosítsa a futó Compose projektet, az alkalmazásszolgáltatást és a konténer SQLite fájljához csatolt host fájlt. A Contabo költözéskor az éles Compose fájl `/opt/kajak-kenu/compose.eles.json` volt. A mindenkori csatolás a futó konténer Mounts adataiban ellenőrizhető. A telepítés előtt rögzíteni kell a jelenlegi forrásverziót, image-et, Compose fájlt és a konfigurációt a telepítés privát mentésében. A hozzáférési adatokat és a mentett adatbázist a szerveren kell tartani korlátozott hozzáféréssel.

Az alábbi parancsok a kiadandó verzió munkakönyvtárából futnak. Az `élő-adatbázis` helyére a csatolásból ellenőrzött abszolút útvonal kerüljön. Migráláshoz a projekt függőségeivel rendelkező Python kell. A `--copy-only` módhoz elegendő a rendszer Pythonja.

```sh
umask 077
DB=/abszolut/utvonal/elo-adatbazis.db
RELEASE_DIR=$(mktemp -d /var/tmp/demecs-affiliate.XXXXXX)
PYTHON=/abszolut/utvonal/.venv/bin/python

"$PYTHON" scripts/migrate_affiliate.py --copy-only --database "$DB" --backup-path "$RELEASE_DIR/online-backup.sqlite"
"$PYTHON" scripts/migrate_affiliate.py --copy-only --database "$RELEASE_DIR/online-backup.sqlite" --backup-path "$RELEASE_DIR/rehearsal.sqlite"
"$PYTHON" scripts/migrate_affiliate.py --database "$RELEASE_DIR/rehearsal.sqlite" --backup-path "$RELEASE_DIR/rehearsal-before.sqlite"
"$PYTHON" scripts/migrate_affiliate.py --database "$RELEASE_DIR/rehearsal.sqlite" --backup-path "$RELEASE_DIR/rehearsal-first-pass.sqlite"
```

A SQLite online mentés a már commitolt WAL-adatokat is átmásolja. Hasonlítsd össze a próba előtt és után a meglévő táblák eredeti oszlopait és sorait. Ellenőrizd a `PRAGMA integrity_check` (`ok`) és a `PRAGMA foreign_key_check` (üres) eredményét, a második futás változatlanságát, valamint a főoldalt próbakörnyezetben. Mérd a visszaállítás és migráció idejét. A `flask init-db` parancs friss adatbázishoz használható és törölheti a meglévő táblákat.

A Contabón, a futó adatbázis 2026-11-22-i friss másolatán végrehajtott próba eredménye:

| Ellenőrzés | Eredmény |
| --- | --- |
| Online mentés / visszaállítás külön fájlba | 0,20 s / 0,08 s |
| Első migráció, hálózat nélküli konténerindítással és mentéssel | 2,21 s |
| Második migráció, hálózat nélküli konténerindítással és mentéssel | 0,95 s |
| Hét meglévő tábla eredeti adatai | Egyeztek |
| SQLite integritás és idegen kulcsok | `ok`, 0 eltérés |
| Gunicorn főoldal, letiltott ajánlói belépés és Safari szkript | HTTP 200, nincs affiliate cookie |

## Kiadás és visszaállítás

1. Egyeztesd az alkalmazás futó verzióját a kiadás Git-verziójával. A Contabón futó javításokat és a tényleges Compose-konfigurációt ellenőrizd a kiadás előtt.
2. Az első indulás környezetében legyen `AFFILIATE_PUBLIC_ENABLED=false`. Az adminfelület, a riportok, az elszámolás és a már indított fizetések visszahívásai működnek. Új ajánlás és kedvezmény csak engedélyezés után érvényesül.
3. Éles migráció előtt tedd karbantartási módba a foglalást, és állítsd le az alkalmazás és az ütemezett feladatok adatbázis-írásait. Készíts ellenőrzött, időbélyegzett mentést, majd futtasd a migrációt a tényleges csatolt fájlon a `--copy-only` kapcsoló nélkül. Ellenőrizd a fájl hozzáférését az alkalmazás futtató felhasználójával és a fenti SQLite-ellenőrzéseket.
4. Indítsd el a kiadást kikapcsolt kapcsolóval. Ellenőrizd a HTTPS főoldalt, az admin belépést, egy normál foglalás ár-előnézetét és az alkalmazásnaplókat. A próba-fizetést csak elkülönített környezetben, hiteles Sandbox-konfigurációval végezd.
5. A belső próba során hozd létre a tesztpartnert és szabályt az elkülönített környezetben. Engedélyezd ott az affiliate funkciót, nyisd meg a privát linket, ellenőrizd a kedvezményes árat, indíts Sandbox-fizetést, majd ellenőrizd a visszahívást, riportot és elszámolást. A próba naplójába a státusz, az ellenőrzött összegek és az eredmény kerüljön.
6. Éles aktiváláskor csak a jóváhagyott partnerlinkeket add ki. Az első órában ellenőrizd a fizetési visszahívások hibáit, a beragadt foglalásokat és a riportösszegeket. Szükség esetén az `AFFILIATE_PUBLIC_ENABLED=false` visszaállítása és az alkalmazás újralétrehozása leállítja az új affiliate forgalmat.
7. Kódvisszaállításkor tartsd meg az éles adatbázist, amennyiben az előző verzió kompatibilis a már megtörtént adatírásokkal. Mentésből csak leállított írók mellett, ellenőrzött külön fájlba állíts vissza `--copy-only` móddal. Őrizd meg az aktuális adatbázist és az esetleges WAL/SHM fájlokat. A mentés utáni foglalásokat és fizetéseket egyeztesd. A csatolt fájl cseréje után hozd újra létre a konténert, és ellenőrizd a csatolás forrását és az egyenlegeket.

### Kódvisszaállítási próba a Contabón

A friss éles másolaton először a korábbi alkalmazással, majd migráció után a kiadási jelölttel, végül ugyanazon a migrált fájlon ismét a korábbi alkalmazással ellenőriztük a főoldalt és a normál ár-előnézetet. Mindhárom esetben HTTP 200 érkezett és két résztvevőre az eredeti ár jelent meg. Az alkalmazáspróbák alatt az adatbázis ellenőrzőösszege változatlan maradt. Ez a próba a nyilvános olvasási útvonalak kompatibilitását igazolja. Ha az új verzió éles foglalást vagy affiliate adatot írt, visszaállítás előtt azokat külön egyeztesd.

## Ütemezett feladatok

Az üzemi Compose szolgáltatásban futtasd az alábbi parancsokat a `DATABASE_URL` csatolás ellenőrzése után. A foglalástakarítás futhat ötpercenként, a kattintásaggregálás naponta. Mindkét parancs egyszerre egy korlátozott méretű köteget dolgoz fel és ismételhető. Ha a kimenet `has_more=yes`, további köteg vár feldolgozásra. Figyeld a kilépési kódot és az ismétlődő hibákat.

```sh
python -m flask --app flaskr cleanup-affiliate-usages --batch-size 100
python -m flask --app flaskr aggregate-affiliate-clicks --batch-size 100
```

A késve érkezett sikeres fizetési visszahívásnál a `requires reconciliation` naplójelzés kézi egyeztetést igényel a SimplePay tranzakció és a foglalás között. A szoftver eltárolja a visszahívás bizonyítékát és megakadályozza, hogy egy közben felszabadított keretből túlfoglalás legyen.

## Adminisztráció

1. Az **Affiliate partnerek** oldalon hozz létre partnert, állítsd be a kedvezményt, jutalékot és keretet, majd aktív szabálynál másold ki a partnerlinket. A szabály módosítása új verzióval történik.
2. Az **Affiliate riport** oldalon partnerre, dátumra és forrásra szűrhetsz. A történeti, havi aggregátumot érintő szűrésnél teljes hónapokat válassz. A riport a lezárt, még ki nem fizetett elszámolás jutalékát a kifizetésig nyitott jutalékként tartja nyilván.
3. A **Partnerelszámolások** oldalon add meg a partnert és a budapesti dátumtartományt, majd ellenőrizd és készítsd elő az előnézetet. Ha előkészítés után lemondás történt, frissítsd a tervezetet úgy, hogy az érvénytelen tételek kikerüljenek, majd nézd át újra az összegeket.
4. Lezárás után nyomtathatod vagy letöltheted az elszámolást. A kifizetett státuszt az átutalás megtörténte után rögzítsd megjegyzéssel. A művelet csak a nyilvántartást módosítja. Lezárás után történt visszatérítésnél a pénzügy egyeztesse a rögzített történeti elszámolást és az érvénytelenített foglalást.

## Élesítési döntés

A kiadás feltétele a teljes tesztcsomag, a friss éles másolaton ellenőrzött mentés és próba-visszaállítás, a sikeres külső Sandbox próba privát partnerrel, a futó Contabo-verzió és csatolás ellenőrzése, valamint a kijelölt üzemeltető által ellenőrzött visszaállítási út. A hálózat nélküli teszt aláírt Sandbox-visszahívást és szimulált START-választ fed le, a külső Sandbox-oldal működését külön próba igazolja. Sikertelen vagy hiányzó feltételnél maradjon kikapcsolva az affiliate forgalom.

### Kiadási döntés záróellenőrzéskor

| Kanban | Ellenőrzött eredmény |
| --- | --- |
| REL-01–03 | A friss Contabo-adatmásolat mentése, visszaállítása, kétszeri migrációja és a használati leírás igazolt. |
| REL-04 | A kiadási image kikapcsolt affiliate kapcsolóval indult a próbán. A normál ár-előnézet egyezett. Az affiliate éles telepítése még hátravan. |
| REL-05 | A nyilvános Sandbox aláírt böngészős engedélyezését, lekérdezését és elutasítását ellenőriztük. A legfrissebb Hostinger image hálózat nélküli Gunicornján a hibás IPN-aláírás 400-at adott. Az ismételt helyi, aláírt `FINISHED` kérések egyetlen 2 400 Ft-os jutalékot és két szabályosan aláírt nyugtát eredményeztek. A saját Sandbox-fiókból érkező szolgáltatói IPN még ellenőrzésre vár. |
| REL-06 | A visszaállítási próba sikerült. Az éles affiliate aktiválás feltétele a kereskedő saját Sandbox IPN-próbája. |

### Tesztbizonyíték

A fejlesztői Compose tesztkonténere hálózat nélkül, `SIMPLEPAY_SANDBOX=true` beállítással fut. A teljes futtatás parancsa:

```sh
scripts/dev-compose.sh -p affiliate-regression build test
scripts/dev-compose.sh -p affiliate-regression run --no-deps --rm test
```

| Kanban | Ellenőrzött esetek |
| --- | --- |
| TST-01 | Friss és régi SQLite-séma, elkülönített mentés és kulcskorlátok, fizetési és elszámolási tesztadatok |
| TST-02–03 | Kedvezménytípusok, hatókör, kerekítés, plafon és hibás bemenet, vendég- és partnerkeret, időszakhatárok, párhuzamos foglalás |
| TST-04 | Új és meglévő cookie, verziórögzítés, utolsó érvényes kattintás, hibás, lejárt vagy inaktív partnerkód |
| TST-05–06 | Aláírt siker, hiba, megszakítás és timeout, ismételt esemény, visszatérítés, keret- és jutalékállapot, dupla elszámolás kizárása |
| TST-07–08 | Admin és CSRF ellenőrzés, manipulált előnézet, művelethez kötött megerősítés, UTF-8 export, fájlnév és egyező összegek, Chromium A4 PDF-ben látható összegek és rejtett vezérlők |
| TST-09, REL-05 | Normál foglalás és belső tesztpartner életciklusa szimulált Sandbox START-tal és aláírt IPN-nel, riporttal és kézi kifizetési státusszal |

A letölthető GitHub-kiadási csomag kizárólag forráskódot, konfigurációs mintákat és publikus statikus elemeket tartalmazhat. A repóban követett régi adatbázisok és mentések miatt a teljes Git-fájlfa csomagolása nem alkalmas terjesztésre.

A forráscsomag kézzel a `scripts/package-vps-release.sh` paranccsal készíthető az aktuális commitból. A GitHub CI a hálózat nélküli regresszió után tölti fel. A csomag mellé a célkörnyezet saját adatbázisa, feltöltési csatolása, naplókönyvtára és környezeti beállítása szükséges.

### Contabo Sandbox-próba előkészítése

A kiadási jelölttel a belső partnerfolyamat és az elszámolás öt célzott tesztje lefutott a Contabón, hálózat nélküli konténerben. A külön szintetikus SQLite-adatbázisban a tesztpartner 25 000 Ft eredeti árból 1 000 Ft kedvezményt adott. A szerver 24 000 Ft fizetendő összeget és 10% jutalékszabályt ellenőrzött. A próbaadatbázisban nincs foglalás vagy fizetési tranzakció.

A külső próba ehhez a szintetikus adatbázishoz, külön HTTPS-próbavégponthoz és az elkülönített környezetbe betöltött Sandbox kereskedői azonosítóhoz és aláírókulcshoz kapcsolódik. A kulcsokat csak a próbapéldány privát környezeti konfigurációjában kell tárolni. A Contabón futó éles alkalmazás meglévő SimplePay-beállítása változatlan.


A Hostinger DEV-en a nyilvános HUF Sandbox-demó böngészős fizetése aláírt `SUCCESS` választ adott 24 000 Ft-ra. A szolgáltató aláírt lekérdezése ugyanazt a tranzakciót `AUTHORIZED` állapotban igazolta. Az affiliate keret és jutalék a javítás után `FINISHED` állapotban véglegesíthető. Az engedélyezéstől az elszámolásig tartó folyamatot aláírt, szimulált `FINISHED` értesítéssel ellenőrzi a tesztcsomag. A saját Sandbox fiókhoz regisztrált IPN végpontra történő külső kézbesítés ellenőrzése nyitott.
