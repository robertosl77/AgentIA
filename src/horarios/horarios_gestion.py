# src/horarios/horarios_gestion.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.horarios.data_loader import DataLoader
from src.sesiones.session_manager import SessionManager
from datetime import datetime, timedelta


class HorariosGestion:
    """
    Servicio de consulta de horarios.
    Provee metodos de consulta para ser consumidos por cualquier enlatado.
    """

    def __init__(self, numero, data_path=None):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.datos = DataLoader(data_path) if data_path else DataLoader()
        self.session_manager = SessionManager()

    # ── CONSULTAS DE HORARIOS ─────────────────────────────────────────────────

    def consultar_horarios_fijos(self):
        """Retorna string con los horarios de atencion."""
        horarios = self.datos.data.get("horarios_fijos", {}).get("dias", {})
        if not horarios:
            return "No hay horarios configurados actualmente."

        lineas = ["*Nuestros Horarios de Atencion:*"]
        orden_dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        for dia in orden_dias:
            config = horarios.get(dia)
            if not config:
                continue
            nombre_dia = dia.capitalize()
            if config.get("abierto"):
                lineas.append(f"{nombre_dia}: {config.get('apertura')} a {config.get('cierre')} hs")
            else:
                lineas.append(f"{nombre_dia}: Cerrado")
        return "\n".join(lineas)

    def consultar_dias_de_guardia(self):
        """Retorna string con los proximos dias de guardia."""
        guardias = self.datos.data.get("dias_de_guardia", {}).get("fechas", [])
        if not guardias:
            return "No hay dias de guardia programados."

        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"
        }
        hoy = datetime.now().date()
        proximas = sorted([
            datetime.strptime(f, "%Y-%m-%d").date()
            for f in guardias
            if datetime.strptime(f, "%Y-%m-%d").date() >= hoy
        ])

        if not proximas:
            return "No hay guardias programadas para los proximos dias."

        lineas = ["*Proximos Dias de Guardia:*"]
        for fecha in proximas:
            dia_semana = dias_es[fecha.strftime('%A')]
            lineas.append(f"- {fecha.strftime('%d/%m/%Y')} ({dia_semana})")
        return "\n".join(lineas)

    def consultar_cierres_eventuales(self):
        """Retorna string con los cierres eventuales vigentes."""
        cierres = self.datos.data.get("cierres_eventuales", {}).get("datos", [])
        if not cierres:
            return "No hay cierres eventuales programados."

        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"
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
        lineas = ["*Informacion de Cierres Eventuales:*"]

        for ev in eventos_vigentes:
            d_nom = dias_es[ev["desde"].strftime('%A')]
            h_nom = dias_es[ev["hasta"].strftime('%A')]
            f_desde_str = f"{ev['desde'].strftime('%d/%m/%Y')} ({d_nom})"
            f_hasta_str = f"{ev['hasta'].strftime('%d/%m/%Y')} ({h_nom})"
            estado = "*CERRADO ACTUALMENTE*" if ev["desde"] <= hoy <= ev["hasta"] else "*Proximo Cierre*"
            bloque = (
                f"\n{estado}\n"
                f"Desde: {f_desde_str}\n"
                f"Hasta: {f_hasta_str}\n"
                f"Motivo: {ev['motivo']}\n"
            )
            lineas.append(bloque)
        return "\n".join(lineas)

    # ── MENSAJES EMERGENTES ───────────────────────────────────────────────────

    def mensaje_proximas_guardias(self):
        """Retorna mensaje de guardia proxima (7 dias) o None."""
        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"
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
        return f"Recorda que nuestra proxima guardia es el *{dia_semana} {fecha.day} de {mes}*."

    def mensaje_proximo_evento(self):
        """Retorna mensaje de cierre eventual proximo o None."""
        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"
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
                return f"Te avisamos que *el dia de hoy* no atendemos por: {motivo}."
            else:
                return f"Te avisamos que el *{formato_fecha(desde)}* no atendemos por: {motivo}."

        if desde <= hoy <= hasta:
            return f"Te avisamos que *desde hoy hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."
        else:
            return f"Te avisamos que *a partir del {formato_fecha(desde)} hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."

    # ── ESTADO Y ACCESO ───────────────────────────────────────────────────────

    def estado_actual(self):
        """Retorna el estado actual (abierto/cerrado) con motivo."""
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
                return f"*Cerrado*: {c.get('motivo', 'Cierre eventual')}."

        guardias = self.datos.data.get("dias_de_guardia", {}).get("fechas", [])
        if hoy.strftime("%Y-%m-%d") in guardias:
            return "*Abierto*: Hoy estamos de Guardia."

        config = self.datos.data.get("horarios_fijos", {}).get("dias", {}).get(dia_json, {})
        if config.get("abierto"):
            ap = datetime.strptime(config["apertura"], "%H:%M").time()
            ci = datetime.strptime(config["cierre"], "%H:%M").time()
            if ap <= hora_actual <= ci:
                return f"*Abierto*: Atendemos hasta las {config['cierre']} hs."
            else:
                return f"*Cerrado*: Abrimos a las {config['apertura']} hs."

        return "*Cerrado*: Hoy no abrimos al publico."

    def tiene_acceso(self):
        """Verifica si el usuario tiene acceso segun horario y rol."""
        rol = self.session_manager.get_rol(self.numero)
        if rol != "usuario":
            return True
        bloquea_por_horario = self.config.data.get("configuracion_bot", {}).get("bloquear_fuera_de_horario", False)
        if not bloquea_por_horario:
            return True
        return "*Cerrado*" not in self.estado_actual()
