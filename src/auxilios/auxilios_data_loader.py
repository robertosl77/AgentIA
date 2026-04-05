# src/auxilios/auxilios_data_loader.py
import json
import os

_instancia = None

class AuxiliosDataLoader:
    """
    Carga y gestiona datos operativos del módulo de auxilios desde auxilios_data.json.
    Singleton — se carga una vez y se reutiliza.
    Contiene: conductores, vehículos propios, vehículos auxiliados, servicios.
    """

    PATH = r"data\auxilios_data.json"

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.data = self._cargar_archivo()

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            estructura = {
                "conductores": [],
                "vehiculos_propios": [],
                "vehiculos_auxiliados": [],
                "servicios": []
            }
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def guardar(self):
        """Persiste el estado actual en auxilios_data.json."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CONDUCTORES ───────────────────────────────────────────────────────────

    def get_conductores(self):
        """Retorna la lista de conductores."""
        return self.data.get("conductores", [])

    def get_conductor_por_id(self, conductor_id):
        """Busca un conductor por su ID."""
        for c in self.get_conductores():
            if c.get("id") == conductor_id:
                return c
        return None

    def agregar_conductor(self, datos):
        """Agrega un conductor y persiste."""
        conductores = self.get_conductores()
        nuevo_id = max([c.get("id", 0) for c in conductores], default=0) + 1
        datos["id"] = nuevo_id
        conductores.append(datos)
        self.guardar()
        return nuevo_id

    def eliminar_conductor(self, conductor_id):
        """Elimina un conductor por ID y persiste."""
        conductores = self.get_conductores()
        self.data["conductores"] = [c for c in conductores if c.get("id") != conductor_id]
        self.guardar()

    # ── VEHÍCULOS PROPIOS ─────────────────────────────────────────────────────

    def get_vehiculos_propios(self):
        """Retorna la lista de vehículos propios."""
        return self.data.get("vehiculos_propios", [])

    def get_vehiculo_propio_por_id(self, vehiculo_id):
        """Busca un vehículo propio por su ID."""
        for v in self.get_vehiculos_propios():
            if v.get("id") == vehiculo_id:
                return v
        return None

    def agregar_vehiculo_propio(self, datos):
        """Agrega un vehículo propio y persiste."""
        vehiculos = self.get_vehiculos_propios()
        nuevo_id = max([v.get("id", 0) for v in vehiculos], default=0) + 1
        datos["id"] = nuevo_id
        vehiculos.append(datos)
        self.guardar()
        return nuevo_id

    def eliminar_vehiculo_propio(self, vehiculo_id):
        """Elimina un vehículo propio por ID y persiste."""
        vehiculos = self.get_vehiculos_propios()
        self.data["vehiculos_propios"] = [v for v in vehiculos if v.get("id") != vehiculo_id]
        self.guardar()

    # ── VEHÍCULOS AUXILIADOS ──────────────────────────────────────────────────

    def get_vehiculos_auxiliados(self):
        """Retorna la lista de vehículos auxiliados."""
        return self.data.get("vehiculos_auxiliados", [])

    def buscar_vehiculo_auxiliado(self, patente):
        """Busca un vehículo auxiliado por patente."""
        for v in self.get_vehiculos_auxiliados():
            if v.get("patente", "").upper() == patente.upper():
                return v
        return None

    def agregar_vehiculo_auxiliado(self, datos):
        """Agrega un vehículo auxiliado y persiste."""
        vehiculos = self.get_vehiculos_auxiliados()
        nuevo_id = max([v.get("id", 0) for v in vehiculos], default=0) + 1
        datos["id"] = nuevo_id
        vehiculos.append(datos)
        self.guardar()
        return nuevo_id

    # ── SERVICIOS ─────────────────────────────────────────────────────────────

    def get_servicios(self):
        """Retorna la lista de servicios registrados."""
        return self.data.get("servicios", [])

    def existe_nro_movimiento(self, nro_movimiento):
        """Verifica si ya existe un servicio con ese nro_movimiento."""
        for s in self.get_servicios():
            if s.get("nro_movimiento") == nro_movimiento:
                return True
        return False

    def agregar_servicio(self, datos):
        """Agrega un servicio y persiste."""
        servicios = self.get_servicios()
        nuevo_id = max([s.get("id", 0) for s in servicios], default=0) + 1
        datos["id"] = nuevo_id
        servicios.append(datos)
        self.guardar()
        return nuevo_id

    def eliminar_servicio(self, servicio_id):
        """Elimina un servicio por ID y persiste."""
        servicios = self.get_servicios()
        self.data["servicios"] = [s for s in servicios if s.get("id") != servicio_id]
        self.guardar()