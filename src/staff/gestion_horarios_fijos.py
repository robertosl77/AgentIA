# src/staff/gestion_horarios_fijos.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.horarios.data_loader import DataLoader
from src.session_manager import SessionManager
from src.registro.validadores import Validadores
from datetime import datetime

class GestionHorariosFijos(Validadores):
    """
    Gestiona el flujo completo de edición de horarios fijos.
    Responsabilidades:
        - Listar horarios actuales
        - Editar horario de un día específico
        - Edición masiva (todos los días / solo días hábiles)
        - Confirmador opcional configurable desde datos.json
    """

    ORDEN_DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    DIAS_HABILES = ["lunes", "martes", "miercoles", "jueves", "viernes"]
    DIAS_ES = {
        "lunes": "Lunes", "martes": "Martes", "miercoles": "Miércoles",
        "jueves": "Jueves", "viernes": "Viernes", "sabado": "Sábado", "domingo": "Domingo"
    }

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.datos = DataLoader()
        self.session_manager = SessionManager()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "staff_campo_actual", None)
        return campo is not None and campo.startswith("horario_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el listado de horarios."""
        sesiones[self.numero].staff_campo_actual = "horario_menu"
        sesiones[self.numero].staff_reintentos = 0
        sesiones[self.numero].staff_dato_temporal = {}
        self.sw.enviar(self._armar_menu_horarios())

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "staff_campo_actual", None)

        if campo == "horario_menu":
            self._procesar_seleccion_dia(comando, sesiones)
        elif campo == "horario_editar_apertura":
            self._procesar_apertura(comando, sesiones)
        elif campo == "horario_editar_cierre":
            self._procesar_cierre(comando, sesiones)
        elif campo == "horario_editar_abierto":
            self._procesar_abierto(comando, sesiones)
        elif campo == "horario_confirmar_edicion":
            self._procesar_confirmacion(comando, sesiones)

    # ── MENÚ DE HORARIOS ──────────────────────────────────────────────────────

    def _armar_menu_horarios(self):
        dias = self.datos.data.get("horarios_fijos", {}).get("dias", {})
        opciones_masivas = self.datos.data.get("horarios_fijos", {}).get("opciones_edicion_masiva", {})

        lineas = ["🕒 *Horarios de atención:*\n"]
        for i, dia in enumerate(self.ORDEN_DIAS, 1):
            config = dias.get(dia, {})
            nombre = self.DIAS_ES[dia]
            if config.get("abierto"):
                lineas.append(f"{i}. {nombre}: {config.get('apertura')} - {config.get('cierre')} ✅")
            else:
                lineas.append(f"{i}. {nombre}: Cerrado ❌")

        # Opciones de edición masiva
        num = len(self.ORDEN_DIAS) + 1
        if opciones_masivas.get("todos_los_dias"):
            lineas.append(f"{num}. Editar todos los días")
            num += 1
        if opciones_masivas.get("solo_dias_habiles"):
            lineas.append(f"{num}. Editar solo días hábiles")

        lineas.append("\nIngresá el número del día a editar")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    # ── SELECCIÓN DE DÍA ──────────────────────────────────────────────────────

    def _procesar_seleccion_dia(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            self._volver_menu_staff(sesiones)
            return

        opciones_masivas = self.datos.data.get("horarios_fijos", {}).get("opciones_edicion_masiva", {})
        tiene_todos = opciones_masivas.get("todos_los_dias", False)
        tiene_habiles = opciones_masivas.get("solo_dias_habiles", False)

        idx_todos = len(self.ORDEN_DIAS) + 1 if tiene_todos else None
        idx_habiles = idx_todos + 1 if (tiene_todos and tiene_habiles) else (len(self.ORDEN_DIAS) + 1 if tiene_habiles else None)

        try:
            opcion = int(comando.strip())
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        if 1 <= opcion <= len(self.ORDEN_DIAS):
            dia = self.ORDEN_DIAS[opcion - 1]
            sesiones[self.numero].staff_dato_temporal = {"dias": [dia]}
            self._iniciar_edicion_apertura(dia, sesiones)
        elif tiene_todos and opcion == idx_todos:
            sesiones[self.numero].staff_dato_temporal = {"dias": self.ORDEN_DIAS.copy()}
            self._iniciar_edicion_apertura("todos los días", sesiones)
        elif tiene_habiles and opcion == idx_habiles:
            sesiones[self.numero].staff_dato_temporal = {"dias": self.DIAS_HABILES.copy()}
            self._iniciar_edicion_apertura("días hábiles", sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    # ── EDICIÓN PASO A PASO ───────────────────────────────────────────────────

    def _iniciar_edicion_apertura(self, label, sesiones):
        dias = sesiones[self.numero].staff_dato_temporal.get("dias", [])
        dia_ref = dias[0]
        config_actual = self.datos.data["horarios_fijos"]["dias"].get(dia_ref, {})
        apertura_actual = config_actual.get("apertura", "--:--")

        sesiones[self.numero].staff_campo_actual = "horario_editar_apertura"
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar(
            f"Editando *{self.DIAS_ES.get(label, label)}*\n\n"
            f"⏰ Apertura actual: {apertura_actual}\n"
            f"Ingresá el nuevo horario de apertura (HH:MM):"
        )

    def _procesar_apertura(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        validadores = self.datos.data.get("horarios_fijos", {}).get("validadores", [])
        config_v = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("hora", comando, validadores, config_v)

        if resultado is True:
            sesiones[self.numero].staff_dato_temporal["apertura"] = datetime.strptime(comando.strip(), "%H:%M").strftime("%H:%M")
            sesiones[self.numero].staff_campo_actual = "horario_editar_cierre"
            sesiones[self.numero].staff_reintentos = 0

            dias = sesiones[self.numero].staff_dato_temporal.get("dias", [])
            dia_ref = dias[0]
            config_actual = self.datos.data["horarios_fijos"]["dias"].get(dia_ref, {})
            cierre_actual = config_actual.get("cierre", "--:--")

            self.sw.enviar(
                f"⏰ Cierre actual: {cierre_actual}\n"
                f"Ingresá el nuevo horario de cierre (HH:MM):"
            )
        else:
            reintentos += 1
            sesiones[self.numero].staff_reintentos = reintentos
            if reintentos >= reintentos_max:
                self._cancelar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else "⚠️ Horario inválido. Intentá nuevamente:"
                self.sw.enviar(msj)

    def _procesar_cierre(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        validadores = self.datos.data.get("horarios_fijos", {}).get("validadores", [])
        config_v = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("hora", comando, validadores, config_v)

        if resultado is True:
            apertura = sesiones[self.numero].staff_dato_temporal.get("apertura")
            # Validamos que cierre > apertura
            try:
                t_apertura = datetime.strptime(apertura, "%H:%M")
                t_cierre = datetime.strptime(comando.strip(), "%H:%M")
                if t_cierre <= t_apertura:
                    reintentos += 1
                    sesiones[self.numero].staff_reintentos = reintentos
                    if reintentos >= reintentos_max:
                        self._cancelar(sesiones)
                    else:
                        self.sw.enviar("⚠️ El horario de cierre debe ser posterior al de apertura. Intentá nuevamente:")
                    return
            except ValueError:
                pass

            sesiones[self.numero].staff_dato_temporal["cierre"] = datetime.strptime(comando.strip(), "%H:%M").strftime("%H:%M")
            sesiones[self.numero].staff_campo_actual = "horario_editar_abierto"
            sesiones[self.numero].staff_reintentos = 0

            dias = sesiones[self.numero].staff_dato_temporal.get("dias", [])
            dia_ref = dias[0]
            config_actual = self.datos.data["horarios_fijos"]["dias"].get(dia_ref, {})
            abierto_actual = "Abierto ✅" if config_actual.get("abierto") else "Cerrado ❌"

            self.sw.enviar(
                f"📋 Estado actual: {abierto_actual}\n"
                f"¿El día estará abierto? Respondé *si* o *no*:"
            )
        else:
            reintentos += 1
            sesiones[self.numero].staff_reintentos = reintentos
            if reintentos >= reintentos_max:
                self._cancelar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else "⚠️ Horario inválido. Intentá nuevamente:"
                self.sw.enviar(msj)

    def _procesar_abierto(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        if comando.strip() == "si":
            sesiones[self.numero].staff_dato_temporal["abierto"] = True
        elif comando.strip() == "no":
            sesiones[self.numero].staff_dato_temporal["abierto"] = False
        else:
            reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0) + 1
            sesiones[self.numero].staff_reintentos = reintentos
            reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
            if reintentos >= reintentos_max:
                self._cancelar(sesiones)
            else:
                self.sw.enviar("⚠️ Respondé *si* o *no*:")
            return

        datos = sesiones[self.numero].staff_dato_temporal
        confirma = self.datos.data.get("horarios_fijos", {}).get("confirma_edicion", False)

        if confirma:
            dias = datos.get("dias", [])
            if len(dias) == 1:
                label = self.DIAS_ES.get(dias[0], dias[0])
            elif dias == self.ORDEN_DIAS:
                label = "todos los días"
            else:
                label = "días hábiles"

            abierto_str = "Abierto ✅" if datos["abierto"] else "Cerrado ❌"
            sesiones[self.numero].staff_campo_actual = "horario_confirmar_edicion"
            sesiones[self.numero].staff_reintentos = 0
            self.sw.enviar(
                f"¿Confirmás los siguientes cambios para *{label}*?\n\n"
                f"⏰ Apertura: *{datos['apertura']}*\n"
                f"⏰ Cierre: *{datos['cierre']}*\n"
                f"📋 Estado: *{abierto_str}*\n\n"
                f"Respondé *si* o *no*:"
            )
        else:
            self._guardar_horario(datos, sesiones)

    def _procesar_confirmacion(self, comando, sesiones):
        if comando.strip() == "si":
            self._guardar_horario(sesiones[self.numero].staff_dato_temporal, sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_dato_temporal = {}
            self.sw.enviar("❌ Edición cancelada.")
            self.iniciar(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0) + 1
            sesiones[self.numero].staff_reintentos = reintentos
            reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
            if reintentos >= reintentos_max:
                self._cancelar(sesiones)
            else:
                self.sw.enviar("⚠️ Respondé *si* o *no*:")

    # ── GUARDAR ───────────────────────────────────────────────────────────────

    def _guardar_horario(self, datos, sesiones):
        dias = datos.get("dias", [])
        for dia in dias:
            self.datos.data["horarios_fijos"]["dias"][dia]["apertura"] = datos["apertura"]
            self.datos.data["horarios_fijos"]["dias"][dia]["cierre"] = datos["cierre"]
            self.datos.data["horarios_fijos"]["dias"][dia]["abierto"] = datos["abierto"]
        self.datos.guardar()

        if len(dias) == 1:
            label = self.DIAS_ES.get(dias[0], dias[0])
        elif dias == self.ORDEN_DIAS:
            label = "todos los días"
        else:
            label = "días hábiles"

        sesiones[self.numero].staff_campo_actual = None
        sesiones[self.numero].staff_dato_temporal = {}
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar(f"✅ Horario de *{label}* actualizado correctamente.")
        self.iniciar(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _cancelar(self, sesiones):
        sesiones[self.numero].staff_campo_actual = None
        sesiones[self.numero].staff_dato_temporal = {}
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar("❌ Edición cancelada.")
        self.iniciar(sesiones)

    def _volver_menu_staff(self, sesiones):
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))