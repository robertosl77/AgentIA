# src/auxilios/auxilios_config_loader.py
import json
import os
from src.tenant import data_path

_instancia = None

class AuxiliosConfigLoader:
    """
    Carga la configuración estática del módulo de auxilios desde auxilios_config.json.
    Singleton — se carga una vez y se reutiliza.
    Contiene: estructura de objetos, catálogos, tarifas, submenú.
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("auxilio", "auxilios_config.json")
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            raise FileNotFoundError(f"Archivo no encontrado: {self.PATH}")
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── OBJETOS ───────────────────────────────────────────────────────────────

    def get_objeto(self, nombre):
        """Retorna la configuración completa de un objeto (campos, reglamental, habilitado)."""
        return self.data.get("objetos", {}).get(nombre, {})

    def get_campos(self, nombre_objeto):
        """Retorna los campos configurados para un objeto."""
        return self.get_objeto(nombre_objeto).get("campos", {})

    def esta_habilitado(self, nombre_objeto):
        """Retorna True si el objeto está habilitado."""
        obj = self.get_objeto(nombre_objeto)
        if obj.get("reglamental"):
            return True
        return obj.get("habilitado", False)

    # ── CATÁLOGOS ─────────────────────────────────────────────────────────────

    def get_puntos_frecuentes(self):
        """Retorna la lista de localidades frecuentes."""
        return self.data.get("catalogos", {}).get("puntos_frecuentes", [])

    def get_recorridos_establecidos(self):
        """Retorna la lista de recorridos con origen, destino y km."""
        return self.data.get("catalogos", {}).get("recorridos_establecidos", [])

    def get_tipos_camino(self):
        """Retorna los tipos de camino con sus precios por ris."""
        return self.data.get("catalogos", {}).get("tipos_camino", [])

    def get_ris_categorias(self):
        """Retorna las categorías RIS con sus rangos de peso."""
        return self.data.get("catalogos", {}).get("ris_categorias", [])

    # ── TARIFAS ───────────────────────────────────────────────────────────────

    def get_movida(self):
        """Retorna la configuración de movida (radio, km_maximo, precios)."""
        return self.data.get("tarifas", {}).get("movida", {})

    def get_tarifa(self, nombre):
        """Retorna la configuración de una tarifa extra por nombre."""
        return self.data.get("tarifas", {}).get(nombre, {})

    def get_tarifas_extras_habilitadas(self):
        """Retorna las tarifas extras que están habilitadas."""
        tarifas = self.data.get("tarifas", {})
        habilitadas = {}
        for nombre, config in tarifas.items():
            if nombre == "movida":
                continue
            if config.get("habilitado", False):
                habilitadas[nombre] = config
        return habilitadas

    # ── SUBMENÚ ───────────────────────────────────────────────────────────────

    def get_submenu(self):
        """Retorna la configuración del submenú de auxilios."""
        return self.data.get("submenu", {})

    def get_opciones_visibles(self, rol):
        """Retorna las opciones del submenú visibles para el rol, filtrando por habilitación."""
        submenu = self.get_submenu()
        opciones = []
        for op in submenu.get("opciones", []):
            if rol not in op.get("roles", []):
                continue
            # Si la opción requiere un objeto habilitado, verificamos
            requiere = op.get("requiere")
            if requiere and not self.esta_habilitado(requiere):
                continue
            opciones.append(op)
        return opciones

    def armar_menu(self, rol):
        """Arma el texto del submenú filtrado por rol y habilitación."""
        submenu = self.get_submenu()
        opciones = self.get_opciones_visibles(rol)
        lineas = [submenu.get("consulta", "")]
        lineas.append("")
        for op in opciones:
            lineas.append(op["texto"])
        return "\n".join(lineas)

    def resolver_activacion(self, comando, rol):
        """Resuelve qué opción del submenú activa el comando dado."""
        opciones = self.get_opciones_visibles(rol)
        for op in opciones:
            if comando in op.get("activacion", []):
                return op
        return None