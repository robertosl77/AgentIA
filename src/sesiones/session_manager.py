# src/sesiones/session_manager.py
import json
import os
from datetime import datetime, timedelta
from src.config_loader import ConfigLoader

_instancia = None

class SessionManager:
    """
    Gestiona las sesiones de los usuarios en sesiones.json.
    Responsabilidades:
        - Crear sesión al primer contacto
        - Verificar si la sesión está vigente (1 hora)
        - Expirar y reiniciar sesión si venció
        - Gestionar rol y pushname
        - Los datos de persona y dirección ahora viven en sus managers propios
    """

    DURACION_SESION_HORAS = 1
    PATH = os.path.join("data", "sesiones.json")

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.config = ConfigLoader()
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        """Carga el archivo de sesiones. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {"sesiones": {}}
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        """Persiste el estado actual en el archivo JSON."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── ESTRUCTURA BASE ───────────────────────────────────────────────────────

    def _sesion_vacia(self):
        """
        Retorna la estructura base de una sesión nueva.
        Solo contiene: rol, login (timestamp + expiración) y pushname.
        Los datos de persona y dirección viven en personas.json y direcciones.json.
        """
        ahora = datetime.now()
        estructura = self.config.data.get("estructura_sesion", {})
        duracion = estructura.get("duracion_horas", 1)
        expira = ahora + timedelta(hours=duracion)

        return {
            "rol": estructura.get("rol_defecto", "usuario"),
            "login": {
                "timestamp": ahora.isoformat(),
                "expira": expira.isoformat()
            },
            "pushname": ""
        }

    # ── LOGIN / SESIÓN ────────────────────────────────────────────────────────

    def verificar_o_crear(self, numero, rol=None):
        """
        Punto de entrada principal. Para cada mensaje entrante:
            - Si no existe: crea la sesión y retorna True (sesión nueva)
            - Si existe y expiró: reinicia el login preservando rol y retorna True
            - Si existe y está vigente: retorna False (sesión activa)
        """
        sesiones = self.data.get("sesiones", {})

        if numero not in sesiones:
            sesiones[numero] = self._sesion_vacia()

            # 🔥 NUEVO: setear rol si viene informado
            if rol:
                sesiones[numero]["rol"] = rol

            self.data["sesiones"] = sesiones
            self._guardar_archivo()
            return True

        # Verificamos expiración
        expira_str = sesiones[numero].get("login", {}).get("expira", "")
        try:
            expira = datetime.fromisoformat(expira_str)
        except ValueError:
            expira = datetime.min

        if datetime.now() > expira:
            rol_actual = sesiones[numero].get("rol", "usuario")

            sesiones[numero] = self._sesion_vacia()

            # 🔥 NUEVO: prioridad al rol recibido, sino mantiene el anterior
            sesiones[numero]["rol"] = rol if rol else rol_actual

            self.data["sesiones"] = sesiones
            self._guardar_archivo()
            return True

        return False

    # ── PUSHNAME ──────────────────────────────────────────────────────────────

    def set_pushname(self, numero, pushname):
        """Guarda el pushname de WhatsApp en la sesión."""
        if numero in self.data["sesiones"]:
            self.data["sesiones"][numero]["pushname"] = pushname
            self._guardar_archivo()

    def get_pushname(self, numero):
        """Retorna el pushname de la sesión, o string vacío."""
        return self.data["sesiones"].get(numero, {}).get("pushname", "")

    # ── ROLES ─────────────────────────────────────────────────────────────────

    def get_rol(self, numero):
        """Retorna el rol del usuario. Si no existe sesión, retorna 'usuario'."""
        return self.data["sesiones"].get(numero, {}).get("rol", "usuario")

    def asignar_rol(self, numero, rol):
        """Asigna un rol al usuario y persiste."""
        roles_validos = ["usuario", "supervisor", "admin", "root"]
        if rol not in roles_validos:
            print(f"❌ Rol inválido: {rol}")
            return False
        if numero in self.data["sesiones"]:
            self.data["sesiones"][numero]["rol"] = rol
            self._guardar_archivo()
            return True
        return False