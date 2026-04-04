# src/cliente/registro_direccion.py
from src.registro.registro_base import RegistroBase

class RegistroDireccion(RegistroBase):
    """
    Gestiona el flujo de registro de datos de dirección.
    Hereda toda la lógica genérica de RegistroBase.
    Define: sección 'direccion', persiste via editar_direccion.
    """

    @property
    def seccion(self):
        """Sección en estructura_sesion."""
        return "direccion"

    @property
    def campos_excluidos(self):
        """No hay campos excluidos en dirección."""
        return []

    def _get_datos_sesion(self):
        """Retorna los datos actuales de dirección desde sesiones.json."""
        return self.session_manager.get_direccion(self.numero)

    def _persistir_campo(self, campo, valor):
        """Persiste el valor de un campo de dirección en sesiones.json."""
        self.session_manager.editar_direccion(self.numero, campo, valor)

    def _get_atributo_campo_actual(self):
        """Atributo en sesión para el campo actual del flujo de dirección."""
        return "direccion_campo_actual"

    def _get_atributo_reintentos(self):
        """Atributo en sesión para el contador de reintentos del flujo de dirección."""
        return "direccion_reintentos"