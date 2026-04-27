# src/farmacia/vinculacion_manager.py
import json
import os
import uuid
from src.tenant import data_path

_instancia = None


class VinculacionManager:
    """
    Gestiona el CRUD de vinculaciones entre personas en vinculaciones.json.
    Singleton — se carga una vez y se reutiliza.
    Responsabilidades:
        - Crear vínculo bidireccional (persona_a visible, persona_b oculta)
        - Activar visibilidad del lado oculto cuando la persona se identifica
        - Buscar vinculados visibles para una persona
        - Buscar si existe vínculo entre dos personas (independiente de visibilidad)
        - Editar alias de un lado del vínculo
        - Eliminar vínculo
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("farmacia", "vinculaciones.json")
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        """Carga el archivo de vinculaciones. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {"vinculaciones": {}}
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        """Persiste el estado actual en vinculaciones.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def crear_vinculacion(self, persona_origen_id, persona_destino_id, alias_origen):
        """
        Crea un vínculo bidireccional entre dos personas.
        - persona_origen: quien crea el vínculo (visible: true, con alias)
        - persona_destino: el vinculado (visible: false, alias vacío)
        Si ya existe vínculo entre ambos, solo activa visibilidad del lado origen.
        Retorna el vinculacion_id (nuevo o existente).
        """
        existente = self.buscar_vinculo(persona_origen_id, persona_destino_id)
        if existente:
            # Ya existe vínculo — solo activamos visibilidad y actualizamos alias
            vid, datos = existente
            lado = self._get_lado(datos, persona_origen_id)
            if lado:
                lado["visible"] = True
                if alias_origen:
                    lado["alias"] = alias_origen.strip()
                self._guardar_archivo()
            return vid

        vinculacion_id = str(uuid.uuid4())
        vinculacion = {
            "persona_a": {
                "persona_id": persona_origen_id,
                "alias": alias_origen.strip(),
                "visible": True
            },
            "persona_b": {
                "persona_id": persona_destino_id,
                "alias": "",
                "visible": False
            }
        }

        self.data["vinculaciones"][vinculacion_id] = vinculacion
        self._guardar_archivo()
        return vinculacion_id

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def buscar_vinculo(self, persona_id_1, persona_id_2):
        """
        Busca si existe un vínculo entre dos personas (sin importar el orden).
        Retorna tupla (vinculacion_id, datos) o None.
        """
        for vid, datos in self.data["vinculaciones"].items():
            ids = {datos["persona_a"]["persona_id"], datos["persona_b"]["persona_id"]}
            if persona_id_1 in ids and persona_id_2 in ids:
                return (vid, datos)
        return None

    def get_vinculados_visibles(self, persona_id):
        """
        Retorna la lista de personas vinculadas que son visibles para persona_id.
        Cada elemento: {vinculacion_id, persona_id (del otro), alias (del otro), mi_alias}.
        """
        resultado = []
        for vid, datos in self.data["vinculaciones"].items():
            mi_lado = self._get_lado(datos, persona_id)
            if not mi_lado or not mi_lado["visible"]:
                continue

            otro_lado = self._get_otro_lado(datos, persona_id)
            if not otro_lado:
                continue

            resultado.append({
                "vinculacion_id": vid,
                "persona_id": otro_lado["persona_id"],
                "mi_alias": mi_lado["alias"],
                "alias_otro": otro_lado["alias"]
            })
        return resultado

    def get_todos_vinculos(self, persona_id):
        """
        Retorna todos los vínculos de una persona (visibles y no visibles).
        Útil para verificaciones internas, no para mostrar al usuario.
        """
        resultado = []
        for vid, datos in self.data["vinculaciones"].items():
            mi_lado = self._get_lado(datos, persona_id)
            if not mi_lado:
                continue

            otro_lado = self._get_otro_lado(datos, persona_id)
            resultado.append({
                "vinculacion_id": vid,
                "persona_id": otro_lado["persona_id"],
                "mi_alias": mi_lado["alias"],
                "mi_visible": mi_lado["visible"],
                "alias_otro": otro_lado["alias"],
                "otro_visible": otro_lado["visible"]
            })
        return resultado

    # ── VISIBILIDAD ───────────────────────────────────────────────────────────

    def activar_visibilidad(self, vinculacion_id, persona_id, alias=""):
        """
        Activa la visibilidad de un lado del vínculo y opcionalmente carga el alias.
        Se usa cuando la persona del lado oculto entra al sistema y se identifica.
        Retorna True si se activó.
        """
        if vinculacion_id not in self.data["vinculaciones"]:
            return False

        datos = self.data["vinculaciones"][vinculacion_id]
        lado = self._get_lado(datos, persona_id)
        if not lado:
            return False

        lado["visible"] = True
        if alias:
            lado["alias"] = alias.strip()
        self._guardar_archivo()
        return True

    def desactivar_visibilidad(self, vinculacion_id, persona_id):
        """
        Desactiva la visibilidad de un lado del vínculo.
        El vínculo sigue existiendo pero la persona deja de verlo.
        Retorna True si se desactivó.
        """
        if vinculacion_id not in self.data["vinculaciones"]:
            return False

        datos = self.data["vinculaciones"][vinculacion_id]
        lado = self._get_lado(datos, persona_id)
        if not lado:
            return False

        lado["visible"] = False
        self._guardar_archivo()
        return True

    # ── EDITAR ────────────────────────────────────────────────────────────────

    def editar_alias(self, vinculacion_id, persona_id, nuevo_alias):
        """
        Edita el alias que una persona le puso a un vínculo.
        Retorna True si se editó.
        """
        if vinculacion_id not in self.data["vinculaciones"]:
            return False

        datos = self.data["vinculaciones"][vinculacion_id]
        lado = self._get_lado(datos, persona_id)
        if not lado:
            return False

        lado["alias"] = nuevo_alias.strip()
        self._guardar_archivo()
        return True

    # ── BORRAR ────────────────────────────────────────────────────────────────

    def borrar_vinculacion(self, vinculacion_id):
        """Elimina un vínculo completo. Retorna True si se borró."""
        if vinculacion_id in self.data["vinculaciones"]:
            del self.data["vinculaciones"][vinculacion_id]
            self._guardar_archivo()
            return True
        return False

    def borrar_vinculos_persona(self, persona_id):
        """
        Elimina todos los vínculos donde participa una persona.
        Se usa al borrar una persona para limpiar referencias.
        Retorna la cantidad de vínculos eliminados.
        """
        a_borrar = []
        for vid, datos in self.data["vinculaciones"].items():
            ids = {datos["persona_a"]["persona_id"], datos["persona_b"]["persona_id"]}
            if persona_id in ids:
                a_borrar.append(vid)

        for vid in a_borrar:
            del self.data["vinculaciones"][vid]

        if a_borrar:
            self._guardar_archivo()
        return len(a_borrar)

    # ── HELPERS INTERNOS ──────────────────────────────────────────────────────

    def _get_lado(self, datos, persona_id):
        """Retorna el lado (persona_a o persona_b) que corresponde al persona_id."""
        if datos["persona_a"]["persona_id"] == persona_id:
            return datos["persona_a"]
        if datos["persona_b"]["persona_id"] == persona_id:
            return datos["persona_b"]
        return None

    def _get_otro_lado(self, datos, persona_id):
        """Retorna el lado contrario al persona_id."""
        if datos["persona_a"]["persona_id"] == persona_id:
            return datos["persona_b"]
        if datos["persona_b"]["persona_id"] == persona_id:
            return datos["persona_a"]
        return None