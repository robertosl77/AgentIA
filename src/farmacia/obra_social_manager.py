# src/farmacia/obra_social_manager.py
import json
import os
import uuid

_instancia = None


class ObraSocialManager:
    """
    Gestiona el CRUD de obras sociales en obras_sociales.json.
    Singleton — se carga una vez y se reutiliza.
    Responsabilidades:
        - Gestionar catálogo de entidades (lista dinámica, crece con el uso)
        - Crear asociación persona ↔ obra social (con número y plan)
        - Buscar obra social por persona
        - Buscar personas por obra social
        - Editar y eliminar asociaciones
    """

    PATH = os.path.join("data", "farmacia", "obras_sociales.json")

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
        """Carga el archivo de obras sociales. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {
                "catalogo": [
                    "OSDE", "Swiss Medical", "PAMI", "IOMA", "Galeno",
                    "Medicus", "Hospital Italiano", "Accord Salud",
                    "OSPRERA", "OSECAC", "Unión Personal", "Luis Pasteur",
                    "Particular"
                ],
                "asociaciones": {}
            }
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        """Persiste el estado actual en obras_sociales.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CATÁLOGO ──────────────────────────────────────────────────────────────

    def get_catalogo(self):
        """Retorna la lista de entidades de obra social disponibles."""
        return self.data.get("catalogo", [])

    def agregar_al_catalogo(self, entidad):
        """
        Agrega una entidad nueva al catálogo si no existe.
        Comparación case-insensitive.
        Retorna True si se agregó, False si ya existía.
        """
        catalogo = self.data.get("catalogo", [])
        existentes_lower = [e.lower() for e in catalogo]

        if entidad.strip().lower() in existentes_lower:
            return False

        catalogo.append(entidad.strip())
        self._guardar_archivo()
        return True

    def buscar_en_catalogo(self, texto):
        """
        Busca coincidencias parciales en el catálogo (case-insensitive).
        Retorna lista de entidades que contienen el texto.
        """
        texto_lower = texto.strip().lower()
        return [e for e in self.data.get("catalogo", []) if texto_lower in e.lower()]

    # ── CREAR ASOCIACIÓN ──────────────────────────────────────────────────────

    def crear_asociacion(self, persona_id, entidad, numero, plan=""):
        """
        Crea una asociación persona ↔ obra social.
        Si la entidad no está en el catálogo, la agrega.
        Verifica que la persona no tenga ya una asociación con la misma entidad.
        Retorna el asociacion_id generado, o None si ya existe.
        """
        # Verificamos duplicado: misma persona + misma entidad
        existente = self.buscar_por_persona_y_entidad(persona_id, entidad)
        if existente:
            return None

        # Si la entidad no está en el catálogo, la agregamos
        self.agregar_al_catalogo(entidad)

        asociacion_id = str(uuid.uuid4())
        self.data["asociaciones"][asociacion_id] = {
            "entidad": entidad.strip(),
            "numero": numero.strip(),
            "plan": plan.strip(),
            "persona_id": persona_id
        }
        self._guardar_archivo()
        return asociacion_id

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get_asociacion(self, asociacion_id):
        """Retorna los datos de una asociación por su ID, o None."""
        datos = self.data["asociaciones"].get(asociacion_id)
        if datos:
            return (asociacion_id, datos)
        return None

    def buscar_por_persona(self, persona_id):
        """
        Retorna todas las asociaciones de obra social de una persona.
        Cada elemento: {asociacion_id, entidad, numero, plan}.
        """
        resultado = []
        for aid, datos in self.data["asociaciones"].items():
            if datos["persona_id"] == persona_id:
                resultado.append({
                    "asociacion_id": aid,
                    "entidad": datos["entidad"],
                    "numero": datos["numero"],
                    "plan": datos["plan"]
                })
        return resultado

    def buscar_por_persona_y_entidad(self, persona_id, entidad):
        """
        Busca si una persona ya tiene asociación con una entidad específica.
        Comparación case-insensitive.
        Retorna tupla (asociacion_id, datos) o None.
        """
        entidad_lower = entidad.strip().lower()
        for aid, datos in self.data["asociaciones"].items():
            if (datos["persona_id"] == persona_id and
                    datos["entidad"].lower() == entidad_lower):
                return (aid, datos)
        return None

    def buscar_personas_por_entidad(self, entidad):
        """
        Retorna todas las personas asociadas a una entidad de obra social.
        Útil para estadísticas o búsquedas inversas.
        """
        entidad_lower = entidad.strip().lower()
        resultado = []
        for aid, datos in self.data["asociaciones"].items():
            if datos["entidad"].lower() == entidad_lower:
                resultado.append({
                    "asociacion_id": aid,
                    "persona_id": datos["persona_id"],
                    "numero": datos["numero"],
                    "plan": datos["plan"]
                })
        return resultado

    # ── EDITAR ────────────────────────────────────────────────────────────────

    def editar_asociacion(self, asociacion_id, campo, valor):
        """
        Edita un campo de la asociación (numero, plan, entidad).
        Si se cambia la entidad y no está en catálogo, la agrega.
        Retorna True si se editó.
        """
        campos_editables = ["entidad", "numero", "plan"]
        if campo not in campos_editables:
            return False
        if asociacion_id not in self.data["asociaciones"]:
            return False

        if campo == "entidad":
            self.agregar_al_catalogo(valor)

        self.data["asociaciones"][asociacion_id][campo] = valor.strip()
        self._guardar_archivo()
        return True

    # ── BORRAR ────────────────────────────────────────────────────────────────

    def borrar_asociacion(self, asociacion_id):
        """Elimina una asociación. Retorna True si se borró."""
        if asociacion_id in self.data["asociaciones"]:
            del self.data["asociaciones"][asociacion_id]
            self._guardar_archivo()
            return True
        return False

    def borrar_asociaciones_persona(self, persona_id):
        """
        Elimina todas las asociaciones de una persona.
        Se usa al borrar una persona para limpiar referencias.
        Retorna la cantidad de asociaciones eliminadas.
        """
        a_borrar = []
        for aid, datos in self.data["asociaciones"].items():
            if datos["persona_id"] == persona_id:
                a_borrar.append(aid)

        for aid in a_borrar:
            del self.data["asociaciones"][aid]

        if a_borrar:
            self._guardar_archivo()
        return len(a_borrar)