# src/auxilios/auxilios_data_loader.py
import json
import os
from src.tenant import data_path

_instancia = None

class AuxiliosDataLoader:
    """
    Carga y gestiona servicios de auxilio desde servicios_data.json.
    Singleton — se carga una vez y se reutiliza.
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("auxilio", "servicios_data.json")
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            estructura = {"servicios": []}
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def guardar(self):
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── SERVICIOS ─────────────────────────────────────────────────────────────

    def get_servicios(self):
        """Retorna la lista de servicios registrados."""
        return self.data.get("servicios", [])

    def existe_nro_movimiento(self, nro_movimiento):
        """Verifica si ya existe un servicio con ese nro_movimiento."""
        for s in self.get_servicios():
            if s.get("nro_movimiento") == nro_movimiento:
                return True
        return False

    def agregar_servicio(self, datos):
        """Agrega un servicio y persiste."""
        servicios = self.get_servicios()
        nuevo_id = max([s.get("id", 0) for s in servicios], default=0) + 1
        datos["id"] = nuevo_id
        servicios.append(datos)
        self.guardar()
        return nuevo_id

    def eliminar_servicio(self, servicio_id):
        """Elimina un servicio por ID y persiste."""
        servicios = self.get_servicios()
        self.data["servicios"] = [s for s in servicios if s.get("id") != servicio_id]
        self.guardar()