import sqlite3

db = sqlite3.connect('kajak_kenu.db')
db.row_factory = sqlite3.Row

print("=== TÚRÁK AMELYEKHEZ VANNAK KÉPEK ===\n")
tours = db.execute('''
    SELECT DISTINCT t.id, t.title, t.date, COUNT(ti.id) as image_count
    FROM tours t
    INNER JOIN tour_images ti ON t.id = ti.tour_id
    GROUP BY t.id
    ORDER BY t.date DESC
''').fetchall()

for tour in tours:
    print(f"Tour #{tour['id']}: {tour['title']}")
    print(f"  Dátum: {tour['date']}")
    print(f"  Képek: {tour['image_count']} db\n")

db.close()
