# src/staff/submenu_staff.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.session_manager import SessionManager
from src.registro.validadores import Validadores
from datetime import datetime

class SubMenuStaff(Validadores):
    """
    Submenú de Staff.
    Responsabilidades:
        - Gestionar el flujo de opciones del panel de staff
        - Carga de fechas de guardia con validación
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()

    def submenu_staff(self, comando, sesiones):
        """Procesa el comando dentro del submenú de staff."""
        print("👤 Entrando al submódulo de Staff...")

        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")

        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        handler_nombre = opcion.get("handler")
        if handler_nombre:
            handler = getattr(self, handler_nombre, None)
            if handler:
                handler(sesiones)
            else:
                self.sw.enviar(f"❌ Handler '{handler_nombre}' no encontrado.")

    # ── FLUJO DE CARGA DE GUARDIA ─────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en medio de un flujo de staff."""
        return getattr(sesiones[self.numero], "staff_campo_actual", None) is not None

    def iniciar_carga_guardia(self, sesiones):
        print(f"🔍 sesiones keys: {list(sesiones.keys())}")
        print(f"🔍 self.numero: {self.numero}")
        sesiones[self.numero].staff_campo_actual = "guardia"
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar("📅 Ingresá la fecha de la guardia (DD/MM/AAAA):")

    def procesar_flujo(self, comando, sesiones):
        """Procesa la respuesta del usuario en el flujo de staff."""
        campo = getattr(sesiones[self.numero], "staff_campo_actual", None)
        if not campo:
            return

        if campo == "guardia":
            self._procesar_fecha_guardia(comando, sesiones)

    def _procesar_fecha_guardia(self, comando, sesiones):
        """Valida y guarda la fecha de guardia."""
        validadores_campo = self.config.data.get("dias_de_guardia", {}).get("validadores", [])
        config_validadores = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos_actuales = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("fecha", comando, validadores_campo, config_validadores)

        if resultado is True:
            fecha_obj = datetime.strptime(comando.strip(), "%d/%m/%Y")
            fecha_iso = fecha_obj.strftime("%Y-%m-%d")

            self.config.data["dias_de_guardia"]["fechas"].append(fecha_iso)
            self._guardar_config()

            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_reintentos = 0
            self.sw.enviar(f"✅ Guardia del {comando.strip()} registrada correctamente.")

            rol = self.session_manager.get_rol(self.numero)
            submenu_data = self.config.get_submenu("staff")
            self.sw.enviar(self.config.armar_menu(submenu_data, rol))
        else:
            reintentos_actuales += 1
            sesiones[self.numero].staff_reintentos = reintentos_actuales

            if reintentos_actuales >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                self.sw.enviar("❌ Se canceló la carga. Volviendo al menú de staff...")
                rol = self.session_manager.get_rol(self.numero)
                submenu_data = self.config.get_submenu("staff")
                self.sw.enviar(self.config.armar_menu(submenu_data, rol))
            else:
                msj = resultado if isinstance(resultado, str) else "⚠️ Fecha inválida. Intentá nuevamente:"
                self.sw.enviar(msj)

    def _guardar_config(self):
        """Persiste configuracion.json con los cambios."""
        import json
        with open(self.config.path, "w", encoding="utf-8") as f:
            json.dump(self.config.data, f, indent=2, ensure_ascii=False)

    def agregar_guardia(self, sesiones):
        """Inicia el flujo de carga de fecha de guardia."""
        self.iniciar_carga_guardia(sesiones)

    def registrar_cierre_eventual(self):
        """[INTERFAZ] Registra un cierre eventual en el JSON."""
        pass

    def editar_horarios_fijos(self):
        """[INTERFAZ] Edita los horarios fijos en el JSON."""
        pass