from send_wpp import SendWPP
from submenu_horarios import SubMenuHorarios

class MenuPrincipal:
    """Menú Principal del Bot"""

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)

    def mostrar_menu(self):
        mensaje = """👋 ¡Hola!

Menú Principal:

1. Consultar Horarios
2. Otra opción (próximamente)

Escribí el número de la opción:"""
        self.sw.enviar(mensaje)

    def iniciar(self):
        print("🤖 Menu Principal iniciado")
        self.mostrar_menu()          # Muestra el menú al iniciar

        while True:
            comando = input("\n>> ").strip().lower()

            if comando == "salir":
                print("Bot detenido.")
                break

            elif comando == "1":
                mh = SubMenuHorarios(self.numero)
                mh.submenu_horarios()
                self.mostrar_menu()      # ← Ajuste: vuelve a mostrar el menú principal

            elif comando == "2":
                self.sw.enviar("Esta opción estará disponible pronto.")
                self.mostrar_menu()

            else:
                self.sw.enviar("❌ Opción no válida.")
                self.mostrar_menu()