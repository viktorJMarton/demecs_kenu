#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script koordináták hozzáadására és tesztelésére
"""

from flaskr.db import get_db
from flaskr import create_app

def test_coordinates():
    app = create_app()
    
    with app.app_context():
        db = get_db()
        
        # Keressünk egy túrát koordináták nélkül
        tours_without_coords = db.execute('''
            SELECT id, title, location, tour_latitude, tour_longitude 
            FROM tours 
            WHERE tour_latitude IS NULL OR tour_longitude IS NULL
            LIMIT 3
        ''').fetchall()
        
        print("Túrák koordináták nélkül:")
        for tour in tours_without_coords:
            print(f"  ID: {tour[0]}, Cím: {tour[1]}, Helyszín: {tour[2]}")
        
        if tours_without_coords:
            # Adjunk hozzá koordinátákat az első túrához
            first_tour = tours_without_coords[0]
            tour_id = first_tour[0]
            
            # Budapest környéki mintakoordináták
            test_lat = 47.5238
            test_lng = 19.0379
            
            print(f"\nKoordináták hozzáadása a túrához (ID: {tour_id})")
            print(f"Lat: {test_lat}, Lng: {test_lng}")
            
            db.execute('''
                UPDATE tours 
                SET tour_latitude = ?, tour_longitude = ? 
                WHERE id = ?
            ''', (test_lat, test_lng, tour_id))
            db.commit()
            
            # Ellenőrizzük a változást
            updated_tour = db.execute('''
                SELECT id, title, tour_latitude, tour_longitude 
                FROM tours 
                WHERE id = ?
            ''', (tour_id,)).fetchone()
            
            print(f"Frissített túra:")
            print(f"  ID: {updated_tour[0]}")
            print(f"  Cím: {updated_tour[1]}")
            print(f"  Lat: {updated_tour[2]}")
            print(f"  Lng: {updated_tour[3]}")
        
        # Listázzuk az összes túrát koordinátákkal
        print("\n" + "="*50)
        print("Összes túra koordináta állapota:")
        
        all_tours = db.execute('''
            SELECT id, title, tour_latitude, tour_longitude 
            FROM tours 
            ORDER BY id
            LIMIT 10
        ''').fetchall()
        
        for tour in all_tours:
            coords_status = "✓" if (tour[2] is not None and tour[3] is not None) else "✗"
            lat_str = f"{tour[2]:10.6f}" if tour[2] is not None else "None".ljust(10)
            lng_str = f"{tour[3]:10.6f}" if tour[3] is not None else "None".ljust(10)
            print(f"{coords_status} ID: {tour[0]:2d}, Lat: {lat_str} Lng: {lng_str} - {tour[1][:40]}")

if __name__ == "__main__":
    test_coordinates()