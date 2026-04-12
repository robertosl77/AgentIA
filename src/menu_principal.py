# src/menu_principal.py
from src.send_wpp import SendWPP
from src.horarios import SubMenuHorarios
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.cliente import SubMenuCliente
from src.staff import SubMenuStaff
from src.farmacia.submenu_farmacia import SubMenuFarmacia

class MenuPrincipal:
    """Menú Principal del Bot"""

    def __init__(self, numero):
        self.config = ConfigLoader()
        self.sw = SendWPP(numero)
        self.horarios = SubMenuHorarios(numero)
        self.session_manager = SessionManager()
        self.registro = SubMenuCliente(numero)
        self.staff = SubMenuStaff(numero)
        self.farmacia = SubMenuFarmacia(numero)
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

        # ── PRIORIDAD MÁXIMA: si está en flujo de registro, todo va ahí ──────────
        if self.registro.esta_en_registro(self.sesiones):
            resultado = self.registro.procesar_registro(comando, self.sesiones)

            if not self.registro.esta_en_registro(self.sesiones):
                if resultado == "ok":
                    # ✅ Registro exitoso: volvemos al menú
                    self.sw.enviar("✅ Datos registrados correctamente. Volviendo al menú...")
                    self.mostrar_menu(rol)
                else:
                    # ❌ Registro cancelado: cerramos la sesión
                    self.sw.enviar(
                        "No pudimos completar el registro. Tu sesión fue cerrada. "
                        "Cuando quieras podés volver a intentarlo. 👋"
                    )
                    self.sesiones[self.numero].menu = None
                    self.sesiones[self.numero].submenu = None
            return
        
        if self.staff.esta_en_flujo(self.sesiones):
            self.staff.procesar_flujo(comando, self.sesiones)
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

        # Usuario bloqueado por horario
        if not self.horarios.tiene_acceso() and seleccion_anterior == "principal":
            self._gestionar_bloqueo(comando, rol)
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
            self.session_manager.editar_cliente(self.numero, "pushname", pushname)

    def _bienvenida_y_menu(self, rol):
        """Muestra la bienvenida completa y el menú principal. Solo al primer contacto o sesión expirada."""
        self.sesiones[self.numero].menu = "principal"

        self.sw.enviar(self.mensaje_bienvenida())
        self._enviar_mensajes_emergentes()

        if self._requiere_registro_cliente():
            return

        if self._requiere_registro_direccion():
            return

        self.mostrar_menu(rol)

    def _enviar_mensajes_emergentes(self):
        """Envía avisos de guardia próxima y cierre eventual si corresponde."""
        msg_guardia = self.horarios.mensaje_proximas_guardias()
        if msg_guardia:
            self.sw.enviar(msg_guardia)

        msg_cierre = self.horarios.mensaje_proximo_evento()
        if msg_cierre:
            self.sw.enviar(msg_cierre)

    def _requiere_registro_cliente(self):
        """
        Valida si el cliente tiene datos obligatorios completos.
        Si no los tiene, lo deriva al flujo de registro y retorna True.
        Reutilizable en cualquier punto del flujo que requiera datos del cliente.
        """
        if self.registro.tiene_datos_cliente_completos():
            return False

        self.sw.enviar(
            "📋 Para poder brindarte una mejor atención, necesitamos que completes "
            "algunos datos antes de continuar.\n\n"
            "Solo te tomará un momento. ¡Empecemos! 😊"
        )
        self.registro.iniciar_registro_cliente(self.sesiones)
        return True

    def _requiere_registro_direccion(self):
        """
        [INTERFAZ] Valida si el cliente tiene datos de dirección completos.
        Si no los tiene, lo deriva al flujo de registro de dirección y retorna True.
        Reutilizable en cualquier punto del flujo que requiera dirección del cliente.
        """
        pass

    def _gestionar_bloqueo(self, comando, rol):
        """Maneja el caso de usuario bloqueado por horario. Solo deja pasar submenús permitidos."""
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
        self.sw.enviar(f"{estado_actual}\n\nEscribí *'horarios'* para ver opciones.")

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

        # Validamos que el comando sea una activación válida para el rol
        submenu_data = self.config.get_submenu(nombre_submenu)
        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        if nombre_submenu == "horarios":
            self.horarios.submenu_horarios(comando)

        elif nombre_submenu == "staff":
            self.staff.submenu_staff(comando, self.sesiones)

        else:
            self.sw.enviar("❌ Submenú no reconocido.")

    def _resetea_si_salio(self, comando, rol):
        """Si el comando fue 'salir', volvemos al menú principal."""
        if getattr(self.sesiones[self.numero], "submenu", None) == "salir":
            self.sesiones[self.numero].menu = "principal"
            self.sesiones[self.numero].submenu = None
            self.mostrar_menu(rol)

    # ── MENÚ Y BIENVENIDA ─────────────────────────────────────────────────────

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

        pushname_data = self.session_manager.get_cliente(self.numero).get("pushname", {})
        pushname = pushname_data.get("valor", "") if isinstance(pushname_data, dict) else pushname_data

        # Prioridad 1: nombre real cargado por el cliente
        if nombre_cliente:
            return self.config.get_bienvenida(nombre_cliente, nombre_negocio)

        # Prioridad 2: pushname de WhatsApp
        if pushname:
            return self.config.get_bienvenida(pushname, nombre_negocio)

        # Prioridad 3: saludo genérico sin nombre
        return self.config.get_bienvenida("", nombre_negocio).replace("¡Hola ! ", "¡Hola! ")