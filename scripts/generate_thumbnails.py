import os
import sys
from PIL import Image

# Define paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(BASE_DIR, 'public', 'uploads')

THUMB_WIDTH = 400
THUMB_QUALITY = 80

def generate_thumbnail(file_path):
    try:
        filename = os.path.basename(file_path)
        name, ext = os.path.splitext(filename)
        
        # Skip if it's already a thumbnail
        if name.endswith('_thumb'):
            return

        # Define thumbnail path (always .webp for efficiency)
        thumb_filename = f"{name}_thumb.webp"
        thumb_path = os.path.join(os.path.dirname(file_path), thumb_filename)
        
        # Check if thumbnail exists and is newer
        if os.path.exists(thumb_path):
            if os.path.getmtime(thumb_path) > os.path.getmtime(file_path):
                # print(f"Skipping {filename} (thumbnail up to date)")
                return

        print(f"Generating thumbnail for {filename}...")
        
        with Image.open(file_path) as img:
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Calculate new height to maintain aspect ratio
            width, height = img.size
            ratio = THUMB_WIDTH / width
            new_height = int(height * ratio)
            
            # Resize
            img.thumbnail((THUMB_WIDTH, new_height), Image.Resampling.LANCZOS)
            
            # Save as WebP
            img.save(thumb_path, format='WEBP', quality=THUMB_QUALITY)
            
        print(f"  -> Created {thumb_filename}")
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def main():
    if not os.path.exists(UPLOADS_DIR):
        print(f"Uploads directory not found: {UPLOADS_DIR}")
        return

    print(f"Scanning {UPLOADS_DIR} for images...")
    count = 0
    for root, dirs, files in os.walk(UPLOADS_DIR):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                generate_thumbnail(os.path.join(root, file))
                count += 1
    
    print(f"Finished scanning {count} files.")

if __name__ == '__main__':
    main()
