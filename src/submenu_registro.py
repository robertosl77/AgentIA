# src/submenu_registro.py
from src.config_loader import ConfigLoader
from src.send_wpp import SendWPP
from src.session_manager import SessionManager
from datetime import datetime

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

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = ConfigLoader()

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
        """Valida formato de fecha DD/MM/AAAA."""
        try:
            datetime.strptime(valor.strip(), "%d/%m/%Y")
            return True
        except ValueError:
            return False

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

    # ── CONFIGURACIÓN DE CAMPOS DESDE CONFIGURACION.JSON ─────────────────────────

    def _get_config_campo_cliente(self, campo):
        """Lee la configuración de un campo de cliente desde configuracion.json."""
        return self.config.data.get("estructura_sesion", {}).get("cliente", {}).get(campo, {})

    def _get_config_campo_direccion(self, campo):
        """Lee la configuración de un campo de dirección desde configuracion.json."""
        return self.config.data.get("estructura_sesion", {}).get("direccion", {}).get(campo, {})

    # ── DETECCIÓN DE CAMPOS INCOMPLETOS ───────────────────────────────────────

    def tiene_datos_cliente_completos(self):
        """
        Verifica si el cliente tiene todos los campos obligatorios completos.
        La obligatoriedad se lee de configuracion.json, el valor de sesiones.json.
        """
        cliente = self.session_manager.get_cliente(self.numero)
        if not cliente:
            return False

        estructura = self.config.data.get("estructura_sesion", {}).get("cliente", {})
        for campo, config in estructura.items():
            if campo == "pushname":
                continue
            if config.get("obligatorio") and not cliente.get(campo, {}).get("valor", "").strip():
                return False
        return True
    
    def tiene_datos_direccion_completos(self):
        """
        Verifica si la dirección tiene todos los campos obligatorios completos.
        La obligatoriedad se lee de configuracion.json, el valor de sesiones.json.
        """
        direccion = self.session_manager.get_direccion(self.numero)
        if not direccion:
            return False

        estructura = self.config.data.get("estructura_sesion", {}).get("direccion", {})
        for campo, config in estructura.items():
            if config.get("obligatorio") and not direccion.get(campo, {}).get("valor", "").strip():
                return False
        return True 

    def get_campos_pendientes_cliente(self):
        """
        Retorna campos de cliente sin valor, leyendo estructura de configuracion.json
        y valores de sesiones.json.
        """
        cliente = self.session_manager.get_cliente(self.numero)
        estructura = self.config.data.get("estructura_sesion", {}).get("cliente", {})
        pendientes = []
        for campo in estructura.keys():
            if campo == "pushname":
                continue
            if not cliente.get(campo, {}).get("valor", "").strip():
                pendientes.append(campo)
        return pendientes
    
    def get_campos_pendientes_direccion(self):
        """
        Retorna campos de dirección sin valor, leyendo estructura de configuracion.json
        y valores de sesiones.json.
        """
        direccion = self.session_manager.get_direccion(self.numero)
        estructura = self.config.data.get("estructura_sesion", {}).get("direccion", {})
        pendientes = []
        for campo in estructura.keys():
            if not direccion.get(campo, {}).get("valor", "").strip():
                pendientes.append(campo)
        return pendientes  

    # ── FLUJO DE REGISTRO ─────────────────────────────────────────────────────

    def iniciar_registro(self, sesiones):
        """Punto de entrada del flujo de registro. Busca el primer campo pendiente y lo solicita."""
        pendientes = self.get_campos_pendientes_cliente()
        if not pendientes:
            self.sw.enviar("✅ Tus datos ya están completos.")
            return

        campo = pendientes[0]
        sesiones[self.numero].registro_campo_actual = campo
        sesiones[self.numero].registro_reintento = False

        # Config del campo viene de configuracion.json
        config_campo = self._get_config_campo_cliente(campo)
        self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá tu {campo}:"))

    def procesar_registro(self, comando, sesiones):
        """
        Procesa la respuesta del usuario durante el flujo de registro.
        Retorna 'ok' si completó, 'cancelado' si falló, None si sigue en curso.
        """
        campo = getattr(sesiones[self.numero], "registro_campo_actual", None)
        if not campo:
            return None

        # Config del campo viene de configuracion.json
        config_campo = self._get_config_campo_cliente(campo)
        tipo = config_campo.get("tipo", "texto")
        es_obligatorio = config_campo.get("obligatorio", False)
        es_reintento = getattr(sesiones[self.numero], "registro_reintento", False)

        # Para campos no obligatorios aceptamos cualquier texto no vacío
        if not es_obligatorio:
            if comando.strip():
                return self._guardar_y_continuar(campo, comando, sesiones)
            else:
                self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá tu {campo}:"))
            return None

        # Para campos obligatorios validamos el tipo
        if self._validar(tipo, comando):
            return self._guardar_y_continuar(campo, comando, sesiones)
        else:
            if es_reintento:
                sesiones[self.numero].registro_campo_actual = None
                sesiones[self.numero].registro_reintento = False
                return "cancelado"
            else:
                sesiones[self.numero].registro_reintento = True
                self.sw.enviar(config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:"))
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
        pendientes = self.get_campos_pendientes_cliente()

        if pendientes:
            siguiente = pendientes[0]
            sesiones[self.numero].registro_campo_actual = siguiente
            # Config del siguiente campo viene de configuracion.json
            config_siguiente = self._get_config_campo_cliente(siguiente)
            self.sw.enviar(config_siguiente.get("msj_pedido", f"Ingresá tu {siguiente}:"))
            return None
        else:
            sesiones[self.numero].registro_campo_actual = None
            return "ok"
 