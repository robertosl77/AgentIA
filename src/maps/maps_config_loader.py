# src/maps/maps_config_loader.py
import json
import os
from src.tenant import data_path

_instancia = None

class MapsConfigLoader:
    """
    Carga la configuración del módulo Maps desde maps_config.json.
    Singleton — se carga una vez y se reutiliza.
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("maps_config.json")
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            raise FileNotFoundError(f"Archivo no encontrado: {self.PATH}")
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── GETTERS ───────────────────────────────────────────────────────────────

    def get_api_key(self):
        """Retorna la API key desde la variable de entorno configurada."""
        nombre_variable = self.data.get("api_key_env", "GOOGLE_MAPS_API_KEY")
        key = os.getenv(nombre_variable)
        if not key:
            raise ValueError(f"Variable de entorno '{nombre_variable}' no configurada.")
        return key

    def get_pais(self):
        """Retorna el código de país para filtrar búsquedas."""
        return self.data.get("pais", "AR")

    def get_idioma(self):
        """Retorna el idioma para los resultados."""
        return self.data.get("idioma", "es")

    def get_max_resultados(self):
        """Retorna la cantidad máxima de resultados a mostrar."""
        return self.data.get("max_resultados", 3)

    def get_mensaje(self, clave):
        """Retorna un mensaje configurado por clave."""
        return self.data.get("mensajes", {}).get(clave, "")