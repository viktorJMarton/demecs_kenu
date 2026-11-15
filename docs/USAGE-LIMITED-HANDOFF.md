# Usage limited

Fejlesztési átadás a másik eszközön futó VS Code Codex extension számára.

## Feladat és állapot

A felhasználó a Google Drive Demecs_kenu projekt utasításai szerint kérte a fejlesztés folytatását a VPS-en. Ezután kifejezetten kérte a munka átadását másik eszközre. Ez a munkamenet feltárást végzett; alkalmazáskódot nem módosított, teszteket nem futtatott, élesítést vagy adatbázis-módosítást nem végzett. A szerveres kapcsolat és a végrehajtó környezet többször megszakadt. A folytatást átvevő ügynök ellenőrizze újra a jelenlegi állapotot.

Repo: https://github.com/viktorJMarton/demecs_kenu
Utolsó ellenőrzött kész affiliate revízió: bdf4c2dfc3861f24cc2635dd67e066ee624cad72, feature/affiliate-rep-01.
A handoff/usage-limited ág ebből indul, és csak ezt az átadási dokumentumot adja hozzá. A repo alapértelmezett ága ettől eltér: feat/tour-images-and-admin-fixes. Ne abból indulj automatikusan az affiliate folytatásához.

## Folytatási pont: WORK-0007 / REP-02

A Drive Kanban legutóbbi ellenőrzésekor 84 feladatból 48 kész (kb. 57% darabszám szerint); REP-02 folyamatban, REP-03..09 és a későbbi feladatok backlogban. Ez kizárólag az affiliate modulra vonatkozik, nem a teljes weboldal készültségére.

REP-02: partnerenkénti admin összesítő kattintás, foglalás, résztvevő, bevétel és kedvezmény metrikákkal; üres és nagyobb adathalmazzal is olvasható, lapozható megjelenítés. Függőség: a kész REP-01 riportmodell.

VPS: ssh root@72.62.43.178
Projekt: /opt/kajak-kenu
Meglévő REP-02 worktree: /tmp/kajak-kenu-rep02
Meglévő ág: feature/affiliate-rep-02
Utolsó ellenőrzéskor HEAD bdf4c2d, és csak az alábbi három koordinációs fájl módosult, alkalmazáskód még nem:
- agent-workflow/work/AGENT-STATUS.md
- agent-workflow/work/ACTIVITY-LOG.md
- agent-workflow/work/TIMESHEET.md

A meglévő REP-02 primary claim: codex-root-20261115-rep02, 2026-11-15T13:30:25+01:00, working. E munkamenet nem módosította és nem zárta le ezt a claimet. Olvasd újra a naplót és ellenőrizd az aktív munkameneteket, majd a projekt orchestrator szabályai szerint dokumentáld az átvételt. A régi claim puszta kora nem elég az automatikus elvételhez.

## Kötelező források

Drive projektmappa: https://drive.google.com/drive/folders/1e_fnIaUfnkiXC3WFHqKqEwM4CKQJZ2f6
Affiliate specifikáció: https://docs.google.com/document/d/1aTScw26dMhbpwxuKQhNUip-OmMS2_tyPOF_QVsH3-4c/edit
Affiliate Kanban: https://docs.google.com/spreadsheets/d/1_p-G5fxMHNyHjjorFfiu_BHlS-mOjLPu2T7oJhYwdvQ/edit
Kanban fül: Feladatok; REP-02 a legutóbbi olvasáskor az 50. sorban.
Agent workflow: https://drive.google.com/drive/folders/16ikE1JONXsr8BA7AKBpWSsZgWwjt9JlS
Drive journal mappa: https://drive.google.com/drive/folders/1epfqnyiL0NFzNDBYw7YHIMZNtUzqhUln

Előbb olvasd az agent-workflow/AGENTS.md, agents/orchestrator.md, agents/reporting.md és a releváns testing/security szerepfájlokat, valamint a work/AGENT-STATUS.md, ACTIVITY-LOG.md és TIMESHEET.md fájlokat a legfrissebb worktree-ből. A Drive koordinációs markdown fájlok utolsó beolvasáskor üres táblázatsablonok voltak, miközben a szerveres REP-02 worktree részletes előzményeket tartalmazott. Őrizd meg mindkét oldalon a meglévő bejegyzéseket, egyeztesd és szinkronizáld a koordinációt; a Kanban a feladatstátuszok irányadó forrása.

## Releváns kód

- flaskr/affiliate_reporting.py: REP-01 kanonikus, read-only összesítés, get_affiliate_report_metrics.
- flaskr/admin/admin_affiliates.py: meglévő védett admin blueprint.
- flaskr/templates/admin/affiliates/index.html és detail.html: jelenlegi megjelenési minták.
- test/integration_tests/test_affiliate_reporting.py: kézzel ellenőrizhető adatkészlet és a riportmodell regressziói.
- test/endpoint_tests/test_admin_affiliates.py: admin jogosultsági és nézettesztek.
- docker-compose.dev.yml, Dockerfile.dev: izolált fejlesztési és hálózat nélküli tesztkörnyezet.

A REP-01 a kattintásokat és foglalási/pénzügyi adatokat külön aggregálja, így nem sokszorozza az összegeket joinokkal. A pénzügyi értékek a foglalási snapshotokból származnak. Az új nézet tartsa meg ezeket a szemantikákat; ne számoljon újra aktuális partnerszabályokból.

## Megőrzendő környezet

A /opt/kajak-kenu fő munkakönyvtár FEATURE-ios-safari-rendering-fix ágon állt, több meglévő, nem commitolt Safari/overlay/template módosítással és egyéb fájlokkal. Ne reseteld, ne stash-eld automatikusan, és ne másold rá az affiliate ágat. Használd a külön REP-02 worktree-t.

Futó konténerek: kajak-kenu-kajak-kenu-1 és kajak-kenu-nginx-1 az éles környezethez; kajak-kenu-dev-app-1 és kajak-kenu-dev-gateway-1 a DEV környezethez. DEV gateway: 127.0.0.1:18000. Ne indítsd újra az éles szolgáltatásokat a fejlesztési munka részeként.

Az előző REP-01 napló szerint 10 célzott és 226 teljes, hálózat nélküli DEV Docker teszt sikeres volt; ezt e munkamenet nem futtatta újra. A következő módosításnál futtasd a célzott és teljes regressziót, kérj független, szerepkör szerinti review-t, és csak tényleges bizonyíték alapján zárd a Kanban feladatot. Ne használj éles SimplePay tranzakciót.

Hitelesítő adatot ez a nyilvános átadási dokumentum nem tartalmaz. A VPS-belépéshez az átvevő eszközön helyben rendelkezésre álló hitelesítést használd.
