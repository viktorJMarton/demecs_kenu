"""Service helpers for editable site sections."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import get_db

TERMS_DEFAULT_BODY = """
<h2>1. Szolgáltató adatai</h2>
<ul>
    <li>Szolgáltató: Demecs Vizitúra Kft.</li>
    <li>Székhely: 1138 Budapest, Dunapart utca 11.</li>
    <li>Cégjegyzékszám: 01-09-123456</li>
    <li>Adószám: 12345678-2-41</li>
    <li>E-mail: hello@demecstura.hu</li>
    <li>Telefon: +36 30 555 1234</li>
</ul>
<h2>2. A szerződés tárgya</h2>
<p>A jelen Általános Szerződési Feltételek (ÁSZF) a Demecs Túra Kft. által szervezett vízi és természetjáró programok online foglalására, részvételére és fizetésére vonatkozik. A foglalás elküldésével a felhasználó elfogadja a jelen feltételeket.</p>
<h2>3. Foglalás menete</h2>
<ol>
    <li>Túra, dátum és létszám kiválasztása.</li>
    <li>Személyes, számlázási és felszereléshez szükséges adatok megadása.</li>
    <li>ÁSZF és Adatvédelmi Nyilatkozat elfogadása.</li>
    <li>Online SimplePay fizetés teljesítése.</li>
</ol>
<h2>4. Díjazás és fizetés</h2>
<p>A megjelenített árak bruttó árak, magyar forintban. A tranzakciók az OTP Mobil Kft. SimplePay felületén, titkosított csatornán keresztül zajlanak.</p>
<h2>5. Lemondás és módosítás</h2>
<ul>
    <li>7 napnál korábbi lemondás: 90% visszatérítés.</li>
    <li>7-3 nap között: 50% visszatérítés.</li>
    <li>72 órán belül vagy meg nem jelenés: nincs visszatérítés.</li>
    <li>Szolgáltatói módosítás esetén új időpontot ajánlunk vagy visszatérítjük a teljes összeget.</li>
</ul>
<h2>6. Résztvevők kötelezettségei</h2>
<p>A résztvevő valós adatokat szolgáltat, betartja a túravezetők utasításait, és megfelelő egészségügyi állapotban jelenik meg.</p>
<h2>7. Felelősség</h2>
<p>A programokon való részvétel saját felelősségre történik; a személyes tárgyakért és a szabályszegésből eredő károkért a szolgáltató nem felel.</p>
<h2>8. Panaszkezelés</h2>
<p>Panaszát a hello@demecstura.hu címen fogadjuk, 14 napon belül válaszolunk. Vita esetén a Budapesti Békéltető Testület illetékes.</p>
<h2>9. Záró rendelkezések</h2>
<p>Az ÁSZF-re a Polgári Törvénykönyv és a vonatkozó fogyasztóvédelmi jogszabályok irányadók. A módosításokat a weboldalon tesszük közzé.</p>
""".strip()

PRIVACY_DEFAULT_BODY = """
<h2>1. Adatkezelő</h2>
<p>Demecs Túra Kft. (1138 Budapest, Dunapart utca 11., hello@demecstura.hu, +36 30 555 1234).</p>
<h2>2. Kezelt adatok</h2>
<ul>
    <li>Azonosítók: név, számlázási adatok, céges adatok.</li>
    <li>Elérhetőségek: e-mail cím, telefonszám.</li>
    <li>Foglalási információk: túra adatai, résztvevők száma, mentőmellény méretek.</li>
    <li>Technikai adatok: IP-cím, böngésző típus.</li>
    <li>Fizetési adatok: SimplePay tranzakció-azonosító, státusz.</li>
</ul>
<h2>3. Adatkezelés célja és jogalapja</h2>
<p>A foglalások kezelése, fizetés, számlázás, ügyfélszolgálat és informatikai biztonság. Jogalap: szerződés teljesítése, jogi kötelezettség, jogos érdek.</p>
<h2>4. Adattovábbítás</h2>
<p>SimplePay (OTP Mobil Kft.) és könyvelő partner felé továbbítunk adatokat kizárólag szerződéses garanciák mellett.</p>
<h2>5. Megőrzési idők</h2>
<ul>
    <li>Foglalási adatok: 5 év.</li>
    <li>Számlaadatok: 8 év.</li>
    <li>Marketing hozzájárulás: visszavonásig.</li>
    <li>Szervernaplók: 90 nap.</li>
