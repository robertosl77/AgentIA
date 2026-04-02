# src/submenu_registro.py
from src.send_wpp import SendWPP
from src.session_manager import SessionManager

class SubMenuRegistro:
    """
    Gestiona el flujo de registro y edición de datos del cliente.
    Responsabilidades:
        - Detectar si el cliente tiene datos obligatorios incompletos
        - Pedir los datos campo a campo
        - Validar cada dato según su tipo configurado en sesiones.json
        - Reintentar una vez si el dato es inválido
        - Cancelar si falla el reintento, sin guardar nada
        - Interfaces preparadas para edición y dirección
    """

    # Mensajes de solicitud por campo
    MENSAJES_CAMPO = {
        "nombre":   "👤 Por favor ingresá tu *nombre*:",
        "apellido": "👤 Por favor ingresá tu *apellido*:",
        "email":    "📧 Por favor ingresá tu *email*:",
        "dni":      "🪪 Por favor ingresá tu *DNI* (solo números):",
        "telefono": "📱 Por favor ingresá tu *teléfono* (solo números):",
    }

    # Mensajes de reintento por campo (segunda oportunidad, más explícitos)
    MENSAJES_REINTENTO = {
        "nombre":   "⚠️ El nombre ingresado no es válido. Por favor ingresá solo letras:",
        "apellido": "⚠️ El apellido ingresado no es válido. Por favor ingresá solo letras:",
        "email":    "⚠️ El email ingresado no es válido. El formato debe ser ejemplo@dominio.com:",
        "dni":      "⚠️ El DNI ingresado no es válido. Por favor ingresá solo números:",
        "telefono": "⚠️ El teléfono ingresado no es válido. Por favor ingresá solo números:",
    }

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()

    # ── VALIDADORES POR TIPO DE DATO ──────────────────────────────────────────

    def valida_texto(self, valor):
        """Valida que el valor no esté vacío y contenga solo letras y espacios."""
        return bool(valor.strip()) and all(c.isalpha() or c.isspace() for c in valor)

    def valida_numero(self, valor):
        """Valida que el valor contenga solo dígitos."""
        return valor.strip().isdigit()

    def valida_email(self, valor):
        """Valida formato básico de email: contiene @ y al menos un punto después."""
        valor = valor.strip()
        return "@" in valor and "." in valor.split("@")[-1]

    def valida_telefono(self, valor):
        """Valida que el valor contenga solo dígitos y tenga al menos 8 caracteres."""
        valor = valor.strip()
        return valor.isdigit() and len(valor) >= 8

    def valida_fecha(self, valor):
        """[INTERFAZ] Valida formato de fecha DD/MM/AAAA."""
        pass

    def valida_fecha_hora(self, valor):
        """[INTERFAZ] Valida formato de fecha y hora DD/MM/AAAA HH:MM."""
        pass

    def _validar(self, tipo, valor):
        """
        Dispatcher de validadores. Llama al validador correspondiente según el tipo.
        Retorna True si el valor es válido, False si no.
        """
        validadores = {
            "texto":    self.valida_texto,
            "numero":   self.valida_numero,
            "email":    self.valida_email,
            "telefono": self.valida_telefono,
        }
        validador = validadores.get(tipo)
        if validador:
            return validador(valor)
        # Tipo desconocido: aceptamos cualquier valor no vacío
        return bool(valor.strip())

    # ── DETECCIÓN DE CAMPOS INCOMPLETOS ───────────────────────────────────────

    def tiene_datos_completos(self):
        """
        Verifica si el cliente tiene todos los campos obligatorios completos.
        Retorna True si está completo, False si falta algún campo obligatorio.
        """
        cliente = self.session_manager.get_cliente(self.numero)
        for campo, config in cliente.items():
            if not isinstance(config, dict):
                continue
            if config.get("obligatorio") and not config.get("valor", "").strip():
                return False
        return True

    def get_campos_pendientes(self):
        """
        Retorna la lista de campos que aún no tienen valor, sean obligatorios o no.
        La diferencia es que los no obligatorios no validan el tipo de dato.
        """
        cliente = self.session_manager.get_cliente(self.numero)
        pendientes = []
        for campo, config in cliente.items():
            if not isinstance(config, dict):
                continue
            # Excluimos pushname porque se precarga automáticamente
            if campo == "pushname":
                continue
            if not config.get("valor", "").strip():
                pendientes.append(campo)
        return pendientes

    # ── FLUJO DE REGISTRO ─────────────────────────────────────────────────────

    def iniciar_registro(self, sesiones):
        """
        Punto de entrada del flujo de registro.
        Busca el primer campo obligatorio pendiente y lo solicita.
        """
        pendientes = self.get_campos_pendientes()
        if not pendientes:
            self.sw.enviar("✅ Tus datos ya están completos.")
            return

        # Arrancamos por el primer campo pendiente
        campo = pendientes[0]
        sesiones[self.numero].registro_campo_actual = campo
        sesiones[self.numero].registro_reintento = False  # ← primer intento
        self.sw.enviar(self.MENSAJES_CAMPO.get(campo, f"Ingresá tu {campo}:"))

    def procesar_registro(self, comando, sesiones):
        """
        Procesa la respuesta del usuario durante el flujo de registro.
        Retorna 'ok' si el registro se completó, 'cancelado' si falló, None si sigue en curso.
        """
        campo = getattr(sesiones[self.numero], "registro_campo_actual", None)
        if not campo:
            return None

        cliente = self.session_manager.get_cliente(self.numero)
        config_campo = cliente.get(campo, {})
        tipo = config_campo.get("tipo", "texto")
        es_obligatorio = config_campo.get("obligatorio", False)
        es_reintento = getattr(sesiones[self.numero], "registro_reintento", False)

        # Para campos no obligatorios aceptamos cualquier texto no vacío
        if not es_obligatorio:
            if comando.strip():
                return self._guardar_y_continuar(campo, comando, sesiones)
            else:
                self.sw.enviar(self.MENSAJES_CAMPO.get(campo, f"Ingresá tu {campo}:"))
            return None

        # Para campos obligatorios validamos el tipo
        if self._validar(tipo, comando):
            return self._guardar_y_continuar(campo, comando, sesiones)
        else:
            if es_reintento:
                # ❌ Segundo fallo: cancelamos
                sesiones[self.numero].registro_campo_actual = None
                sesiones[self.numero].registro_reintento = False
                return "cancelado"
            else:
                # ⚠️ Primer fallo: reintentamos
                sesiones[self.numero].registro_reintento = True
                self.sw.enviar(self.MENSAJES_REINTENTO.get(campo, f"⚠️ Dato inválido. Intentá nuevamente:"))
            return None
    
    def esta_en_registro(self, sesiones):
        """Retorna True si el usuario está en medio de un flujo de registro."""
        return getattr(sesiones[self.numero], "registro_campo_actual", None) is not None

    # ── ABM CLIENTE (interfaces preparadas para implementar) ──────────────────

    def editar_dato_cliente(self, sesiones):
        """[INTERFAZ] Inicia el flujo para editar un dato específico del cliente."""
        pass

    def borrar_datos_cliente(self, sesiones):
        """[INTERFAZ] Borra todos los datos del cliente previa confirmación."""
        pass

    # ── ABM DIRECCIÓN (interfaces preparadas para implementar) ────────────────

    def iniciar_registro_direccion(self, sesiones):
        """[INTERFAZ] Inicia el flujo de registro de dirección campo a campo."""
        pass

    def editar_dato_direccion(self, sesiones):
        """[INTERFAZ] Inicia el flujo para editar un dato específico de la dirección."""
        pass

    def borrar_direccion(self, sesiones):
        """[INTERFAZ] Borra los datos de dirección previa confirmación."""
        pass

    def _guardar_y_continuar(self, campo, comando, sesiones):
        """Guarda el valor del campo y avanza al siguiente pendiente o cierra el registro."""
        self.session_manager.editar_cliente(self.numero, campo, comando.strip().lower())
        sesiones[self.numero].registro_reintento = False
        pendientes = self.get_campos_pendientes()

        if pendientes:
            # Hay más campos: pedimos el siguiente
            siguiente = pendientes[0]
            sesiones[self.numero].registro_campo_actual = siguiente
            self.sw.enviar(self.MENSAJES_CAMPO.get(siguiente, f"Ingresá tu {siguiente}:"))
            return None  # ← sigue en curso
        else:
            # ✅ Registro completo
            sesiones[self.numero].registro_campo_actual = None
            return "ok"  # ← terminó bien
 