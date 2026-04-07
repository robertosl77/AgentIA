# src/cliente/registro_cliente.py
from src.registro.registro_base import RegistroBase

class RegistroCliente(RegistroBase):
    """
    Gestiona el flujo de registro de datos del cliente.
    Hereda toda la lógica genérica de RegistroBase.
    Define: sección 'cliente', excluye 'pushname', persiste via editar_cliente.
    """

    @property
    def seccion(self):
        """Sección en estructura_sesion."""
        return "cliente"

    @property
    def campos_excluidos(self):
        """Pushname se precarga automáticamente desde WhatsApp, no se pide al usuario."""
        return ["pushname"]

    def _get_datos_sesion(self):
        """Retorna los datos actuales del cliente desde sesiones_data.json."""
        return self.session_manager.get_cliente(self.numero)

    def _persistir_campo(self, campo, valor):
        """Persiste el valor de un campo del cliente en sesiones_data.json."""
        self.session_manager.editar_cliente(self.numero, campo, valor)

    def _get_atributo_campo_actual(self):
        """Atributo en sesión para el campo actual del flujo de cliente."""
        return "registro_campo_actual"

    def _get_atributo_reintentos(self):
        """Atributo en sesión para el contador de reintentos del flujo de cliente."""
        return "registro_reintentos"