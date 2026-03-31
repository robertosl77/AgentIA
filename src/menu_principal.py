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

    def administro_menu(self, comando, sesiones):
        print("Numero: "+sesiones[self.numero].numero)

        # Si no existe 'menu' en la sesión, es porque es la primera vez que se llama a este método.
        menu = getattr(sesiones[self.numero], "menu", None)

        # Si no hay menú, lo asignamos y mostramos el menú inicial. Si lo hay, verificamos si es un comando de menú o submenú.
        if menu is None:
            sesiones[self.numero].menu = "principal"
            self.mostrar_menu()
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
            SubMenuHorarios(self.numero).mostrar_menu(sesiones)
                
        elif comando == "2":
            self.sw.enviar("Próximamente...")

        elif comando == "horarios":
            SubMenuHorarios(self.numero).mostrar_menu(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida.")

        # Si el comando es 'salir', volvemos al menú principal reseteando las variables de sesión.
        if getattr(sesiones[self.numero], "submenu", None) == "salir":
            sesiones[self.numero].menu = None
            sesiones[self.numero].submenu = None
            self.mostrar_menu()
                        
    def mostrar_menu(self):
        """
        Determina dinámicamente si muestra el menú o el bloqueo.
        Se ejecuta al inicio y cada vez que se vuelve de un submenú.
        """
        # 1. Pedimos al loader el diagnóstico actual
        mensaje, acceso_liberado = self.config.obtener_menu_inicial(self.numero)
        
        # 2. Enviamos lo que corresponda (Menú o Bloqueo)
        self.sw.enviar(mensaje)
        
        # 3. Retornamos el estado para que el 'iniciar' sepa si debe frenar
        return acceso_liberado

