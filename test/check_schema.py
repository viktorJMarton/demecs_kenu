import sqlite3

conn = sqlite3.connect('kajak_kenu.db')
cursor = conn.cursor()

# Tours tabla sema
cursor.execute("PRAGMA table_info(tours)")
tours_schema = cursor.fetchall()
print('Tours tabla oszlopai:')
for col in tours_schema:
    print(col)

print('\nOsszet tura szam:')
cursor.execute("SELECT COUNT(*) FROM tours")
total_count = cursor.fetchone()[0]
print(f'Osszes tura: {total_count}')

print('\nElso 5 tura:')
cursor.execute("SELECT * FROM tours LIMIT 5")
tours = cursor.fetchall()
for tour in tours:
    print(tour)

conn.close()