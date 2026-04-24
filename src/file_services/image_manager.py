# src/file_services/image_manager.py
import base64
import json
import os
import uuid
from datetime import datetime


class ImageManager:
    """
    Servicio transversal de gestión de archivos de imagen.
    Responsabilidades:
      - Decodificar base64 y detectar tipo de archivo
      - Convertir PDF a JPEG (página configurable)
      - Normalizar nombre del archivo
      - Delegar el almacenamiento al proveedor configurado por proyecto
    Cada proyecto puede usar un proveedor distinto (google_drive, local, etc.).
    El proveedor activo se define en data/file_services_config.json.
    """

    CONFIG_PATH = os.path.join("data", "file_services_config.json")

    def __init__(self):
        self.config = self._cargar_config()
        self._cache_proveedores = {}

    def _cargar_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── RESOLUCIÓN DE PROVEEDOR ───────────────────────────────────────────────

    def _get_proveedor(self, proyecto: str):
        """
        Resuelve el proveedor para el proyecto dado.
        Orden: proveedor del proyecto → proveedor_defecto → local hardcoded.
        Los proveedores se instancian una sola vez y se cachean por nombre.
        """
        nombre_proveedor = (
            self.config.get("storage", {})
                       .get("proyectos", {})
                       .get(proyecto, {})
                       .get("proveedor")
            or self.config.get("storage", {}).get("proveedor_defecto", "local")
        )

        if nombre_proveedor in self._cache_proveedores:
            return self._cache_proveedores[nombre_proveedor]

        definicion = self.config.get("proveedores", {}).get(nombre_proveedor, {})
        tipo = definicion.get("tipo", "local")

        if tipo == "google_drive":
            from src.file_services.storage.google_drive_provider import GoogleDriveProvider
            credentials_path = os.environ.get(definicion.get("env_credentials", ""), "")
            folder_id = os.environ.get(definicion.get("env_folder_id", ""), "")
            proveedor = GoogleDriveProvider(credentials_path, folder_id)
        else:
            from src.file_services.storage.local_provider import LocalProvider
            base_path = definicion.get("base_path", "data/archivos")
            proveedor = LocalProvider(base_path)

        self._cache_proveedores[nombre_proveedor] = proveedor
        return proveedor

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _detectar_tipo(self, data: bytes):
        """Detecta (mimetype, extension) por magic bytes."""
        if data[:4] == b'%PDF':
            return "application/pdf", "pdf"
        if data[:3] == b'\xff\xd8\xff':
            return "image/jpeg", "jpg"
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png", "png"
        return "image/jpeg", "jpg"

    def _normalizar_nombre(self, proyecto: str, ext: str) -> str:
        fecha = datetime.now().strftime("%Y%m%d")
        uid = str(uuid.uuid4())[:8]
        patron = self.config.get("filename", {}).get("patron", "{proyecto}_{fecha}_{uid}.{ext}")
        return patron.format(proyecto=proyecto, fecha=fecha, uid=uid, ext=ext)

    def _carpeta_para_proyecto(self, proyecto: str) -> str:
        return (
            self.config.get("storage", {})
                       .get("proyectos", {})
                       .get(proyecto, {})
                       .get("carpeta", proyecto)
        )

    # ── INTERFAZ PÚBLICA ──────────────────────────────────────────────────────

    def procesar(self, base64_data: str, proyecto: str):
        """
        Recibe el contenido en base64, lo prepara (convirtiendo PDF si aplica)
        y lo sube al proveedor configurado para el proyecto.
        Retorna la URL/path del archivo guardado, o None si ocurre un error.
        """
        try:
            contenido = base64.b64decode(base64_data)
            mimetype, ext = self._detectar_tipo(contenido)

            if mimetype == "application/pdf":
                from src.file_services.converters.pdf_converter import pdf_a_imagen
                pagina = self.config.get("imagen", {}).get("pdf_pagina", 0)
                contenido = pdf_a_imagen(contenido, pagina=pagina)
                ext = "jpg"

            filename = self._normalizar_nombre(proyecto, ext)
            carpeta = self._carpeta_para_proyecto(proyecto)

            proveedor = self._get_proveedor(proyecto)
            return proveedor.subir(contenido, filename, carpeta)

        except Exception as e:
            print(f"❌ ImageManager.procesar error: {e}")
            return None
