# src/session_manager.py
import json
import os
from datetime import datetime, timedelta
from src.config_loader import ConfigLoader

_instancia = None

class SessionManager:
    """
    Gestiona las sesiones de los usuarios en sesiones_data.json.
    Responsabilidades:
        - Crear sesión al primer contacto
        - Verificar si la sesión está vigente (1 hora)
        - Expirar y reiniciar sesión si venció (preservando datos del cliente)
        - Guardar y recuperar datos del cliente y dirección
        - Preparado para migración a base de datos
    """

    DURACION_SESION_HORAS = 1
    PATH = r"data\sesiones_data.json"

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        # Solo inicializamos una vez
        if not hasattr(self, 'data'):
            self.config = ConfigLoader()
            self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        """Carga el archivo de sesiones. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {"sesiones": {}}
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
        La estructura de campos se lee de configuracion.json.
        Solo se persiste el valor por campo, el resto es configuración del sistema.
        """
        ahora = datetime.now()
        estructura = self.config.data.get("estructura_sesion", {})
        duracion = estructura.get("duracion_horas", 1)
        expira = ahora + timedelta(hours=duracion)

        # Solo guardamos el valor, la config del campo vive en configuracion.json
        cliente = {k: {"valor": ""} for k in estructura.get("cliente", {}).keys()}
        direccion = {k: {"valor": ""} for k in estructura.get("direccion", {}).keys()}

        return {
            "rol": estructura.get("rol_defecto", "usuario"),
            "login": {
                "timestamp": ahora.isoformat(),
                "expira": expira.isoformat()
            },
            "cliente": cliente,
            "direccion": direccion
        }

    # ── LOGIN / SESIÓN ────────────────────────────────────────────────────────

    def verificar_o_crear(self, numero):
        """
        Punto de entrada principal. Para cada mensaje entrante:
            - Si no existe: crea la sesión y retorna True (sesión nueva)
            - Si existe y expiró: reinicia el login preservando datos del cliente y retorna True
            - Si existe y está vigente: retorna False (sesión activa)
        El valor de retorno indica a MenuPrincipal si debe mostrar bienvenida o no.
        """
        sesiones = self.data.get("sesiones", {})

        if numero not in sesiones:
            # Primera vez que se conecta: creamos sesión desde cero
            sesiones[numero] = self._sesion_vacia()
            self.data["sesiones"] = sesiones
            self._guardar_archivo()
            return True

        # Verificamos expiración
        expira_str = sesiones[numero].get("login", {}).get("expira", "")
        try:
            expira = datetime.fromisoformat(expira_str)
        except ValueError:
            # Timestamp corrupto: forzamos reinicio
            expira = datetime.min

        if datetime.now() > expira:
            datos_cliente = sesiones[numero].get("cliente", {})
            datos_direccion = sesiones[numero].get("direccion", {})
            rol_actual = sesiones[numero].get("rol", "usuario")
            sesiones[numero] = self._sesion_vacia()
            sesiones[numero]["cliente"] = datos_cliente
            sesiones[numero]["direccion"] = datos_direccion
            sesiones[numero]["rol"] = rol_actual
            self.data["sesiones"] = sesiones
            self._guardar_archivo()
            return True  # Sesión reiniciada = tratar como nuevo ingreso

        return False  # Sesión vigente

    # ── BIENVENIDA PERSONALIZADA ──────────────────────────────────────────────

    def get_nombre_cliente(self, numero):
        """
        Retorna el nombre y apellido del cliente si están cargados, o None si no.
        Usado para personalizar el mensaje de bienvenida.
        """
        cliente = self.data["sesiones"].get(numero, {}).get("cliente", {})
        nombre = cliente.get("nombre", {}).get("valor", "").strip().title()
        apellido = cliente.get("apellido", {}).get("valor", "").strip().upper()
        if nombre:
            # .title() formatea cada palabra con la primera letra en mayúscula
            return f"{nombre} {apellido}".strip()
        return None

    # ── GETTERS ───────────────────────────────────────────────────────────────

    def get_cliente(self, numero):
        """Retorna los datos del cliente para ese número."""
        return self.data["sesiones"].get(numero, {}).get("cliente", {})

    def get_direccion(self, numero):
        """Retorna los datos de dirección para ese número."""
        return self.data["sesiones"].get(numero, {}).get("direccion", {})

    # ── ABM CLIENTE (interfaz preparada para implementar) ─────────────────────

    def agregar_cliente(self, numero, datos):
        """[INTERFAZ] Carga los datos del cliente por primera vez."""
        pass

    def editar_cliente(self, numero, campo, valor):
        """Edita el valor de un campo específico del cliente y persiste."""
        if numero in self.data["sesiones"]:
            cliente = self.data["sesiones"][numero]["cliente"]
            if campo not in cliente:
                # ← campo nuevo que no existía en la sesión, lo creamos
                cliente[campo] = {"valor": ""}
            cliente[campo]["valor"] = valor
            self._guardar_archivo()

    def borrar_cliente(self, numero):
        """[INTERFAZ] Borra los datos del cliente (no la sesión)."""
        pass

    # ── ABM DIRECCIÓN (interfaz preparada para implementar) ───────────────────

    def agregar_direccion(self, numero, datos):
        """[INTERFAZ] Carga los datos de dirección por primera vez."""
        pass

    def editar_direccion(self, numero, campo, valor):
        """Edita el valor de un campo específico de la dirección y persiste."""
        if numero in self.data["sesiones"]:
            direccion = self.data["sesiones"][numero]["direccion"]
            if campo not in direccion:
                # ← campo nuevo que no existía en la sesión, lo creamos
                direccion[campo] = {"valor": ""}
            direccion[campo]["valor"] = valor
            self._guardar_archivo()

    def borrar_direccion(self, numero):
        """[INTERFAZ] Borra los datos de dirección."""
        pass

    # ── ROLES ─────────────────────────────────────────────────────────────────

    def get_rol(self, numero):
        """Retorna el rol del usuario. Si no existe sesión, retorna 'usuario'."""
        return self.data["sesiones"].get(numero, {}).get("rol", "usuario")

    def asignar_rol(self, numero, rol):
        """Asigna un rol al usuario y persiste. Roles válidos: usuario, supervisores, administradores, root."""
        roles_validos = ["usuario", "supervisores", "administradores", "root"]
        if rol not in roles_validos:
            print(f"❌ Rol inválido: {rol}")
            return False
        if numero in self.data["sesiones"]:
            self.data["sesiones"][numero]["rol"] = rol
            self._guardar_archivo()
            return True
        return False    