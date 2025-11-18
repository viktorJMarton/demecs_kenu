"""Seed script to add extra tour locations and future tours."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Tuple

DB_PATH = Path(__file__).resolve().parents[1] / "kajak_kenu.db"

NEW_LOCATIONS = [
    {
        "name": "Bodrogzug, Tokaj",
        "latitude": 48.1535,
        "longitude": 21.4091,
    },
    {
        "name": "Szigetköz, Dunakiliti",
        "latitude": 47.9966,
        "longitude": 17.2594,
    },
    {
        "name": "Fertő-tó, Balf",
        "latitude": 47.6366,
        "longitude": 16.7258,
    },
    {
        "name": "Körös-holtág, Szarvas",
        "latitude": 46.8664,
        "longitude": 20.5492,
    },
]

TOURS = [
    {
        "title": "Tokaji Ártéri Felfedezés",
        "date": "2026-01-10",
        "time": "09:00",
        "duration": 210,
        "max_participants": 14,
        "price": 15500,
        "difficulty": "Kezdő",
        "location_name": "Bodrogzug, Tokaj",
        "description": "Ártéri labirintus, meleg tea és helyi borkóstoló a parton.",
        "distance": 16.5,
        "meeting_point": "Tokaj, Vízimolnár kikötő (Bodrog part)",
        "equipment_included": "Prémium túrakajak, mentőmellény, szárazzsák, meleg ital",
        "cancellation_policy": "48 órával indulás előtt díjmentes lemondás.",
    },
    {
        "title": "Bodrogzugi Fotós Szafári",
        "date": "2026-01-25",
        "time": "13:30",
        "duration": 180,
        "max_participants": 10,
        "price": 16500,
        "difficulty": "Kezdő",
        "location_name": "Bodrogzug, Tokaj",
        "description": "Lassú tempójú túra hivatásos fotós kísérettel és sastanyákkal.",
        "distance": 12.0,
        "meeting_point": "Tokaj, Fesztiválkatlan parkoló",
        "equipment_included": "Távcső, mentőmellény, vízálló táska",
        "cancellation_policy": "72 órán belüli lemondásnál 30% díj.",
    },
    {
        "title": "Tavaszi Áradás Expedíció",
        "date": "2026-02-22",
        "time": "08:00",
        "duration": 300,
        "max_participants": 12,
        "price": 18500,
        "difficulty": "Haladó",
        "location_name": "Bodrogzug, Tokaj",
        "description": "Áradó Bodrogon sodródó szigetek, erősebb áramlással és taktikai megállókkal.",
        "distance": 22.5,
        "meeting_point": "Tokaj, Aranyparti rév állomás",
        "equipment_included": "Túrakenuk, mentőmellény, forró leves a célban",
        "cancellation_policy": "Időjárás miatti lemondás esetén 100% visszatérítés.",
    },
    {
        "title": "Szigetközi Labirintus Túra",
        "date": "2026-03-07",
        "time": "09:30",
        "duration": 240,
        "max_participants": 16,
        "price": 14900,
        "difficulty": "Kezdő",
        "location_name": "Szigetköz, Dunakiliti",
        "description": "Rejtett csatornák és kiszélesedő ágak, madárles beiktatással.",
        "distance": 18.0,
        "meeting_point": "Dunakiliti, vízlépcső parkoló",
        "equipment_included": "Kajak, mentőmellény, vízhatlan térkép",
        "cancellation_policy": "48 órával indulás előtt díjmentes lemondás.",
    },
    {
        "title": "Napfelkelte Áramlat Szigetközben",
        "date": "2026-03-21",
        "time": "06:00",
        "duration": 150,
        "max_participants": 12,
        "price": 13900,
        "difficulty": "Kezdő",
        "location_name": "Szigetköz, Dunakiliti",
        "description": "Korai rajt kávészünettel, első napsugarak a Mosoni-Duna felett.",
        "distance": 11.0,
        "meeting_point": "Dunakiliti, vadvízi telep bejárat",
        "equipment_included": "Forró ital, mentőmellény, szárazzsák",
        "cancellation_policy": "24 órán belüli lemondásnál a díj 50%-a terhelődik.",
    },
    {
        "title": "Szigetközi Marathon Felkészítő",
        "date": "2026-04-04",
        "time": "08:30",
        "duration": 330,
        "max_participants": 10,
        "price": 19500,
        "difficulty": "Haladó",
        "location_name": "Szigetköz, Dunakiliti",
        "description": "Hosszú etap tempó edzésekkel, technika javító checkpointokkal.",
        "distance": 28.0,
        "meeting_point": "Rajka-Dunakiliti közötti sólyatér",
        "equipment_included": "Edzői rádiós támogatás, energia szelet, mentőmellény",
        "cancellation_policy": "5 nappal indulás előtt 100% visszatérítés.",
    },
    {
        "title": "Vadvízi Ébredés Dunakilitinél",
        "date": "2026-04-19",
        "time": "07:15",
        "duration": 210,
        "max_participants": 14,
        "price": 15900,
        "difficulty": "Kezdő",
        "location_name": "Szigetköz, Dunakiliti",
        "description": "Közepes sodrás, könnyed hullámok és gátak betekintéssel.",
        "distance": 15.5,
        "meeting_point": "Dunakiliti, erdészház melletti parkoló",
        "equipment_included": "Kajak, lapát, mentőmellény, snack csomag",
        "cancellation_policy": "48 órával indulás előtt díjmentes lemondás.",
    },
    {
        "title": "Fertő-tavi Flamingó Kör",
        "date": "2026-04-12",
        "time": "10:00",
        "duration": 180,
        "max_participants": 18,
        "price": 14900,
        "difficulty": "Kezdő",
        "location_name": "Fertő-tó, Balf",
        "description": "Sekély tavon madármegfigyelés és nádas-labirintus.",
        "distance": 13.0,
        "meeting_point": "Balf, kikötő melletti parkoló",
        "equipment_included": "Madárhatározó, mentőmellény, vízhatlan távcső",
        "cancellation_policy": "72 órán belül 30% kezelési költség.",
    },
    {
        "title": "Fertő-tavi Naplemente Chill",
        "date": "2026-05-02",
        "time": "18:00",
        "duration": 150,
        "max_participants": 20,
        "price": 13500,
        "difficulty": "Kezdő",
        "location_name": "Fertő-tó, Balf",
        "description": "Premixed chill zene, vízi piknik és fényfestés a parton.",
        "distance": 9.5,
        "meeting_point": "Balf, vízitelepi stég",
        "equipment_included": "SUP opcionálisan, mentőmellény, LED lámpa",
        "cancellation_policy": "48 órával indulás előtt díjmentes lemondás.",
    },
    {
        "title": "Fertő-tavi Szélteszt Haladó",
        "date": "2026-05-18",
        "time": "11:00",
        "duration": 240,
        "max_participants": 12,
        "price": 18900,
        "difficulty": "Haladó",
        "location_name": "Fertő-tó, Balf",
        "description": "Oldalszélben evezéstechnika és vészmanőverek gyakorlása.",
        "distance": 20.0,
        "meeting_point": "Balf, strand centrál",
        "equipment_included": "Szélfogó kabát, mentőmellény, biztosító kötél",
        "cancellation_policy": "Időjárásfüggő túra, vihar esetén új időpont.",
    },
    {
        "title": "Szent Iván-éji Fertő Túra",
        "date": "2026-06-20",
        "time": "20:30",
        "duration": 180,
        "max_participants": 18,
        "price": 15900,
        "difficulty": "Kezdő",
        "location_name": "Fertő-tó, Balf",
        "description": "Lampionok, csillaghullás és parázs-parti a nádas öblében.",
        "distance": 11.5,
        "meeting_point": "Balf, Fertő-parti sétány",
        "equipment_included": "Lámpások, mentőmellény, hideg limonádé",
        "cancellation_policy": "24 órán belüli lemondásnál 70% térítés.",
    },
    {
        "title": "Körös-holtág Csillagtúra",
        "date": "2026-04-26",
        "time": "19:30",
        "duration": 150,
        "max_participants": 15,
        "price": 12900,
        "difficulty": "Kezdő",
        "location_name": "Körös-holtág, Szarvas",
        "description": "Éjszakai evezés mécsesekkel és csillagképektől szegélyezve.",
        "distance": 9.0,
        "meeting_point": "Szarvas, Arborétum csónakház",
        "equipment_included": "Fejlámpa, mentőmellény, termosz tea",
        "cancellation_policy": "48 órával indulás előtt díjmentes lemondás.",
    },
    {
        "title": "Vízitök Labirintus Túra",
        "date": "2026-06-07",
        "time": "09:00",
        "duration": 210,
        "max_participants": 16,
        "price": 14900,
        "difficulty": "Kezdő",
        "location_name": "Körös-holtág, Szarvas",
        "description": "Sűrű vízitök mezők és növényismereti játék családoknak.",
        "distance": 14.0,
        "meeting_point": "Szarvas, Kacsa-tanya stég",
        "equipment_included": "Gyerekmentőmellény, vízálló térkép, harapnivaló",
        "cancellation_policy": "72 órán belül 30% kezelési költség.",
    },
    {
        "title": "Körös Ultra Haladó Edzés",
        "date": "2026-07-05",
        "time": "07:00",
        "duration": 360,
        "max_participants": 8,
        "price": 21500,
        "difficulty": "Haladó",
        "location_name": "Körös-holtág, Szarvas",
        "description": "Hosszú, tempós körök erőnléti fókuszokkal és GPS elemzéssel.",
        "distance": 32.0,
        "meeting_point": "Szarvas, vízisport centrum",
        "equipment_included": "Teljesítmény monitor, energia csomag, mentőmellény",
        "cancellation_policy": "7 nappal indulás előtt 100% visszatérítés.",
    },
    {
        "title": "Szarvasi Napkelte Chill",
        "date": "2026-07-19",
        "time": "05:30",
        "duration": 150,
        "max_participants": 18,
        "price": 13500,
        "difficulty": "Kezdő",
        "location_name": "Körös-holtág, Szarvas",
        "description": "Korai madárdal, reggeli smoothie és vízre épített reggeli.",
        "distance": 10.5,
        "meeting_point": "Szarvas, Mini Magyarország bejárata melletti stég",
        "equipment_included": "Mentőmellény, könnyű reggeli, vízhatlan táska",
        "cancellation_policy": "48 órával indulás előtt díjmentes lemondás.",
    },
]


def ensure_locations(cur: sqlite3.Cursor) -> Dict[str, Tuple[int, float, float]]:
    for loc in NEW_LOCATIONS:
        cur.execute(
            "INSERT OR IGNORE INTO tour_locations (name, latitude, longitude) VALUES (?, ?, ?)",
            (loc["name"], loc["latitude"], loc["longitude"]),
        )

    placeholders = ",".join("?" for _ in NEW_LOCATIONS)
    rows = cur.execute(
        f"SELECT id, name, latitude, longitude FROM tour_locations WHERE name IN ({placeholders})",
        [loc["name"] for loc in NEW_LOCATIONS],
    ).fetchall()

    lookup: Dict[str, Tuple[int, float, float]] = {}
    for row in rows:
        lookup[row[1]] = (row[0], row[2], row[3])
    return lookup


def seed_tours(cur: sqlite3.Cursor, lookup: Dict[str, Tuple[int, float, float]]) -> Tuple[int, int]:
    inserted = 0
    skipped = 0
    for tour in TOURS:
        if tour["location_name"] not in lookup:
            raise RuntimeError(f"Hiányzó lokáció: {tour['location_name']}")

        exists = cur.execute(
            "SELECT 1 FROM tours WHERE title = ? AND date = ?",
            (tour["title"], tour["date"]),
        ).fetchone()
        if exists:
            skipped += 1
            continue

        loc_id, lat, lng = lookup[tour["location_name"]]
        cur.execute(
            """
            INSERT INTO tours (
                title,
                description,
                date,
                time,
                duration,
                max_participants,
                price,
                difficulty,
                location,
                distance,
                meeting_point,
                equipment_included,
                cancellation_policy,
                tour_latitude,
                tour_longitude,
                tour_location_id,
                is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                tour["title"],
                tour["description"],
                tour["date"],
                tour["time"],
                tour["duration"],
                tour["max_participants"],
                tour["price"],
                tour["difficulty"],
                tour["location_name"],
                tour["distance"],
                tour["meeting_point"],
                tour["equipment_included"],
                tour["cancellation_policy"],
                lat,
                lng,
                loc_id,
            ),
        )
        inserted += 1
    return inserted, skipped


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        lookup = ensure_locations(cur)
        inserted, skipped = seed_tours(cur, lookup)
        conn.commit()
        print(f"Lokációk száma ebben a futásban: {len(lookup)} (új vagy meglévő)")
        print(f"Új túrák beszúrva: {inserted}, kihagyva (duplikátum): {skipped}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
