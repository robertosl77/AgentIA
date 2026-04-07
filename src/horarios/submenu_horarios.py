# src/horarios/submenu_horarios.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.horarios.data_loader import DataLoader
from src.sesiones.session_manager import SessionManager
from datetime import datetime, timedelta

class SubMenuHorarios:
    """Submenú de Horarios"""

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.datos = DataLoader()
        self.session_manager = SessionManager()

    def mostrar_submenu(self, sesiones):
        submenu = getattr(sesiones[self.numero], "submenu", None)
        if submenu is None:
            sesiones[self.numero].submenu = -1
            self.submenu_binevenida()
            return
        else:
            self.submenu_horarios(submenu)

    def submenu_binevenida(self):
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("horarios")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))

    def submenu_horarios(self, comando):
        print("📅 Entrando al submódulo de Horarios...")
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("horarios")
        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return
        handler_nombre = opcion.get("handler")
        if handler_nombre:
            handler = getattr(self, handler_nombre, None)
            if handler:
                self.sw.enviar(handler())
            else:
                self.sw.enviar(f"❌ Handler '{handler_nombre}' no encontrado.")

    def submenu_horarios_fijos(self):
        horarios = self.datos.data.get("horarios_fijos", {}).get("dias", {})
        if not horarios:
            return "No hay horarios configurados actualmente."

        lineas = ["🕒 *Nuestros Horarios de Atención:*"]
        orden_dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        for dia in orden_dias:
            config = horarios.get(dia)
            if not config:
                continue
            nombre_dia = dia.capitalize()
            if config.get("abierto"):
                lineas.append(f"✅ {nombre_dia}: {config.get('apertura')} a {config.get('cierre')} hs")
            else:
                lineas.append(f"❌ {nombre_dia}: Cerrado")
        return "\n".join(lineas)

    def submenu_dias_de_guardia(self):
        guardias = self.datos.data.get("dias_de_guardia", {}).get("fechas", [])
        if not guardias:
            return "No hay días de guardia programados."

        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        hoy = datetime.now().date()
        proximas = sorted([
            datetime.strptime(f, "%Y-%m-%d").date()
            for f in guardias
            if datetime.strptime(f, "%Y-%m-%d").date() >= hoy
        ])

        if not proximas:
            return "No hay guardias programadas para los próximos días."

        lineas = ["🏥 *Próximos Días de Guardia:*"]
        for fecha in proximas:
            dia_semana = dias_es[fecha.strftime('%A')]
            lineas.append(f"🔹 {fecha.strftime('%d/%m/%Y')} ({dia_semana})")
        return "\n".join(lineas)

    def submenu_cierres_eventuales(self):
        cierres = self.datos.data.get("cierres_eventuales", {}).get("datos", [])
        if not cierres:
            return "No hay cierres eventuales programados."

        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        hoy = datetime.now().date()
        eventos_vigentes = []

        for c in cierres:
            try:
                f_desde = datetime.strptime(c["desde"], "%Y-%m-%d").date()
                f_hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").date()
                if f_hasta < hoy:
                    continue
                eventos_vigentes.append({
                    "desde": f_desde,
                    "hasta": f_hasta,
                    "motivo": c.get("motivo", "No especificado")
                })
            except (ValueError, KeyError):
                continue

        if not eventos_vigentes:
            return "No hay cierres eventuales activos ni programados."

        eventos_vigentes.sort(key=lambda x: x["desde"])
        lineas = ["⚠️ *Información de Cierres Eventuales:*"]

        for ev in eventos_vigentes:
            d_nom = dias_es[ev["desde"].strftime('%A')]
            h_nom = dias_es[ev["hasta"].strftime('%A')]
            f_desde_str = f"{ev['desde'].strftime('%d/%m/%Y')} ({d_nom})"
            f_hasta_str = f"{ev['hasta'].strftime('%d/%m/%Y')} ({h_nom})"
            estado = "🚫 *CERRADO ACTUALMENTE*" if ev["desde"] <= hoy <= ev["hasta"] else "📅 *Próximo Cierre*"
            bloque = (
                f"\n{estado}\n"
                f"🗓️ Desde: {f_desde_str}\n"
                f"🗓️ Hasta: {f_hasta_str}\n"
                f"📝 Motivo: {ev['motivo']}\n"
            )
            lineas.append(bloque)
        return "\n".join(lineas)

    def mensaje_proximas_guardias(self):
        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        meses_es = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        hoy = datetime.now().date()
        en_7_dias = hoy + timedelta(days=7)
        guardias = self.datos.data.get("dias_de_guardia", {}).get("fechas", [])
        proximas = sorted([
            datetime.strptime(f, "%Y-%m-%d").date()
            for f in guardias
            if hoy < datetime.strptime(f, "%Y-%m-%d").date() <= en_7_dias
        ])

        if not proximas:
            return None

        fecha = proximas[0]
        dia_semana = dias_es[fecha.strftime('%A')]
        mes = meses_es[fecha.month]
        return f"💊 Recordá que nuestra próxima guardia es el *{dia_semana} {fecha.day} de {mes}*."

    def mensaje_proximo_evento(self):
        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        meses_es = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }

        def formato_fecha(fecha):
            return f"{dias_es[fecha.strftime('%A')]} {fecha.day} de {meses_es[fecha.month]}"

        hoy = datetime.now().date()
        cierres = self.datos.data.get("cierres_eventuales", {}).get("datos", [])
        vigentes = []

        for c in cierres:
            try:
                f_desde = datetime.strptime(c["desde"], "%Y-%m-%d").date()
                f_hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").date()
                if f_hasta >= hoy:
                    vigentes.append({"desde": f_desde, "hasta": f_hasta, "motivo": c.get("motivo", "No especificado")})
            except (ValueError, KeyError):
                continue

        if not vigentes:
            return None

        vigentes.sort(key=lambda x: x["desde"])
        ev = vigentes[0]
        desde, hasta, motivo = ev["desde"], ev["hasta"], ev["motivo"]

        if desde == hasta:
            if desde == hoy:
                return f"⚠️ Te avisamos que *el día de hoy* no atendemos por: {motivo}."
            else:
                return f"⚠️ Te avisamos que el *{formato_fecha(desde)}* no atendemos por: {motivo}."

        if desde <= hoy <= hasta:
            return f"⚠️ Te avisamos que *desde hoy hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."
        else:
            return f"⚠️ Te avisamos que *a partir del {formato_fecha(desde)} hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."

    def estado_actual(self):
        ahora = datetime.now()
        hoy = ahora.date()
        hora_actual = ahora.time()
        traduccion = {
            "monday": "lunes", "tuesday": "martes", "wednesday": "miercoles",
            "thursday": "jueves", "friday": "viernes", "saturday": "sabado", "sunday": "domingo"
        }
        dia_json = traduccion[ahora.strftime('%A').lower()]

        for c in self.datos.data.get("cierres_eventuales", {}).get("datos", []):
            f_desde = datetime.strptime(c["desde"], "%Y-%m-%d").date()
            f_hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").date()
            if f_desde <= hoy <= f_hasta:
                return f"🚫 *Cerrado*: {c.get('motivo', 'Cierre eventual')}."

        guardias = self.datos.data.get("dias_de_guardia", {}).get("fechas", [])
        if hoy.strftime("%Y-%m-%d") in guardias:
            return "✅ *Abierto*: Hoy estamos de Guardia."

        config = self.datos.data.get("horarios_fijos", {}).get("dias", {}).get(dia_json, {})
        if config.get("abierto"):
            ap = datetime.strptime(config["apertura"], "%H:%M").time()
            ci = datetime.strptime(config["cierre"], "%H:%M").time()
            if ap <= hora_actual <= ci:
                return f"✅ *Abierto*: Atendemos hasta las {config['cierre']} hs."
            else:
                return f"🚫 *Cerrado*: Abrimos a las {config['apertura']} hs."

        return "🚫 *Cerrado*: Hoy no abrimos al público."

    def tiene_acceso(self):
        rol = self.session_manager.get_rol(self.numero)
        if rol != "usuario":
            return True
        bloquea_por_horario = self.config.data.get("configuracion_bot", {}).get("bloquear_fuera_de_horario", False)
        if not bloquea_por_horario:
            return True
        return "🚫" not in self.estado_actual()