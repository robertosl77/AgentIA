# src/farmacia/farmacia_config_loader.py
import json
import os
from src.tenant import data_path

_instancia = None


class FarmaciaConfigLoader:
    """
    Carga la configuración del módulo farmacia desde farmacia_config.json.
    Singleton — se carga una vez y se reutiliza.
    Contiene: estructura_persona (persona, direccion, vinculacion, obra_social), agente_ia, recetas.
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("farmacia", "farmacia_config.json")
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            raise FileNotFoundError(f"Archivo no encontrado: {self.PATH}")
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── ESTRUCTURA PERSONA ────────────────────────────────────────────────────

    def _estructura(self):
        return self.data.get("estructura_persona", {})

    def get_estructura_persona(self):
        return self._estructura().get("persona", {})

    def get_estructura_direccion(self):
        return self._estructura().get("direccion", {})

    def get_estructura_vinculacion(self):
        return self._estructura().get("vinculacion", {})

    def get_estructura_obra_social(self):
        return self._estructura().get("obra_social", {})

    # ── AGENTE IA ─────────────────────────────────────────────────────────────

    def get_agente_ia(self):
        return self.data.get("agente_ia", {})

    # ── RECETAS ───────────────────────────────────────────────────────────────

    def get_recetas(self):
        return self.data.get("recetas", {})

    def get_estados_receta(self):
        return self.get_recetas().get("estados_receta", {})

    def get_estados_item(self):
        return self.get_recetas().get("estados_item", {})

    def get_mensajes_receta(self):
        return self.get_recetas().get("mensajes", {})

    def get_mensajes_staff(self):
        return self.get_recetas().get("mensajes_staff", {})

    def get_opciones_staff_labels(self):
        return self.get_recetas().get("opciones_staff_labels", {})

    # ── GESTIÓN DIRECCIÓN ─────────────────────────────────────────────────────

    def get_mensajes_gestion_direccion(self):
        return self.data.get("gestion_direccion", {}).get("mensajes", {})
