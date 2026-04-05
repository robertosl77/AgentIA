# src/staff/submenu_staff.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.data_loader import DataLoader
from src.session_manager import SessionManager
from src.registro.validadores import Validadores
from datetime import datetime

class SubMenuStaff(Validadores):
    """
    Submenú de Staff.
    Responsabilidades:
        - Gestionar el flujo de opciones del panel de staff
        - Carga y eliminación de fechas de guardia con validación
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.datos = DataLoader()
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

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en medio de un flujo de staff."""
        return getattr(sesiones[self.numero], "staff_campo_actual", None) is not None

    def procesar_flujo(self, comando, sesiones):
        """Dispatcher principal según el estado actual del flujo."""
        campo = getattr(sesiones[self.numero], "staff_campo_actual", None)

        if campo == "guardia_menu":
            self._procesar_seleccion_guardia(comando, sesiones)
        elif campo == "guardia_agregar":
            self._procesar_fecha_guardia(comando, sesiones)
        elif campo == "guardia_confirmar_ingreso":
            self._procesar_confirmacion_ingreso(comando, sesiones)
        elif campo == "guardia_confirmar_elimina":
            self._procesar_confirmacion_elimina(comando, sesiones)

    # ── GESTIONAR GUARDIAS ────────────────────────────────────────────────────

    def gestionar_guardias(self, sesiones):
        """Muestra el listado de guardias futuras y espera una selección."""
        sesiones[self.numero].staff_campo_actual = "guardia_menu"
        sesiones[self.numero].staff_reintentos = 0
        sesiones[self.numero].staff_dato_temporal = None
        self.sw.enviar(self._armar_menu_guardias())

    def _armar_menu_guardias(self):
        """Arma el texto del listado de guardias futuras."""
        fechas = self._get_guardias_futuras()

        if not fechas:
            return (
                "No hay guardias programadas.\n"
                "Ingresá *0* para agregar una:"
            )

        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }

        lineas = ["📅 *Guardias programadas:*\n"]
        for i, fecha in enumerate(fechas, 1):
            f_obj = datetime.strptime(fecha, "%Y-%m-%d")
            dia = dias_es[f_obj.strftime('%A')]
            lineas.append(f"{i}. {f_obj.strftime('%d/%m/%Y')} ({dia})")

        lineas.append("\nIngresá el número para eliminar una guardia,")
        lineas.append("*nuevo* para agregar una nueva")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    def _get_guardias_futuras(self):
        hoy = datetime.now().date()
        fechas = self.datos.data.get("dias_de_guardia", {}).get("fechas", [])
        futuras = [f for f in fechas if datetime.strptime(f, "%Y-%m-%d").date() > hoy]
        return sorted(futuras)

    def _procesar_seleccion_guardia(self, comando, sesiones):
        """Procesa la selección del usuario en el menú de guardias."""
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            self._volver_menu_staff(sesiones)
            return

        if comando.strip().lower() == "nuevo":
            # Agregar nueva guardia
            sesiones[self.numero].staff_campo_actual = "guardia_agregar"
            sesiones[self.numero].staff_reintentos = 0
            self.sw.enviar("📅 Ingresá la fecha de la guardia (DD/MM/AAAA):")
            return

        # Eliminar guardia
        futuras = self._get_guardias_futuras()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(futuras):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        fecha_elegida = futuras[indice]
        sesiones[self.numero].staff_dato_temporal = fecha_elegida

        confirma = self.datos.data.get("dias_de_guardia", {}).get("confirma_elimina", False)
        if confirma:
            f_obj = datetime.strptime(fecha_elegida, "%Y-%m-%d")
            sesiones[self.numero].staff_campo_actual = "guardia_confirmar_elimina"
            self.sw.enviar(
                f"¿Confirmás que querés eliminar la guardia del "
                f"*{f_obj.strftime('%d/%m/%Y')}*?\n"
                f"Respondé *si* o *no*:"
            )
        else:
            self._eliminar_guardia(fecha_elegida, sesiones)

    def _procesar_confirmacion_elimina(self, comando, sesiones):
        """Procesa la confirmación de eliminación."""
        if comando.strip() == "si":
            fecha = getattr(sesiones[self.numero], "staff_dato_temporal", None)
            self._eliminar_guardia(fecha, sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("❌ Eliminación cancelada.")
            self.gestionar_guardias(sesiones)
        else:
            self.sw.enviar("⚠️ Respondé *si* o *no*:")

    def _eliminar_guardia(self, fecha_iso, sesiones):
        """Elimina la guardia del JSON y vuelve al menú."""
        fechas = self.datos.data["dias_de_guardia"]["fechas"]
        if fecha_iso in fechas:
            fechas.remove(fecha_iso)
            self._guardar_config()

        f_obj = datetime.strptime(fecha_iso, "%Y-%m-%d")
        sesiones[self.numero].staff_campo_actual = None
        sesiones[self.numero].staff_dato_temporal = None
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar(f"✅ Guardia del *{f_obj.strftime('%d/%m/%Y')}* eliminada correctamente.")
        self.gestionar_guardias(sesiones)

    # ── AGREGAR GUARDIA ───────────────────────────────────────────────────────

    def _procesar_fecha_guardia(self, comando, sesiones):
        """Valida y guarda la fecha de guardia."""
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_reintentos = 0
            self.sw.enviar("❌ Carga cancelada.")
            self.gestionar_guardias(sesiones)
            return

        validadores_campo = self.datos.data.get("dias_de_guardia", {}).get("validadores", [])
        config_validadores = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos_actuales = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("fecha", comando, validadores_campo, config_validadores)

        if resultado is True:
            fecha_obj = datetime.strptime(comando.strip(), "%d/%m/%Y")
            fecha_iso = fecha_obj.strftime("%Y-%m-%d")

            confirma = self.datos.data.get("dias_de_guardia", {}).get("confirma_ingreso", False)
            if confirma:
                sesiones[self.numero].staff_dato_temporal = fecha_iso
                sesiones[self.numero].staff_campo_actual = "guardia_confirmar_ingreso"
                self.sw.enviar(
                    f"¿Confirmás que querés agregar la guardia del "
                    f"*{comando.strip()}*?\n"
                    f"Respondé *si* o *no*:"
                )
            else:
                self._guardar_guardia(fecha_iso, comando.strip(), sesiones)
        else:
            reintentos_actuales += 1
            sesiones[self.numero].staff_reintentos = reintentos_actuales

            if reintentos_actuales >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                self.sw.enviar("❌ Se canceló la carga. Volviendo al menú de guardias...")
                self.gestionar_guardias(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else "⚠️ Fecha inválida. Intentá nuevamente:"
                self.sw.enviar(msj)

    def _procesar_confirmacion_ingreso(self, comando, sesiones):
        """Procesa la confirmación de ingreso."""
        if comando.strip() == "si":
            fecha_iso = getattr(sesiones[self.numero], "staff_dato_temporal", None)
            f_obj = datetime.strptime(fecha_iso, "%Y-%m-%d")
            self._guardar_guardia(fecha_iso, f_obj.strftime("%d/%m/%Y"), sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("❌ Carga cancelada.")
            self.gestionar_guardias(sesiones)
        else:
            self.sw.enviar("⚠️ Respondé *si* o *no*:")

    def _guardar_guardia(self, fecha_iso, fecha_display, sesiones):
        """Guarda la guardia en el JSON y vuelve al menú."""
        self.datos.data["dias_de_guardia"]["fechas"].append(fecha_iso)
        self._guardar_config()
        sesiones[self.numero].staff_campo_actual = None
        sesiones[self.numero].staff_dato_temporal = None
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar(f"✅ Guardia del *{fecha_display}* registrada correctamente.")
        self.gestionar_guardias(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _volver_menu_staff(self, sesiones):
        """Muestra el menú de staff."""
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))

    def _guardar_config(self):
        """Persiste datos.json con los cambios."""
        self.datos.guardar()

    def agregar_guardia(self, sesiones):
        """Handler legacy — redirige a gestionar_guardias."""
        self.gestionar_guardias(sesiones)

    def registrar_cierre_eventual(self):
        """[INTERFAZ] Registra un cierre eventual en el JSON."""
        pass

    def editar_horarios_fijos(self):
        """[INTERFAZ] Edita los horarios fijos en el JSON."""
        pass