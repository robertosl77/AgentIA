# src/horarios/submenu_horarios.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.session_manager import SessionManager
from datetime import datetime, timedelta

class SubMenuHorarios:
    """Submenú de Horarios"""

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()

    # Administración del submenú de horarios
    def mostrar_submenu(self, sesiones):
        submenu = getattr(sesiones[self.numero], "submenu", None)

        if submenu is None:
            sesiones[self.numero].submenu = -1
            self.submenu_binevenida()
            return
        else:
            self.submenu_horarios(submenu)


    # Funciones para generar las leyendas de cada sección del submenú de horarios
    def submenu_binevenida(self):
        """Arma y envía el mensaje del submenú de horarios según el rol."""
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("horarios")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))

    def submenu_horarios(self, comando):
        """Procesa el comando dentro del submenú de horarios."""
        print("📅 Entrando al submódulo de Horarios...")

        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("horarios")

        # Validamos que el comando sea una activación válida para el rol
        opcion = self.config.resolver_activacion(comando, submenu_data, rol)
        if opcion is None:
            self.sw.enviar("❌ Opción no válida.")
            return

        # Obtenemos el nombre del método desde el JSON y lo ejecutamos dinámicamente
        handler_nombre = opcion.get("handler")
        if handler_nombre:
            handler = getattr(self, handler_nombre, None)
            if handler:
                self.sw.enviar(handler())
            else:
                self.sw.enviar(f"❌ Handler '{handler_nombre}' no encontrado.")

    def submenu_horarios_fijos(self):
        """Extrae los horarios del JSON y arma la leyenda para el usuario."""
        horarios = self.config.data.get("horarios_fijos", {})
        if not horarios:
            return "No hay horarios configurados actualmente."

        lineas = ["🕒 *Nuestros Horarios de Atención:*"]
        
        # Ordenamos los días para que no salgan al azar
        orden_dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        
        for dia in orden_dias:
            config = horarios.get(dia)
            if not config:
                continue
                
            nombre_dia = dia.capitalize()
            
            if config.get("abierto"):
                apertura = config.get("apertura")
                cierre = config.get("cierre")
                lineas.append(f"✅ {nombre_dia}: {apertura} a {cierre} hs")
            else:
                lineas.append(f"❌ {nombre_dia}: Cerrado")

        return "\n".join(lineas)

    def submenu_dias_de_guardia(self):
        """Filtra, ordena y formatea las guardias con el día de la semana."""
        guardias = self.config.data.get("dias_de_guardia", [])
        if not guardias:
            return "No hay días de guardia programados."

        # Diccionario para traducir el día de la semana
        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }

        hoy = datetime.now().date()
        proximas = []

        for f_str in guardias:
            try:
                f_obj = datetime.strptime(f_str, "%Y-%m-%d").date()
                if f_obj >= hoy:
                    proximas.append(f_obj)
            except ValueError:
                continue

        if not proximas:
            return "No hay guardias programadas para los próximos días."

        proximas.sort()

        lineas = ["🏥 *Próximos Días de Guardia:*"]
        for fecha in proximas:
            # Obtenemos el nombre del día en inglés y lo traducimos
            dia_semana = dias_es[fecha.strftime('%A')]
            # Formato: 29/03/2026 (Domingo)
            lineas.append(f"🔹 {fecha.strftime('%d/%m/%Y')} ({dia_semana})")

        return "\n".join(lineas)

    def submenu_cierres_eventuales(self):
        """Procesa, ordena y clasifica los cierres eventuales vigentes."""
        cierres = self.config.data.get("cierres_eventuales", [])
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
                
                # Validación de vigencia: si el cierre ya terminó, lo ignoramos
                if f_hasta < hoy:
                    continue
                
                # Guardamos los datos procesados para ordenar después
                eventos_vigentes.append({
                    "desde": f_desde,
                    "hasta": f_hasta,
                    "motivo": c.get("motivo", "No especificado")
                })
            except (ValueError, KeyError):
                continue

        if not eventos_vigentes:
            return "No hay cierres eventuales activos ni programados."

        # Ordenamos por la fecha de inicio
        eventos_vigentes.sort(key=lambda x: x["desde"])

        lineas = ["⚠️ *Información de Cierres Eventuales:*"]

        for ev in eventos_vigentes:
            d_nom = dias_es[ev["desde"].strftime('%A')]
            h_nom = dias_es[ev["hasta"].strftime('%A')]
            
            # Formateo de fechas
            f_desde_str = f"{ev['desde'].strftime('%d/%m/%Y')} ({d_nom})"
            f_hasta_str = f"{ev['hasta'].strftime('%d/%m/%Y')} ({h_nom})"

            # Lógica de estado (¿Es ahora o después?)
            if ev["desde"] <= hoy <= ev["hasta"]:
                estado = "🚫 *CERRADO ACTUALMENTE*"
            else:
                estado = "📅 *Próximo Cierre*"

            # Construcción del bloque de texto
            bloque = (
                f"\n{estado}\n"
                f"🗓️ Desde: {f_desde_str}\n"
                f"🗓️ Hasta: {f_hasta_str}\n"
                f"📝 Motivo: {ev['motivo']}\n"
            )
            lineas.append(bloque)

        return "\n".join(lineas)


    # Administracion de mensajes emergentes al primer contacto
    def mensaje_proximas_guardias(self):
        """
        Busca si hay una guardia en los próximos 7 días y genera una leyenda.
        Retorna el mensaje si encuentra una, o None si no hay ninguna próxima.
        """
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

        guardias = self.config.data.get("dias_de_guardia", [])
        proximas = []

        for f_str in guardias:
            try:
                f_obj = datetime.strptime(f_str, "%Y-%m-%d").date()
                # Solo guardias dentro de los próximos 7 días (sin incluir hoy)
                if hoy < f_obj <= en_7_dias:
                    proximas.append(f_obj)
            except ValueError:
                continue

        if not proximas:
            return None

        # Tomamos la más cercana
        proximas.sort()
        fecha = proximas[0]

        dia_semana = dias_es[fecha.strftime('%A')]
        mes = meses_es[fecha.month]

        return f"💊 Recordá que nuestra próxima guardia es el *{dia_semana} {fecha.day} de {mes}*."

    def mensaje_proximo_evento(self):
        """
        Busca el próximo cierre eventual vigente o próximo y genera una leyenda contextual.
        Retorna el mensaje si encuentra uno, o None si no hay ninguno próximo.
        Condiciones:
            - Fecha única (desde == hasta):
                * Si es hoy:         "recuerda que el día de hoy no atendemos por: xxx"
                * Si es desde mañana: "recuerda que el martes 3 de abril no atendemos por: xxx"
            - Rango de fechas (desde != hasta):
                * Si desde es hoy o hoy está dentro del rango: "recuerda que desde hoy hasta el martes 5 de abril no atendemos por: xxx"
                * Si desde es a partir de mañana:              "recuerda que a partir del miércoles 1 de abril hasta el jueves 5 de abril no atendemos por: xxx"
        """
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
            """Formatea una fecha como 'martes 5 de abril'"""
            dia_semana = dias_es[fecha.strftime('%A')]
            mes = meses_es[fecha.month]
            return f"{dia_semana} {fecha.day} de {mes}"

        hoy = datetime.now().date()
        cierres = self.config.data.get("cierres_eventuales", [])
        vigentes = []

        for c in cierres:
            try:
                f_desde = datetime.strptime(c["desde"], "%Y-%m-%d").date()
                f_hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").date()
                motivo = c.get("motivo", "No especificado")

                # Solo consideramos cierres que no hayan terminado
                if f_hasta >= hoy:
                    vigentes.append({
                        "desde": f_desde,
                        "hasta": f_hasta,
                        "motivo": motivo
                    })
            except (ValueError, KeyError):
                continue

        if not vigentes:
            return None

        # Tomamos el más próximo ordenando por fecha de inicio
        vigentes.sort(key=lambda x: x["desde"])
        ev = vigentes[0]

        desde = ev["desde"]
        hasta = ev["hasta"]
        motivo = ev["motivo"]

        # ── FECHA ÚNICA (desde == hasta) ──
        if desde == hasta:
            if desde == hoy:
                return f"⚠️ Te avisamos que *el día de hoy* no atendemos por: {motivo}."
            else:
                return f"⚠️ Te avisamos que el *{formato_fecha(desde)}* no atendemos por: {motivo}."

        # ── RANGO DE FECHAS (desde != hasta) ──
        if desde <= hoy <= hasta:
            # Hoy está dentro del rango
            return f"⚠️ Te avisamos que *desde hoy hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."
        else:
            # El cierre arranca a partir de mañana o más adelante
            return f"⚠️ Te avisamos que *a partir del {formato_fecha(desde)} hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."

    def estado_actual(self):
        """Determina si el negocio está abierto o cerrado JUSTO AHORA."""
        ahora = datetime.now()
        hoy = ahora.date()
        hora_actual = ahora.time()
        dia_semana = ahora.strftime('%A').lower() # ej: 'sunday'
        
        # Diccionario para traducir el día al formato de tu JSON
        traduccion = {
            "monday": "lunes", "tuesday": "martes", "wednesday": "miercoles",
            "thursday": "jueves", "friday": "viernes", "saturday": "sabado", "sunday": "domingo"
        }
        dia_json = traduccion[dia_semana]

        # 1. Prioridad 1: ¿Estamos en un cierre eventual hoy?
        for c in self.config.data.get("cierres_eventuales", []):
            f_desde = datetime.strptime(c["desde"], "%Y-%m-%d").date()
            f_hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").date()
            if f_desde <= hoy <= f_hasta:
                return f"🚫 *Cerrado*: {c.get('motivo', 'Cierre eventual')}."

        # 2. Prioridad 2: ¿Hoy es día de guardia? (Si es guardia, asumimos abierto 24hs o según lógica)
        if hoy.strftime("%Y-%m-%d") in self.config.data.get("dias_de_guardia", []):
            return "✅ *Abierto*: Hoy estamos de Guardia."

        # 3. Prioridad 3: Horarios fijos
        config = self.config.data.get("horarios_fijos", {}).get(dia_json, {})
        if config.get("abierto"):
            ap = datetime.strptime(config["apertura"], "%H:%M").time()
            ci = datetime.strptime(config["cierre"], "%H:%M").time()
            if ap <= hora_actual <= ci:
                return f"✅ *Abierto*: Atendemos hasta las {config['cierre']} hs."
            else:
                return f"🚫 *Cerrado*: Abrimos a las {config['apertura']} hs."
        
        return "🚫 *Cerrado*: Hoy no abrimos al público."    

    # Funcion para determinar si el usuario tiene acceso al menú principal o si debe ver el bloqueo por horario
    def tiene_acceso(self):
        """
        Determina si el usuario tiene acceso al menú principal.
        - Staff (rol != usuario): siempre True, sin importar el horario
        - Usuario común: True si el local está abierto, False si está cerrado
        """
        # El staff siempre tiene acceso
        rol = self.session_manager.get_rol(self.numero)
        if rol != "usuario":
            return True

        # Usuarios comunes: verificamos horario solo si el bloqueo está activo
        bloquea_por_horario = self.config.data.get("configuracion_bot", {}).get("bloquear_fuera_de_horario", False)
        if not bloquea_por_horario:
            return True

        # Si el bloqueo está activo y el local está cerrado, denegamos acceso
        estado_actual = self.estado_actual()
        return "🚫" not in estado_actual

