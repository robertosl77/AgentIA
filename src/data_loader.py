# src/data_loader.py
import json
import os

_instancia = None

class DataLoader:
    """
    Carga y gestiona datos operativos desde datos.json.
    Singleton — se carga una vez y se reutiliza.
    A diferencia de ConfigLoader, estos datos se modifican en runtime.
    """

    PATH = r"data\datos.json"

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            raise FileNotFoundError(f"Archivo no encontrado: {self.PATH}")
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def guardar(self):
        """Persiste el estado actual en datos.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)