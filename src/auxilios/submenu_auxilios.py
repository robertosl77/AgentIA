# src/auxilios/submenu_auxilios.py
from src.send_wpp import SendWPP
from src.sesiones.session_manager import SessionManager
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader
from src.auxilios.registro_servicio import RegistroServicio
from src.auxilios.gestion_conductores import GestionConductores
from src.auxilios.gestion_vehiculos_propios import GestionVehiculosPropios
from src.auxilios.gestion_vehiculos_auxiliados import GestionVehiculosAuxiliados
from src.auxilios.gestion_recorridos import GestionRecorridos
from src.auxilios.configuracion_auxilios import ConfiguracionAuxilios

class SubMenuAuxilios:
    """
    Orquestador del módulo de auxilios mecánicos.
    Delega cada flujo en su clase de gestión correspondiente.
    Diseñado como módulo enlatado: vinculación mínima con el sistema base.
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = AuxiliosConfigLoader()
        self.servicio = RegistroServicio(numero)
        self.conductores = GestionConductores(numero)
        self.vehiculos_propios = GestionVehiculosPropios(numero)
        self.vehiculos_auxiliados = GestionVehiculosAuxiliados(numero)
        self.recorridos = GestionRecorridos(numero)
        self.configuracion = ConfiguracionAuxilios(numero)

    # ── SUBMENÚ ───────────────────────────────────────────────────────────────

    def submenu_auxilios(self, comando, sesiones):
        """Procesa el comando dentro del submenú de auxilios."""
        print("🚛 Entrando al submódulo de Auxilios...")

        rol = self.session_manager.get_rol(self.numero)
        opcion = self.config.resolver_activacion(comando, rol)

        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        handler_nombre = opcion.get("handler")
        if handler_nombre:
            handler = getattr(self, handler_nombre, None)
            if handler:
                handler(sesiones)
            else:
                self.sw.enviar(f"❌ Handler '{handler_nombre}' no encontrado.")

    def mostrar_menu(self, sesiones):
        """Muestra el submenú de auxilios filtrado por rol."""
        rol = self.session_manager.get_rol(self.numero)
        self.sw.enviar(self.config.armar_menu(rol))

    # ── FLUJO ─────────────────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en medio de cualquier flujo de auxilios."""
        return (
            self.servicio.esta_en_flujo(sesiones) or
            self.conductores.esta_en_flujo(sesiones) or
            self.vehiculos_propios.esta_en_flujo(sesiones) or
            self.vehiculos_auxiliados.esta_en_flujo(sesiones) or
            self.recorridos.esta_en_flujo(sesiones) or
            self.configuracion.esta_en_flujo(sesiones)
        )

    def procesar_flujo(self, comando, sesiones):
        """Delega el comando al flujo activo."""
        if self.servicio.esta_en_flujo(sesiones):
            self.servicio.procesar(comando, sesiones)
        elif self.conductores.esta_en_flujo(sesiones):
            self.conductores.procesar(comando, sesiones)
        elif self.vehiculos_propios.esta_en_flujo(sesiones):
            self.vehiculos_propios.procesar(comando, sesiones)
        elif self.vehiculos_auxiliados.esta_en_flujo(sesiones):
            self.vehiculos_auxiliados.procesar(comando, sesiones)           
        elif self.recorridos.esta_en_flujo(sesiones):
            self.recorridos.procesar(comando, sesiones)
        elif self.configuracion.esta_en_flujo(sesiones):
            self.configuracion.procesar(comando, sesiones)

    # ── HANDLERS ──────────────────────────────────────────────────────────────

    def registrar_servicio(self, sesiones):
        self.servicio.iniciar(sesiones)

    def gestionar_conductores(self, sesiones):
        self.conductores.iniciar(sesiones)

    def gestionar_vehiculos_propios(self, sesiones):
        self.vehiculos_propios.iniciar(sesiones)

    def gestionar_vehiculos_auxiliados(self, sesiones):
        self.vehiculos_auxiliados.iniciar(sesiones)

    def gestionar_recorridos(self, sesiones):
        self.recorridos.iniciar(sesiones)

    def configuracion_modulo(self, sesiones):
        self.configuracion.iniciar(sesiones)
        