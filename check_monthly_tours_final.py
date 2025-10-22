import sqlite3

conn = sqlite3.connect('kajak_kenu.db')
cursor = conn.cursor()

cursor.execute("SELECT strftime('%Y-%m', date) as month, COUNT(*) as count FROM tours WHERE is_active = 1 GROUP BY strftime('%Y-%m', date) ORDER BY month")

results = cursor.fetchall()
print('Turak havi eloszlasa:')
for month, count in results:
    print(f'{month}: {count} tura')

print('\nOktober 2025 turak:')
cursor.execute("SELECT date, title, difficulty FROM tours WHERE strftime('%Y-%m', date) = '2025-10' AND is_active = 1 ORDER BY date")

october_tours = cursor.fetchall()
for date, title, difficulty in october_tours:
    print(f'{date}: {title} ({difficulty})')

print('\nNovember 2025 turak:')
cursor.execute("SELECT date, title, difficulty FROM tours WHERE strftime('%Y-%m', date) = '2025-11' AND is_active = 1 ORDER BY date")

november_tours = cursor.fetchall()
for date, title, difficulty in november_tours:
    print(f'{date}: {title} ({difficulty})')

conn.close()