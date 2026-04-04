# src/cliente/registro_base.py
from src.registro.validadores import Validadores
from src.session_manager import SessionManager
from src.config_loader import ConfigLoader
from src.send_wpp import SendWPP

class RegistroBase(Validadores):
    """
    Clase base para el flujo de registro de datos.
    Responsabilidades:
        - Lógica genérica de registro campo a campo
        - Detección de campos pendientes
        - Validación de completitud
        - Parametrizable por sección (cliente, direccion)
    Las clases hijas definen: seccion, campos_excluidos, y el método de persistencia.
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = ConfigLoader()

    # ── MÉTODOS A IMPLEMENTAR POR LAS CLASES HIJAS ───────────────────────────

    @property
    def seccion(self):
        """Nombre de la sección en estructura_sesion (ej: 'cliente', 'direccion')."""
        raise NotImplementedError

    @property
    def campos_excluidos(self):
        """Campos que se omiten en el flujo de registro (ej: pushname)."""
        return []

    def _get_datos_sesion(self):
        """Retorna los datos actuales de la sección desde sesiones.json."""
        raise NotImplementedError

    def _persistir_campo(self, campo, valor):
        """Persiste el valor de un campo en sesiones.json."""
        raise NotImplementedError

    def _get_atributo_campo_actual(self):
        """Nombre del atributo en sesión para el campo actual del flujo."""
        raise NotImplementedError

    def _get_atributo_reintentos(self):
        """Nombre del atributo en sesión para el contador de reintentos."""
        raise NotImplementedError

    # ── CONFIGURACIÓN DE CAMPOS ───────────────────────────────────────────────

    def _get_config_campo(self, campo):
        """Lee la configuración de un campo desde configuracion.json."""
        return self.config.data.get("estructura_sesion", {}).get(self.seccion, {}).get(campo, {})

    def _get_config_validadores(self):
        """Retorna el catálogo de validadores desde configuracion.json."""
        return self.config.data.get("validadores", {})

    def _get_reintentos_max(self):
        """Retorna el máximo de reintentos configurado en configuracion.json."""
        return self.config.data.get("estructura_sesion", {}).get("reintentos_input", 2)

    # ── DETECCIÓN DE CAMPOS INCOMPLETOS ───────────────────────────────────────

    def tiene_datos_completos(self):
        """
        Verifica si la sección tiene todos los campos obligatorios completos y válidos.
        La estructura se lee de configuracion.json, los valores de sesiones.json.
        """
        datos = self._get_datos_sesion()
        if not datos:
            return False

        estructura = self.config.data.get("estructura_sesion", {}).get(self.seccion, {})
        for campo, config in estructura.items():
            if campo in self.campos_excluidos:
                continue
            if config.get("obligatorio"):
                valor = datos.get(campo, {}).get("valor", "").strip()
                if not valor:
                    return False
                tipo = config.get("tipo", "texto")
                validadores_campo = config.get("validadores", [])
                resultado = self._validar(tipo, valor, validadores_campo, self._get_config_validadores())
                if resultado is not True:
                    return False
        return True

    def get_campos_pendientes(self):
        """
        Retorna campos sin valor o con valor inválido.
        Los obligatorios además validan tipo y validadores adicionales.
        """
        datos = self._get_datos_sesion()
        estructura = self.config.data.get("estructura_sesion", {}).get(self.seccion, {})
        pendientes = []

        for campo, config in estructura.items():
            if campo in self.campos_excluidos:
                continue
            valor = datos.get(campo, {}).get("valor", "").strip()

            # Campo vacío: siempre pendiente
            if not valor:
                pendientes.append(campo)
                continue

            # Campo obligatorio con valor: validamos tipo y validadores adicionales
            if config.get("obligatorio"):
                tipo = config.get("tipo", "texto")
                validadores_campo = config.get("validadores", [])
                resultado = self._validar(tipo, valor, validadores_campo, self._get_config_validadores())
                if resultado is not True:
                    pendientes.append(campo)

        return pendientes

    # ── FLUJO DE REGISTRO ─────────────────────────────────────────────────────

    def iniciar_registro(self, sesiones):
        """Punto de entrada del flujo. Busca el primer campo pendiente y lo solicita."""
        pendientes = self.get_campos_pendientes()
        if not pendientes:
            self.sw.enviar("✅ Tus datos ya están completos.")
            return

        campo = pendientes[0]
        setattr(sesiones[self.numero], self._get_atributo_campo_actual(), campo)
        setattr(sesiones[self.numero], self._get_atributo_reintentos(), 0)

        config_campo = self._get_config_campo(campo)
        self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá tu {campo}:"))

    def procesar_registro(self, comando, sesiones):
        """
        Procesa la respuesta del usuario.
        Retorna 'ok' si completó, 'cancelado' si agotó reintentos, None si sigue en curso.
        """
        campo = getattr(sesiones[self.numero], self._get_atributo_campo_actual(), None)
        if not campo:
            return None

        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        validadores_campo = config_campo.get("validadores", [])
        es_obligatorio = config_campo.get("obligatorio", False)
        reintentos_max = self._get_reintentos_max()
        reintentos_actuales = getattr(sesiones[self.numero], self._get_atributo_reintentos(), 0)

        # Campos no obligatorios: aceptamos cualquier texto no vacío
        if not es_obligatorio:
            if comando.strip():
                return self._guardar_y_continuar(campo, comando, sesiones)
            else:
                self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá tu {campo}:"))
            return None

        # Campos obligatorios: validamos tipo y validadores adicionales
        resultado = self._validar(tipo, comando, validadores_campo, self._get_config_validadores())

        if resultado is True:
            setattr(sesiones[self.numero], self._get_atributo_reintentos(), 0)
            return self._guardar_y_continuar(campo, comando, sesiones)
        else:
            reintentos_actuales += 1
            setattr(sesiones[self.numero], self._get_atributo_reintentos(), reintentos_actuales)

            if reintentos_actuales >= reintentos_max:
                # ❌ Agotó reintentos
                setattr(sesiones[self.numero], self._get_atributo_campo_actual(), None)
                setattr(sesiones[self.numero], self._get_atributo_reintentos(), 0)
                return "cancelado"
            else:
                # ⚠️ Reintento con mensaje específico o genérico
                msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:")
                self.sw.enviar(msj)
            return None

    def esta_en_registro(self, sesiones):
        """Retorna True si el usuario está en medio de un flujo de registro."""
        return getattr(sesiones[self.numero], self._get_atributo_campo_actual(), None) is not None

    def _guardar_y_continuar(self, campo, comando, sesiones):
        """Persiste el valor y avanza al siguiente campo pendiente o cierra el registro."""
        self._persistir_campo(campo, comando.strip().lower())
        setattr(sesiones[self.numero], self._get_atributo_reintentos(), 0)
        pendientes = self.get_campos_pendientes()

        if pendientes:
            siguiente = pendientes[0]
            setattr(sesiones[self.numero], self._get_atributo_campo_actual(), siguiente)
            config_siguiente = self._get_config_campo(siguiente)
            self.sw.enviar(config_siguiente.get("msj_pedido", f"Ingresá tu {siguiente}:"))
            return None
        else:
            setattr(sesiones[self.numero], self._get_atributo_campo_actual(), None)
            return "ok"