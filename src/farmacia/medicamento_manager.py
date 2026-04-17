# src/farmacia/medicamento_manager.py
import json
import os
import uuid

_instancia = None


class MedicamentoManager:
    """
    Gestiona el catálogo de medicamentos en medicamentos.json.
    Singleton — se carga una vez y se reutiliza.
    El catálogo crece con el uso: cada receta interpretada agrega
    medicamentos que no existían.
    """

    PATH = os.path.join("data", "farmacia", "medicamentos.json")

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            estructura = {"medicamentos": {}}
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CREAR / BUSCAR ────────────────────────────────────────────────────────

    def crear_o_encontrar(self, farmaco, nombre_comercial="", dosis="", presentacion=""):
        """
        Busca un medicamento por fármaco + dosis. Si existe retorna su ID.
        Si no existe, lo crea y retorna el nuevo ID.
        Retorna (medicamento_id, "existente"|"creado").
        """
        existente = self.buscar_por_farmaco_y_dosis(farmaco, dosis)
        if existente:
            return (existente[0], "existente")

        med_id = str(uuid.uuid4())
        self.data["medicamentos"][med_id] = {
            "farmaco": farmaco.strip(),
            "nombre_comercial": nombre_comercial.strip(),
            "dosis": dosis.strip(),
            "presentacion": presentacion.strip()
        }
        self._guardar_archivo()
        return (med_id, "creado")

    def buscar_por_farmaco_y_dosis(self, farmaco, dosis):
        """
        Busca medicamento por fármaco + dosis (clave de negocio).
        Retorna (med_id, datos) o None.
        """
        farmaco_lower = farmaco.strip().lower()
        dosis_lower = dosis.strip().lower()
        for mid, datos in self.data["medicamentos"].items():
            if (datos["farmaco"].lower() == farmaco_lower and
                    datos["dosis"].lower() == dosis_lower):
                return (mid, datos)
        return None

    def get_medicamento(self, med_id):
        """Retorna (med_id, datos) o None."""
        datos = self.data["medicamentos"].get(med_id)
        if datos:
            return (med_id, datos)
        return None

    def get_label(self, med_id):
        """Retorna un label legible del medicamento para mostrar al usuario."""
        med = self.get_medicamento(med_id)
        if not med:
            return "Medicamento desconocido"
        datos = med[1]
        nombre = datos.get("nombre_comercial") or datos.get("farmaco", "")
        dosis = datos.get("dosis", "")
        presentacion = datos.get("presentacion", "")
        partes = [p for p in [nombre, dosis, presentacion] if p]
        return " ".join(partes)