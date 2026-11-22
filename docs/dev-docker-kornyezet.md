# Elkülönített DEV Docker-környezet

Ez a környezet ugyanazon a szerveren futtatható, de nem használja a PROD konténer, adatbázis, feltöltések vagy `.env` fájl erőforrásait.

## Biztonsági határok

- külön Compose-projektnév: `kajak-kenu-dev`;
- csak a hitelesítő adat nélküli DEV Nginx-gateway publikál portot a host `127.0.0.1:18000` címére;
- az alkalmazás kizárólag a belső `dev-isolated` hálózathoz kapcsolódik, így nem érheti el a SimplePay vagy SMTP külső végpontjait;
- külön Docker volume-ok a DEV adatbázishoz, cache-hez és feltöltésekhez;
- a build contextből kizárt minden `.env`, SQLite-adatbázis, mentés és PROD feltöltés;
- a `scripts/dev-compose.sh` wrapper letiltja a gyökérben lévő PROD `.env` automatikus Compose-beolvasását;
- `SIMPLEPAY_SANDBOX=true`, nem éles hitelesítő adatok;
- belső Docker-hálózat, ezért a konténerből nincs kimenő internetkapcsolat;
- a tesztkonténer teljesen hálózat nélkül fut;
- read-only root fájlrendszer, eldobott Linux capability-k és `no-new-privileges`.

Az alap DEV admin felhasználó `dev_admin`, jelszava `dev-only-change-me`. A szolgáltatás kizárólag localhoston érhető el; megosztott fejlesztői környezet előtt a hitelesítőket felül kell írni.

## Ellenőrzés és használat

```bash
scripts/dev-compose.sh config
scripts/dev-compose.sh build
scripts/dev-compose.sh run --rm test
scripts/dev-compose.sh up -d app gateway
scripts/dev-compose.sh ps
```

DEV felület: `http://127.0.0.1:18000/`

Leállítás:

```bash
scripts/dev-compose.sh down
```

A DEV-adatok tudatos törlése csak külön, kézi döntéssel történjen:

```bash
scripts/dev-compose.sh down --volumes
```

Az utolsó parancs visszaállíthatatlanul törli a DEV volume-okat; PROD erőforrást nem céloz.


## Affiliate próba Hostinger szerveren

A Hostinger külön affiliate DEV projektje a szerveren a 18081-es helyi porton fut. A normál DEV-projekt a megszokott 18000-es porton marad. A projekt külön köteteket használ, így újraindításkor az affiliate próbaadatok megmaradnak.

```bash
KAJAK_KENU_DEV_PORT=18081 scripts/dev-compose.sh -p demecs-affiliate-dev up -d --build --wait app gateway
scripts/dev-compose.sh -p demecs-affiliate-dev run --no-deps --rm test
```

A felület a saját gépről SSH-alagúton érhető el. A parancs futása közben nyisd meg a `http://localhost:18081/` címet.

```bash
ssh -N -L 18081:127.0.0.1:18081 root@72.62.43.178
```

A `HOSTINGER-DEV` ajánlói kód a szintetikus Hostinger affiliate próbatúrán két résztvevőnek 1 000 Ft kedvezményt ad a 25 000 Ft-os árból. Az alkalmazás belső hálózatot használ, a fizetési tesztek pedig hálózat nélküli konténerben futnak. A külső SimplePay Sandbox-próba külön teszthitelesítőket igényel.

### Külső demó START-próba

A SimplePay nyilvános HUF demófiókjával a kiadási jelölt aláírt START-kérését a szolgáltató Sandbox API-ja elfogadta. Az alkalmazás ellenőrizte a válasz aláírását, 24 000 Ft-tal rögzítette a függő tranzakciót, és a `sb-checkout.simplepay.hu` tesztoldalra irányított. A hálózati próba külön, eldobható konténerben és szintetikus adatbázison futott. A rendes DEV-példány továbbra is belső hálózatot használ.

A nyilvános demó fizetésindításra és böngészős visszatérésre alkalmas. A teljes kereskedői folyamat ellenőrzéséhez a SimplePay saját Sandbox-fiókot ír elő. [Hivatalos SimplePay demóleírás](https://simplepartner.hu/download.php?target=demomerchanthu)

Chromiumban a szolgáltató fizetőoldala is betöltött, megjelent rajta a Sandbox jelzés, a nyilvános HUF demókereskedő és a 24 000 Ft-os összeg. A megszakítás során a helyi visszatérési címre nem érkezett elfogható kérés. A szolgáltatói visszatérés és az IPN továbbra is nyitott ellenőrzés.


A szolgáltató Sandbox fizetőoldala a beépített tesztkártyával aláírt `SUCCESS` böngészős választ adott a 24 000 Ft-os tranzakcióra. A SimplePay aláírt lekérdezési válasza ugyanarra a tranzakcióra `AUTHORIZED` állapotot és 24 000 Ft-ot adott. Ez a próba az engedélyezést igazolta. A korábbi változat már a böngészős visszatéréskor véglegesítette a keretet és elszámolta a jutalékot a szintetikus adatbázisban. A javított változat az affiliate foglalást függőben hagyja, amíg aláírt `FINISHED` esemény nem érkezik. Ezt a sorrendet és a 2 400 Ft-os jutalék egyszeri rögzítését automatizált teszt ellenőrzi. Az élő Sandbox IPN kézbesítési próbához a kereskedő saját tesztfiókjában regisztrált végpont szükséges. [SimplePay fizetési dokumentáció](https://simplepartner.hu/download.php?target=v21docen)

Az elutasított kártyás ág is végigfutott a SimplePay nyilvános Sandbox tesztkártyájával. Az eredeti, aláírt `FAIL` böngészős visszatérés kétszeri feldolgozása egy keretfelszabadítást eredményezett. A 24 000 Ft-os foglalás sikertelen státuszban maradt, és a riportban nem keletkezett fizetett bevétel vagy jutalék.
