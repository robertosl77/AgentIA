import json
import os
from datetime import datetime

class ConfigLoader:
    def __init__(self, path=r"data\configuracion.json"):
        self.path = path
        self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.path}")
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_mensaje(self, categoria, clave):
        seccion = self.data.get(categoria, {})
        texto = seccion.get(clave, "")
        if not isinstance(texto, str): return str(texto)
        return texto.format(**self.data)

    def obtener_rol(self, numero):
        """Devuelve el nombre del rol (root, administradores, supervisores) o 'usuario'."""
        roles_dict = self.data.get("roles", {})
        for rol, lista_numeros in roles_dict.items():
            if numero in lista_numeros:
                return rol
        return "usuario"

    def tiene_permiso(self, rol, propiedad_json):
        """Verifica en 'permisos_edicion' si el rol puede tocar esa propiedad."""
        permisos = self.data.get("permisos_edicion", {})
        roles_autorizados = permisos.get(propiedad_json, [])
        return rol in roles_autorizados

