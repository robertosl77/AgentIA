# src/horarios/horarios_service.py
from datetime import date, timedelta
from src.horarios.data_loader import DataLoader

_TRADUCCION_DIAS = {
    "monday": "lunes", "tuesday": "martes", "wednesday": "miercoles",
    "thursday": "jueves", "friday": "viernes", "saturday": "sabado", "sunday": "domingo"
}

DIAS_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}


def es_dia_laborable(fecha: date) -> bool:
    """
    Retorna True si `fecha` es día laborable.
    Prioridad: cierres eventuales > días de guardia > horarios fijos.
    """
    datos = DataLoader().data
    fecha_str = fecha.strftime("%Y-%m-%d")

    for c in datos.get("cierres_eventuales", {}).get("datos", []):
        try:
            f_desde = date.fromisoformat(c["desde"])
            f_hasta = date.fromisoformat(c["hasta"])
            if f_desde <= fecha <= f_hasta:
                return False
        except (ValueError, KeyError):
            continue

    if fecha_str in datos.get("dias_de_guardia", {}).get("fechas", []):
        return True

    dia_json = _TRADUCCION_DIAS[fecha.strftime("%A").lower()]
    config_dia = datos.get("horarios_fijos", {}).get("dias", {}).get(dia_json, {})
    return config_dia.get("abierto", False)


def dias_laborables_cercanos(fecha: date, cantidad: int = 3, limite_max: date = None) -> list:
    """
    Retorna hasta `cantidad` días laborables antes y después de `fecha`.
    Si `limite_max` se especifica, no incluye días posteriores a ese límite.
    """
    anteriores = []
    dia = fecha - timedelta(days=1)
    while len(anteriores) < cantidad:
        if (fecha - dia).days > 60:
            break
        if es_dia_laborable(dia):
            anteriores.insert(0, dia)
        dia -= timedelta(days=1)

    posteriores = []
    dia = fecha + timedelta(days=1)
    while len(posteriores) < cantidad:
        if (dia - fecha).days > 60:
            break
        if limite_max and dia > limite_max:
            break
        if es_dia_laborable(dia):
            posteriores.append(dia)
        dia += timedelta(days=1)

    return anteriores + posteriores
