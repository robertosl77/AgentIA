# src/cliente/direccion_manager.py
import json
import os
import uuid
from src.tenant import data_path

_instancia = None


class DireccionManager:
    """
    Gestiona el CRUD de direcciones físicas en direcciones.json.
    Singleton — se carga una vez y se reutiliza.
    Las direcciones se almacenan sin referencias a personas — el vínculo
    persona↔dirección (con tipo: casa, trabajo, etc.) vive en personas.json.
    Los datos físicos provienen de Maps (place_id, coordenadas, componentes).
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("persona", "direcciones.json")
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            estructura = {
                "catalogo_tipo_direccion": ["casa", "trabajo", "facturacion", "envio"],
                "direcciones": {}
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

    # ── CATÁLOGO ──────────────────────────────────────────────────────────────

    def get_catalogo_tipo(self):
        return self.data.get("catalogo_tipo_direccion", [])

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get(self, direccion_id):
        """Retorna (direccion_id, datos) o None."""
        datos = self.data["direcciones"].get(direccion_id)
        if datos:
            return (direccion_id, datos)
        return None

    def buscar_exacta(self, campos):
        """
        Busca una dirección existente para deduplicar antes de crear una nueva.
        Estrategia: primero por place_id (exacto), luego por campos físicos normalizados.
        Retorna (direccion_id, datos) o None.
        """
        place_id = campos.get("place_id", "")
        if place_id:
            for did, datos in self.data["direcciones"].items():
                if datos.get("place_id") == place_id:
                    return (did, datos)

        CAMPOS_FISICOS = ["calle", "altura", "entre_calle_1", "entre_calle_2", "piso", "depto", "localidad", "codigo_postal", "provincia"]
        entrada = {k: campos.get(k, "").strip().lower() for k in CAMPOS_FISICOS}
        for did, datos in self.data["direcciones"].items():
            existente = {k: datos.get(k, "").strip().lower() for k in CAMPOS_FISICOS}
            if existente == entrada:
                return (did, datos)
        return None

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def agregar(self, campos):
        """
        Agrega una dirección nueva con UUID autogenerado.
        campos debe incluir los componentes de Maps + piso/depto manual.
        Retorna el direccion_id generado.
        """
        direccion_id = str(uuid.uuid4())
        self.data["direcciones"][direccion_id] = {
            "direccion_formateada": campos.get("direccion_formateada", ""),
            "calle": campos.get("calle", "").strip().lower(),
            "altura": campos.get("altura", "").strip(),
            "entre_calle_1": campos.get("entre_calle_1", "").strip().lower(),
            "entre_calle_2": campos.get("entre_calle_2", "").strip().lower(),
            "piso": campos.get("piso", "").strip().lower(),
            "depto": campos.get("depto", "").strip().lower(),
            "localidad": campos.get("localidad", "").strip().lower(),
            "codigo_postal": campos.get("codigo_postal", "").strip(),
            "provincia": campos.get("provincia", "").strip().lower(),
            "place_id": campos.get("place_id", ""),
            "coordenadas": campos.get("coordenadas", {"lat": None, "lng": None, "origen": ""})
        }
        self._guardar_archivo()
        return direccion_id

    # ── EDITAR ────────────────────────────────────────────────────────────────

    def actualizar_coordenadas(self, direccion_id, lat, lng, origen="maps"):
        """Actualiza las coordenadas de una dirección. Retorna True si se actualizó."""
        if direccion_id not in self.data["direcciones"]:
            return False
        self.data["direcciones"][direccion_id]["coordenadas"] = {
            "lat": lat, "lng": lng, "origen": origen
        }
        self._guardar_archivo()
        return True

    # ── BORRAR ────────────────────────────────────────────────────────────────

    def borrar(self, direccion_id):
        """Elimina una dirección por ID. Retorna True si se borró."""
        if direccion_id in self.data["direcciones"]:
            del self.data["direcciones"][direccion_id]
            self._guardar_archivo()
            return True
        return False
