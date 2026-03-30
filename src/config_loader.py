import json
import os
from datetime import datetime

class ConfigLoader:
    def __init__(self, path=r"data\configuracion.json"):
        self.path = path
        self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.path}")
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_mensaje(self, categoria, clave):
        seccion = self.data.get(categoria, {})
        texto = seccion.get(clave, "")
        if not isinstance(texto, str): return str(texto)
        return texto.format(**self.data)

    def obtener_rol(self, numero):
        """Devuelve el nombre del rol (root, administradores, supervisores) o 'usuario'."""
        roles_dict = self.data.get("roles", {})
        for rol, lista_numeros in roles_dict.items():
            if numero in lista_numeros:
                return rol
        return "usuario"

    def tiene_permiso(self, rol, propiedad_json):
        """Verifica en 'permisos_edicion' si el rol puede tocar esa propiedad."""
        permisos = self.data.get("permisos_edicion", {})
        roles_autorizados = permisos.get(propiedad_json, [])
        return rol in roles_autorizados

    # 
    def obtener_menu_inicial(self, numero):
        rol = self.obtener_rol(numero)
        if rol != "usuario":
            return self.get_mensaje("mensajes", "menu_principal_staff"), True

        # Si el JSON dice que bloquee y está cerrado:
        if self.data.get("configuracion_bot", {}).get("bloquear_fuera_de_horario") and "🚫" in self.estado_actual():
            msg = f"{self.estado_actual()}\n\nEscribí *'horarios'* para ver opciones."
            return msg, False
            
        return self.get_mensaje("mensajes", "menu_principal"), True

    # Funciones específicas para el módulo de horarios (extraen, ordenan y formatean la info del JSON)
    def horarios_fijos(self):
            """Extrae los horarios del JSON y arma la leyenda para el usuario."""
            horarios = self.data.get("horarios_fijos", {})
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
    
    def dias_de_guardia(self):
            """Filtra, ordena y formatea las guardias con el día de la semana."""
            guardias = self.data.get("dias_de_guardia", [])
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
    
    def cierres_eventuales(self):
            """Procesa, ordena y clasifica los cierres eventuales vigentes."""
            cierres = self.data.get("cierres_eventuales", [])
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
            for c in self.data.get("cierres_eventuales", []):
                f_desde = datetime.strptime(c["desde"], "%Y-%m-%d").date()
                f_hasta = datetime.strptime(c["hasta"], "%Y-%m-%d").date()
                if f_desde <= hoy <= f_hasta:
                    return f"🚫 *Cerrado*: {c.get('motivo', 'Cierre eventual')}."

            # 2. Prioridad 2: ¿Hoy es día de guardia? (Si es guardia, asumimos abierto 24hs o según lógica)
            if hoy.strftime("%Y-%m-%d") in self.data.get("dias_de_guardia", []):
                return "✅ *Abierto*: Hoy estamos de Guardia."

            # 3. Prioridad 3: Horarios fijos
            config = self.data.get("horarios_fijos", {}).get(dia_json, {})
            if config.get("abierto"):
                ap = datetime.strptime(config["apertura"], "%H:%M").time()
                ci = datetime.strptime(config["cierre"], "%H:%M").time()
                if ap <= hora_actual <= ci:
                    return f"✅ *Abierto*: Atendemos hasta las {config['cierre']} hs."
                else:
                    return f"🚫 *Cerrado*: Abrimos a las {config['apertura']} hs."
            
            return "🚫 *Cerrado*: Hoy no abrimos al público."    
    
