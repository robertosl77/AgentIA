# src/auxilios/vehiculo_manager.py
import json
import os
import uuid
from src.tenant import data_path

_instancia = None


class VehiculoManager:
    """
    Gestiona el CRUD de vehículos en vehiculos.json.
    Singleton — se carga una vez y se reutiliza.
    Tipos: auxilio_propio (grúas propias), auxilio_auxiliado (vehículos atendidos).
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("persona", "vehiculos.json")
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            estructura = {
                "catalogo_tipo_vehiculo": ["auxilio_propio", "auxilio_auxiliado"],
                "vehiculos": {}
            }
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get_por_tipo(self, tipo):
        """Retorna lista de (vehiculo_id, datos) para el tipo dado."""
        return [
            (vid, datos)
            for vid, datos in self.data["vehiculos"].items()
            if tipo in datos.get("tipos", [])
        ]

    def buscar_por_patente(self, patente, tipo=None):
        """
        Busca un vehículo por patente, opcionalmente filtrando por tipo.
        Retorna (vehiculo_id, datos) o None.
        """
        for vid, datos in self.data["vehiculos"].items():
            if datos.get("patente", "").upper() == patente.strip().upper():
                if tipo is None or tipo in datos.get("tipos", []):
                    return (vid, datos)
        return None

    def get_vehiculo(self, vehiculo_id):
        """Retorna (vehiculo_id, datos) o None."""
        datos = self.data["vehiculos"].get(vehiculo_id)
        if datos:
            return (vehiculo_id, datos)
        return None

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def agregar(self, tipo, campos):
        """
        Agrega un vehículo nuevo con UUID autogenerado.
        campos: dict con los campos propios del tipo (patente, alias, ris, etc).
        Retorna vehiculo_id generado.
        """
        vehiculo_id = str(uuid.uuid4())
        self.data["vehiculos"][vehiculo_id] = {"tipos": [tipo], **campos}
        self._guardar_archivo()
        return vehiculo_id

    def actualizar_campo(self, vehiculo_id, campo, valor):
        """Actualiza o agrega un campo en un vehículo existente. Retorna True si se actualizó."""
        if vehiculo_id not in self.data["vehiculos"]:
            return False
        self.data["vehiculos"][vehiculo_id][campo] = valor
        self._guardar_archivo()
        return True

    def agregar_tipo(self, vehiculo_id, tipo):
        """Agrega un tipo al vehículo si no lo tiene ya. Retorna True si se agregó."""
        if vehiculo_id not in self.data["vehiculos"]:
            return False
        tipos = self.data["vehiculos"][vehiculo_id].setdefault("tipos", [])
        if tipo not in tipos:
            tipos.append(tipo)
            self._guardar_archivo()
        return True

    # ── BORRAR ────────────────────────────────────────────────────────────────

    def borrar(self, vehiculo_id):
        """Elimina un vehículo por ID. Retorna True si se borró."""
        if vehiculo_id in self.data["vehiculos"]:
            del self.data["vehiculos"][vehiculo_id]
            self._guardar_archivo()
            return True
        return False
