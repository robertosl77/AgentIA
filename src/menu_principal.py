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

    def iniciar(self):
        print("🤖 Menu Principal iniciado")
        
        # El primer intento de mostrar_menu nos dice si estamos bloqueados
        if not self.mostrar_menu():
            return
        else:
            return

    def gestionar_bloqueo(self, comando):
        """Módulo portero: solo sale de aquí si escribe 'horarios'."""
        comando = comando.strip().lower()
        if comando == "horarios":
            from src.submenu_horarios import SubMenuHorarios
            SubMenuHorarios(self.numero).mostrar_menu()
        else:
            self.sw.enviar("Sesión cerrada por bloqueo de horario.")

    def loop_principal(self):
        return

    def procesar_comando(self, comando):
        comando = comando.strip().lower()

        if comando == "1":
            SubMenuHorarios(self.numero).mostrar_menu()
                
        elif comando in ["1", "2", "3", "salir"]:
            SubMenuHorarios(self.numero).submenu_horarios(comando)

        elif comando == "2":
            self.sw.enviar("Próximamente...")

        elif comando == "horarios":
            SubMenuHorarios(self.numero).mostrar_menu()

        else:
            self.sw.enviar("❌ Opción no válida.")
            
        self.mostrar_menu()