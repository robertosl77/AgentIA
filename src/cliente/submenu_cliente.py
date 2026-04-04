# src/cliente/submenu_cliente.py
from src.registro.registro_cliente import RegistroCliente
from src.registro.registro_direccion import RegistroDireccion

class SubMenuCliente:
    """
    Orquestador de los flujos de registro de cliente y dirección.
    Delega toda la lógica en RegistroCliente y RegistroDireccion.
    """

    def __init__(self, numero):
        self.numero = numero
        self._cliente = RegistroCliente(numero)
        self._direccion = RegistroDireccion(numero)

    def esta_en_registro(self, sesiones):
        return (
            self._cliente.esta_en_registro(sesiones) or
            self._direccion.esta_en_registro(sesiones)
        )

    def procesar_registro(self, comando, sesiones):
        if self._cliente.esta_en_registro(sesiones):
            return self._cliente.procesar_registro(comando, sesiones)
        if self._direccion.esta_en_registro(sesiones):
            return self._direccion.procesar_registro(comando, sesiones)
        return None

    def tiene_datos_cliente_completos(self):
        return self._cliente.tiene_datos_completos()

    def tiene_datos_direccion_completos(self):
        return self._direccion.tiene_datos_completos()

    def iniciar_registro_cliente(self, sesiones):
        self._cliente.iniciar_registro(sesiones)

    def iniciar_registro_direccion(self, sesiones):
        self._direccion.iniciar_registro(sesiones)

    # ABM interfaces
    def editar_dato_cliente(self, sesiones): pass
    def borrar_datos_cliente(self, sesiones): pass
    def editar_dato_direccion(self, sesiones): pass
    def borrar_direccion(self, sesiones): pass