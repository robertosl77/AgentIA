# src/staff/submenu_staff.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.session_manager import SessionManager

class SubMenuStaff:
    """
    Submenú de Staff.
    Responsabilidades:
        - Gestionar el flujo de opciones del panel de staff
        - Interfaces preparadas para implementar
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()

    def submenu_staff(self, comando):
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
                self.sw.enviar(handler())
            else:
                self.sw.enviar(f"❌ Handler '{handler_nombre}' no encontrado.")

    # ── OPCIONES DEL PANEL DE STAFF ───────────────────────────────────────────

    def agregar_guardia(self):
        """[INTERFAZ] Agrega un día de guardia al JSON."""
        pass

    def registrar_cierre_eventual(self):
        """[INTERFAZ] Registra un cierre eventual en el JSON."""
        pass

    def editar_horarios_fijos(self):
        """[INTERFAZ] Edita los horarios fijos en el JSON."""
        pass