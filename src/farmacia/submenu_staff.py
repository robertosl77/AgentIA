# src/farmacia/submenu_staff.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.horarios import GuardiasGestion, CierresGestion, HorariosFijosGestion


class SubMenuStaff:
    """
    Orquestador del panel de staff para farmacia.
    Delega cada flujo en su clase de gestion correspondiente.
    Consume servicios de src/horarios/ con ruta de datos de farmacia.
    """

    DATA_PATH = "data/farmacia/horarios.json"

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()
        
        # Instanciamos gestiones con la ruta de datos de farmacia
        self.guardias = GuardiasGestion(numero, self.DATA_PATH)
        self.cierres = CierresGestion(numero, self.DATA_PATH)
        self.horarios = HorariosFijosGestion(numero, self.DATA_PATH)
        
        # Configuramos callbacks para volver al menu de staff
        self.guardias.set_callback_volver(self._mostrar_menu_staff)
        self.cierres.set_callback_volver(self._mostrar_menu_staff)
        self.horarios.set_callback_volver(self._mostrar_menu_staff)

    def iniciar(self, sesiones):
        """Punto de entrada al panel de staff."""
        sesiones[self.numero].farmacia_staff_activo = True
        self._mostrar_menu_staff(sesiones)

    def _mostrar_menu_staff(self, sesiones):
        """Muestra el menu de staff."""
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))

    def procesar(self, comando, sesiones):
        """Procesa el comando dentro del submenu de staff."""
        # Si estamos en un flujo de gestion, delegamos
        if self.guardias.esta_en_flujo(sesiones):
            self.guardias.procesar(comando, sesiones)
            return
        
        if self.cierres.esta_en_flujo(sesiones):
            self.cierres.procesar(comando, sesiones)
            return
        
        if self.horarios.esta_en_flujo(sesiones):
            self.horarios.procesar(comando, sesiones)
            return

        # Procesamos comando del menu de staff
        if comando.strip() == "salir":
            sesiones[self.numero].farmacia_staff_activo = False
            return  # Vuelve al menu de farmacia

        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")

        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("Opcion no valida.")
            return

        handler_nombre = opcion.get("handler")
        if handler_nombre:
            handler = getattr(self, handler_nombre, None)
            if handler:
                handler(sesiones)
            else:
                self.sw.enviar(f"Handler '{handler_nombre}' no encontrado.")

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario esta en el panel de staff o en un flujo de gestion."""
        staff_activo = getattr(sesiones[self.numero], "farmacia_staff_activo", False)
        if staff_activo:
            return True
        return (self.guardias.esta_en_flujo(sesiones) or 
                self.cierres.esta_en_flujo(sesiones) or 
                self.horarios.esta_en_flujo(sesiones))

    # ── HANDLERS ──────────────────────────────────────────────────────────────

    def gestionar_guardias(self, sesiones):
        self.guardias.iniciar(sesiones)

    def gestionar_cierre_eventual(self, sesiones):
        self.cierres.iniciar(sesiones)

    def editar_horarios_fijos(self, sesiones):
        self.horarios.iniciar(sesiones)
