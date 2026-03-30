from send_wpp import SendWPP
from submenu_horarios import SubMenuHorarios
from config_loader import ConfigLoader

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
            self.gestionar_bloqueo()
        else:
            self.loop_principal()

    def gestionar_bloqueo(self):
        """Módulo portero: solo sale de aquí si escribe 'horarios'."""
        comando = input("\n[Bloqueo] >> ").strip().lower()
        if comando == "horarios":
            # Vamos al submenú y al volver, re-evaluamos TODO
            from submenu_horarios import SubMenuHorarios
            SubMenuHorarios(self.numero).submenu_horarios()
            
            # ¡IMPORTANTE! Al salir del submenú, llamamos de nuevo a iniciar()
            # para que vuelva a chequear el horario y lo bloquee otra vez.
            self.iniciar() 
        else:
            print("Sesión cerrada por bloqueo de horario.")

    def loop_principal(self):
        while True:
            comando = input("\n>> ").strip().lower()
            if comando == "salir": break
            
            # Ejecución de opciones...
            self.procesar_comando(comando)

    def procesar_comando(self, comando):
        """Modularizamos las acciones para no repetir self.mostrar_menu()"""
        if comando == "1":
            SubMenuHorarios(self.numero).submenu_horarios()
            
        elif comando == "2":
            self.sw.enviar("Próximamente...")
        else:
            self.sw.enviar("❌ Opción no válida.")
        
        self.mostrar_menu()