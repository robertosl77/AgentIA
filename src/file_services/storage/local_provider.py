# src/file_services/storage/local_provider.py
import os
from src.file_services.storage.storage_provider import StorageProvider


class LocalProvider(StorageProvider):
    """
    Proveedor de almacenamiento local.
    Guarda archivos en el sistema de archivos bajo base_path/{carpeta}/{filename}.
    Útil para desarrollo y testing sin dependencias externas.
    """

    def __init__(self, base_path: str):
        self.base_path = base_path

    def subir(self, contenido: bytes, filename: str, carpeta: str) -> str:
        dir_path = os.path.join(self.base_path, carpeta)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, filename)
        with open(file_path, "wb") as f:
            f.write(contenido)
        return file_path.replace("\\", "/")
