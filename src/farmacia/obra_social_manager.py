# src/farmacia/obra_social_manager.py
import json
import os
import uuid
from src.tenant import data_path

_instancia = None


class ObraSocialManager:
    """
    Gestiona el CRUD de obras sociales en obras_sociales.json.
    Singleton — se carga una vez y se reutiliza.
    
    Estructura de asociación:
        {entidad, numero, plan, personas: [persona_id, ...]}
    Una obra social (entidad+numero) existe una sola vez.
    Múltiples personas se vinculan a la misma asociación (grupo familiar).
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("farmacia", "obras_sociales.json")
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        """Carga el archivo de obras sociales. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {
                "catalogo": [
                    {"nombre": "OSDE", "destacada": True},
                    {"nombre": "Swiss Medical", "destacada": True},
                    {"nombre": "PAMI", "destacada": True},
                    {"nombre": "IOMA", "destacada": True},
                    {"nombre": "Galeno", "destacada": True},
                    {"nombre": "Medicus", "destacada": False},
                    {"nombre": "Hospital Italiano", "destacada": False},
                    {"nombre": "Accord Salud", "destacada": False},
                    {"nombre": "Particular", "destacada": False}
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
        """Retorna la lista completa del catálogo [{nombre, destacada}]."""
        return self.data.get("catalogo", [])

    def get_destacadas(self):
        """Retorna solo los nombres de las entidades destacadas."""
        return [e["nombre"] for e in self.get_catalogo() if e.get("destacada")]

    def get_nombres_catalogo(self):
        """Retorna todos los nombres del catálogo."""
        return [e["nombre"] for e in self.get_catalogo()]

    def agregar_al_catalogo(self, entidad, destacada=False):
        """
        Agrega una entidad nueva al catálogo si no existe.
        Comparación case-insensitive.
        Retorna True si se agregó, False si ya existía.
        """
        catalogo = self.get_catalogo()
        existentes_lower = [e["nombre"].lower() for e in catalogo]

        if entidad.strip().lower() in existentes_lower:
            return False

        catalogo.append({"nombre": entidad.strip(), "destacada": destacada})
        self._guardar_archivo()
        return True

    def buscar_en_catalogo(self, texto):
        """
        Busca coincidencias parciales en el catálogo (case-insensitive).
        Retorna lista de nombres que contienen el texto.
        """
        texto_lower = texto.strip().lower()
        return [e["nombre"] for e in self.get_catalogo() if texto_lower in e["nombre"].lower()]

    def resolver_entidad(self, comando, destacadas):
        """
        Resuelve la entidad seleccionada por el usuario.
        Si es un número, busca en la lista de destacadas.
        Si es texto, busca coincidencia en el catálogo completo.
        Retorna (nombre_entidad, es_nueva) o (None, False) si no se resuelve.
        """
        try:
            indice = int(comando.strip()) - 1
            if 0 <= indice < len(destacadas):
                return (destacadas[indice], False)
        except ValueError:
            pass

        coincidencias = self.buscar_en_catalogo(comando)
        if len(coincidencias) == 1:
            return (coincidencias[0], False)
        elif len(coincidencias) > 1:
            return (None, False)

        nombre_nuevo = comando.strip().title()
        if len(nombre_nuevo) >= 3:
            return (nombre_nuevo, True)

        return (None, False)

    # ── CREAR / VINCULAR ──────────────────────────────────────────────────────

    def crear_o_vincular(self, persona_id, entidad, numero, plan=""):
        """
        Punto de entrada principal para asociar una persona a una obra social.
        1. Busca si ya existe una asociación con misma entidad+numero.
           - Si existe: vincula la persona (si no estaba ya).
        2. Si no existe: crea la asociación nueva.
        Agrega la entidad al catálogo si es nueva.
        Retorna (asociacion_id, "vinculado"|"creado"|"ya_vinculado").
        """
        self.agregar_al_catalogo(entidad)

        # Buscar asociación existente por entidad + numero
        existente = self.buscar_por_entidad_y_numero(entidad, numero)
        if existente:
            aid, datos = existente
            if persona_id in datos["personas"]:
                return (aid, "ya_vinculado")
            datos["personas"].append(persona_id)
            self._guardar_archivo()
            return (aid, "vinculado")

        # No existe: crear nueva
        asociacion_id = str(uuid.uuid4())
        self.data["asociaciones"][asociacion_id] = {
            "entidad": entidad.strip(),
            "numero": numero.strip(),
            "plan": plan.strip(),
            "personas": [persona_id]
        }
        self._guardar_archivo()
        return (asociacion_id, "creado")

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get_asociacion(self, asociacion_id):
        """Retorna tupla (asociacion_id, datos) o None."""
        datos = self.data["asociaciones"].get(asociacion_id)
        if datos:
            return (asociacion_id, datos)
        return None

    def buscar_por_entidad_y_numero(self, entidad, numero):
        """
        Busca una asociación por entidad + numero (clave de negocio).
        Comparación case-insensitive en entidad.
        Retorna tupla (asociacion_id, datos) o None.
        """
        entidad_lower = entidad.strip().lower()
        numero_clean = numero.strip()
        for aid, datos in self.data["asociaciones"].items():
            if (datos["entidad"].lower() == entidad_lower and
                    datos["numero"] == numero_clean):
                return (aid, datos)
        return None

    def buscar_por_persona(self, persona_id):
        """
        Retorna todas las asociaciones donde participa la persona.
        Cada elemento: {asociacion_id, entidad, numero, plan}.
        """
        resultado = []
        for aid, datos in self.data["asociaciones"].items():
            if persona_id in datos.get("personas", []):
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
        Retorna tupla (asociacion_id, datos) o None.
        """
        entidad_lower = entidad.strip().lower()
        for aid, datos in self.data["asociaciones"].items():
            if (persona_id in datos.get("personas", []) and
                    datos["entidad"].lower() == entidad_lower):
                return (aid, datos)
        return None

    def buscar_personas_por_entidad(self, entidad):
        """Retorna todas las asociaciones de una entidad."""
        entidad_lower = entidad.strip().lower()
        resultado = []
        for aid, datos in self.data["asociaciones"].items():
            if datos["entidad"].lower() == entidad_lower:
                resultado.append({
                    "asociacion_id": aid,
                    "personas": datos["personas"],
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

    # ── DESVINCULAR / BORRAR ──────────────────────────────────────────────────

    def desvincular_persona(self, asociacion_id, persona_id):
        """
        Desvincula una persona de una asociación.
        Si la asociación queda sin personas, se elimina.
        Retorna True si se desvinculó.
        """
        if asociacion_id not in self.data["asociaciones"]:
            return False

        personas = self.data["asociaciones"][asociacion_id]["personas"]
        if persona_id in personas:
            personas.remove(persona_id)
            if not personas:
                del self.data["asociaciones"][asociacion_id]
            self._guardar_archivo()
            return True
        return False

    def borrar_asociacion(self, asociacion_id):
        """Elimina una asociación completa. Retorna True si se borró."""
        if asociacion_id in self.data["asociaciones"]:
            del self.data["asociaciones"][asociacion_id]
            self._guardar_archivo()
            return True
        return False

    def desvincular_todas_persona(self, persona_id):
        """
        Desvincula una persona de todas sus asociaciones.
        Elimina asociaciones que queden sin personas.
        Se usa al borrar una persona para limpiar referencias.
        Retorna la cantidad de desvinculaciones.
        """
        count = 0
        a_borrar = []
        for aid, datos in self.data["asociaciones"].items():
            if persona_id in datos.get("personas", []):
                datos["personas"].remove(persona_id)
                count += 1
                if not datos["personas"]:
                    a_borrar.append(aid)

        for aid in a_borrar:
            del self.data["asociaciones"][aid]

        if count > 0:
            self._guardar_archivo()
        return count