#!/usr/bin/env python3
"""
Túrák hozzáadása a következő 5 hónap minden hétvégéjére
"""

import sqlite3
import datetime
from typing import List, Tuple

# Túra adatok listája (váltakozva)
TOUR_TEMPLATES = [
    {
        'title': 'Hétvégi Tisza-tavi Kaland',
        'description': 'Pihentető hétvégi túra a gyönyörű Tisza-tavon, családoknak és kezdőknek ajánlott.',
        'time': '09:00',
        'duration': 180,
        'max_participants': 15,
        'price': 8500,
        'difficulty': 'Könnyű',
        'location': 'Tisza-tó, Tiszafüred',
        'distance': 12.5,
        'meeting_point': 'Tiszafüred, Fürdő utca parkoló',
        'equipment_included': 'Kajak, evező, mentőmellény, vízzáró táska',
        'what_to_bring': 'Kényelmes ruházat, napszemüveg, napkrém, ivóvíz'
    },
    {
        'title': 'Duna-parti Felfedező Túra',
        'description': 'Izgalmas hétvégi túra a Duna mentén, vadregényes tájak és történelmi helyek felfedezésével.',
        'time': '10:30',
        'duration': 240,
        'max_participants': 12,
        'price': 12000,
        'difficulty': 'Közepes',
        'location': 'Duna, Szentendre',
        'distance': 18.0,
        'meeting_point': 'Szentendre, Duna-part',
        'equipment_included': 'Kajak, evező, mentőmellény, térképes táska',
        'what_to_bring': 'Sport ruházat, sapka, uzsonna, 1.5L víz'
    },
    {
        'title': 'Balaton Déli Part Túra',
        'description': 'Hétvégi kaland a Balaton déli partján, festői kilátásokkal és fürdőzési lehetőséggel.',
        'time': '08:30',
        'duration': 300,
        'max_participants': 18,
        'price': 10500,
        'difficulty': 'Könnyű',
        'location': 'Balaton, Siófok',
        'distance': 15.0,
        'meeting_point': 'Siófok, Aranypart parkoló',
        'equipment_included': 'Kajak, evező, mentőmellény, strandtáska',
        'what_to_bring': 'Fürdőruha, törölköző, napszemüveg, védőkrém'
    },
    {
        'title': 'Velencei-tavi Vadászkastély Túra',
        'description': 'Kulturális hétvégi túra a Velencei-tavon, történelmi vadászkastély meglátogatással.',
        'time': '09:15',
        'duration': 210,
        'max_participants': 14,
        'price': 9500,
        'difficulty': 'Könnyű',
        'location': 'Velencei-tó, Agárd',
        'distance': 11.0,
        'meeting_point': 'Agárd, termálfürdő parkoló',
        'equipment_included': 'Kajak, evező, mentőmellény, túratérkép',
        'what_to_bring': 'Kényelmes cipő, hátizsák, fényképezőgép'
    },
    {
        'title': 'Hortobágyi Halastavak Túra',
        'description': 'Természetközeli hétvégi élmény a Hortobágyi halastavak között, madárles lehetőséggel.',
        'time': '07:45',
        'duration': 270,
        'max_participants': 10,
        'price': 11500,
        'difficulty': 'Közepes',
        'location': 'Hortobágy, Halastavak',
        'distance': 14.5,
        'meeting_point': 'Hortobágy, Nemzeti Park látogatóközpont',
        'equipment_included': 'Kajak, evező, mentőmellény, távcső',
        'what_to_bring': 'Csendes ruházat, tartalék póló, energiaszelet'
    }
]

def get_weekends_in_next_months(months: int = 5) -> List[datetime.date]:
    """
    Visszaadja az elkövetkező N hónap összes hétvégéjét (szombat és vasárnap)
    """
    weekends = []
    
    # Kezdő dátum: következő szombat
    start_date = datetime.date.today()
    days_until_saturday = (5 - start_date.weekday()) % 7  # 5 = szombat (0=hétfő)
    current_saturday = start_date + datetime.timedelta(days=days_until_saturday)
    
    # Végdátum: 5 hónap múlva
    end_date = start_date.replace(month=start_date.month + months) if start_date.month <= 7 else \
               start_date.replace(year=start_date.year + 1, month=start_date.month + months - 12)
    
    # Hétvégék gyűjtése
    current_date = current_saturday
    while current_date <= end_date:
        weekends.append(current_date)  # Szombat
        weekends.append(current_date + datetime.timedelta(days=1))  # Vasárnap
        current_date += datetime.timedelta(days=7)  # Következő szombat
    
    return sorted(weekends)

def create_tour_inserts(weekends: List[datetime.date]) -> List[Tuple]:
    """
    Létrehozza a túra beszúrási adatokat
    """
    tours = []
    template_index = 0
    
    for i, weekend_date in enumerate(weekends):
        template = TOUR_TEMPLATES[template_index % len(TOUR_TEMPLATES)]
        
        # Szombat/vasárnap megkülönböztetés
        day_suffix = " (Szombat)" if weekend_date.weekday() == 5 else " (Vasárnap)"
        
        tour_data = (
            template['title'] + day_suffix,
            template['description'],
            weekend_date.strftime('%Y-%m-%d'),
            template['time'],
            template['duration'],
            template['max_participants'],
            template['price'],
            template['difficulty'],
            template['location'],
            template['distance'],
            template['meeting_point'],
            template['equipment_included'],
            template['what_to_bring'],
            'Ingyenes lemondás 24 órával korábban. Időjárás függő program.',
            None,  # image_url
            None,  # tour_latitude  
            None,  # tour_longitude
            1,     # is_active
        )
        
        tours.append(tour_data)
        
        # Vasárnap után váltunk következő template-re
        if weekend_date.weekday() == 6:  # Vasárnap
            template_index += 1
    
    return tours

def insert_tours_to_database(db_path: str = "kajak_kenu.db"):
    """
    Beszúrja a túrákat az adatbázisba
    """
    try:
        # Adatbázis kapcsolat
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Hétvégék lekérése
        print("Hétvégék számítása...")
        weekends = get_weekends_in_next_months(5)
        print(f"Talált hétvége napok: {len(weekends)}")
        
        # Túra adatok készítése
        print("Túra adatok generálása...")
        tours = create_tour_inserts(weekends)
        print(f"Generált túrák: {len(tours)}")
        
        # SQL beszúrás
        insert_sql = """
        INSERT INTO tours (
            title, description, date, time, duration, max_participants, 
            price, difficulty, location, distance, meeting_point, 
            equipment_included, what_to_bring, cancellation_policy,
            image_url, tour_latitude, tour_longitude, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        print("Túrák beszúrása az adatbázisba...")
        cursor.executemany(insert_sql, tours)
        conn.commit()
        
        print(f"Sikeresen beszúrva {len(tours)} túra!")
        
        # Ellenőrzés
        cursor.execute("SELECT COUNT(*) FROM tours WHERE is_active = 1")
        total_tours = cursor.fetchone()[0]
        print(f"Összes aktív túra az adatbázisban: {total_tours}")
        
    except sqlite3.Error as e:
        print(f"Adatbázis hiba: {e}")
    except Exception as e:
        print(f"Általános hiba: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("🚣 Hétvégi túrák hozzáadása az adatbázishoz...")
    print("=" * 50)
    insert_tours_to_database()
    print("=" * 50)
    print("✅ Kész!")