# iOS Safari megjelenítési és görgetési javítás

Dátum: 2026-11-01

## Bizonyított hibák

- Az iOS/WebKit felismerés a teljes `body` elemre `translate3d(0,0,0)` transzformációt és rejtett backface-t állított. Ez új containing blockot és stacking contextet hozott létre a fixed/sticky rétegek körül, majd a modalnyitás külön kódból ki- és visszaállította ugyanezeket a stílusokat.
- A `[data-tour-card]` alapállapota `opacity: 0` volt. A reduced-motion szabály letiltotta a láthatóvá tevő animációt, ezért a kártyák helye megmaradt, de a tartalmuk láthatatlan maradt.
- A foglalási modal scroll állapotát több inline handler és két külön script módosította. A nyitás/bezárás nem volt idempotens, és az egymásba ágyazott térkép/galéria rétegek feloldhatták egymás scroll lockját.
- Az iOS modal szabály `40vh` alsó paddinget alkalmazott, ami indokolatlanul nagy üres területet hozott létre.
- Ha a bélyegkép és az eredeti kép is hibás volt, a dinamikus galéria spinner/átlátszó kép állapotban maradhatott.

## Javítás

- A globális iOS `body`-transzformáció és minden kapcsolódó transform-mentés/visszaállítás megszűnt.
- A túrakártyák alapból láthatók; a belépő animáció csak `prefers-reduced-motion: no-preference` esetén indul. Reduced-motion alatt a kártyák és a 3D-s galériaszöveg explicit látható állapotot kapnak.
- Az `overlay-scroll-lock.js` tokenes, referencia-számlált scroll lockot ad a foglalási modalnak, térképnek és képgalériának. Az első lock pontos inline-stílus és scroll pozíció snapshotot készít, az utolsó unlock állítja vissza.
- A modal viewportmérete `dvh`-t és iOS safe-area insetet használ; a `40vh` workaround megszűnt.
- A dinamikus galéria eredeti képre vált, majd végleges hiba esetén olvasható helyettesítő üzenetet mutat; a túrainformáció és vezérlők ettől függetlenül használhatók.

Módosított fő fájlok:

- `flaskr/static/overlay-scroll-lock.js`
- `flaskr/static/map-overlay.js`
- `flaskr/static/modal-control.js`
- `flaskr/templates/base.html`
- `flaskr/templates/partials/hero_section.html`
- `flaskr/templates/partials/calendar_modal.html`
- `flaskr/templates/partials/tour_locations_section.html`
- `playwright/ios-rendering-regression.spec.js`

## Lefuttatott ellenőrzések

```text
BASE_URL=http://127.0.0.1:5000 npx playwright test playwright/ios-rendering-regression.spec.js --reporter=list --workers=1
6 passed (1.4m)

.venv/bin/pytest -q
151 passed in 23.46s
```

A böngészős teszt WebKitet használ 375, 390 és 430 CSS px szélességen, reduced-motion beállítással; WebKit és Chromium alatt ismételt modal-, térkép- és galériahasználatot, scroll-visszaállítást, tájolás/viewport-váltást, asztali 1440 px nézetet, vízszintes túlcsordulást és sikertelen képbetöltést is ellenőriz. A kritikus elemeknél számított opacity, méret és viewportba görgethetőség is ellenőrzött.

Képernyőképek:

- `test-results/ios-webkit-reduced-375.png`
- `test-results/ios-webkit-reduced-390.png`
- `test-results/ios-webkit-reduced-430.png`

A 390 px-es teljesoldalas képet vizuálisan is ellenőriztük; a helyszínkártya, túrakártyák, GYIK és kapcsolat tartalma folyamatosan látható.

## Korlát és kézi ellenőrzés

A feladathoz nem állt rendelkezésre videófájl vagy valódi iPhone/eszközfarm, ezért a javítás nem állítható valódi iOS Safari compositor-szinten igazoltnak. A hátralévő kézi menet:

1. Valódi iPhone-on, Safariban ellenőrizni normál és Beállítások > Kisegítő lehetőségek > Mozgás csökkentése módban; az energiatakarékos módot külön ki- és bekapcsolva.
2. Végiggörgetni a főoldalt a Hévíz-patak kártyáktól a GYIK aljáig, álló és fekvő tájolásban, a Safari címsávját megjelenítve és elrejtve.
3. Kétszer egymás után megnyitni/bezárni a galériát, térképet és túranaptárt; bezárás után ellenőrizni a visszatérést az előző scroll pozícióra és a további görgetést.
4. Rögzíteni az iPhone modellt, iOS/Safari verziót, reduced-motion és energiatakarékos állapotot.

Valószínű, de asztali WebKittel teljesen nem bizonyítható ok marad az iOS Safari compositor és a korábbi globális body-transzformáció kölcsönhatása a canvas/video, overflow és fixed rétegekkel. A közvetlenül bizonyított, láthatatlanságot okozó reduced-motion hiba ettől függetlenül megszűnt.
