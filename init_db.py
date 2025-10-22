#!/usr/bin/env python3
"""
Adatbázis inicializáló script
Futtatás: python init_db.py
"""

import sqlite3
import os

def init_database():
    # Projekt gyökérkönyvtár
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Adatbázis fájl path
    db_path = os.path.join(project_root, 'kajak_kenu.db')
    
    # Schema fájl path
    schema_path = os.path.join(project_root, 'flaskr', 'schema.sql')
    
    # Ellenőrizzük, hogy létezik-e a schema fájl
    if not os.path.exists(schema_path):
        print(f"HIBA: Schema fájl nem található: {schema_path}")
        return False
    
    try:
        # Adatbázis kapcsolat
        conn = sqlite3.connect(db_path)
        
        # Schema beolvasása és futtatása
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        conn.executescript(schema_sql)
        conn.commit()
        conn.close()
        
        print(f"✅ Adatbázis sikeresen inicializálva: {db_path}")
        print("📝 Minta adatok beszúrva")
        print("\n🚀 Most indíthatod a Flask alkalmazást:")
        print("   export FLASK_APP=flaskr")
        print("   flask run")
        print("\n🔧 Admin felület: http://localhost:5000/admin")
        
        return True
        
    except Exception as e:
        print(f"❌ HIBA az adatbázis inicializálása során: {str(e)}")
        return False

if __name__ == '__main__':
    print("🗃️  Kajak-Kenu adatbázis inicializálása...")
    init_database()