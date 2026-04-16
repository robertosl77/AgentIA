# src/horarios/data_loader.py
import json
import os

# Cache de instancias por ruta
_instancias = {}

class DataLoader:
    """
    Carga y gestiona datos operativos de horarios.
    Singleton por ruta — se carga una vez por archivo y se reutiliza.
    A diferencia de ConfigLoader, estos datos se modifican en runtime.
    """

    DEFAULT_PATH = r"data/farmacia/horarios.json"

    def __new__(cls, path=None):
        global _instancias
        ruta = path or cls.DEFAULT_PATH
        if ruta not in _instancias:
            instancia = super().__new__(cls)
            instancia._path = ruta
            _instancias[ruta] = instancia
        return _instancias[ruta]

    def __init__(self, path=None):
        if not hasattr(self, 'data'):
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"Archivo no encontrado: {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def guardar(self):
        """Persiste el estado actual en el archivo de datos."""
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def recargar(self):
        """Recarga los datos desde el archivo."""
        self.data = self._cargar_archivo()
