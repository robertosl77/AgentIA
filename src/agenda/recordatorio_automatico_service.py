# src/agenda/recordatorio_automatico_service.py
import json
import os
from datetime import datetime, timedelta
from src.tenant import data_path
from src.agenda.agenda_manager import AgendaManager
from src.agenda.validar_fecha_recordatorio import validar_fecha_recordatorio


class RecordatorioAutomaticoService:
    """
    Crea recordatorios automáticos vinculados a estados de receta.
    Orientado a Google Calendar: cada recordatorio genera un google_event_id
    al activar M13. Los recordatorios de seguimiento se cancelan vía B13
    al cambiar de estado.
    """

    def __init__(self, enlatado="farmacia"):
        self.enlatado = enlatado
        self.agenda = AgendaManager()
        config_path = data_path("agenda", "agenda_config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

    def _hora_defecto(self):
        return self.config.get("hora_defecto", {}).get(self.enlatado, "10:00")

    def _margen(self):
        return self.config.get("margen_minimo_dias", {}).get(self.enlatado, 2)

    def _seguimiento_horas(self):
        return self.config.get("seguimiento_automatico_horas", {}).get(self.enlatado, 24)

    def _flag(self, key):
        return self.config.get("recordatorios_automaticos", {}).get(self.enlatado, {}).get(key, False)

    def _dt_a_str(self, dt):
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")

    # ── B10 — vencimiento al cargar receta ────────────────────────────────────

    def crear_recordatorios_vencimiento(self, receta_id, persona_id, fecha_vencimiento_str):
        """
        Crea R1 y R2 al momento de crear la receta (B10).
        R1: fecha_vencimiento - margen_minimo_dias (si hay margen suficiente)
        R2: fecha_vencimiento mismo día
        Ambos con estado_vinculado="*final*".
        Retorna lista de rids creados.
        """
        creados = []
        hora = self._hora_defecto()

        try:
            f_venc = datetime.strptime(fecha_vencimiento_str, "%d/%m/%Y")
        except ValueError:
            return creados

        hoy = datetime.now().date()
        margen = self._margen()

        hora = self._hora_defecto()

        # R1
        if self._flag("vencimiento_r1"):
            f_r1 = f_venc - timedelta(days=margen)
            fecha_r1 = f_r1.strftime("%d/%m/%Y")
            ok, _ = validar_fecha_recordatorio(fecha_r1, hora, fecha_vencimiento_str, margen, modo="automatico")
            if ok:
                rid = self.agenda.crear(
                    persona_id=persona_id,
                    enlatado=self.enlatado,
                    entidad_id=receta_id,
                    fecha=fecha_r1,
                    hora=hora,
                    descripcion=f"⏰ Tu receta vence en {margen} días ({fecha_vencimiento_str}). Verificá su estado.",
                    estado_vinculado="*final*",
                    origen="automatico",
                )
                creados.append(rid)

        # R2 — dispara el mismo día del vencimiento; no pasa por validar_fecha_recordatorio
        # porque fecha == fecha_vencimiento es válido solo en este caso específico.
        if self._flag("vencimiento_r2") and f_venc.date() >= hoy:
            fecha_r2 = f_venc.strftime("%d/%m/%Y")
            rid = self.agenda.crear(
                persona_id=persona_id,
                enlatado=self.enlatado,
                entidad_id=receta_id,
                fecha=fecha_r2,
                hora=hora,
                descripcion=f"⚠️ Tu receta vence HOY ({fecha_vencimiento_str}). Retirá tu medicación.",
                estado_vinculado="*final*",
                origen="automatico",
            )
            creados.append(rid)

        return creados

    # ── B11/B12/B16 — seguimiento al cliente por estado ───────────────────────

    def crear_seguimiento_cliente(self, receta_id, persona_id, fecha_vencimiento_str,
                                   estado_vinculado, descripcion, flag_key):
        """
        Crea recordatorio de seguimiento para el cliente al entrar a un estado.
        Si delta >= seguimiento_automatico_horas → crea recordatorio.
        Si delta < seguimiento_automatico_horas → retorna push_urgente=True.
        Retorna dict: {"creado": bool, "rid": str|None, "push_urgente": bool, "msg_urgente": str}
        """
        resultado = {"creado": False, "rid": None, "push_urgente": False, "msg_urgente": ""}

        if not self._flag(flag_key):
            return resultado

        try:
            f_venc = datetime.strptime(fecha_vencimiento_str, "%d/%m/%Y")
        except ValueError:
            return resultado

        ahora = datetime.now()
        horas = self._seguimiento_horas()
        delta_horas = (f_venc - ahora).total_seconds() / 3600

        if delta_horas >= horas:
            f_rec = ahora + timedelta(hours=horas)
            fecha_str, hora_str = self._dt_a_str(f_rec)
            ok, _ = validar_fecha_recordatorio(
                fecha_str, hora_str, fecha_vencimiento_str, 0, modo="automatico"
            )
            if ok:
                rid = self.agenda.crear(
                    persona_id=persona_id,
                    enlatado=self.enlatado,
                    entidad_id=receta_id,
                    fecha=fecha_str,
                    hora=hora_str,
                    descripcion=descripcion,
                    estado_vinculado=estado_vinculado,
                    origen="automatico",
                )
                resultado["creado"] = True
                resultado["rid"] = rid
        else:
            resultado["push_urgente"] = True
            resultado["msg_urgente"] = (
                f"⚠️ Tu receta está por vencer ({fecha_vencimiento_str}) y tiene acciones pendientes. "
                "Ingresá a *Mis recetas* para resolverlas."
            )

        return resultado

    # ── B14 — seguimiento al staff por estado ────────────────────────────────

    def crear_seguimiento_staff(self, receta_id, fecha_vencimiento_str,
                                 estado_vinculado, descripcion, flag_key,
                                 operadores_lids):
        """
        Crea recordatorio de seguimiento para TODOS los operadores del tenant (B14).
        operadores_lids: lista de LIDs de operadores desde farmacia_config.
        Retorna dict: {"creados": list, "push_urgente": bool, "msg_urgente": str}
        """
        resultado = {"creados": [], "push_urgente": False, "msg_urgente": ""}

        if not self._flag(flag_key):
            return resultado

        try:
            f_venc = datetime.strptime(fecha_vencimiento_str, "%d/%m/%Y")
        except ValueError:
            return resultado

        ahora = datetime.now()
        horas = self._seguimiento_horas()
        delta_horas = (f_venc - ahora).total_seconds() / 3600

        if delta_horas >= horas:
            f_rec = ahora + timedelta(hours=horas)
            fecha_str, hora_str = self._dt_a_str(f_rec)
            ok, _ = validar_fecha_recordatorio(
                fecha_str, hora_str, fecha_vencimiento_str, 0, modo="automatico"
            )
            if ok:
                for lid in operadores_lids:
                    rid = self.agenda.crear(
                        persona_id=lid,
                        enlatado=self.enlatado,
                        entidad_id=receta_id,
                        fecha=fecha_str,
                        hora=hora_str,
                        descripcion=descripcion,
                        estado_vinculado=estado_vinculado,
                        origen="automatico",
                    )
                    resultado["creados"].append(rid)
        else:
            resultado["push_urgente"] = True
            resultado["msg_urgente"] = descripcion

        return resultado
