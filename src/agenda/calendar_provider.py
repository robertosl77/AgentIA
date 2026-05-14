# src/agenda/calendar_provider.py


class CalendarProvider:
    """
    Abstracción del proveedor de calendario.
    Implementación local (no-op) — cuando se active M13 (OAuth2 Google),
    se reemplaza por GoogleCalendarProvider.
    """

    def crear_evento(self, recordatorio_id, persona_id, fecha, hora, descripcion, enlatado):
        """
        Crea un evento en el proveedor externo.
        Retorna google_event_id (str) o None si no hay proveedor activo.
        """
        return None

    def cancelar_evento(self, google_event_id):
        """Elimina o cancela el evento en el proveedor externo."""
        return True

    def modificar_evento(self, google_event_id, nueva_fecha, nueva_hora):
        """Actualiza fecha y hora del evento en el proveedor externo."""
        return True
