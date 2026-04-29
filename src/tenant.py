# src/tenant.py
import json
import os

_tenant_id = None


def get_tenant_id() -> str:
    global _tenant_id
    if _tenant_id is None:
        config_path = os.path.join("data", "configuracion.json")
        with open(config_path, "r", encoding="utf-8") as f:
            _tenant_id = json.load(f).get("tenant_id", "default")
    return _tenant_id


def data_path(*parts) -> str:
    """
    Construye el path a un archivo de datos dentro del tenant activo.
    Uso: data_path("farmacia", "recetas.json") → "data/farmacia_core/farmacia/recetas.json"
    """
    return os.path.join("data", get_tenant_id(), *parts)
