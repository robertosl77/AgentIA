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

    def tiene_permiso(self, rol, propiedad_json):
        """Verifica en 'permisos_edicion' si el rol puede tocar esa propiedad."""
        permisos = self.data.get("permisos_edicion", {})
        roles_autorizados = permisos.get(propiedad_json, [])
        return rol in roles_autorizados

    # ── MOTOR DE MENÚS DINÁMICO ───────────────────────────────────────────────

    def get_bienvenida(self, pushname, nombre_negocio):
        """Retorna el mensaje de bienvenida con los datos del cliente."""
        template = self.data["mensajes"]["bienvenida"]
        return template.format(pushname=pushname, nombre_negocio=nombre_negocio)

    def get_opciones_visibles(self, seccion, rol):
        """
        Filtra las opciones de un menú o submenú según el rol del usuario.
        seccion: dict con 'consulta' y 'opciones' (ya resuelto, no el nombre)
        Retorna lista de opciones visibles para ese rol.
        """
        return [op for op in seccion.get("opciones", []) if rol in op.get("roles", [])]

    def armar_menu(self, seccion, rol):
        """
        Arma el texto completo del menú filtrando opciones por rol.
        Concatena: consulta + opciones visibles.
        seccion: dict con 'consulta' y 'opciones'
        """
        opciones_visibles = self.get_opciones_visibles(seccion, rol)
        lineas = [seccion.get("consulta", "")]
        lineas.append("")  # ← línea en blanco entre consulta y opciones
        for op in opciones_visibles:
            lineas.append(op["texto"])
        return "\n".join(lineas)

    def get_menu_principal(self):
        """Retorna la sección menu_principal del JSON."""
        return self.data["mensajes"]["menu_principal"]

    def get_submenu(self, nombre):
        """Retorna la sección de un submenú por nombre (ej: 'horarios', 'staff')."""
        return self.data["mensajes"]["submenus"].get(nombre)

    def resolver_activacion(self, comando, seccion, rol):
        """
        Dado un comando del usuario, busca qué opción del menú lo activa.
        Filtra por rol y por activacion.
        Retorna la opción completa si la encuentra, o None si no matchea nada.
        """
        opciones_visibles = self.get_opciones_visibles(seccion, rol)
        for op in opciones_visibles:
            if comando in op.get("activacion", []):
                return op
        return None