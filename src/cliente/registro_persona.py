# src/cliente/registro_persona.py
from src.cliente.persona_manager import PersonaManager
from src.config_loader import ConfigLoader
from src.send_wpp import SendWPP


class RegistroPersona:
    """
    Flujo de registro de persona nueva usando PersonaManager.
    Nivel 1: solo campos obligatorios (tipo_documento, numero_documento, nombre, apellido).
    No hereda de RegistroBase — es un flujo independiente adaptado al nuevo modelo.
    
    Responsabilidades:
        - Pedir campos obligatorios paso a paso
        - Validar cada campo según configuracion.json
        - Al ingresar documento, verificar si la persona ya existe (deduplicación)
        - Crear persona en personas.json y vincular LID
        - Retornar persona_id al completar
    """

    # Campos de nivel 1 en orden de pedido
    CAMPOS_NIVEL_1 = ["tipo_documento", "numero_documento", "nombre", "apellido"]

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.persona_manager = PersonaManager()
        self.config = ConfigLoader()

    # ── CONFIGURACIÓN ─────────────────────────────────────────────────────────

    def _get_config_campo(self, campo):
        """Lee la configuración de un campo desde estructura_sesion.persona."""
        return self.config.data.get("estructura_sesion", {}).get("persona", {}).get(campo, {})

    def _get_config_validadores(self):
        """Retorna el catálogo de validadores desde configuracion.json."""
        return self.config.data.get("validadores", {})

    def _get_reintentos_max(self):
        """Retorna el máximo de reintentos configurado."""
        return self.config.data.get("estructura_sesion", {}).get("reintentos_input", 3)

    # ── VALIDACIÓN DE TIPO BASE ───────────────────────────────────────────────

    def _validar_tipo_base(self, tipo, valor):
        """Valida el tipo base del campo."""
        if tipo == "texto":
            return bool(valor.strip()) and all(c.isalpha() or c.isspace() for c in valor.strip())
        elif tipo == "numero":
            return valor.strip().isdigit()
        elif tipo == "catalogo":
            return True  # Se valida aparte contra la lista
        return True

    def _validar_campo(self, campo, valor):
        """
        Valida un campo completo: tipo base + validadores adicionales.
        Retorna True si válido, o string con mensaje de error.
        """
        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        validadores = config_campo.get("validadores", [])
        config_validadores = self._get_config_validadores()

        # Tipo catálogo: validar contra la lista
        if tipo == "catalogo":
            catalogo_nombre = config_campo.get("catalogo", "")
            catalogo = self.persona_manager.data.get(catalogo_nombre, [])
            try:
                indice = int(valor.strip()) - 1
                if 0 <= indice < len(catalogo):
                    return True
            except ValueError:
                pass
            return False

        # Tipo base
        if not self._validar_tipo_base(tipo, valor):
            return False

        # Validadores adicionales
        for nombre_v in validadores:
            config_v = config_validadores.get(nombre_v, {})
            if not config_v:
                continue
            tipo_v = config_v.get("tipo")

            if tipo_v == "longitud_minima":
                if len(valor.strip()) < config_v.get("parametro", 3):
                    return config_v.get("msj_error", "⚠️ Dato inválido.")
            elif tipo_v == "longitud_maxima":
                if len(valor.strip()) > config_v.get("parametro", 50):
                    return config_v.get("msj_error", "⚠️ Dato inválido.")

        return True

    # ── FLUJO ─────────────────────────────────────────────────────────────────

    def esta_en_registro(self, sesiones):
        """Retorna True si el usuario está en medio del flujo de registro de persona."""
        return getattr(sesiones[self.numero], "registro_persona_campo", None) is not None

    def iniciar_registro(self, sesiones):
        """Punto de entrada — pide el primer campo (tipo_documento)."""
        sesiones[self.numero].registro_persona_campo = self.CAMPOS_NIVEL_1[0]
        sesiones[self.numero].registro_persona_reintentos = 0
        sesiones[self.numero].registro_persona_datos = {}

        self.sw.enviar(
            "📋 Para poder atenderte necesitamos algunos datos.\n"
            "¡Solo te tomará un momento! 😊"
        )
        self._pedir_campo(self.CAMPOS_NIVEL_1[0])

    def procesar_registro(self, comando, sesiones):
        """
        Procesa la respuesta del usuario.
        Retorna persona_id si completó, 'cancelado' si agotó reintentos, None si sigue en curso.
        """
        campo = getattr(sesiones[self.numero], "registro_persona_campo", None)
        if not campo:
            return None

        # Cancelación manual
        if comando.strip() == "cancelar":
            self._limpiar_estado(sesiones)
            return "cancelado"

        config_campo = self._get_config_campo(campo)
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "registro_persona_reintentos", 0)

        resultado = self._validar_campo(campo, comando)

        if resultado is True:
            # Guardar valor en datos temporales
            valor = self._resolver_valor(campo, comando)
            sesiones[self.numero].registro_persona_datos[campo] = valor
            sesiones[self.numero].registro_persona_reintentos = 0

            # Si es numero_documento, verificar si la persona ya existe
            if campo == "numero_documento":
                tipo_doc = sesiones[self.numero].registro_persona_datos.get("tipo_documento", "DNI")
                existente = self.persona_manager.buscar_por_documento(tipo_doc, valor)
                if existente:
                    # Persona ya existe — vincular LID y retornar
                    persona_id = existente[0]
                    self.persona_manager.agregar_lid(persona_id, self.numero)
                    nombre = self.persona_manager.get_nombre_completo(persona_id) or "usuario"
                    self.sw.enviar(f"✅ ¡Te identificamos, *{nombre}*! Tus datos ya están registrados.")
                    self._limpiar_estado(sesiones)
                    return persona_id

            # Avanzar al siguiente campo
            return self._siguiente_campo(campo, sesiones)
        else:
            reintentos += 1
            sesiones[self.numero].registro_persona_reintentos = reintentos

            if reintentos >= reintentos_max:
                self._limpiar_estado(sesiones)
                return "cancelado"
            else:
                msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:")
                self.sw.enviar(msj)
                return None

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _pedir_campo(self, campo):
        """Envía el mensaje de pedido para un campo."""
        config_campo = self._get_config_campo(campo)

        if config_campo.get("tipo") == "catalogo":
            # Mostrar lista numerada del catálogo
            catalogo_nombre = config_campo.get("catalogo", "")
            catalogo = self.persona_manager.data.get(catalogo_nombre, [])
            lineas = [config_campo.get("msj_pedido", f"Seleccioná {campo}:"), ""]
            for i, item in enumerate(catalogo, 1):
                lineas.append(f"{i}. {item}")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá tu {campo}:"))

    def _resolver_valor(self, campo, comando):
        """Resuelve el valor final según el tipo de campo."""
        config_campo = self._get_config_campo(campo)

        if config_campo.get("tipo") == "catalogo":
            catalogo_nombre = config_campo.get("catalogo", "")
            catalogo = self.persona_manager.data.get(catalogo_nombre, [])
            indice = int(comando.strip()) - 1
            return catalogo[indice]

        return comando.strip()

    def _siguiente_campo(self, campo_actual, sesiones):
        """Avanza al siguiente campo o crea la persona si ya completó todos."""
        idx = self.CAMPOS_NIVEL_1.index(campo_actual)

        if idx + 1 < len(self.CAMPOS_NIVEL_1):
            siguiente = self.CAMPOS_NIVEL_1[idx + 1]
            sesiones[self.numero].registro_persona_campo = siguiente
            self._pedir_campo(siguiente)
            return None
        else:
            # Todos los campos completos — crear persona
            return self._crear_persona(sesiones)

    def _crear_persona(self, sesiones):
        """Crea la persona en PersonaManager y vincula el LID."""
        datos = sesiones[self.numero].registro_persona_datos

        persona_id = self.persona_manager.crear_persona(
            tipo_documento=datos.get("tipo_documento", "DNI"),
            numero_documento=datos.get("numero_documento", ""),
            nombre=datos.get("nombre", ""),
            apellido=datos.get("apellido", ""),
            lid=self.numero
        )

        if persona_id:
            nombre = self.persona_manager.get_nombre_completo(persona_id) or "usuario"
            self.sw.enviar(f"✅ ¡Registro completado, *{nombre}*!")
            self._limpiar_estado(sesiones)
            return persona_id
        else:
            # No debería pasar (ya verificamos duplicado), pero por seguridad
            self.sw.enviar("⚠️ Ocurrió un error al registrar. Intentá nuevamente.")
            self._limpiar_estado(sesiones)
            return "cancelado"

    def _limpiar_estado(self, sesiones):
        """Limpia todos los atributos de sesión del flujo de registro."""
        sesiones[self.numero].registro_persona_campo = None
        sesiones[self.numero].registro_persona_reintentos = 0
        sesiones[self.numero].registro_persona_datos = {}