# src/session_manager.py
import json
import os
from datetime import datetime, timedelta

class SessionManager:
    """
    Gestiona las sesiones de los usuarios en sesiones.json.
    Responsabilidades:
        - Crear sesión al primer contacto
        - Verificar si la sesión está vigente (1 hora)
        - Expirar y reiniciar sesión si venció (preservando datos del cliente)
        - Guardar y recuperar datos del cliente y dirección
        - Preparado para migración a base de datos
    """

    DURACION_SESION_HORAS = 1
    PATH = r"data\sesiones.json"

    def __init__(self):
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

    def _sesion_vacia(self, numero):
        """Retorna la estructura base de una sesión nueva."""
        ahora = datetime.now()
        expira = ahora + timedelta(hours=self.DURACION_SESION_HORAS)
        return {
            "rol": "usuario",  # ← por defecto todos son usuarios
            "login": {
                "timestamp": ahora.isoformat(),
                "expira": expira.isoformat()
            },
            "menu": {
                # Estado del menú: se usa en memoria (MenuPrincipal),
                # pero se persiste acá para poder recuperarse si el servidor se reinicia
                "menu": None,
                "submenu": None
            },
            "cliente": {
                "pushname": "",  # ← nombre de WhatsApp, se precarga automáticamente
                "telefono": "",
                "nombre": "",
                "apellido": "",
                "email": "",
                "dni": ""
            },
            "direccion": {
                "direccion": "",
                "altura": "",
                "piso": "",
                "depto": "",
                "localidad": "",
                "codigo_postal": "",
                "provincia": ""
            }
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
            sesiones[numero] = self._sesion_vacia(numero)
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
            # Sesión expirada: reiniciamos login pero preservamos datos del cliente
            datos_cliente = sesiones[numero].get("cliente", {})
            datos_direccion = sesiones[numero].get("direccion", {})
            sesiones[numero] = self._sesion_vacia(numero)
            sesiones[numero]["cliente"] = datos_cliente       # ← preservamos
            sesiones[numero]["direccion"] = datos_direccion   # ← preservamos
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
        nombre = cliente.get("nombre", "").strip()
        apellido = cliente.get("apellido", "").strip()
        if nombre:
            return f"{nombre} {apellido}".strip()
        return None  # Sin datos: el saludo queda genérico

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
        """Edita un campo específico del cliente y persiste."""
        if numero in self.data["sesiones"]:
            self.data["sesiones"][numero]["cliente"][campo] = valor
            self._guardar_archivo()

    def borrar_cliente(self, numero):
        """[INTERFAZ] Borra los datos del cliente (no la sesión)."""
        pass

    # ── ABM DIRECCIÓN (interfaz preparada para implementar) ───────────────────

    def agregar_direccion(self, numero, datos):
        """[INTERFAZ] Carga los datos de dirección por primera vez."""
        pass

    def editar_direccion(self, numero, campo, valor):
        """[INTERFAZ] Edita un campo específico de la dirección y persiste."""
        pass

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