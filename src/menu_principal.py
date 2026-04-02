from src.send_wpp import SendWPP
from src.submenu_horarios import SubMenuHorarios
from src.config_loader import ConfigLoader
from src.session_manager import SessionManager

class MenuPrincipal:
    """Menú Principal del Bot"""

    def __init__(self, numero):
        self.numero = numero
        self.config = ConfigLoader()
        self.sw = SendWPP(numero)
        self.horarios = SubMenuHorarios(numero)
        self.session_manager = SessionManager()
        # 
        self.sesiones = None

    def administro_menu(self, sesioness, comando, pushname=""):
        self.sesiones = sesioness

        # 
        print("Numero: "+self.sesiones[self.numero].numero)

        # Si no existe 'menu' en la sesión, es porque es la primera vez que se llama a este método.
        seleccion_anterior = getattr(self.sesiones[self.numero], "menu", None)

        # Si no hay menú, lo asignamos y mostramos el menú inicial. Si lo hay, verificamos si es un comando de menú o submenú.
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
            self.mostrar_menu()
            return
        elif comando in ["horarios"]:
            self.sesiones[self.numero].menu = "1"
            self.sesiones[self.numero].submenu = None
            self.horarios.mostrar_submenu(self.sesiones)
            return
        elif not self.horarios.tiene_acceso() and not seleccion_anterior in ["1", "2"]:
            comando = "bloqueado"
        elif seleccion_anterior in ["1", "2"]:
            self.sesiones[self.numero].submenu = comando
            comando = seleccion_anterior
        else:
            comando = comando.strip().lower()

        # Guardamos la opción actual en la sesión para que los submenús puedan acceder a ella.
        self.sesiones[self.numero].menu = comando
            
        if comando == "0":
            self.sw.enviar("Próximamente...")
                
        elif comando == "1":
            self.horarios.mostrar_submenu(self.sesiones)
                
        elif comando == "2":
            self.sw.enviar("Próximamente...")

        elif comando == "horarios":
            self.horarios.mostrar_submenu(self.sesiones)

        else:
            self.sw.enviar("❌ Opción no válida.")

        # Si el comando es 'salir', volvemos al menú principal reseteando las variables de sesión.
        if getattr(self.sesiones[self.numero], "submenu", None) == "salir":
            self.sesiones[self.numero].menu = "principal"
            self.sesiones[self.numero].submenu = None
            self.mostrar_menu()
                        
    def mostrar_menu(self):
        """
        Determina dinámicamente si muestra el menú o el bloqueo.
        Se ejecuta al inicio y cada vez que se vuelve de un submenú.
        """
        # Mostramos Menu para Staff si el rol lo indica
        rol = self.session_manager.get_rol(self.numero)  # ← antes era self.config.obtener_rol
        if rol != "usuario":
            self.sw.enviar(self.config.get_mensaje("mensajes", "menu_principal_staff"))
            return  # ← el staff no pasa por el bloqueo de horario

        # Mostramos opcion de bloqueo por horario si el JSON lo indica y el horario actual lo amerita
        if not self.horarios.tiene_acceso():
            estado_actual = self.horarios.estado_actual()
            msg = f"{estado_actual}\n\nEscribí *'horarios'* para ver opciones."
            self.sw.enviar(msg)
            return  # ← bloqueado, no mostramos el menú principal

        # Si no hay bloqueo, mostramos el menú principal normal
        self.sw.enviar(self.config.get_mensaje("mensajes", "menu_principal"))

    # Funciones específicas para el módulo de menú principal (extraen info del JSON y aplican la lógica de negocio)
    def mensaje_bienvenida(self):
        """
        Genera el mensaje de bienvenida.
        Prioridad: nombre real > pushname > saludo genérico.
        """
        nombre_negocio = self.config.data.get("nombre_negocio", "nuestro negocio")
        nombre_cliente = self.session_manager.get_nombre_cliente(self.numero)
        if nombre_cliente:
            # Cliente con datos completos cargados
            return f"👋 ¡Hola {nombre_cliente}! Bienvenido a {nombre_negocio}."
        
        # Fallback: usamos el pushname de WhatsApp
        pushname = self.session_manager.get_cliente(self.numero).get("pushname", "")
        if pushname:
            return f"👋 ¡Hola {pushname}! Bienvenido a {nombre_negocio}."

        # Sin datos: saludo genérico
        return self.config.data["mensajes"]["mensaje_bienvenida"].format(nombre_negocio=nombre_negocio)




