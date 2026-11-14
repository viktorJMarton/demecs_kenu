import sqlite3
import os
import shutil

DB_PATH = '/opt/kajak-kenu/kajak_kenu.db'
UPLOADS_DIR = '/opt/kajak-kenu/public/uploads'
SOURCE_TOUR_ID = 44
LOCATION_ID = 18

def fix_images():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get source images
    source_images = cursor.execute(
        "SELECT * FROM tour_images WHERE tour_id = ?", 
        (SOURCE_TOUR_ID,)
    ).fetchall()

    if not source_images:
        print(f"No source images found for tour {SOURCE_TOUR_ID}")
        return

    # Get target tours (Szigetköz tours without images)
    target_tours = cursor.execute("""
        SELECT t.id, t.title 
        FROM tours t
        WHERE t.tour_location_id = ? 
          AND t.id != ?
          AND (SELECT COUNT(*) FROM tour_images ti WHERE ti.tour_id = t.id) = 0
    """, (LOCATION_ID, SOURCE_TOUR_ID)).fetchall()

    for target in target_tours:
        target_id = target['id']
        print(f"Fixing images for tour {target_id} ({target['title']})")
        
        # Create target directory
        target_dir = os.path.join(UPLOADS_DIR, 'tours', str(target_id))
        os.makedirs(target_dir, exist_ok=True)

        for img in source_images:
            source_file_path = os.path.join(UPLOADS_DIR, img['file_path'])
            filename = img['filename']
            target_rel_path = f"tours/{target_id}/{filename}"
            target_file_path = os.path.join(UPLOADS_DIR, target_rel_path)

            # Copy main image
            if os.path.exists(source_file_path):
                shutil.copy2(source_file_path, target_file_path)
            else:
                print(f"Warning: Source file {source_file_path} missing!")
                continue
                
            # Try to copy thumbnail
            source_dir = os.path.dirname(source_file_path)
            name_no_ext, ext = os.path.splitext(filename)
            source_thumb = os.path.join(source_dir, f"{name_no_ext}_thumb.webp")
            target_thumb = os.path.join(target_dir, f"{name_no_ext}_thumb.webp")
            
            if os.path.exists(source_thumb):
                shutil.copy2(source_thumb, target_thumb)

            # Insert into database
            try:
                cursor.execute("""
                    INSERT INTO tour_images 
                    (tour_id, filename, file_path, alt_text, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                """, (target_id, filename, target_rel_path, img['alt_text'], img['sort_order']))
            except sqlite3.Error as e:
                print(f"DB Error inserting {filename}: {e}")

    conn.commit()
    conn.close()
    print("Done!")

if __name__ == '__main__':
    fix_images()
