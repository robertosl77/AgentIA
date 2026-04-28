# src/farmacia/farmacia_config_loader.py
import json
import os
from src.tenant import data_path

_instancia = None


class FarmaciaConfigLoader:
    """
    Carga la configuración del módulo farmacia desde farmacia_config.json.
    Singleton — se carga una vez y se reutiliza.
    Contiene: estructura_sesion.persona, agente_ia, recetas.
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

    # ── ESTRUCTURA SESION ─────────────────────────────────────────────────────

    def get_estructura_persona(self):
        """Retorna la config de campos de persona (registro/edición de beneficiario)."""
        return self.data.get("estructura_sesion", {}).get("persona", {})

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
