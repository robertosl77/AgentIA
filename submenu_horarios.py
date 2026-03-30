from send_wpp import SendWPP
from config_loader import ConfigLoader

class SubMenuHorarios:
    """Submenú de Horarios"""

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()

    def mostrar_menu(self):
        mensaje = self.config.get_mensaje("mensajes", "submenu_horarios")
        self.sw.enviar(mensaje)

    def submenu_horarios(self):
        print("📅 Entrando al submódulo de Horarios...")
        self.mostrar_menu()

        while True:
            comando = input(">> ").strip().lower()

            if comando == "salir":
                self.sw.enviar("Volviendo al menú principal...")
                break

            elif comando == "1":
                # El config_loader hace todo el trabajo de formateo
                leyenda = self.config.horarios_fijos()
                self.sw.enviar(leyenda)                

            elif comando == "2":
                leyenda = self.config.dias_de_guardia()
                self.sw.enviar(leyenda)     

            elif comando == "3":
                leyenda = self.config.cierres_eventuales()
                self.sw.enviar(leyenda)

            else:
                self.sw.enviar("❌ Opción no válida.\n")
                self.mostrar_menu()