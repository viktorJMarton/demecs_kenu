import os
import sys
from PIL import Image

# Add project root to path to import image_utils if needed, 
# but here we can just use the logic directly.

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'public', 'uploads')
MAX_DIMENSION = 1920
JPEG_QUALITY = 85

def optimize_image(file_path):
    try:
        img = Image.open(file_path)
        
        # Check if optimization is needed
        width, height = img.size
        file_size = os.path.getsize(file_path)
        
        # If image is small enough and file size is reasonable (e.g. < 500KB), skip
        if width <= MAX_DIMENSION and height <= MAX_DIMENSION and file_size < 500 * 1024:
            print(f"Skipping {file_path} (already optimized)")
            return

        print(f"Optimizing {file_path} ({width}x{height}, {file_size/1024:.1f} KB)...")
        
        # Convert to RGB if necessary (e.g. for PNGs with transparency or RGBA)
        # Only convert if we are saving as JPEG. If keeping PNG, we might want to keep transparency.
        # But for photos, JPEG is better.
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
        # Save back to the same path
        # If it's JPEG, use quality setting
        if ext in ('.jpg', '.jpeg'):
            img.save(file_path, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        elif ext == '.png':
            # For PNG, we can optimize but it's lossless usually. 
            # If it's a photo, it should be JPG, but we can't easily change extension without DB update.
            # We can just save with optimize=True
            img.save(file_path, format='PNG', optimize=True)
        elif ext == '.webp':
            img.save(file_path, format='WEBP', quality=JPEG_QUALITY)
            
        new_size = os.path.getsize(file_path)
        print(f"  -> Done. New size: {new_size/1024:.1f} KB")
        
    except Exception as e:
        print(f"Error optimizing {file_path}: {e}")

def main():
    print(f"Scanning {UPLOADS_DIR}...")
    for root, dirs, files in os.walk(UPLOADS_DIR):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                file_path = os.path.join(root, file)
                optimize_image(file_path)

if __name__ == '__main__':
    main()
