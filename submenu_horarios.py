from send_wpp import SendWPP

class SubMenuHorarios:
    """Submenú de Horarios"""

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)

    def mostrar_menu(self):
        mensaje = """🕒 Módulo de Horarios

1. Consultar horario de atención
2. Ver próximos días de guardia
3. Ver cierres eventuales

Escribí el número o 'salir' para volver al menú principal:"""
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
                self.sw.enviar("🕒 Horario de atención normal:\nLunes a Viernes: 9:00 - 20:00\nSábados: 9:00 - 14:00")

            elif comando == "2":
                self.sw.enviar("🛡️ Próximos días de guardia:\n• Jueves 2 de abril - 24hs\n• Domingo 5 de abril - 24hs")

            elif comando == "3":
                self.sw.enviar("⚠️ No hay cierres eventuales programados por ahora.")

            else:
                self.sw.enviar("❌ Opción no válida.\n")
                self.mostrar_menu()   # Vuelve a mostrar el menú