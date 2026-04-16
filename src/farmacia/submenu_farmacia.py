# src/farmacia/submenu_farmacia.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.cliente.persona_manager import PersonaManager
from src.cliente.registro_persona import RegistroPersona
from src.farmacia.vinculacion_manager import VinculacionManager
from src.farmacia.gestion_obra_social import GestionObraSocial
from src.farmacia.gestion_datos_persona import GestionDatosPersona
from src.farmacia.gestion_beneficiario import GestionBeneficiario
from src.farmacia.submenu_staff import SubMenuStaff
from src.horarios import HorariosGestion


class SubMenuFarmacia:
    """
    Orquestador del enlatado farmacia.
    Responsabilidades:
        - Verificar acceso por horario (bloqueo propio del enlatado)
        - Mostrar mensajes emergentes al entrar (guardias, cierres)
        - Resolver identidad del operador (LID -> persona)
        - Si no existe persona, disparar registro nivel 1
        - Seleccion de beneficiario (yo / vinculados visibles)
        - Mostrar submenu farmacia con placeholder {beneficiario} resuelto
        - Delegar cada opcion a su handler
        - Flag recordatorio de beneficiario activo en cada mensaje
        - Panel de staff (opcion 0) para roles admin/root
    """

    DATA_PATH = "data/farmacia/horarios.json"

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()
        self.persona_manager = PersonaManager()
        self.vinculacion_manager = VinculacionManager()
        self.registro_persona = RegistroPersona(numero)
        self.gestion_os = GestionObraSocial(numero)
        self.gestion_datos = GestionDatosPersona(numero)
        self.gestion_beneficiario = GestionBeneficiario(numero)
        self.horarios = HorariosGestion(numero, self.DATA_PATH)
        self.staff = SubMenuStaff(numero)

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario esta en algun flujo de farmacia."""
        campo = getattr(sesiones[self.numero], "farmacia_estado", None)
        if campo is not None:
            return True
        # Verificar subflujos activos
        return (self.gestion_os.esta_en_flujo(sesiones) or
                self.gestion_datos.esta_en_flujo(sesiones) or
                self.gestion_beneficiario.esta_en_flujo(sesiones) or
                self.staff.esta_en_flujo(sesiones))

    def iniciar(self, sesiones):
        """
        Punto de entrada al enlatado farmacia.
        Paso 0: verificar acceso por horario.
        Paso 1: mensajes emergentes.
        Paso 2: verificar si hay persona vinculada al LID.
        """
        # Paso 0: bloqueo por horario
        if not self.horarios.tiene_acceso():
            estado = self.horarios.estado_actual()
            self.sw.enviar(f"{estado}\n\nLa farmacia no esta atendiendo en este momento.")
            return  # No activa flujo, vuelve al menu principal

        # Paso 1: mensajes emergentes
        self._enviar_mensajes_emergentes()

        # Paso 2: verificar persona
        persona = self.persona_manager.buscar_por_lid(self.numero)

        if not persona:
            # No hay persona — disparar registro nivel 1
            sesiones[self.numero].farmacia_estado = "registro_persona"
            self.registro_persona.iniciar_registro(sesiones)
            return

        persona_id = persona[0]
        sesiones[self.numero].farmacia_operador_id = persona_id

        # Paso 3: seleccion de beneficiario
        self._seleccionar_beneficiario(persona_id, sesiones)

    def procesar(self, comando, sesiones):
        """Dispatcher segun estado actual de farmacia."""
        # Subflujo de staff tiene prioridad
        if self.staff.esta_en_flujo(sesiones):
            self.staff.procesar(comando, sesiones)
            # Si salio del staff, volvemos al menu de farmacia
            if not self.staff.esta_en_flujo(sesiones):
                estado_farmacia = getattr(sesiones[self.numero], "farmacia_estado", None)
                if estado_farmacia == "menu_farmacia":
                    self._mostrar_menu_farmacia(sesiones)
            return

        # Subflujo de obra social tiene prioridad
        if self.gestion_os.esta_en_flujo(sesiones):
            self.gestion_os.procesar(comando, sesiones)
            if not self.gestion_os.esta_en_flujo(sesiones):
                estado_farmacia = getattr(sesiones[self.numero], "farmacia_estado", None)
                if estado_farmacia == "menu_farmacia":
                    self._mostrar_menu_farmacia(sesiones)
            return

        # Subflujo de datos persona
        if self.gestion_datos.esta_en_flujo(sesiones):
            self.gestion_datos.procesar(comando, sesiones)
            if not self.gestion_datos.esta_en_flujo(sesiones):
                estado_farmacia = getattr(sesiones[self.numero], "farmacia_estado", None)
                if estado_farmacia == "menu_farmacia":
                    self._mostrar_menu_farmacia(sesiones)
            return

        # Subflujo de registro de beneficiario
        if self.gestion_beneficiario.esta_en_flujo(sesiones):
            self.gestion_beneficiario.procesar(comando, sesiones)
            if not self.gestion_beneficiario.esta_en_flujo(sesiones):
                estado_farmacia = getattr(sesiones[self.numero], "farmacia_estado", None)
                if estado_farmacia == "menu_farmacia":
                    self._mostrar_menu_farmacia(sesiones)
            return

        estado = getattr(sesiones[self.numero], "farmacia_estado", None)

        if estado == "registro_persona" or estado == "post_registro_os":
            self._procesar_registro_persona(comando, sesiones)

        elif estado == "seleccion_beneficiario":
            self._procesar_seleccion_beneficiario(comando, sesiones)

        elif estado == "menu_farmacia":
            self._procesar_menu_farmacia(comando, sesiones)

    # ── MENSAJES EMERGENTES ───────────────────────────────────────────────────

    def _enviar_mensajes_emergentes(self):
        """Envia avisos de guardia proxima y cierre eventual al entrar a farmacia."""
        msg_guardia = self.horarios.mensaje_proximas_guardias()
        if msg_guardia:
            self.sw.enviar(msg_guardia)

        msg_cierre = self.horarios.mensaje_proximo_evento()
        if msg_cierre:
            self.sw.enviar(msg_cierre)

    # ── REGISTRO DE PERSONA ───────────────────────────────────────────────────

    def _procesar_registro_persona(self, comando, sesiones):
        """Procesa el flujo de registro de persona nivel 1."""
        # Post-registro: pregunta si quiere cargar obra social
        if getattr(sesiones[self.numero], "farmacia_estado", None) == "post_registro_os":
            if comando.strip() == "si":
                persona_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)
                sesiones[self.numero].farmacia_estado = "menu_farmacia"
                sesiones[self.numero].farmacia_beneficiario_id = persona_id
                sesiones[self.numero].farmacia_beneficiario_alias = "mi"
                self.gestion_os.iniciar(sesiones, persona_id)
                return
            else:
                persona_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)
                self._seleccionar_beneficiario(persona_id, sesiones)
                return

        resultado = self.registro_persona.procesar_registro(comando, sesiones)

        if resultado is None:
            return  # Sigue en curso

        if resultado == "cancelado":
            self.sw.enviar("No pudimos completar el registro. Volviendo al menu principal...")
            self._salir(sesiones)
            return

        # resultado es persona_id — registro exitoso
        sesiones[self.numero].farmacia_operador_id = resultado
        sesiones[self.numero].farmacia_estado = "post_registro_os"
        self.sw.enviar("Queres registrar tu *obra social* ahora? (si/no)")

    # ── SELECCION DE BENEFICIARIO ─────────────────────────────────────────────

    def _seleccionar_beneficiario(self, persona_id, sesiones):
        """
        Evalua vinculados visibles y decide el flujo:
        - 0 vinculados -> beneficiario = operador (automatico)
        - 1+ vinculados -> muestra lista para elegir
        """
        vinculados = self.vinculacion_manager.get_vinculados_visibles(persona_id)

        if not vinculados:
            # Sin vinculados — beneficiario es el operador
            sesiones[self.numero].farmacia_beneficiario_id = persona_id
            sesiones[self.numero].farmacia_beneficiario_alias = "mi"
            sesiones[self.numero].farmacia_estado = "menu_farmacia"
            self._mostrar_menu_farmacia(sesiones)
            return

        # Hay vinculados — mostrar lista
        sesiones[self.numero].farmacia_estado = "seleccion_beneficiario"
        sesiones[self.numero].farmacia_vinculados = vinculados
        self.sw.enviar(self._armar_lista_beneficiarios(persona_id, vinculados))

    def _armar_lista_beneficiarios(self, persona_id, vinculados):
        """Arma la lista de beneficiarios para seleccion."""
        nombre_operador = self.persona_manager.get_nombre_completo(persona_id) or "mi"

        lineas = ["Para quien es el tramite?\n"]
        lineas.append(f"1. Para mi ({nombre_operador})")

        for i, v in enumerate(vinculados, 2):
            nombre_vinculado = self.persona_manager.get_nombre_completo(v["persona_id"]) or "Sin nombre"
            alias = v["mi_alias"]
            lineas.append(f"{i}. {alias} ({nombre_vinculado})")

        return "\n".join(lineas)

    def _procesar_seleccion_beneficiario(self, comando, sesiones):
        """Procesa la seleccion de beneficiario de la lista."""
        vinculados = getattr(sesiones[self.numero], "farmacia_vinculados", [])
        operador_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)

        try:
            opcion = int(comando.strip())
        except ValueError:
            self.sw.enviar("Opcion no valida. Ingresa el numero de la opcion:")
            return

        if opcion == 1:
            # Para mi
            sesiones[self.numero].farmacia_beneficiario_id = operador_id
            sesiones[self.numero].farmacia_beneficiario_alias = "mi"
        elif 2 <= opcion <= len(vinculados) + 1:
            vinculado = vinculados[opcion - 2]
            sesiones[self.numero].farmacia_beneficiario_id = vinculado["persona_id"]
            sesiones[self.numero].farmacia_beneficiario_alias = vinculado["mi_alias"]
        else:
            self.sw.enviar("Opcion no valida. Ingresa el numero de la opcion:")
            return

        sesiones[self.numero].farmacia_estado = "menu_farmacia"
        self._mostrar_menu_farmacia(sesiones)

    # ── MENU FARMACIA ─────────────────────────────────────────────────────────

    def _mostrar_menu_farmacia(self, sesiones):
        """Muestra el submenu de farmacia con beneficiario resuelto."""
        beneficiario_alias = getattr(sesiones[self.numero], "farmacia_beneficiario_alias", "mi")
        beneficiario_id = getattr(sesiones[self.numero], "farmacia_beneficiario_id", None)
        operador_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)

        # Resolver nombre para {beneficiario}
        if beneficiario_id == operador_id:
            nombre_beneficiario = "mi"
        else:
            nombre_beneficiario = beneficiario_alias

        # Flag de beneficiario si no es el operador
        if beneficiario_id != operador_id:
            nombre_completo = self.persona_manager.get_nombre_completo(beneficiario_id) or beneficiario_alias
            flag = f"\nGestionando para: *{beneficiario_alias} ({nombre_completo})*"
        else:
            flag = ""

        # Armar menu desde configuracion
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("farmacia")

        if not submenu_data:
            self.sw.enviar("Submenu de farmacia no configurado.")
            return

        # Reemplazar placeholders en consulta
        consulta = submenu_data.get("consulta", "")
        consulta = consulta.replace("{flag_beneficiario}", flag)

        # Armar opciones visibles con {beneficiario} resuelto
        opciones_visibles = self.config.get_opciones_visibles(submenu_data, rol)
        lineas = [consulta, ""]
        for op in opciones_visibles:
            texto = op["texto"].replace("{beneficiario}", nombre_beneficiario)
            lineas.append(texto)

        self.sw.enviar("\n".join(lineas))

    def _procesar_menu_farmacia(self, comando, sesiones):
        """Procesa comandos dentro del submenu farmacia."""
        if comando.strip() == "salir":
            self._salir(sesiones)
            return

        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("farmacia")
        opcion = self.config.resolver_activacion(comando, submenu_data, rol)

        if opcion is None:
            self.sw.enviar("Opcion no valida.")
            return

        handler_nombre = opcion.get("handler")
        if handler_nombre:
            handler = getattr(self, handler_nombre, None)
            if handler:
                handler(sesiones)
            else:
                self.sw.enviar(f"Funcion '{handler_nombre}' proximamente...")

    # ── HANDLERS ──────────────────────────────────────────────────────────────

    def panel_staff(self, sesiones):
        """Abre el panel de administracion de staff."""
        self.staff.iniciar(sesiones)

    def consultar_horarios_fijos(self, sesiones):
        """Reutiliza HorariosGestion para mostrar horarios de atencion."""
        msg = self.horarios.consultar_horarios_fijos()
        beneficiario_flag = self._get_flag_beneficiario(sesiones)
        self.sw.enviar(f"{beneficiario_flag}{msg}")
        self._mostrar_menu_farmacia(sesiones)

    def consultar_guardias(self, sesiones):
        """Reutiliza HorariosGestion para mostrar guardias."""
        msg = self.horarios.consultar_dias_de_guardia()
        beneficiario_flag = self._get_flag_beneficiario(sesiones)
        self.sw.enviar(f"{beneficiario_flag}{msg}")
        self._mostrar_menu_farmacia(sesiones)

    def consultar_cierres(self, sesiones):
        """Reutiliza HorariosGestion para mostrar cierres eventuales."""
        msg = self.horarios.consultar_cierres_eventuales()
        beneficiario_flag = self._get_flag_beneficiario(sesiones)
        self.sw.enviar(f"{beneficiario_flag}{msg}")
        self._mostrar_menu_farmacia(sesiones)

    def registrar_beneficiario(self, sesiones):
        """Dispara el flujo de registro de un nuevo beneficiario/vinculado."""
        operador_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)
        if not operador_id:
            self.sw.enviar("No se pudo identificar al operador.")
            self._mostrar_menu_farmacia(sesiones)
            return
        self.gestion_beneficiario.iniciar(sesiones, operador_id)

    def cambiar_beneficiario(self, sesiones):
        """Muestra la lista de beneficiarios para cambiar."""
        operador_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)
        vinculados = self.vinculacion_manager.get_vinculados_visibles(operador_id)

        if not vinculados:
            self.sw.enviar("No tenes beneficiarios registrados. Podes registrar uno desde el menu.")
            self._mostrar_menu_farmacia(sesiones)
            return

        sesiones[self.numero].farmacia_estado = "seleccion_beneficiario"
        sesiones[self.numero].farmacia_vinculados = vinculados
        self.sw.enviar(self._armar_lista_beneficiarios(operador_id, vinculados))

    def completar_datos(self, sesiones):
        """Dispara el flujo de gestion de datos para el beneficiario activo."""
        beneficiario_id = getattr(sesiones[self.numero], "farmacia_beneficiario_id", None)
        if not beneficiario_id:
            self.sw.enviar("No hay beneficiario seleccionado.")
            self._mostrar_menu_farmacia(sesiones)
            return
        self.gestion_datos.iniciar(sesiones, beneficiario_id)

    def administrar_obra_social(self, sesiones):
        """Dispara el flujo de gestion de obra social para el beneficiario activo."""
        beneficiario_id = getattr(sesiones[self.numero], "farmacia_beneficiario_id", None)
        if not beneficiario_id:
            self.sw.enviar("No hay beneficiario seleccionado.")
            self._mostrar_menu_farmacia(sesiones)
            return
        self.gestion_os.iniciar(sesiones, beneficiario_id)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _get_flag_beneficiario(self, sesiones):
        """Retorna el flag de beneficiario si no es el operador, o string vacio."""
        beneficiario_id = getattr(sesiones[self.numero], "farmacia_beneficiario_id", None)
        operador_id = getattr(sesiones[self.numero], "farmacia_operador_id", None)

        if beneficiario_id and beneficiario_id != operador_id:
            alias = getattr(sesiones[self.numero], "farmacia_beneficiario_alias", "")
            nombre = self.persona_manager.get_nombre_completo(beneficiario_id) or alias
            return f"Gestionando para: *{alias} ({nombre})*\n\n"
        return ""

    def _salir(self, sesiones):
        """Limpia estado de farmacia y vuelve al menu principal."""
        sesiones[self.numero].farmacia_estado = None
        sesiones[self.numero].farmacia_operador_id = None
        sesiones[self.numero].farmacia_beneficiario_id = None
        sesiones[self.numero].farmacia_beneficiario_alias = None
        sesiones[self.numero].farmacia_vinculados = None
        sesiones[self.numero].farmacia_staff_activo = None
