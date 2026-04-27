# testing/reset_data.py
import json
import os
import glob
from datetime import datetime, timedelta

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_PATH = os.path.join(ROOT, "data", "configuracion.json")


def get_tenant_path(*parts):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        tenant_id = json.load(f).get("tenant_id", "demo")
    return os.path.join(ROOT, "data", tenant_id, *parts)


def guardar(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ {os.path.relpath(path, ROOT)}")


def reset_sesiones():
    path = get_tenant_path("sesiones.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    roles_conservar = {"root", "admin"}
    data["sesiones"] = {
        k: v for k, v in data["sesiones"].items()
        if v.get("rol") in roles_conservar
    }
    guardar(path, data)


def reset_recetas():
    guardar(get_tenant_path("farmacia", "recetas.json"), {"recetas": {}})


def reset_medicamentos():
    guardar(get_tenant_path("farmacia", "medicamentos.json"), {"medicamentos": {}})


def reset_obras_sociales():
    path = get_tenant_path("farmacia", "obras_sociales.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["asociaciones"] = {}
    guardar(path, data)


def reset_vinculaciones():
    guardar(get_tenant_path("farmacia", "vinculaciones.json"), {"vinculaciones": {}})


def reset_personas():
    """Limpia personas de tipo farmacia_cliente (preserva conductores y catálogos)."""
    path = get_tenant_path("persona", "personas.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["personas"] = {
        pid: p for pid, p in data["personas"].items()
        if "farmacia_cliente" not in p.get("tipo_persona", [])
    }
    guardar(path, data)


def reset_conductores():
    """Limpia personas de tipo auxilio_conductor (preserva farmacia_cliente y catálogos)."""
    path = get_tenant_path("persona", "personas.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["personas"] = {
        pid: p for pid, p in data["personas"].items()
        if "auxilio_conductor" not in p.get("tipo_persona", [])
    }
    guardar(path, data)


def reset_direcciones():
    guardar(get_tenant_path("persona", "direcciones.json"), {"direcciones": {}})


def reset_error_log():
    guardar(get_tenant_path("error_log.json"), {"errores": []})


def reset_auxilios_data():
    guardar(get_tenant_path("auxilio", "auxilios_data.json"), {
        "vehiculos_propios": [],
        "vehiculos_auxiliados": [],
        "servicios": []
    })


def reset_horarios_data():
    path = get_tenant_path("farmacia", "horarios_data.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    hoy = datetime.now().date()

    # dias_de_guardia: un solo día a hoy + 5, preserva config
    data["dias_de_guardia"]["fechas"] = [
        (hoy + timedelta(days=5)).strftime("%Y-%m-%d")
    ]

    # cierres_eventuales: un rango desde hoy+7 hasta hoy+12, preserva config
    data["cierres_eventuales"]["datos"] = [
        {
            "desde": (hoy + timedelta(days=7)).strftime("%Y-%m-%d"),
            "hasta": (hoy + timedelta(days=12)).strftime("%Y-%m-%d"),
            "motivo": "cierre de prueba"
        }
    ]

    guardar(path, data)


def reset_archivos_recetas():
    carpeta = get_tenant_path("archivos", "recetas")
    if not os.path.exists(carpeta):
        return
    archivos = glob.glob(os.path.join(carpeta, "*"))
    for archivo in archivos:
        os.remove(archivo)
    print(f"✅ archivos/recetas/ — {len(archivos)} archivo(s) eliminado(s)")


if __name__ == "__main__":
    print("🔄 Reseteando datos del tenant...\n")

    print("── común ────────────────────────────────")
    reset_sesiones()
    reset_error_log()

    print("── farmacia ─────────────────────────────")
    reset_recetas()
    reset_medicamentos()
    reset_obras_sociales()
    reset_vinculaciones()
    reset_horarios_data()
    reset_archivos_recetas()

    print("── auxilio ──────────────────────────────")
    reset_auxilios_data()
    reset_conductores()

    print("── persona ──────────────────────────────")
    reset_personas()
    reset_direcciones()

    print("\n✅ Reset completo.")
