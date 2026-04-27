# src/cliente/persona_manager.py
import json
import os
import uuid
from src.tenant import data_path

_instancia = None


class PersonaManager:
    """
    Gestiona el CRUD de personas en personas.json.
    Singleton — se carga una vez y se reutiliza.
    Responsabilidades:
        - Crear persona nueva (con generación de UUID)
        - Buscar persona por documento (tipo + número)
        - Buscar persona por LID (WhatsApp)
        - Gestionar LIDs asociados a una persona
        - Gestionar contactos (teléfonos, emails)
        - Acceder a catálogos de tipo_documento y tipo_contacto
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("cliente", "personas.json")
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        """Carga el archivo de personas. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {
                "catalogo_tipo_documento": ["DNI", "Pasaporte", "CI", "LE"],
                "catalogo_tipo_contacto": ["telefono", "email"],
                "personas": {}
            }
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        """Persiste el estado actual en personas.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CATÁLOGOS ─────────────────────────────────────────────────────────────

    def get_catalogo_tipo_documento(self):
        """Retorna la lista de tipos de documento disponibles."""
        return self.data.get("catalogo_tipo_documento", [])

    def get_catalogo_tipo_contacto(self):
        """Retorna la lista de tipos de contacto disponibles."""
        return self.data.get("catalogo_tipo_contacto", [])

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def crear_persona(self, tipo_documento, numero_documento, nombre, apellido,
                      fecha_nacimiento="", lid=None, contactos=None):
        """
        Crea una persona nueva con UUID autogenerado.
        Verifica que no exista otra persona con el mismo tipo+número de documento.
        Retorna el persona_id generado, o None si ya existe.
        """
        # Verificamos duplicado por documento
        existente = self.buscar_por_documento(tipo_documento, numero_documento)
        if existente:
            return None

        persona_id = str(uuid.uuid4())
        persona = {
            "tipo_documento": tipo_documento,
            "numero_documento": numero_documento,
            "nombre": nombre.strip().lower(),
            "apellido": apellido.strip().lower(),
            "fecha_nacimiento": fecha_nacimiento,
            "lids": [lid] if lid else [],
            "contactos": contactos if contactos else []
        }

        self.data["personas"][persona_id] = persona
        self._guardar_archivo()
        return persona_id

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def buscar_por_documento(self, tipo_documento, numero_documento):
        """
        Busca una persona por tipo y número de documento.
        Retorna tupla (persona_id, datos) o None si no existe.
        """
        for pid, datos in self.data["personas"].items():
            if (datos.get("tipo_documento", "").upper() == tipo_documento.upper() and
                    datos.get("numero_documento", "") == numero_documento.strip()):
                return (pid, datos)
        return None

    def buscar_por_lid(self, lid):
        """
        Busca la persona asociada a un LID de WhatsApp.
        Retorna tupla (persona_id, datos) o None si no existe.
        """
        for pid, datos in self.data["personas"].items():
            if lid in datos.get("lids", []):
                return (pid, datos)
        return None

    def get_persona(self, persona_id):
        """Retorna los datos de una persona por su ID, o None si no existe."""
        datos = self.data["personas"].get(persona_id)
        if datos:
            return (persona_id, datos)
        return None

    # ── EDITAR ────────────────────────────────────────────────────────────────

    def editar_campo(self, persona_id, campo, valor):
        """
        Edita un campo simple de la persona (nombre, apellido, fecha_nacimiento).
        No aplica a lids ni contactos (tienen métodos propios).
        Retorna True si se editó, False si no existe la persona o campo inválido.
        """
        campos_editables = ["nombre", "apellido", "fecha_nacimiento",
                            "tipo_documento", "numero_documento"]
        if campo not in campos_editables:
            return False
        if persona_id not in self.data["personas"]:
            return False

        self.data["personas"][persona_id][campo] = valor.strip()
        self._guardar_archivo()
        return True

    # ── LIDS ──────────────────────────────────────────────────────────────────

    def agregar_lid(self, persona_id, lid):
        """
        Asocia un LID a la persona. Verifica que el LID no esté asignado a otra persona.
        Retorna True si se agregó, False si el LID ya pertenece a otra persona.
        """
        if persona_id not in self.data["personas"]:
            return False

        # Verificamos que el LID no esté en otra persona
        otra = self.buscar_por_lid(lid)
        if otra and otra[0] != persona_id:
            return False

        lids = self.data["personas"][persona_id]["lids"]
        if lid not in lids:
            lids.append(lid)
            self._guardar_archivo()
        return True

    def quitar_lid(self, persona_id, lid):
        """Desasocia un LID de la persona. Retorna True si se quitó."""
        if persona_id not in self.data["personas"]:
            return False

        lids = self.data["personas"][persona_id]["lids"]
        if lid in lids:
            lids.remove(lid)
            self._guardar_archivo()
            return True
        return False

    # ── CONTACTOS ─────────────────────────────────────────────────────────────

    def agregar_contacto(self, persona_id, tipo, valor, etiqueta=""):
        """
        Agrega un contacto a la persona.
        Verifica que no exista un contacto con el mismo tipo y valor.
        Retorna True si se agregó, False si ya existe o persona no encontrada.
        """
        if persona_id not in self.data["personas"]:
            return False

        contactos = self.data["personas"][persona_id]["contactos"]

        # Verificamos duplicado
        for c in contactos:
            if c["tipo"] == tipo and c["valor"] == valor.strip():
                return False

        contactos.append({
            "tipo": tipo,
            "valor": valor.strip(),
            "etiqueta": etiqueta.strip()
        })
        self._guardar_archivo()
        return True

    def quitar_contacto(self, persona_id, tipo, valor):
        """Elimina un contacto por tipo y valor. Retorna True si se quitó."""
        if persona_id not in self.data["personas"]:
            return False

        contactos = self.data["personas"][persona_id]["contactos"]
        for i, c in enumerate(contactos):
            if c["tipo"] == tipo and c["valor"] == valor.strip():
                contactos.pop(i)
                self._guardar_archivo()
                return True
        return False

    def get_contactos(self, persona_id):
        """Retorna la lista de contactos de la persona, o lista vacía."""
        if persona_id not in self.data["personas"]:
            return []
        return self.data["personas"][persona_id].get("contactos", [])

    # ── NOMBRE PARA BIENVENIDA ────────────────────────────────────────────────

    def get_nombre_completo(self, persona_id):
        """
        Retorna 'Nombre APELLIDO' formateado, o None si no tiene nombre.
        Usado para personalizar mensajes.
        """
        if persona_id not in self.data["personas"]:
            return None

        persona = self.data["personas"][persona_id]
        nombre = persona.get("nombre", "").strip().title()
        apellido = persona.get("apellido", "").strip().upper()

        if nombre:
            return f"{nombre} {apellido}".strip()
        return None

    # ── BORRAR ────────────────────────────────────────────────────────────────

    def borrar_persona(self, persona_id):
        """
        Elimina una persona del registro.
        ATENCIÓN: no verifica vinculaciones ni direcciones asociadas.
        La limpieza de referencias es responsabilidad del flujo que invoca.
        Retorna True si se borró, False si no existía.
        """
        if persona_id in self.data["personas"]:
            del self.data["personas"][persona_id]
            self._guardar_archivo()
            return True
        return False