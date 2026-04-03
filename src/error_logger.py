# src/error_logger.py
import json
import os
import traceback
from datetime import datetime

class ErrorLogger:
    """
    Registra errores técnicos en error_log.json.
    Responsabilidades:
        - Registrar errores con timestamp, usuario, comando y traceback
        - Listar errores sin resolver
        - Marcar errores como resueltos
        - Preparado para mostrarse desde el panel root
    """

    PATH = r"data\error_log.json"

    def __init__(self):
        self.data = self._cargar_archivo()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        """Carga el archivo de errores. Si no existe, lo crea con estructura vacía."""
        if not os.path.exists(self.PATH):
            estructura = {"errores": []}
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        """Persiste el estado actual en el archivo JSON."""
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── REGISTRO DE ERRORES ───────────────────────────────────────────────────

    def registrar(self, numero, comando, excepcion):
        """
        Registra un error técnico con todos sus datos.
        numero: LID o número del usuario que generó el error
        comando: texto que mandó el usuario cuando ocurrió el error
        excepcion: la excepción capturada en el except
        """
        error = {
            "id": len(self.data["errores"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "numero": numero,
            "comando": comando,
            "traceback": traceback.format_exc(),
            "resuelto": False
        }
        self.data["errores"].append(error)
        self._guardar_archivo()
        print(f"🔴 Error registrado [#{error['id']}]: {excepcion}")

    # ── CONSULTAS ─────────────────────────────────────────────────────────────

    def get_errores_sin_resolver(self):
        """Retorna la lista de errores que aún no fueron marcados como resueltos."""
        return [e for e in self.data["errores"] if not e.get("resuelto")]

    def get_cantidad_sin_resolver(self):
        """Retorna la cantidad de errores sin resolver."""
        return len(self.get_errores_sin_resolver())

    def marcar_resuelto(self, error_id):
        """Marca un error como resuelto por su ID."""
        for error in self.data["errores"]:
            if error["id"] == error_id:
                error["resuelto"] = True
                self._guardar_archivo()
                return True
        return False

    def marcar_todos_resueltos(self):
        """Marca todos los errores pendientes como resueltos."""
        for error in self.data["errores"]:
            error["resuelto"] = True
        self._guardar_archivo()