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
