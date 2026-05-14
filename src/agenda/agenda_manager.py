# src/agenda/agenda_manager.py
import json
import os
import uuid
from datetime import datetime
from src.tenant import data_path
from src.agenda.calendar_provider import CalendarProvider

_instancia = None


class AgendaManager:
    """
    Gestiona el CRUD de recordatorios en recordatorios.json.
    Singleton — se carga una vez y se reutiliza.
    Llama a CalendarProvider en cada operación para sincronización externa.
    Cuando se active M13, reemplazar CalendarProvider() por GoogleCalendarProvider().
    """

    PENDIENTE = "pendiente"
    ENVIADO = "enviado"

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, "data"):
            self.PATH = data_path("agenda", "recordatorios.json")
            self.CONFIG_PATH = data_path("agenda", "agenda_config.json")
            self.data = self._cargar()
            self.config = self._cargar_config()
            self.calendar = CalendarProvider()

    def _cargar_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cargar(self):
        if not os.path.exists(self.PATH):
            estructura = {"recordatorios": {}}
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar(self):
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def crear(self, persona_id, enlatado, entidad_id, fecha, hora, descripcion="", estado_vinculado=None, origen="manual"):
        """
        fecha: str DD/MM/YYYY
        hora: str HH:MM
        estado_vinculado: str estado de receta al que pertenece, o "*final*" para finales.
        origen: "manual" (visible al cliente) | "automatico" (oculto en la vista del cliente).
        Retorna recordatorio_id.
        """
        rid = str(uuid.uuid4())[:8]
        self.data["recordatorios"][rid] = {
            "persona_id": persona_id,
            "enlatado": enlatado,
            "entidad_id": entidad_id,
            "fecha": fecha,
            "hora": hora,
            "descripcion": descripcion,
            "estado": self.PENDIENTE,
            "estado_vinculado": estado_vinculado,
            "origen": origen,
            "google_event_id": None,
            "timestamp_creacion": datetime.now().isoformat(),
        }
        self._guardar()

        event_id = self.calendar.crear_evento(rid, persona_id, fecha, hora, descripcion, enlatado)
        if event_id:
            self.data["recordatorios"][rid]["google_event_id"] = event_id
            self._guardar()

        return rid

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get(self, recordatorio_id):
        """Retorna (id, datos) o None."""
        datos = self.data["recordatorios"].get(recordatorio_id)
        return (recordatorio_id, datos) if datos else None

    def buscar_por_persona(self, persona_id, estado=None, origen=None):
        """Retorna lista de dicts ordenados por fecha y hora."""
        resultado = [
            {"id": rid, **datos}
            for rid, datos in self.data["recordatorios"].items()
            if datos["persona_id"] == persona_id
            and (estado is None or datos["estado"] == estado)
            and (origen is None or datos.get("origen") == origen)
        ]
        return sorted(resultado, key=lambda x: (x.get("fecha", ""), x.get("hora", "")))

    def buscar_pendientes_vencidos(self):
        """Retorna recordatorios pendientes cuya fecha+hora ya pasó (para el scheduler local)."""
        ahora = datetime.now()
        resultado = []
        for rid, datos in self.data["recordatorios"].items():
            if datos["estado"] != self.PENDIENTE:
                continue
            try:
                dt = datetime.strptime(f"{datos['fecha']} {datos['hora']}", "%d/%m/%Y %H:%M")
                if dt <= ahora:
                    resultado.append({"id": rid, **datos})
            except ValueError:
                continue
        return resultado

    # ── MODIFICAR ESTADO ──────────────────────────────────────────────────────

    def cancelar_por_entidad_y_vinculo(self, entidad_id, estados_inflow, es_final=False, origen=None):
        """
        Elimina recordatorios de una entidad según estado_vinculado.
        - Si origen es None: respeta eliminacion_automatica de agenda_config.json.
        - Si origen está especificado: elimina solo los de ese origen, sin revisar config.
        - Elimina los que tienen estado_vinculado en estados_inflow.
        - Si es_final=True, elimina TODOS los pendientes de la entidad (del origen dado si aplica).
        Retorna lista de ids eliminados.
        """
        if origen is None and not self.config.get("eliminacion_automatica", False):
            return []
        eliminados = []
        for rid, datos in list(self.data["recordatorios"].items()):
            if datos.get("entidad_id") != entidad_id:
                continue
            if datos["estado"] != self.PENDIENTE:
                continue
            if origen is not None and datos.get("origen") != origen:
                continue
            vinculo = datos.get("estado_vinculado")
            if es_final or vinculo in estados_inflow:
                if datos.get("google_event_id"):
                    self.calendar.cancelar_evento(datos["google_event_id"])
                del self.data["recordatorios"][rid]
                eliminados.append(rid)
        if eliminados:
            self._guardar()
        return eliminados

    def cancelar(self, recordatorio_id):
        """
        Elimina un recordatorio pendiente.
        Retorna: "ok" | "no_encontrado" | "ya_enviado"
        """
        resultado = self.get(recordatorio_id)
        if not resultado:
            return "no_encontrado"
        _, datos = resultado
        if datos["estado"] == self.ENVIADO:
            return "ya_enviado"
        if datos.get("google_event_id"):
            self.calendar.cancelar_evento(datos["google_event_id"])
        del self.data["recordatorios"][recordatorio_id]
        self._guardar()
        return "ok"

    def marcar_enviado(self, recordatorio_id):
        resultado = self.get(recordatorio_id)
        if not resultado:
            return False
        _, datos = resultado
        if datos["estado"] != self.PENDIENTE:
            return False
        datos["estado"] = self.ENVIADO
        self._guardar()
        return True

    def modificar_fecha_hora(self, recordatorio_id, nueva_fecha, nueva_hora):
        """
        Modifica fecha y hora de un recordatorio pendiente.
        Retorna: "ok" | "no_encontrado" | "no_pendiente"
        """
        resultado = self.get(recordatorio_id)
        if not resultado:
            return "no_encontrado"
        _, datos = resultado
        if datos["estado"] != self.PENDIENTE:
            return "no_pendiente"
        datos["fecha"] = nueva_fecha
        datos["hora"] = nueva_hora
        self._guardar()

        if datos.get("google_event_id"):
            self.calendar.modificar_evento(datos["google_event_id"], nueva_fecha, nueva_hora)

        return "ok"
