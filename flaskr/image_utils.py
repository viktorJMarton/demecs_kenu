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
WEBP_QUALITY = 80

def process_and_save_image(file_storage, target_dir, filename):
    """
    Resizes and compresses an uploaded image, then saves it to the target directory as WebP.
    Returns the final filename (e.g. .webp).
    """
    # Open the image
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    
    # Convert to RGB if necessary (WebP supports transparency but RGB is safer for consistent photos)
    # If image has transparency (RGBA), keep it for WebP, otherwise convert P/CMYK to RGB
    if img.mode in ('P', 'CMYK'):
        img = img.convert('RGB')
    
    # Resize if too large
    width, height = img.size
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    # Force WebP extension
    base_name = os.path.splitext(filename)[0]
    final_filename = f"{base_name}.webp"
    
    # Ensure unique filename
    counter = 1
    while os.path.exists(os.path.join(target_dir, final_filename)):
        final_filename = f"{base_name}_{counter}.webp"
        counter += 1
        
    target_path = os.path.join(target_dir, final_filename)
    
    # Save with optimization
    # WebP supports both lossy and lossless. We use lossy keying off quality=80
    img.save(target_path, format='WEBP', quality=WEBP_QUALITY, method=4)
    
    return final_filename
