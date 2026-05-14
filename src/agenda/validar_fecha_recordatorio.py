# src/agenda/validar_fecha_recordatorio.py
from datetime import datetime, date


def validar_fecha_recordatorio(fecha_str, hora_str, fecha_vencimiento_str, margen_minimo_dias, modo="manual"):
    """
    Valida que una fecha/hora sea apta para crear un recordatorio vinculado a una receta.

    modo "manual"  → devuelve (ok, mensaje_error) para mostrar al usuario.
    modo "automatico" → devuelve (ok, None); falla = skip silencioso.

    Validaciones (en orden):
      1. Formato fecha DD/MM/YYYY y hora HH:MM.
      2. fecha > hoy; si es hoy, hora > hora actual.
      3. fecha < fecha_vencimiento.
      4. (fecha_vencimiento - fecha).days >= margen_minimo_dias.

    La validación de día laborable (horarios_service) se aplica SOLO en modo "manual"
    y es responsabilidad del caller antes de invocar esta función.
    """
    try:
        fecha = datetime.strptime(fecha_str, "%d/%m/%Y").date()
    except ValueError:
        return False, "Formato de fecha inválido. Usá DD/MM/AAAA."

    try:
        hora_parts = hora_str.split(":")
        hora_dt = datetime.now().replace(
            hour=int(hora_parts[0]), minute=int(hora_parts[1]), second=0, microsecond=0
        )
    except (ValueError, IndexError):
        return False, "Formato de hora inválido. Usá HH:MM."

    try:
        fecha_venc = datetime.strptime(fecha_vencimiento_str, "%d/%m/%Y").date()
    except ValueError:
        return False, "Fecha de vencimiento inválida."

    ahora = datetime.now()
    hoy = ahora.date()

    if fecha < hoy:
        return False, "La fecha debe ser hoy o posterior."
    if fecha == hoy and int(hora_parts[0]) * 60 + int(hora_parts[1]) <= ahora.hour * 60 + ahora.minute:
        return False, "La hora ya pasó para hoy. Elegí una hora futura."

    if fecha >= fecha_venc:
        return False, f"La fecha debe ser anterior al vencimiento ({fecha_vencimiento_str})."

    delta = (fecha_venc - fecha).days
    if delta < margen_minimo_dias:
        return False, (
            f"Quedan solo {delta} día(s) hasta el vencimiento. "
            f"El recordatorio debe ser al menos {margen_minimo_dias} día(s) antes."
        )

    return True, None
