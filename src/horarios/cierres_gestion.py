# src/horarios/cierres_gestion.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.horarios.data_loader import DataLoader
from src.sesiones.session_manager import SessionManager
from src.registro.validadores import Validadores
from datetime import datetime


class CierresGestion(Validadores):
    """
    Gestiona el flujo completo de cierres eventuales.
    Responsabilidades:
        - Listar cierres activos y futuros
        - Agregar cierre con validacion (desde, hasta, motivo)
        - Eliminar cierre
        - Confirmadores opcionales configurables desde datos.json
    """

    def __init__(self, numero, data_path=None):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.datos = DataLoader(data_path) if data_path else DataLoader()
        self.session_manager = SessionManager()
        self._callback_volver = None

    def set_callback_volver(self, callback):
        """Define la funcion callback para volver al menu anterior."""
        self._callback_volver = callback

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "staff_campo_actual", None)
        return campo is not None and campo.startswith("cierre_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el listado de cierres."""
        sesiones[self.numero].staff_campo_actual = "cierre_menu"
        sesiones[self.numero].staff_reintentos = 0
        sesiones[self.numero].staff_dato_temporal = None
        self.sw.enviar(self._armar_menu_cierres())

    def procesar(self, comando, sesiones):
        """Dispatcher interno segun estado actual."""
        campo = getattr(sesiones[self.numero], "staff_campo_actual", None)

        if campo == "cierre_menu":
            self._procesar_seleccion_cierre(comando, sesiones)
        elif campo == "cierre_agregar_desde":
            self._procesar_fecha_desde(comando, sesiones)
        elif campo == "cierre_agregar_hasta":
            self._procesar_fecha_hasta(comando, sesiones)
        elif campo == "cierre_agregar_motivo":
            self._procesar_motivo(comando, sesiones)
        elif campo == "cierre_confirmar_ingreso":
            self._procesar_confirmacion_ingreso(comando, sesiones)
        elif campo == "cierre_confirmar_elimina":
            self._procesar_confirmacion_elimina(comando, sesiones)

    # ── MENU DE CIERRES ───────────────────────────────────────────────────────

    def _armar_menu_cierres(self):
        cierres = self._get_cierres_activos()

        if not cierres:
            return (
                "No hay cierres eventuales programados.\n"
                "Ingresa *nuevo* para agregar uno\n"
                "o *cancelar* para volver:"
            )

        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"
        }

        lineas = ["*Cierres eventuales:*\n"]
        for i, c in enumerate(cierres, 1):
            desde = datetime.strptime(c["desde"], "%Y-%m-%d")
            hasta = datetime.strptime(c["hasta"], "%Y-%m-%d")
            dia_desde = dias_es[desde.strftime('%A')]
            dia_hasta = dias_es[hasta.strftime('%A')]
            lineas.append(
                f"{i}. {desde.strftime('%d/%m/%Y')} ({dia_desde}) -> "
                f"{hasta.strftime('%d/%m/%Y')} ({dia_hasta}) | {c['motivo']}"
            )

        lineas.append("\nIngresa el numero para eliminar un cierre,")
        lineas.append("*nuevo* para agregar uno nuevo")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    def _get_cierres_activos(self):
        """Retorna cierres donde hasta >= hoy, ordenados por fecha de inicio."""
        hoy = datetime.now().date()
        cierres = self.datos.data.get("cierres_eventuales", {}).get("datos", [])
        activos = [
            c for c in cierres
            if datetime.strptime(c["hasta"], "%Y-%m-%d").date() >= hoy
        ]
        return sorted(activos, key=lambda x: x["desde"])

    # ── SELECCION ─────────────────────────────────────────────────────────────

    def _procesar_seleccion_cierre(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            self._volver_menu_anterior(sesiones)
            return

        if comando.strip().lower() == "nuevo":
            sesiones[self.numero].staff_campo_actual = "cierre_agregar_desde"
            sesiones[self.numero].staff_reintentos = 0
            sesiones[self.numero].staff_dato_temporal = {}
            self.sw.enviar("Ingresa la fecha de *inicio* del cierre (DD/MM/AAAA):")
            return

        activos = self._get_cierres_activos()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(activos):
                raise ValueError
        except ValueError:
            self.sw.enviar("Opcion no valida.")
            return

        sesiones[self.numero].staff_dato_temporal = activos[indice]

        confirma = self.datos.data.get("cierres_eventuales", {}).get("confirma_elimina", False)
        if confirma:
            c = activos[indice]
            desde = datetime.strptime(c["desde"], "%Y-%m-%d").strftime("%d/%m/%Y")
            hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").strftime("%d/%m/%Y")
            sesiones[self.numero].staff_campo_actual = "cierre_confirmar_elimina"
            self.sw.enviar(
                f"Confirmas que queres eliminar el cierre del "
                f"*{desde}* al *{hasta}* por {c['motivo']}?\n"
                f"Responde *si* o *no*:"
            )
        else:
            self._eliminar_cierre(activos[indice], sesiones)

    # ── AGREGAR ───────────────────────────────────────────────────────────────

    def _procesar_fecha_desde(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_reintentos = 0
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("Carga cancelada.")
            self.iniciar(sesiones)
            return

        validadores = self.datos.data.get("cierres_eventuales", {}).get("validadores_desde", [])
        config_v = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("fecha", comando, validadores, config_v)

        if resultado is True:
            fecha_iso = datetime.strptime(comando.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            sesiones[self.numero].staff_dato_temporal = {"desde": fecha_iso}
            sesiones[self.numero].staff_campo_actual = "cierre_agregar_hasta"
            sesiones[self.numero].staff_reintentos = 0
            self.sw.enviar("Ingresa la fecha de *fin* del cierre (DD/MM/AAAA):")
        else:
            reintentos += 1
            sesiones[self.numero].staff_reintentos = reintentos
            if reintentos >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                sesiones[self.numero].staff_dato_temporal = None
                self.sw.enviar("Se cancelo la carga. Volviendo al menu de cierres...")
                self.iniciar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else "Fecha invalida. Intenta nuevamente:"
                self.sw.enviar(msj)

    def _procesar_fecha_hasta(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_reintentos = 0
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("Carga cancelada.")
            self.iniciar(sesiones)
            return

        validadores = self.datos.data.get("cierres_eventuales", {}).get("validadores_hasta", [])
        config_v = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("fecha", comando, validadores, config_v)

        if resultado is True:
            fecha_iso = datetime.strptime(comando.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            desde_iso = sesiones[self.numero].staff_dato_temporal.get("desde")

            # Validacion: hasta >= desde
            if fecha_iso < desde_iso:
                reintentos += 1
                sesiones[self.numero].staff_reintentos = reintentos
                if reintentos >= reintentos_max:
                    sesiones[self.numero].staff_campo_actual = None
                    sesiones[self.numero].staff_reintentos = 0
                    sesiones[self.numero].staff_dato_temporal = None
                    self.sw.enviar("Se cancelo la carga. Volviendo al menu de cierres...")
                    self.iniciar(sesiones)
                else:
                    self.sw.enviar("La fecha de fin no puede ser anterior a la de inicio. Intenta nuevamente:")
                return
            
            # Verificamos duplicado exacto de fechas
            existentes = self.datos.data["cierres_eventuales"]["datos"]
            for c in existentes:
                if c["desde"] == desde_iso and c["hasta"] == fecha_iso:
                    self.sw.enviar(
                        f"Ya existe un cierre para ese periodo. "
                        f"No se puede registrar el mismo rango de fechas dos veces."
                    )
                    sesiones[self.numero].staff_campo_actual = None
                    sesiones[self.numero].staff_reintentos = 0
                    sesiones[self.numero].staff_dato_temporal = None
                    self.iniciar(sesiones)
                    return     

            sesiones[self.numero].staff_dato_temporal["hasta"] = fecha_iso
            sesiones[self.numero].staff_campo_actual = "cierre_agregar_motivo"
            sesiones[self.numero].staff_reintentos = 0
            self.sw.enviar("Ingresa el *motivo* del cierre (ej: Vacaciones, Reformas):")
        else:
            reintentos += 1
            sesiones[self.numero].staff_reintentos = reintentos
            if reintentos >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                sesiones[self.numero].staff_dato_temporal = None
                self.sw.enviar("Se cancelo la carga. Volviendo al menu de cierres...")
                self.iniciar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else "Fecha invalida. Intenta nuevamente:"
                self.sw.enviar(msj)

    def _procesar_motivo(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_reintentos = 0
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("Carga cancelada.")
            self.iniciar(sesiones)
            return

        validadores = self.datos.data.get("cierres_eventuales", {}).get("validadores_motivo", [])
        config_v = self.config.data.get("validadores", {})
        reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
        reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0)

        resultado = self._validar("texto", comando, validadores, config_v)

        if resultado is True:
            sesiones[self.numero].staff_dato_temporal["motivo"] = comando.strip()
            datos = sesiones[self.numero].staff_dato_temporal

            desde = datetime.strptime(datos["desde"], "%Y-%m-%d")
            hasta = datetime.strptime(datos["hasta"], "%Y-%m-%d")
            dias = (hasta - desde).days + 1

            confirma = self.datos.data.get("cierres_eventuales", {}).get("confirma_ingreso", False)
            if confirma:
                sesiones[self.numero].staff_campo_actual = "cierre_confirmar_ingreso"
                sesiones[self.numero].staff_reintentos = 0
                self.sw.enviar(
                    f"Confirmas el siguiente cierre eventual?\n\n"
                    f"Desde: *{desde.strftime('%d/%m/%Y')}*\n"
                    f"Hasta: *{hasta.strftime('%d/%m/%Y')}* ({dias} {'dia' if dias == 1 else 'dias'})\n"
                    f"Motivo: *{datos['motivo']}*\n\n"
                    f"Responde *si* o *no*:"
                )
            else:
                self._guardar_cierre(datos, sesiones)
        else:
            reintentos += 1
            sesiones[self.numero].staff_reintentos = reintentos
            if reintentos >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                sesiones[self.numero].staff_dato_temporal = None
                self.sw.enviar("Se cancelo la carga. Volviendo al menu de cierres...")
                self.iniciar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else "Motivo invalido. Intenta nuevamente:"
                self.sw.enviar(msj)

    def _procesar_confirmacion_ingreso(self, comando, sesiones):
        if comando.strip() == "si":
            self._guardar_cierre(sesiones[self.numero].staff_dato_temporal, sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("Carga cancelada.")
            self.iniciar(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0) + 1
            sesiones[self.numero].staff_reintentos = reintentos
            reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
            if reintentos >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                sesiones[self.numero].staff_dato_temporal = None
                self.sw.enviar("Se cancelo la operacion.")
                self.iniciar(sesiones)
            else:
                self.sw.enviar("Responde *si* o *no*:")

    def _guardar_cierre(self, datos, sesiones):
        self.datos.data["cierres_eventuales"]["datos"].append({
            "desde": datos["desde"],
            "hasta": datos["hasta"],
            "motivo": datos["motivo"]
        })
        self.datos.guardar()

        desde = datetime.strptime(datos["desde"], "%Y-%m-%d").strftime("%d/%m/%Y")
        hasta = datetime.strptime(datos["hasta"], "%Y-%m-%d").strftime("%d/%m/%Y")

        sesiones[self.numero].staff_campo_actual = None
        sesiones[self.numero].staff_dato_temporal = None
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar(f"Cierre del *{desde}* al *{hasta}* registrado correctamente.")
        self.iniciar(sesiones)

    # ── ELIMINAR ──────────────────────────────────────────────────────────────

    def _procesar_confirmacion_elimina(self, comando, sesiones):
        if comando.strip() == "si":
            self._eliminar_cierre(sesiones[self.numero].staff_dato_temporal, sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].staff_campo_actual = None
            sesiones[self.numero].staff_dato_temporal = None
            self.sw.enviar("Eliminacion cancelada.")
            self.iniciar(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "staff_reintentos", 0) + 1
            sesiones[self.numero].staff_reintentos = reintentos
            reintentos_max = self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)
            if reintentos >= reintentos_max:
                sesiones[self.numero].staff_campo_actual = None
                sesiones[self.numero].staff_reintentos = 0
                sesiones[self.numero].staff_dato_temporal = None
                self.sw.enviar("Se cancelo la operacion.")
                self.iniciar(sesiones)
            else:
                self.sw.enviar("Responde *si* o *no*:")

    def _eliminar_cierre(self, cierre, sesiones):
        datos = self.datos.data["cierres_eventuales"]["datos"]
        if cierre in datos:
            datos.remove(cierre)
            self.datos.guardar()

        desde = datetime.strptime(cierre["desde"], "%Y-%m-%d").strftime("%d/%m/%Y")
        hasta = datetime.strptime(cierre["hasta"], "%Y-%m-%d").strftime("%d/%m/%Y")

        sesiones[self.numero].staff_campo_actual = None
        sesiones[self.numero].staff_dato_temporal = None
        sesiones[self.numero].staff_reintentos = 0
        self.sw.enviar(f"Cierre del *{desde}* al *{hasta}* eliminado correctamente.")
        self.iniciar(sesiones)

    # ── HELPER ────────────────────────────────────────────────────────────────

    def _volver_menu_anterior(self, sesiones):
        """Vuelve al menu anterior usando el callback configurado."""
        if self._callback_volver:
            self._callback_volver(sesiones)
        else:
            rol = self.session_manager.get_rol(self.numero)
            submenu_data = self.config.get_submenu("staff")
            self.sw.enviar(self.config.armar_menu(submenu_data, rol))
