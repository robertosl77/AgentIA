# testing/reset_data.py
import json
import os
import glob
import uuid
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
    """Limpia TODAS las asociaciones de obras sociales (uso manual/independiente)."""
    path = get_tenant_path("farmacia", "obras_sociales.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["asociaciones"] = {}
    guardar(path, data)


def reset_vinculaciones():
    """Limpia TODAS las vinculaciones (uso manual/independiente)."""
    guardar(get_tenant_path("farmacia", "vinculaciones.json"), {"vinculaciones": {}})


def reset_personas():
    """
    Limpia personas de rol usuario en cascada.
    Preserva personas cuyos lids tengan rol root/admin/supervisor en sesiones.json.
    Cascade sobre: direcciones físicas, vinculaciones, obras sociales.
    """
    # 1. Lids con rol privilegiado
    sesiones_path = get_tenant_path("sesiones.json")
    with open(sesiones_path, encoding="utf-8") as f:
        sesiones = json.load(f).get("sesiones", {})
    lids_privilegiados = {
        lid for lid, s in sesiones.items()
        if s.get("rol") in {"root", "admin", "supervisor"}
    }

    # 2. Clasificar personas
    personas_path = get_tenant_path("persona", "personas.json")
    with open(personas_path, encoding="utf-8") as f:
        personas_data = json.load(f)

    ids_conservar = set()
    ids_borrar = set()
    for pid, p in personas_data["personas"].items():
        if set(p.get("lids", [])) & lids_privilegiados:
            ids_conservar.add(pid)
        else:
            ids_borrar.add(pid)

    if not ids_borrar:
        print("✅ personas.json — nada que borrar")
        return

    # 3. Cascade direcciones: conservar solo las que referencian personas que quedan
    dir_ids_conservar = {
        d["direccion_id"]
        for pid in ids_conservar
        for d in personas_data["personas"][pid].get("direcciones", [])
    }
    dir_path = get_tenant_path("persona", "direcciones.json")
    with open(dir_path, encoding="utf-8") as f:
        dir_data = json.load(f)
    dir_data["direcciones"] = {
        did: datos for did, datos in dir_data["direcciones"].items()
        if did in dir_ids_conservar
    }
    guardar(dir_path, dir_data)

    # 4. Cascade vinculaciones: borrar las que involucran personas borradas
    vinc_path = get_tenant_path("farmacia", "vinculaciones.json")
    with open(vinc_path, encoding="utf-8") as f:
        vinc_data = json.load(f)
    vinc_data["vinculaciones"] = {
        vid: v for vid, v in vinc_data["vinculaciones"].items()
        if v["persona_a"]["persona_id"] not in ids_borrar
        and v["persona_b"]["persona_id"] not in ids_borrar
    }
    guardar(vinc_path, vinc_data)

    # 5. Cascade obras sociales: desligar personas borradas; eliminar asociacion si queda vacía
    os_path = get_tenant_path("farmacia", "obras_sociales.json")
    with open(os_path, encoding="utf-8") as f:
        os_data = json.load(f)
    nuevas_asoc = {}
    for aid, asoc in os_data.get("asociaciones", {}).items():
        restantes = [p for p in asoc.get("personas", []) if p not in ids_borrar]
        if restantes:
            asoc["personas"] = restantes
            nuevas_asoc[aid] = asoc
    os_data["asociaciones"] = nuevas_asoc
    guardar(os_path, os_data)

    # 6. Borrar personas
    personas_data["personas"] = {
        pid: p for pid, p in personas_data["personas"].items()
        if pid in ids_conservar
    }
    guardar(personas_path, personas_data)


def reset_conductores():
    """Limpia solo personas de tipo auxilio_conductor (uso manual/independiente)."""
    path = get_tenant_path("persona", "personas.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["personas"] = {
        pid: p for pid, p in data["personas"].items()
        if "auxilio_conductor" not in p.get("tipo_persona", [])
    }
    guardar(path, data)


def reset_direcciones():
    """Limpia TODAS las direcciones físicas (uso manual/independiente)."""
    path = get_tenant_path("persona", "direcciones.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["direcciones"] = {}
    guardar(path, data)


def reset_error_log():
    guardar(get_tenant_path("error_log.json"), {"errores": []})


def reset_servicios_data():
    guardar(get_tenant_path("auxilio", "servicios_data.json"), {"servicios": []})


def reset_vehiculos():
    path = get_tenant_path("persona", "vehiculos.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["vehiculos"] = {}
    guardar(path, data)


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


def seed_recetas_testing():
    """
    Genera recetas de prueba para testear el flujo en_consulta y acciones del cliente.

    Escenario A — en_consulta:
        Receta con 2 items (sin_stock + alternativa_ofrecida).
        El cliente ya consultó sobre el sin_stock → receta en en_consulta.
        El farmacéutico ve la consulta pendiente y puede responderla.

    Escenario B — a_la_espera:
        Receta con 1 item alternativa_ofrecida sin ninguna acción del cliente.
        El cliente ve la acción pendiente con opciones: aceptar/rechazar/esperar/consultar.

    Requiere que exista al menos una persona en personas.json.
    """
    # Leer persona para usar como paciente
    personas_path = get_tenant_path("persona", "personas.json")
    with open(personas_path, encoding="utf-8") as f:
        personas_data = json.load(f)
    if not personas_data["personas"]:
        print("⚠️  seed_recetas_testing — no hay personas, se omite")
        return
    persona_id = next(iter(personas_data["personas"]))

    # Leer u crear medicamentos de prueba
    med_path = get_tenant_path("farmacia", "medicamentos.json")
    with open(med_path, encoding="utf-8") as f:
        med_data = json.load(f)

    def get_or_create_med(farmaco, dosis, presentacion):
        for mid, m in med_data["medicamentos"].items():
            if m["farmaco"] == farmaco and m["dosis"] == dosis:
                return mid
        mid = str(uuid.uuid4())
        med_data["medicamentos"][mid] = {
            "farmaco": farmaco, "dosis": dosis, "presentacion": presentacion,
            "label": f"{farmaco} {dosis} {presentacion}"
        }
        return mid

    mid_a = get_or_create_med("HIDROTISONA", "10 mg", "comp.x 30")
    mid_b = get_or_create_med("LIPOMAX 105", "105 mg", "comp.x 30")
    guardar(med_path, med_data)

    ahora = datetime.now()
    ts = ahora.isoformat()
    fecha_hoy = ahora.strftime("%d/%m/%Y")
    fecha_venc = (ahora + timedelta(days=28)).strftime("%d/%m/%Y")

    def make_item(mid, cant, estado):
        return {"medicamento_id": mid, "cantidad_receta": cant,
                "cantidad_solicitada": cant, "estado_item": estado}

    # ── Escenario A: en_consulta ─────────────────────────────────────────────
    receta_id_a = str(uuid.uuid4())
    receta_a = {
        "persona_id": persona_id,
        "obra_social_id": None,
        "credencial_validada": False,
        "fecha_creacion": fecha_hoy,
        "fecha_validez_desde": fecha_hoy,
        "fecha_vencimiento": fecha_venc,
        "medico": {"nombre": "Dra. Prueba", "matricula": "12345", "especialidad": "Clínica"},
        "diagnostico": "Testing en_consulta",
        "items": [
            make_item(mid_a, 2, "sin_stock"),
            make_item(mid_b, 1, "alternativa_ofrecida"),
        ],
        "estado": "en_consulta",
        "operador_id": persona_id,
        "receta_url": None,
        "notas": [],
        "chat": [
            # Farmacia notifica sin_stock sobre mid_a
            {"id": "c001", "autor": "farmacia", "tipo": "sin_stock",
             "mensaje": "HIDROTISONA 10 mg no está disponible (sin stock). ¿Esperás o cancelás?",
             "medicamento_id": mid_a, "timestamp": ts, "leido_por": ["farmacia", persona_id]},
            # Farmacia ofrece alternativa para mid_b
            {"id": "c002", "autor": "farmacia", "tipo": "alternativa",
             "mensaje": "No tenemos LIPOMAX 105 disponible. Ofrecemos como alternativa: LIPOMAX GENÉRICO 105 mg. ¿Lo aceptás?",
             "medicamento_id": mid_b, "timestamp": ts, "leido_por": ["farmacia", persona_id]},
            # Cliente consulta sobre el sin_stock (mid_a) — genera la transición H→M
            {"id": "c003", "autor": persona_id, "tipo": "consulta",
             "mensaje": "¿Cuándo van a tener stock?",
             "medicamento_id": mid_a, "timestamp": ts, "leido_por": [persona_id]},
        ],
        "historial_estados": [
            {"estado": "pendiente",    "timestamp": ts, "motivo": "Receta cargada por usuario"},
            {"estado": "en_gestion",   "timestamp": ts, "motivo": "Farmacia procesando"},
            {"estado": "a_la_espera",  "timestamp": ts, "motivo": "Items procesados — esperando respuesta del cliente"},
            {"estado": "en_consulta",  "timestamp": ts, "motivo": "Cliente consulta sobre medicamento"},
        ]
    }

    # ── Escenario B: a_la_espera ─────────────────────────────────────────────
    receta_id_b = str(uuid.uuid4())
    receta_b = {
        "persona_id": persona_id,
        "obra_social_id": None,
        "credencial_validada": False,
        "fecha_creacion": fecha_hoy,
        "fecha_validez_desde": fecha_hoy,
        "fecha_vencimiento": fecha_venc,
        "medico": {"nombre": "Dr. Ejemplo", "matricula": "99999", "especialidad": "Clínica"},
        "diagnostico": "Testing a_la_espera",
        "items": [
            make_item(mid_b, 1, "alternativa_ofrecida"),
        ],
        "estado": "a_la_espera",
        "operador_id": persona_id,
        "receta_url": None,
        "notas": [],
        "chat": [
            # Farmacia ofrece alternativa — pendiente de respuesta del cliente
            {"id": "d001", "autor": "farmacia", "tipo": "alternativa",
             "mensaje": "No tenemos LIPOMAX 105 disponible. Ofrecemos como alternativa: LIPOMAX GENÉRICO 105 mg. ¿Lo aceptás?",
             "medicamento_id": mid_b, "timestamp": ts, "leido_por": ["farmacia"]},
        ],
        "historial_estados": [
            {"estado": "pendiente",   "timestamp": ts, "motivo": "Receta cargada por usuario"},
            {"estado": "en_gestion",  "timestamp": ts, "motivo": "Farmacia procesando"},
            {"estado": "a_la_espera", "timestamp": ts, "motivo": "Items procesados — esperando respuesta del cliente"},
        ]
    }

    recetas_path = get_tenant_path("farmacia", "recetas.json")
    with open(recetas_path, encoding="utf-8") as f:
        recetas_data = json.load(f)
    recetas_data["recetas"][receta_id_a] = receta_a
    recetas_data["recetas"][receta_id_b] = receta_b
    guardar(recetas_path, recetas_data)
    print(f"   ├ Escenario A (en_consulta):  {receta_id_a[:8]}...")
    print(f"   └ Escenario B (a_la_espera):  {receta_id_b[:8]}...")


if __name__ == "__main__":
    print("🔄 Reseteando datos del tenant...\n")

    print("── común ────────────────────────────────")
    reset_sesiones()
    reset_error_log()

    print("── farmacia ─────────────────────────────")
    reset_recetas()
    reset_medicamentos()
    reset_horarios_data()
    reset_archivos_recetas()
    print("── seed testing ─────────────────────────")
    seed_recetas_testing()

    print("── auxilio ──────────────────────────────")
    reset_servicios_data()
    reset_vehiculos()

    print("── persona (con cascade) ────────────────")
    reset_personas()

    print("\n✅ Reset completo.")
