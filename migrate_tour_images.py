"""
Migration script to add image_data and mime_type columns to tour_images table.
Run this once to update the database schema.
"""

import sqlite3
import os

# Get the database path
db_path = os.path.join(os.path.dirname(__file__), 'kajak_kenu.db')

print(f"📁 Database path: {db_path}")

if not os.path.exists(db_path):
    print("❌ Database file not found!")
    exit(1)

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("🔍 Checking current table structure...")

# Check if columns already exist
cursor.execute("PRAGMA table_info(tour_images)")
columns = cursor.fetchall()
column_names = [col[1] for col in columns]

print(f"Current columns: {column_names}")

# Add image_data column if it doesn't exist
if 'image_data' not in column_names:
    print("➕ Adding 'image_data' column...")
    try:
        cursor.execute("ALTER TABLE tour_images ADD COLUMN image_data TEXT")
        print("✅ 'image_data' column added successfully")
    except sqlite3.OperationalError as e:
        print(f"⚠️ Warning: {e}")
else:
    print("✅ 'image_data' column already exists")

# Add mime_type column if it doesn't exist
if 'mime_type' not in column_names:
    print("➕ Adding 'mime_type' column...")
    try:
        cursor.execute("ALTER TABLE tour_images ADD COLUMN mime_type TEXT")
        print("✅ 'mime_type' column added successfully")
    except sqlite3.OperationalError as e:
        print(f"⚠️ Warning: {e}")
else:
    print("✅ 'mime_type' column already exists")

# Commit changes
conn.commit()

# Verify the changes
print("\n🔍 Verifying updated table structure...")
cursor.execute("PRAGMA table_info(tour_images)")
columns = cursor.fetchall()
print("\nFinal table structure:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

conn.close()

print("\n✅ Migration completed successfully!")
print("🚀 You can now restart your Flask application and upload images.")
