from src.send_wpp import SendWPP
from src.submenu_horarios import SubMenuHorarios
from src.config_loader import ConfigLoader

class MenuPrincipal:
    """Menú Principal del Bot"""

    def __init__(self, numero):
        self.numero = numero
        self.config = ConfigLoader()
        self.sw = SendWPP(numero)
        self.autorizado = False  # ← La "llave" de sesión
        self.horarios = SubMenuHorarios(numero)

    def administro_menu(self, comando, sesiones):
        print("Numero: "+sesiones[self.numero].numero)

        # Si no existe 'menu' en la sesión, es porque es la primera vez que se llama a este método.
        menu = getattr(sesiones[self.numero], "menu", None)

        # Si no hay menú, lo asignamos y mostramos el menú inicial. Si lo hay, verificamos si es un comando de menú o submenú.
        if menu is None:
            sesiones[self.numero].menu = "principal"
            self.sw.enviar(self.mensaje_bienvenida())
            self.sw.enviar(self.horarios.mensaje_proximas_guardias())
            self.sw.enviar(self.horarios.mensaje_proximo_evento())
            self.mostrar_menu(sesiones)
            return
        elif menu in ["horarios"]:
            sesiones[self.numero].menu = "1"
            sesiones[self.numero].submenu = None
            self.horarios.mostrar_submenu(sesiones)
            return
        elif menu in ["1", "horarios"]:
            sesiones[self.numero].submenu = comando
            comando = menu
        else:
            comando = comando.strip().lower()

        # Guardamos la opción actual en la sesión para que los submenús puedan acceder a ella.
        sesiones[self.numero].menu = comando
            
        if comando == "0":
            self.sw.enviar("Próximamente...")
                
        elif comando == "1":
            self.horarios.mostrar_submenu(sesiones)
                
        elif comando == "2":
            self.sw.enviar("Próximamente...")

        elif comando == "horarios":
            self.horarios.mostrar_submenu(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida.")

        # Si el comando es 'salir', volvemos al menú principal reseteando las variables de sesión.
        if getattr(sesiones[self.numero], "submenu", None) == "salir":
            sesiones[self.numero].menu = None
            sesiones[self.numero].submenu = None
            self.mostrar_menu(sesiones)
                        
    def mostrar_menu(self, sesiones):
        """
        Determina dinámicamente si muestra el menú o el bloqueo.
        Se ejecuta al inicio y cada vez que se vuelve de un submenú.
        """
        # Mostramos Menu para Staff si el rol lo indica
        rol = self.config.obtener_rol(self.numero)
        if rol != "usuario":
            self.sw.enviar(self.config.get_mensaje("mensajes", "menu_principal_staff"))

        # Mostramos opcion de bloqueo por horario si el JSON lo indica y el horario actual lo amerita
        bloquea_por_horario = self.config.data.get("configuracion_bot", {}).get("bloquear_fuera_de_horario", False)
        estado_actual = self.horarios.estado_actual()

        if bloquea_por_horario and "🚫" in estado_actual:
            sesiones[self.numero].menu = "horarios"
            msg = f"{estado_actual}\n\nEscribí *'horarios'* para ver opciones."
            self.sw.enviar(msg)


    # Funciones específicas para el módulo de menú principal (extraen info del JSON y aplican la lógica de negocio)
    def mensaje_bienvenida(self):
        """
        Genera el mensaje de bienvenida personalizado con el nombre del negocio.
        """
        nombre_negocio = self.config.data.get("nombre_negocio", "nuestro negocio")
        return self.config.data["mensajes"]["mensaje_bienvenida"].format(nombre_negocio=nombre_negocio)




