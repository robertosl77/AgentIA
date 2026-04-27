# src/data_loader.py
import json
import os
from src.tenant import data_path

_instancia = None

class DataLoader:
    """
    Carga y gestiona horarios desde horarios_data.json.
    Singleton — se carga una vez y se reutiliza.
    A diferencia de ConfigLoader, estos datos se modifican en runtime.
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("farmacia", "horarios_data.json")
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            raise FileNotFoundError(f"Archivo no encontrado: {self.PATH}")
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def guardar(self):
        """Persiste el estado actual en horarios_data.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)