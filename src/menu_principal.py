# src/menu_principal.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.cliente.persona_manager import PersonaManager
from src.staff import SubMenuStaff
from src.farmacia.submenu_farmacia import SubMenuFarmacia
from src.auxilios import SubMenuAuxilios

class MenuPrincipal:
    """Menú Principal del Bot — Router de enlatados"""

    def __init__(self, numero):
        self.config = ConfigLoader()
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.persona_manager = PersonaManager()
        self.staff = SubMenuStaff(numero)
        self.farmacia = SubMenuFarmacia(numero)
        self.auxilios = SubMenuAuxilios(numero)
        # 
        self.sesiones = None
        self.numero = numero

    def administro_menu(self, sesiones, comando, pushname):
        self.sesiones = sesiones
        print(f"📱 Número: {self.numero} | 📝 Comando: {comando} | 👤 Pushname: {pushname}")

        # Verificamos/creamos sesión en cada mensaje
        es_nueva = self.session_manager.verificar_o_crear(self.numero)
        if es_nueva:
            self._resetear_estado_memoria(pushname)

        rol = self.session_manager.get_rol(self.numero)

        # ── FLUJOS ACTIVOS DE ENLATADOS ──────────────────────────────────────────
        if self.staff.esta_en_flujo(self.sesiones):
            self.staff.procesar_flujo(comando, self.sesiones)
            return

        # ── FLUJO DE AUXILIOS ──
        if self.auxilios.esta_en_flujo(self.sesiones):
            self.auxilios.procesar_flujo(comando, self.sesiones)
            return

        # ── FLUJO DE FARMACIA (incluye registro de persona y selección de beneficiario) ──
        if self.farmacia.esta_en_flujo(self.sesiones):
            self.farmacia.procesar(comando, self.sesiones)

            # Si farmacia terminó (salió), volvemos al menú principal
            if not self.farmacia.esta_en_flujo(self.sesiones):
                self.sw.enviar("Volviendo al menú principal...")
                self.sesiones[self.numero].menu = "principal"
                self.sesiones[self.numero].submenu = None
                self.mostrar_menu(rol)
            return

        seleccion_anterior = getattr(self.sesiones[self.numero], "menu", None)

        # Primera vez o sesión expirada
        if seleccion_anterior is None:
            self._bienvenida_y_menu(rol)
            return

        # Está dentro de un submenú
        opcion_activa = self._get_opcion_activa(seleccion_anterior)
        if opcion_activa and opcion_activa.get("submenu"):
            self.sesiones[self.numero].submenu = comando
            self._procesar_submenu(opcion_activa["submenu"], comando, rol)
            return

        # Menú principal
        self._procesar_menu_principal(comando, rol)

    # ── MÓDULOS DE ADMINISTRO_MENU ────────────────────────────────────────────

    def _resetear_estado_memoria(self, pushname):
        """Resetea el estado en memoria cuando la sesión es nueva o expiró."""
        self.sesiones[self.numero].menu = None
        self.sesiones[self.numero].submenu = None
        # Precargamos el pushname si está disponible
        if pushname:
            self.session_manager.set_pushname(self.numero, pushname)

    def _bienvenida_y_menu(self, rol):
        """Muestra la bienvenida y el menú principal. Solo al primer contacto o sesión expirada."""
        self.sesiones[self.numero].menu = "principal"

        self.sw.enviar(self.mensaje_bienvenida())
        self.mostrar_menu(rol)

    def _get_opcion_activa(self, seleccion_anterior):
        """Busca en el menú principal la opción que corresponde a la selección anterior."""
        menu_principal = self.config.get_menu_principal()
        for op in menu_principal.get("opciones", []):
            if seleccion_anterior in op.get("activacion", []) or seleccion_anterior == op["id"]:
                return op
        return None

    def _procesar_menu_principal(self, comando, rol):
        """Resuelve el comando en el contexto del menú principal y muestra el submenú correspondiente."""
        menu_principal = self.config.get_menu_principal()
        opcion = self.config.resolver_activacion(comando, menu_principal, rol)

        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        # Guardamos en sesión qué opción eligió para el próximo mensaje
        self.sesiones[self.numero].menu = opcion["id"]
        self.sesiones[self.numero].submenu = None

        if opcion.get("submenu"):
            # Farmacia tiene su propio flujo de entrada (no muestra submenú directo)
            if opcion["submenu"] == "farmacia":
                self.farmacia.iniciar(self.sesiones)
                return

            # Auxilios tiene su propio submenú enlatado
            if opcion["submenu"] == "auxilios":
                self.auxilios.mostrar_menu(self.sesiones)
                return

            # Mostramos el submenú correspondiente
            submenu_data = self.config.get_submenu(opcion["submenu"])
            if submenu_data:
                self.sw.enviar(self.config.armar_menu(submenu_data, rol))
        else:
            # Opción sin submenú: próximamente
            self.sw.enviar("🚧 Próximamente...")

    def _procesar_submenu(self, nombre_submenu, comando, rol):
        """
        Delega el comando al handler correspondiente según el nombre del submenú.
        Cada submenú tiene su propia lógica de negocio.
        """
        if comando == "salir":
            self.sesiones[self.numero].menu = "principal"
            self.sesiones[self.numero].submenu = None
            self.sw.enviar("Volviendo al menú principal...")
            self.mostrar_menu(rol)
            return

        # Farmacia maneja su propio flujo completo
        if nombre_submenu == "farmacia":
            self.farmacia.procesar(comando, self.sesiones)
            return

        # Auxilios maneja su propio flujo completo
        if nombre_submenu == "auxilios":
            self.auxilios.submenu_auxilios(comando, self.sesiones)
            return

        # Validamos que el comando sea una activación válida para el rol
        submenu_data = self.config.get_submenu(nombre_submenu)
        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        if nombre_submenu == "staff":
            self.staff.submenu_staff(comando, self.sesiones)

        else:
            self.sw.enviar("❌ Submenú no reconocido.")

    # ── MENÚ Y BIENVENIDA ─────────────────────────────────────────────────────

    def mostrar_menu(self, rol):
        """Muestra el menú principal filtrando opciones por rol."""
        menu_principal = self.config.get_menu_principal()
        self.sw.enviar(self.config.armar_menu(menu_principal, rol))

    def mensaje_bienvenida(self):
        """
        Genera el mensaje de bienvenida.
        Prioridad: nombre real (PersonaManager) > pushname (sesión) > saludo genérico.
        """
        nombre_negocio = self.config.data.get("nombre_negocio", "nuestro negocio")

        # Prioridad 1: nombre real desde PersonaManager (busca por LID)
        persona = self.persona_manager.buscar_por_lid(self.numero)
        if persona:
            nombre_completo = self.persona_manager.get_nombre_completo(persona[0])
            if nombre_completo:
                return self.config.get_bienvenida(nombre_completo, nombre_negocio)

        # Prioridad 2: pushname de WhatsApp
        pushname = self.session_manager.get_pushname(self.numero)
        if pushname:
            return self.config.get_bienvenida(pushname, nombre_negocio)

        # Prioridad 3: saludo genérico sin nombre
        return self.config.get_bienvenida("", nombre_negocio).replace("¡Hola ! ", "¡Hola! ")