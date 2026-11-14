import sqlite3
from datetime import datetime

conn = sqlite3.connect('kajak_kenu.db')
cursor = conn.cursor()

cursor.execute('''
SELECT strftime('%Y-%m', date) as month, COUNT(*) as count 
FROM tours 
WHERE active = 1 
GROUP BY strftime('%Y-%m', date) 
ORDER BY month
''')

results = cursor.fetchall()
print('Túrák havi eloszlása:')
for month, count in results:
    print(f'{month}: {count} túra')

# Október 2025 konkrét túrái
print('\nOktóber 2025 túrák:')
cursor.execute('''
SELECT date, name, difficulty 
FROM tours 
WHERE strftime('%Y-%m', date) = '2025-10' 
AND active = 1
ORDER BY date
''')

october_tours = cursor.fetchall()
for date, name, difficulty in october_tours:
    print(f'{date}: {name} ({difficulty})')

conn.close()