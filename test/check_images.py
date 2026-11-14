import sqlite3
import os

db = sqlite3.connect('kajak_kenu.db')
db.row_factory = sqlite3.Row
cursor = db.cursor()

print("=== TOUR_IMAGES TÁBLA TARTALOM ===\n")
images = cursor.execute("SELECT * FROM tour_images").fetchall()

if not images:
    print("❌ NINCS EGYETLEN KÉP SEM AZ ADATBÁZISBAN!\n")
else:
    for img in images:
        print(f"ID: {img['id']}")
        print(f"  Tour ID: {img['tour_id']}")
        print(f"  Filename: {img['filename']}")
        print(f"  File Path: {img['file_path']}")
        
        # Ellenőrizzük, hogy a fájl létezik-e
        full_path = os.path.join('public', 'uploads', img['file_path'])
        exists = "✅ LÉTEZIK" if os.path.exists(full_path) else "❌ NEM LÉTEZIK"
        print(f"  Fájl: {full_path} - {exists}")
        print()

print("\n=== TOURS TÁBLA (első 3 túra) ===\n")
tours = cursor.execute("SELECT id, title FROM tours LIMIT 3").fetchall()
for tour in tours:
    print(f"Tour #{tour['id']}: {tour['title']}")
    tour_images = cursor.execute("SELECT COUNT(*) as cnt FROM tour_images WHERE tour_id = ?", (tour['id'],)).fetchone()
    print(f"  → Képek száma: {tour_images['cnt']}\n")

db.close()
