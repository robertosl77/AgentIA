# src/farmacia/gestion_beneficiario.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.cliente.persona_manager import PersonaManager
from src.cliente.registro_persona import RegistroPersona
from src.farmacia.vinculacion_manager import VinculacionManager
from src.farmacia.gestion_obra_social import GestionObraSocial


class GestionBeneficiario:
    """
    Flujo de registro de un nuevo beneficiario (persona vinculada).
    Pasos:
        1. Registrar persona (nivel 1) — reutiliza RegistroPersona
           - Si el DNI ya existe, vincula sin crear
           - Si no existe, crea persona nueva (sin vincular LID — no es su WhatsApp)
        2. Pedir alias para la vinculación
        3. Crear vinculación bidireccional (visible para operador, invisible para beneficiario)
        4. Ofrecer cargar obra social del nuevo beneficiario
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.persona_manager = PersonaManager()
        self.vinculacion_manager = VinculacionManager()
        self.gestion_os = GestionObraSocial(numero)

    # ── CONFIGURACIÓN ─────────────────────────────────────────────────────────

    def _get_config_alias(self):
        """Retorna la config del campo alias desde estructura_sesion.vinculacion."""
        return self.config.data.get("estructura_sesion", {}).get("vinculacion", {}).get("alias", {})

    def _get_config_validadores(self):
        return self.config.data.get("validadores", {})

    def _get_reintentos_max(self):
        return self.config.data.get("estructura_sesion", {}).get("reintentos_input", 3)

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en el flujo de registro de beneficiario."""
        estado = getattr(sesiones[self.numero], "ben_estado", None)
        return estado is not None

    def iniciar(self, sesiones, operador_id):
        """Punto de entrada — inicia registro de persona para el beneficiario."""
        sesiones[self.numero].ben_estado = "registro_persona"
        sesiones[self.numero].ben_operador_id = operador_id
        sesiones[self.numero].ben_reintentos = 0
        sesiones[self.numero].ben_persona_id = None

        self.sw.enviar(
            "👥 Vamos a registrar un nuevo beneficiario.\n"
            "Ingresá los datos de la persona que querés vincular.\n"
        )

        # Reutilizamos RegistroPersona pero sin vincular LID
        self._registro = RegistroPersona(self.numero)
        self._registro.iniciar_registro(sesiones)

    def procesar(self, comando, sesiones):
        """Dispatcher según estado."""
        estado = getattr(sesiones[self.numero], "ben_estado", None)

        if estado == "registro_persona":
            self._procesar_registro(comando, sesiones)
        elif estado == "pedir_alias":
            self._procesar_alias(comando, sesiones)
        elif estado == "ofrecer_os":
            self._procesar_ofrecer_os(comando, sesiones)
        elif estado == "flujo_os":
            self._procesar_flujo_os(comando, sesiones)

    # ── REGISTRO DE PERSONA ───────────────────────────────────────────────────

    def _procesar_registro(self, comando, sesiones):
        """Procesa el flujo de registro de persona del beneficiario."""
        if not hasattr(self, '_registro'):
            self._registro = RegistroPersona(self.numero)

        resultado = self._registro.procesar_registro(comando, sesiones)

        if resultado is None:
            return  # Sigue en curso

        if resultado == "cancelado":
            self.sw.enviar("❌ Registro de beneficiario cancelado.")
            self._salir(sesiones)
            return

        # resultado es persona_id
        persona_id = resultado

        # Si la persona ya existía (detectada por DNI en RegistroPersona),
        # el LID se vinculó automáticamente. Necesitamos desvincularlo
        # porque no es el WhatsApp del beneficiario, sino del operador.
        persona = self.persona_manager.get_persona(persona_id)
        if persona and self.numero in persona[1].get("lids", []):
            # Solo quitar si la persona tiene más de un LID o si no es el operador
            operador = self.persona_manager.buscar_por_lid(self.numero)
            if operador and operador[0] != persona_id:
                self.persona_manager.quitar_lid(persona_id, self.numero)

        # Verificar si ya hay vinculación con el operador
        operador_id = getattr(sesiones[self.numero], "ben_operador_id", None)
        existente = self.vinculacion_manager.buscar_vinculo(operador_id, persona_id)

        if existente:
            # Ya existe vínculo — activar visibilidad
            vid, datos = existente
            self.vinculacion_manager.activar_visibilidad(vid, operador_id)
            nombre = self.persona_manager.get_nombre_completo(persona_id) or "la persona"
            self.sw.enviar(f"✅ *{nombre}* ya estaba registrado/a. Se activó la vinculación.")
            sesiones[self.numero].ben_persona_id = persona_id
            self._ofrecer_os(sesiones)
            return

        # No hay vínculo — pedir alias
        sesiones[self.numero].ben_persona_id = persona_id
        sesiones[self.numero].ben_estado = "pedir_alias"
        sesiones[self.numero].ben_reintentos = 0

        nombre = self.persona_manager.get_nombre_completo(persona_id) or "la persona"
        config_alias = self._get_config_alias()
        self.sw.enviar(
            f"✅ Datos de *{nombre}* registrados.\n\n"
            f"{config_alias.get('msj_pedido', 'Ingresá un alias para esta persona:')}"
        )

    # ── ALIAS ─────────────────────────────────────────────────────────────────

    def _procesar_alias(self, comando, sesiones):
        """Procesa el alias para la vinculación."""
        if comando.strip() == "cancelar":
            self.sw.enviar("❌ Registro de beneficiario cancelado.")
            self._salir(sesiones)
            return

        config_alias = self._get_config_alias()
        validadores = config_alias.get("validadores", [])
        config_validadores = self._get_config_validadores()
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "ben_reintentos", 0)

        # Validar alias
        valor = comando.strip()
        if not valor or not all(c.isalpha() or c.isspace() for c in valor):
            reintentos += 1
            sesiones[self.numero].ben_reintentos = reintentos
            if reintentos >= reintentos_max:
                self.sw.enviar("❌ Se canceló el registro.")
                self._salir(sesiones)
            else:
                self.sw.enviar(config_alias.get("msj_reintento", "⚠️ Alias no válido."))
            return

        # Validadores adicionales (longitud)
        for nombre_v in validadores:
            config_v = config_validadores.get(nombre_v, {})
            tipo_v = config_v.get("tipo")
            if tipo_v == "longitud_minima" and len(valor) < config_v.get("parametro", 3):
                reintentos += 1
                sesiones[self.numero].ben_reintentos = reintentos
                if reintentos >= reintentos_max:
                    self.sw.enviar("❌ Se canceló el registro.")
                    self._salir(sesiones)
                else:
                    self.sw.enviar(config_v.get("msj_error", "⚠️ Alias muy corto."))
                return
            if tipo_v == "longitud_maxima" and len(valor) > config_v.get("parametro", 30):
                reintentos += 1
                sesiones[self.numero].ben_reintentos = reintentos
                if reintentos >= reintentos_max:
                    self.sw.enviar("❌ Se canceló el registro.")
                    self._salir(sesiones)
                else:
                    self.sw.enviar(config_v.get("msj_error", "⚠️ Alias muy largo."))
                return

        # Crear vinculación bidireccional
        operador_id = getattr(sesiones[self.numero], "ben_operador_id", None)
        persona_id = getattr(sesiones[self.numero], "ben_persona_id", None)

        self.vinculacion_manager.crear_vinculacion(
            persona_origen_id=operador_id,
            persona_destino_id=persona_id,
            alias_origen=valor
        )

        nombre = self.persona_manager.get_nombre_completo(persona_id) or valor
        self.sw.enviar(f"✅ *{nombre}* vinculado/a como *{valor}* correctamente.")

        # Ofrecer cargar obra social
        self._ofrecer_os(sesiones)

    # ── OBRA SOCIAL POST-REGISTRO ─────────────────────────────────────────────

    def _ofrecer_os(self, sesiones):
        """Ofrece cargar obra social del beneficiario recién registrado."""
        sesiones[self.numero].ben_estado = "ofrecer_os"
        self.sw.enviar("¿Querés registrar la *obra social* de esta persona ahora? (si/no)")

    def _procesar_ofrecer_os(self, comando, sesiones):
        """Procesa si el usuario quiere cargar obra social."""
        if comando.strip() == "si":
            persona_id = getattr(sesiones[self.numero], "ben_persona_id", None)
            sesiones[self.numero].ben_estado = "flujo_os"
            self.gestion_os.iniciar(sesiones, persona_id)
        else:
            self.sw.enviar("👍 Podés cargarla después desde el menú.")
            self._salir(sesiones)

    def _procesar_flujo_os(self, comando, sesiones):
        """Procesa el subflujo de obra social."""
        self.gestion_os.procesar(comando, sesiones)
        if not self.gestion_os.esta_en_flujo(sesiones):
            self._salir(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _salir(self, sesiones):
        """Limpia estado del flujo de beneficiario."""
        sesiones[self.numero].ben_estado = None
        sesiones[self.numero].ben_operador_id = None
        sesiones[self.numero].ben_persona_id = None
        sesiones[self.numero].ben_reintentos = 0