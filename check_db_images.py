import sqlite3
import os

# Ellenőrizzük az adatbázisban lévő képeket
db = sqlite3.connect('kajak_kenu.db')
db.row_factory = sqlite3.Row

print("=== KÉPEK AZ ADATBÁZISBAN ===")
images = db.execute('SELECT tour_id, filename, file_path FROM tour_images').fetchall()

for img in images:
    print(f"Tour {img['tour_id']}: {img['filename']}")
    print(f"  File path: {img['file_path']}")
    
    # Ellenőrizzük, hogy létezik-e a fájl
    full_path = os.path.join('public', 'uploads', img['file_path'])
    exists = "✅ LÉTEZIK" if os.path.exists(full_path) else "❌ HIÁNYZIK"
    print(f"  Fájl: {full_path} - {exists}")
    print()

db.close()