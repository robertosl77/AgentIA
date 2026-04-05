# src/staff/submenu_staff.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.session_manager import SessionManager
from src.staff.gestion_guardias import GestionGuardias
from src.staff.gestion_cierres_eventuales import GestionCierresEventuales
from src.staff.gestion_horarios_fijos import GestionHorariosFijos

class SubMenuStaff:
    """
    Orquestador del panel de staff.
    Delega cada flujo en su clase de gestión correspondiente.
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()
        self.guardias = GestionGuardias(numero)
        self.cierres = GestionCierresEventuales(numero)
        self.horarios = GestionHorariosFijos(numero)

    def submenu_staff(self, comando, sesiones):
        """Procesa el comando dentro del submenú de staff."""
        print("👤 Entrando al submódulo de Staff...")

        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")

        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
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

    # ── FLUJO ─────────────────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en medio de cualquier flujo de staff."""
        return (self.guardias.esta_en_flujo(sesiones) or 
            self.cierres.esta_en_flujo(sesiones) or 
            self.horarios.esta_en_flujo(sesiones))

    def procesar_flujo(self, comando, sesiones):
        """Delega el comando al flujo activo."""
        if self.guardias.esta_en_flujo(sesiones):
            self.guardias.procesar(comando, sesiones)
        elif self.cierres.esta_en_flujo(sesiones):
            self.cierres.procesar(comando, sesiones)       
        elif self.horarios.esta_en_flujo(sesiones):
            self.horarios.procesar(comando, sesiones)                 

    # ── HANDLERS ──────────────────────────────────────────────────────────────

    def gestionar_guardias(self, sesiones):
        self.guardias.iniciar(sesiones)

    def gestionar_cierre_eventual(self, sesiones):
        self.cierres.iniciar(sesiones)

    def editar_horarios_fijos(self, sesiones):
        self.horarios.iniciar(sesiones)