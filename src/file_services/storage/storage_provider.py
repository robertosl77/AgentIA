# src/file_services/storage/storage_provider.py
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """
    Contrato que deben cumplir todos los proveedores de almacenamiento.
    Para agregar un nuevo proveedor: heredar esta clase e implementar `subir`.
    """

    @abstractmethod
    def subir(self, contenido: bytes, filename: str, carpeta: str) -> str:
        """
        Sube el archivo al proveedor.
        Retorna la URL o path de acceso al archivo guardado.
        """
        pass
