import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.file_services.image_manager import ImageManager
import base64

# Imagen de prueba: un pixel rojo en JPEG
pixel_rojo = base64.b64encode(
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
    b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
    b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1eB'
    b'\xed\xa3\xc3\xc3\xc3\x00\xff\xd9'
).decode()

url = ImageManager().procesar(pixel_rojo, proyecto="farmacia")
print(f"✅ URL: {url}" if url else "❌ No se pudo subir")
