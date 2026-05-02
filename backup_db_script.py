import shutil
import datetime
import os

db_path = "/opt/kajak-kenu/kajak_kenu.db"
timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
backup_path = f"/opt/kajak-kenu/kajak_kenu.db.backup.{timestamp}"

try:
    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)
        print(f"Successfully backed up database to {backup_path}")
    else:
        print(f"Error: Database file not found at {db_path}")
except Exception as e:
    print(f"Error during backup: {e}")