</ul>
<h2>6. Érintetti jogok</h2>
<p>Hozzáférés, helyesbítés, törlés, korlátozás, tiltakozás, adathordozhatóság. A kérelmekre 30 napon belül válaszolunk az adatvedelem@demecstura.hu címen.</p>
<h2>7. Jogorvoslat</h2>
<p>Nemzeti Adatvédelmi és Információszabadság Hatóság (NAIH) vagy bírósági út.</p>
<h2>8. Adatbiztonság</h2>
<p>TLS titkosítás, szerepkör-alapú hozzáférés, rendszeres mentések, fizetési adatok kezelése kizárólag SimplePay környezetben.</p>
<h2>9. Módosítás</h2>
<p>A tájékoztatót szükség esetén frissítjük, és a weboldalon tesszük közzé.</p>
""".strip()

# Seed data for first-run experience and validation fallbacks.
DEFAULT_SECTIONS: Dict[str, Dict[str, Any]] = {
    "hero": {
        "label": "Hero szekció",
        "content": {
            "headline": "Hello There",
            "subheadline": "Provident cupiditate voluptatem et in. Quaerat fugiat ut assumenda excepturi exercitat quasi.",
            "cta_label": "Túranaptár megnyitása",
            "cta_target": "modal:my_modal_7",
            "video_url": "/static/hero-bg.mp4",
        },
    },
    "faq": {
        "label": "Gyakran Ismételt Kérdések",
        "content": {
            "items": [
                {
                    "question": "Hogyan tudok foglalni?",
                    "answer": "Válassz egy túrát az oldalon, töltsd ki az űrlapot, és erősítsd meg a foglalást.",
                },
                {
                    "question": "Milyen felszerelést biztosítotok?",
                    "answer": "Minden túrán biztosítjuk a kajakot, evezőt, mentőmellényt és a szükséges kiegészítőket.",
                },
                {
                    "question": "Lehet-e lemondani a túrát?",
                    "answer": "A túra előtt legalább 48 órával díjmentesen lemondhatod vagy átfoglalhatod az időpontot.",
                },
            ]
            ,
            "tips": [
                "Fix Listaelem egy",
                "Fix Listaelem kettő",
                "Fix Listaelem három",
            ]
        },
    },
    "info_cards": {
        "label": "Infó kártyák",
        "content": {
            "heading": "Általános leírás a vállalkozásról",
            "cards": [
                {
                    "title": "Személyes méretek",
                    "description": "Lorem ipsum dolor sit amet et delectus accommodare his consul copiosae legendos.",
                },
                {
                    "title": "Nézhető hely képpel",
                    "description": "Lorem ipsum dolor sit amet et delectus accommodare his consul copiosae legendos.",
                },
                {
                    "title": "Második blokk, stb",
                    "description": "Lorem ipsum dolor sit amet et delectus accommodare his consul copiosae legendos.",
                },
            ],
            "highlights": [
                {"icon": "🖼️", "label": "Galéria"},
                {"icon": "🖼️", "label": "Élményeink"},
                {"icon": "🖼️", "label": "Hangulat"},
            ],
        },
    },
    "terms_page": {
        "label": "ÁSZF oldal",
        "content": {
            "title": "Általános Szerződési Feltételek",
            "effective_date": "2025. január 1.",
            "body": TERMS_DEFAULT_BODY,
        },
    },
    "privacy_page": {
        "label": "Adatvédelmi tájékoztató",
        "content": {
            "title": "Adatvédelmi és Adatkezelési Tájékoztató",
            "effective_date": "2025. január 1.",
            "body": PRIVACY_DEFAULT_BODY,
        },
    },
    "contact_socials": {
        "label": "Kapcsolati közösségi linkek",
        "content": {
            "facebook_url": "https://facebook.com/demecstura",
            "instagram_url": "https://instagram.com/demecstura",
            "tiktok_url": "https://www.tiktok.com/@demecstura",
        },
    },
    "contact_info": {
        "label": "Kapcsolati blokk",
        "content": {
            "heading": "Írj Nekünk",
            "subheading": "Keress minket bármikor — visszahívunk, amint a partra érünk.",
            "company_name": "Demecs Vizitúra",
            "phone": "+36 30 123 4567",
            "email": "hello@demecstura.hu",
            "address": "1138 Budapest, Duna-part",
            "note": "Foglalásokkal, csoportos igényekkel kapcsolatban is állunk rendelkezésre.",
        },
    },
    "partners": {
        "label": "Együttműködő partnereink",
        "content": {
            "heading": "Együttműködő Partnereink",
            "items": []
        },
    },
}


def _ensure_table() -> None:
    """Create storage and seed defaults once."""
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS page_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    for slug, meta in DEFAULT_SECTIONS.items():
        row = db.execute("SELECT 1 FROM page_sections WHERE slug = ?", (slug,)).fetchone()
        if not row:
            db.execute(
                "INSERT INTO page_sections (slug, label, content) VALUES (?, ?, ?)",
                (slug, meta["label"], json.dumps(meta["content"])),
            )
    db.commit()


def list_sections() -> List[Dict[str, Any]]:
    """Return all sections for admin editing UI."""
    _ensure_table()
    db = get_db()
    rows = db.execute(
        "SELECT slug, label, content, updated_at FROM page_sections ORDER BY slug"
    ).fetchall()

    sections: List[Dict[str, Any]] = []
    for row in rows:
        try:
            content = json.loads(row["content"]) if row["content"] else {}
        except json.JSONDecodeError:
            content = {}
        sections.append(
            {
                "slug": row["slug"],
                "label": row["label"],
                "content": content,
                "updated_at": row["updated_at"],
            }
        )
    return sections


def get_section(slug: str) -> Dict[str, Any]:
    """Load a single section with fallback to defaults."""
    _ensure_table()
    db = get_db()
    row = db.execute(
        "SELECT slug, label, content FROM page_sections WHERE slug = ?",
        (slug,),
    ).fetchone()

    if not row:
        default = DEFAULT_SECTIONS.get(slug, {"label": slug, "content": {}})
        return {"slug": slug, "label": default["label"], "content": default["content"]}

    try:
        content = json.loads(row["content"]) if row["content"] else {}
    except json.JSONDecodeError:
        content = {}
    return {"slug": row["slug"], "label": row["label"], "content": content}


def update_section(slug: str, label: str, content: Dict[str, Any]) -> None:
    """Insert or update the stored JSON blob for a section."""
    _ensure_table()
    db = get_db()
    payload = json.dumps(content, ensure_ascii=False)
    exists = db.execute("SELECT 1 FROM page_sections WHERE slug = ?", (slug,)).fetchone()

    if exists:
        db.execute(
            "UPDATE page_sections SET label = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
            (label, payload, slug),
        )
    else:
        db.execute(
            "INSERT INTO page_sections (slug, label, content) VALUES (?, ?, ?)",
            (slug, label, payload),
        )
    db.commit()
