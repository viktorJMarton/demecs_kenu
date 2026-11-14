#!/usr/bin/env python3
"""
Adatbázis ellenőrzés - túrák listázása
"""

import sqlite3

def check_tours():
    try:
        conn = sqlite3.connect('kajak_kenu.db')
        cursor = conn.cursor()
        
        # Összes aktív túra számolása
        cursor.execute('SELECT COUNT(*) FROM tours WHERE is_active = 1')
        total_tours = cursor.fetchone()[0]
        print(f'📊 Összes aktív túra: {total_tours}')
        
        # Első 15 túra listázása
        cursor.execute('''
            SELECT title, date, price, location 
            FROM tours 
            WHERE date >= date("now") AND is_active = 1 
            ORDER BY date 
            LIMIT 15
        ''')
        tours = cursor.fetchall()
        
        print('\n🗓️ Következő 15 túra:')
        print('-' * 80)
        for i, (title, date, price, location) in enumerate(tours, 1):
            print(f'{i:2d}. {date} - {title[:40]:<40} | {price:>6} Ft | {location}')
        
        # Hónapok szerinti statisztika
        cursor.execute('''
            SELECT strftime('%Y-%m', date) as month, COUNT(*) as count
            FROM tours 
            WHERE date >= date("now") AND is_active = 1 
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month
            LIMIT 6
        ''')
        monthly_stats = cursor.fetchall()
        
        print('\n📈 Havi statisztika:')
        print('-' * 30)
        for month, count in monthly_stats:
            print(f'{month}: {count:2d} túra')
        
        conn.close()
        
    except Exception as e:
        print(f'Hiba: {e}')

if __name__ == "__main__":
    check_tours()