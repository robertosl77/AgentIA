# src/cliente/direccion_manager.py
import json
import os
import uuid

_instancia = None


class DireccionManager:
    """
    Gestiona el CRUD de direcciones en direcciones.json.
    Singleton — se carga una vez y se reutiliza.
    Responsabilidades:
        - Crear dirección nueva (con generación de UUID)
        - Buscar direcciones por persona_id
        - Vincular/desvincular personas a direcciones existentes
        - Gestionar alias y dirección principal por persona
        - Actualizar coordenadas (integración con Maps)
    """

    PATH = os.path.join("data", "cliente", "direcciones.json")

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
        """Carga el archivo de direcciones. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {"direcciones": {}}
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        """Persiste el estado actual en direcciones.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def crear_direccion(self, calle, altura, localidad, provincia, codigo_postal,
                        piso="", depto="", persona_id=None, alias="", es_principal=False):
        """
        Crea una dirección nueva con UUID autogenerado.
        Opcionalmente vincula una persona con alias y marca de principal.
        Retorna el direccion_id generado.
        """
        direccion_id = str(uuid.uuid4())
        direccion = {
            "calle": calle.strip(),
            "altura": str(altura).strip(),
            "piso": piso.strip(),
            "depto": depto.strip(),
            "localidad": localidad.strip(),
            "codigo_postal": str(codigo_postal).strip(),
            "provincia": provincia.strip(),
            "coordenadas": {
                "lat": None,
                "lng": None,
                "origen": ""
            },
            "personas": []
        }

        if persona_id:
            # Si es_principal, desmarcar las demás de esta persona
            if es_principal:
                self._desmarcar_principales(persona_id)

            direccion["personas"].append({
                "persona_id": persona_id,
                "alias": alias.strip(),
                "es_principal": es_principal
            })

        self.data["direcciones"][direccion_id] = direccion
        self._guardar_archivo()
        return direccion_id

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get_direccion(self, direccion_id):
        """Retorna los datos de una dirección por su ID, o None si no existe."""
        datos = self.data["direcciones"].get(direccion_id)
        if datos:
            return (direccion_id, datos)
        return None

    def get_direcciones_persona(self, persona_id):
        """
        Retorna todas las direcciones vinculadas a una persona.
        Cada elemento incluye: direccion_id, datos de dirección, alias y es_principal.
        """
        resultado = []
        for did, datos in self.data["direcciones"].items():
            for p in datos.get("personas", []):
                if p["persona_id"] == persona_id:
                    resultado.append({
                        "direccion_id": did,
                        "datos": datos,
                        "alias": p["alias"],
                        "es_principal": p["es_principal"]
                    })
        return resultado

    def get_direccion_principal(self, persona_id):
        """
        Retorna la dirección marcada como principal para una persona.
        Retorna dict con direccion_id, datos, alias o None si no tiene principal.
        """
        direcciones = self.get_direcciones_persona(persona_id)
        for d in direcciones:
            if d["es_principal"]:
                return d
        return None

    # ── VINCULAR / DESVINCULAR PERSONA ────────────────────────────────────────

    def vincular_persona(self, direccion_id, persona_id, alias="", es_principal=False):
        """
        Vincula una persona a una dirección existente.
        Verifica que no esté ya vinculada.
        Retorna True si se vinculó, False si ya existía o dirección no encontrada.
        """
        if direccion_id not in self.data["direcciones"]:
            return False

        personas = self.data["direcciones"][direccion_id]["personas"]

        # Verificamos duplicado
        for p in personas:
            if p["persona_id"] == persona_id:
                return False

        if es_principal:
            self._desmarcar_principales(persona_id)

        personas.append({
            "persona_id": persona_id,
            "alias": alias.strip(),
            "es_principal": es_principal
        })
        self._guardar_archivo()
        return True

    def desvincular_persona(self, direccion_id, persona_id):
        """
        Desvincula una persona de una dirección.
        Si la dirección queda sin personas vinculadas, se elimina.
        Retorna True si se desvinculó.
        """
        if direccion_id not in self.data["direcciones"]:
            return False

        personas = self.data["direcciones"][direccion_id]["personas"]
        for i, p in enumerate(personas):
            if p["persona_id"] == persona_id:
                personas.pop(i)
                # Si quedó sin personas, eliminamos la dirección
                if not personas:
                    del self.data["direcciones"][direccion_id]
                self._guardar_archivo()
                return True
        return False

    # ── EDITAR ────────────────────────────────────────────────────────────────

    def editar_campo(self, direccion_id, campo, valor):
        """
        Edita un campo simple de la dirección.
        No aplica a coordenadas ni personas (tienen métodos propios).
        Retorna True si se editó.
        """
        campos_editables = ["calle", "altura", "piso", "depto",
                            "localidad", "codigo_postal", "provincia"]
        if campo not in campos_editables:
            return False
        if direccion_id not in self.data["direcciones"]:
            return False

        self.data["direcciones"][direccion_id][campo] = valor.strip()
        self._guardar_archivo()
        return True

    def editar_alias(self, direccion_id, persona_id, nuevo_alias):
        """Edita el alias que una persona le dio a una dirección. Retorna True si se editó."""
        if direccion_id not in self.data["direcciones"]:
            return False

        for p in self.data["direcciones"][direccion_id]["personas"]:
            if p["persona_id"] == persona_id:
                p["alias"] = nuevo_alias.strip()
                self._guardar_archivo()
                return True
        return False

    def marcar_principal(self, direccion_id, persona_id):
        """
        Marca una dirección como principal para una persona.
        Desmarca la principal anterior si existía.
        Retorna True si se marcó.
        """
        if direccion_id not in self.data["direcciones"]:
            return False

        # Verificamos que la persona esté vinculada a esta dirección
        encontrada = False
        for p in self.data["direcciones"][direccion_id]["personas"]:
            if p["persona_id"] == persona_id:
                encontrada = True
                break

        if not encontrada:
            return False

        # Desmarcamos todas las principales de esta persona
        self._desmarcar_principales(persona_id)

        # Marcamos la nueva
        for p in self.data["direcciones"][direccion_id]["personas"]:
            if p["persona_id"] == persona_id:
                p["es_principal"] = True
                self._guardar_archivo()
                return True
        return False

    # ── COORDENADAS (integración Maps) ────────────────────────────────────────

    def actualizar_coordenadas(self, direccion_id, lat, lng, origen="maps"):
        """
        Actualiza las coordenadas de una dirección.
        origen: 'maps' (Google Maps API) o 'manual' (ingresadas por el usuario).
        Retorna True si se actualizó.
        """
        if direccion_id not in self.data["direcciones"]:
            return False

        self.data["direcciones"][direccion_id]["coordenadas"] = {
            "lat": lat,
            "lng": lng,
            "origen": origen
        }
        self._guardar_archivo()
        return True

    # ── BORRAR ────────────────────────────────────────────────────────────────

    def borrar_direccion(self, direccion_id):
        """
        Elimina una dirección del registro.
        Retorna True si se borró, False si no existía.
        """
        if direccion_id in self.data["direcciones"]:
            del self.data["direcciones"][direccion_id]
            self._guardar_archivo()
            return True
        return False

    # ── HELPERS INTERNOS ──────────────────────────────────────────────────────

    def _desmarcar_principales(self, persona_id):
        """Desmarca todas las direcciones principales de una persona."""
        for did, datos in self.data["direcciones"].items():
            for p in datos.get("personas", []):
                if p["persona_id"] == persona_id and p["es_principal"]:
                    p["es_principal"] = False