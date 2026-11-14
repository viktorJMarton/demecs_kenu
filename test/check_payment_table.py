import sqlite3

conn = sqlite3.connect('kajak_kenu.db')
cursor = conn.cursor()

# Táblák listázása
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("Adatbázis táblák:")
for table in tables:
    print(f"  - {table[0]}")

# Ellenőrizzük a payment_transactions táblát
if ('payment_transactions',) in tables:
    print("\n✓ payment_transactions tábla létezik")
    cursor.execute("PRAGMA table_info(payment_transactions)")
    columns = cursor.fetchall()
    print("\nOszlopok:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
else:
    print("\n✗ payment_transactions tábla NEM található!")

conn.close()
