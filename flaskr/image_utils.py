import os
import io
from PIL import Image

# Try to register HEIF opener
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_DIMENSION = 1920
JPEG_QUALITY = 85

def process_and_save_image(file_storage, target_dir, filename):
    """
    Resizes and compresses an uploaded image, then saves it to the target directory.
    Returns the final filename (which might have a different extension, e.g. .jpg).
    """
    # Open the image
    # Note: file_storage.stream might need to be reset if it was read before
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    
    # Convert to RGB if necessary (e.g. for PNGs with transparency or RGBA)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    # Resize if too large
    width, height = img.size
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    # Force JPEG extension for consistency and compression
    base_name = os.path.splitext(filename)[0]
    final_filename = f"{base_name}.jpg"
    
    # Ensure unique filename
    counter = 1
    while os.path.exists(os.path.join(target_dir, final_filename)):
        final_filename = f"{base_name}_{counter}.jpg"
        counter += 1
        
    target_path = os.path.join(target_dir, final_filename)
    
    # Save with optimization
    img.save(target_path, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    
    return final_filename
