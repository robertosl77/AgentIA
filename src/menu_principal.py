from src.send_wpp import SendWPP
from src.submenu_horarios import SubMenuHorarios
from src.config_loader import ConfigLoader
from datetime import datetime, timedelta

class MenuPrincipal:
    """Menú Principal del Bot"""

    def __init__(self, numero):
        self.numero = numero
        self.config = ConfigLoader()
        self.sw = SendWPP(numero)
        self.autorizado = False  # ← La "llave" de sesión

    def administro_menu(self, comando, sesiones):
        print("Numero: "+sesiones[self.numero].numero)

        # Si no existe 'menu' en la sesión, es porque es la primera vez que se llama a este método.
        menu = getattr(sesiones[self.numero], "menu", None)

        # Si no hay menú, lo asignamos y mostramos el menú inicial. Si lo hay, verificamos si es un comando de menú o submenú.
        if menu is None:
            sesiones[self.numero].menu = "principal"
            self.sw.enviar(self.mensaje_bienvenida())
            self.sw.enviar(self.mensaje_proximas_guardias())
            self.sw.enviar(self.proximo_cierre_eventual())
            self.mostrar_menu()
            return
        elif menu in ["1", "horarios"]:
            sesiones[self.numero].submenu = comando
            comando = menu
        else:
            comando = comando.strip().lower()

        # Guardamos la opción actual en la sesión para que los submenús puedan acceder a ella.
        sesiones[self.numero].menu = comando
            
        if comando == "0":
            self.sw.enviar("Próximamente...")
                
        elif comando == "1":
            SubMenuHorarios(self.numero).mostrar_menu(sesiones)
                
        elif comando == "2":
            self.sw.enviar("Próximamente...")

        elif comando == "horarios":
            SubMenuHorarios(self.numero).mostrar_menu(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida.")

        # Si el comando es 'salir', volvemos al menú principal reseteando las variables de sesión.
        if getattr(sesiones[self.numero], "submenu", None) == "salir":
            sesiones[self.numero].menu = None
            sesiones[self.numero].submenu = None
            self.mostrar_menu()
                        
    def mostrar_menu(self):
        """
        Determina dinámicamente si muestra el menú o el bloqueo.
        Se ejecuta al inicio y cada vez que se vuelve de un submenú.
        """
        # 1. Pedimos al loader el diagnóstico actual
        mensaje, acceso_liberado = self.config.obtener_menu_inicial(self.numero)
        
        # 2. Enviamos lo que corresponda (Menú o Bloqueo)
        self.sw.enviar(mensaje)
        
        # 3. Retornamos el estado para que el 'iniciar' sepa si debe frenar
        return acceso_liberado

    # Funciones específicas para el módulo de menú principal (extraen info del JSON y aplican la lógica de negocio)
    def mensaje_bienvenida(self):
        """
        Genera el mensaje de bienvenida personalizado con el nombre del negocio.
        """
        nombre_negocio = self.config.data.get("nombre_negocio", "nuestro negocio")
        return self.config.data["mensajes"]["mensaje_bienvenida"].format(nombre_negocio=nombre_negocio)

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

    def proximo_cierre_eventual(self):
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
                return f"⚠️ Recordá que *el día de hoy* no atendemos por: {motivo}."
            else:
                return f"⚠️ Recordá que el *{formato_fecha(desde)}* no atendemos por: {motivo}."

        # ── RANGO DE FECHAS (desde != hasta) ──
        if desde <= hoy <= hasta:
            # Hoy está dentro del rango
            return f"⚠️ Recordá que *desde hoy hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."
        else:
            # El cierre arranca a partir de mañana o más adelante
            return f"⚠️ Recordá que *a partir del {formato_fecha(desde)} hasta el {formato_fecha(hasta)}* no atendemos por: {motivo}."