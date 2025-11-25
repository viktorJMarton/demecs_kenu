import sqlite3
import shutil
import os
import sys

ROOT = os.path.dirname(__file__)
DB = os.path.join(ROOT, 'kajak_kenu.db')
SQL = os.path.join(ROOT, 'add_invoice_columns.sql')
BACKUP = os.path.join(ROOT, 'kajak_kenu.db.bak')

if not os.path.exists(DB):
    print('Database not found at', DB)
    sys.exit(2)
if not os.path.exists(SQL):
    print('Migration SQL not found at', SQL)
    sys.exit(2)

print('Backing up', DB, '->', BACKUP)
shutil.copy2(DB, BACKUP)

print('Applying migration', SQL)
conn = sqlite3.connect(DB)
try:
    with open(SQL, 'r', encoding='utf8') as f:
        sql = f.read()
    conn.executescript(sql)
    conn.commit()
    print('Migration applied successfully')
except Exception as e:
    print('Migration failed:', e)
    print('Restoring backup...')
    shutil.copy2(BACKUP, DB)
    print('Backup restored')
    sys.exit(1)
finally:
    conn.close()
