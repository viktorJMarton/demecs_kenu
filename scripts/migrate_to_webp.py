
import os
import sqlite3
import shutil
from PIL import Image

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'kajak_kenu.db')
UPLOADS_DIR = os.path.join(BASE_DIR, 'public', 'uploads')
BACKUP_DIR = os.path.join(BASE_DIR, 'public', 'uploads_backup_pre_webp')

MAX_DIMENSION = 1920
WEBP_QUALITY = 80

def setup_backup():
    if not os.path.exists(BACKUP_DIR):
        print(f"Creating backup directory: {BACKUP_DIR}")
        os.makedirs(BACKUP_DIR)

def convert_image(file_path):
    """
    Converts a single image file to WebP and resizes it.
    Returns the new file path and new filename if successful, else None.
    """
    try:
        if not os.path.exists(file_path):
            return None, None
            
        filename = os.path.basename(file_path)
        name, ext = os.path.splitext(filename)
        
        # Skip if already webp
        if ext.lower() == '.webp':
            return None, None
            
        # Define new path
        new_filename = f"{name}.webp"
        new_file_path = os.path.join(os.path.dirname(file_path), new_filename)
        
        # Open and process
        img = Image.open(file_path)
        
        # Handle modes
        if img.mode in ('P', 'CMYK'):
            img = img.convert('RGB')
            
        # Resize
        width, height = img.size
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
        # Save as WebP
        img.save(new_file_path, format='WEBP', quality=WEBP_QUALITY, method=4)
        print(f"Converted: {filename} -> {new_filename}")
        
        return new_file_path, new_filename
        
    except Exception as e:
        print(f"Failed to convert {file_path}: {e}")
        return None, None

def backup_original(file_path):
    try:
        # Replicate folder structure in backup
        rel_path = os.path.relpath(file_path, UPLOADS_DIR)
        backup_path = os.path.join(BACKUP_DIR, rel_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(file_path, backup_path)
    except Exception as e:
        print(f"Backup failed for {file_path}: {e}")

def process_table(cursor, table_name):
    print(f"\nProcessing table: {table_name}...")
    cursor.execute(f"SELECT id, file_path, filename FROM {table_name}")
    rows = cursor.fetchall()
    
    updated_count = 0
    
    for row in rows:
        row_id, db_path, db_filename = row
        full_path = os.path.join(UPLOADS_DIR, db_path)
        
        # Check if file exists
        if not os.path.exists(full_path):
            print(f"Warning: File not found for ID {row_id}: {full_path}")
            continue
            
        # Backup original
        backup_original(full_path)
        
        # Convert
        new_path, new_filename = convert_image(full_path)
        
        if new_path and new_filename:
            # Update DB
            # db_path might include subdirectories like 'tours/1/image.jpg'
            # We need to replace the extension in the db_path
            dir_name = os.path.dirname(db_path)
            new_db_path = os.path.join(dir_name, new_filename).replace('\\', '/')
            
            cursor.execute(
                f"UPDATE {table_name} SET file_path = ?, filename = ? WHERE id = ?",
                (new_db_path, new_filename, row_id)
            )
            
            # Optional: Remove original file after successful conversion and update
            # os.remove(full_path) 
            
            updated_count += 1
            
    return updated_count

def main():
    print("Starting WebP Migration...")
    setup_backup()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Tour images
        count_tours = process_table(cursor, 'tour_images')
        
        # Location images (if table exists)
        try:
            count_locs = process_table(cursor, 'location_images')
        except sqlite3.OperationalError:
            print("location_images table not found, skipping.")
            count_locs = 0
            
        conn.commit()
        print(f"\nMigration complete!")
        print(f"Updated {count_tours} tour images.")
        print(f"Updated {count_locs} location images.")
        print(f"Originals backed up to: {BACKUP_DIR}")
        
    except Exception as e:
        conn.rollback()
        print(f"\nCRITICAL ERROR: {e}")
        print("Rolled back database changes.")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
