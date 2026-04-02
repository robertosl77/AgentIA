from src.send_wpp import SendWPP
from src.submenu_horarios import SubMenuHorarios
from src.config_loader import ConfigLoader
from src.session_manager import SessionManager

class MenuPrincipal:
    """Menú Principal del Bot"""

    def __init__(self, numero):
        self.config = ConfigLoader()
        self.sw = SendWPP(numero)
        self.horarios = SubMenuHorarios(numero)
        self.session_manager = SessionManager()
        # 
        self.sesiones = None
        self.numero = numero

    def administro_menu(self, sesiones, comando, pushname):
        self.sesiones = sesiones

        # 
        print(f"📱 Número: {self.numero} | 📝 Comando: {comando} | 👤 Pushname: {pushname}")

        # Obtenemos el rol del usuario para filtrar opciones durante toda la sesión
        rol = self.session_manager.get_rol(self.numero)

        # Si no existe 'menu' en la sesión, es porque es la primera vez que se llama a este método.
        seleccion_anterior = getattr(self.sesiones[self.numero], "menu", None)

        if seleccion_anterior is None:
            self.sesiones[self.numero].menu = "principal"

            # Creamos/verificamos sesión y precargamos el pushname si es nuevo
            es_nueva = self.session_manager.verificar_o_crear(self.numero)
            if es_nueva and pushname:
                # Guardamos el pushname como nombre provisional hasta que el cliente cargue sus datos
                self.session_manager.editar_cliente(self.numero, "pushname", pushname)

            # Bienvenida personalizada si el cliente ya tiene datos cargados
            self.sw.enviar(self.mensaje_bienvenida())

            # Mostramos mensaje de guardias próximas si corresponde
            msg_guardia = self.horarios.mensaje_proximas_guardias()
            if msg_guardia:
                self.sw.enviar(msg_guardia)

            # Mostramos mensaje de próximo evento de cierre si corresponde
            msg_cierre = self.horarios.mensaje_proximo_evento()
            if msg_cierre:
                self.sw.enviar(msg_cierre)

            # Finalmente, mostramos el menú principal o bloqueo por horario según corresponda.
            self.mostrar_menu(rol)
            return

        # ── USUARIO BLOQUEADO POR HORARIO ────────────────────────────────────
        # Si no tiene acceso, solo dejamos pasar comandos que activen submenús permitidos
        if not self.horarios.tiene_acceso() and seleccion_anterior == "principal":
            menu_principal = self.config.get_menu_principal()
            opcion = self.config.resolver_activacion(comando, menu_principal, rol)
            
            if opcion and opcion.get("submenu"):
                # El comando activa un submenú válido, lo dejamos pasar
                self.sesiones[self.numero].menu = opcion["id"]
                self.sesiones[self.numero].submenu = None
                submenu_data = self.config.get_submenu(opcion["submenu"])
                if submenu_data:
                    self.sw.enviar(self.config.armar_menu(submenu_data, rol))
                return
            
            # Comando no válido: mostramos el bloqueo
            estado_actual = self.horarios.estado_actual()
            msg = f"{estado_actual}\n\nEscribí *'horarios'* para ver opciones."
            self.sw.enviar(msg)
            return

        # ── ESTÁ EN UN SUBMENÚ ────────────────────────────────────────────────
        # Si la selección anterior era una opción del menú principal, el comando actual es para el submenú
        menu_principal = self.config.get_menu_principal()
        opcion_activa = None
        for op in menu_principal.get("opciones", []):
            if seleccion_anterior in op.get("activacion", []) or seleccion_anterior == op["id"]:
                opcion_activa = op
                break

        if opcion_activa and opcion_activa.get("submenu"):
            # Estamos dentro de un submenú: procesamos el comando en ese contexto
            self.sesiones[self.numero].submenu = comando
            self._procesar_submenu(opcion_activa["submenu"], comando, rol)
            return

        # ── MENÚ PRINCIPAL ────────────────────────────────────────────────────
        # Resolvemos qué opción del menú principal activa este comando
        opcion = self.config.resolver_activacion(comando, menu_principal, rol)

        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        # Guardamos en sesión qué opción eligió para el próximo mensaje
        self.sesiones[self.numero].menu = opcion["id"]
        self.sesiones[self.numero].submenu = None

        # Si la opción tiene submenú, lo mostramos
        if opcion.get("submenu"):
            submenu_data = self.config.get_submenu(opcion["submenu"])
            if submenu_data:
                self.sw.enviar(self.config.armar_menu(submenu_data, rol))
        else:
            # Opción sin submenú: próximamente
            self.sw.enviar("🚧 Próximamente...")

        self._resetea_si_salio(comando, rol)

    def _procesar_submenu(self, nombre_submenu, comando, rol):
        """
        Delega el comando al handler correspondiente según el nombre del submenú.
        Cada submenú tiene su propia lógica de negocio.
        """
        if comando == "salir":
            # Reseteamos al menú principal
            self.sesiones[self.numero].menu = "principal"
            self.sesiones[self.numero].submenu = None
            self.sw.enviar("Volviendo al menú principal...")
            self.mostrar_menu(rol)
            return

        # ← Validamos que el comando sea una activación válida para el rol
        submenu_data = self.config.get_submenu(nombre_submenu)
        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        if nombre_submenu == "horarios":
            self.horarios.submenu_horarios(comando)

        elif nombre_submenu == "staff":
            # Próximamente: submenú de staff
            self.sw.enviar("🚧 Panel de staff próximamente...")

        else:
            self.sw.enviar("❌ Submenú no reconocido.")
    def _resetea_si_salio(self, comando, rol):
        """Si el comando fue 'salir', volvemos al menú principal."""
        if getattr(self.sesiones[self.numero], "submenu", None) == "salir":
            self.sesiones[self.numero].menu = "principal"
            self.sesiones[self.numero].submenu = None
            self.mostrar_menu(rol)

    def mostrar_menu(self, rol):
        """
        Determina dinámicamente si muestra el menú o el bloqueo.
        Se ejecuta al inicio y cada vez que se vuelve de un submenú.
        """
        # Verificamos acceso por horario (el staff siempre tiene acceso)
        if not self.horarios.tiene_acceso():
            estado_actual = self.horarios.estado_actual()
            msg = f"{estado_actual}\n\nEscribí *'horarios'* para ver opciones."
            self.sw.enviar(msg)
            return

        # Armamos el menú principal filtrando opciones por rol
        menu_principal = self.config.get_menu_principal()
        self.sw.enviar(self.config.armar_menu(menu_principal, rol))

    def mensaje_bienvenida(self):
        """
        Genera el mensaje de bienvenida.
        Prioridad: nombre real > pushname > saludo genérico.
        """
        nombre_negocio = self.config.data.get("nombre_negocio", "nuestro negocio")
        nombre_cliente = self.session_manager.get_nombre_cliente(self.numero)
        pushname = self.session_manager.get_cliente(self.numero).get("pushname", "")

        # Prioridad 1: nombre real cargado por el cliente
        if nombre_cliente:
            return self.config.get_bienvenida(nombre_cliente, nombre_negocio)

        # Prioridad 2: pushname de WhatsApp
        if pushname:
            return self.config.get_bienvenida(pushname, nombre_negocio)

        # Prioridad 3: saludo genérico sin nombre
        return self.config.get_bienvenida("", nombre_negocio).replace("¡Hola ! ", "¡Hola! ")