# src/agenda/recordatorio_service.py
import json
import os
from datetime import datetime, date, timedelta
from src.send_wpp import SendWPP
from src.tenant import data_path
from src.agenda.agenda_manager import AgendaManager
from src.horarios.horarios_service import es_dia_laborable, dias_laborables_cercanos, DIAS_ES


def _cargar_config():
    path = data_path("agenda", "agenda_config.json")
    if not os.path.exists(path):
        return {"hora_defecto": {"farmacia": "10:00"}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class RecordatorioService:
    """
    Handler conversacional para gestión de recordatorios.
    Flujos: ver/cancelar/modificar (desde mis_recordatorios) y crear (desde acciones M7).
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.manager = AgendaManager()
        self.config = _cargar_config()

    # ── API PÚBLICA ───────────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        return getattr(sesiones[self.numero], "agenda_estado", None) is not None

    def iniciar_ver(self, sesiones, persona_id, enlatado="farmacia"):
        """Punto de entrada desde el handler mis_recordatorios."""
        sesiones[self.numero].agenda_persona_id = persona_id
        sesiones[self.numero].agenda_enlatado = enlatado
        sesiones[self.numero].agenda_reintentos = 0
        self._mostrar_ver(sesiones)

    def iniciar_crear(self, sesiones, persona_id, enlatado, entidad_id, descripcion, fecha_max=None, pedir_descripcion=False, estado_vinculado=None):
        """
        Punto de entrada desde el flujo de acciones (M7) y staff (M14).
        fecha_max: str DD/MM/YYYY | None — límite superior de fecha (vencimiento receta).
        pedir_descripcion: si True, pide descripción libre antes de fecha/hora (M14).
        estado_vinculado: str | None — vincula el recordatorio a un estado para que B13 lo cancele.
        En entornos dv/qa la fecha/hora se fija automáticamente a now+5min.
        """
        sesiones[self.numero].agenda_persona_id = persona_id
        sesiones[self.numero].agenda_enlatado = enlatado
        sesiones[self.numero].agenda_entidad_id = entidad_id
        sesiones[self.numero].agenda_descripcion = descripcion
        sesiones[self.numero].agenda_fecha_max = fecha_max
        sesiones[self.numero].agenda_estado_vinculado = estado_vinculado
        sesiones[self.numero].agenda_opciones_fecha = None
        sesiones[self.numero].agenda_reintentos = 0

        if pedir_descripcion:
            sesiones[self.numero].agenda_estado = "crear_descripcion"
            self.sw.enviar("📝 ¿Para qué es el recordatorio? (texto libre)\n\nEscribí *cancelar* para volver:")
            return

        self._iniciar_crear_fecha(sesiones, descripcion, enlatado)

    def _iniciar_crear_fecha(self, sesiones, descripcion, enlatado):
        if self._es_entorno_test():
            fecha_str, hora_str = self._get_fecha_hora_test()
            sesiones[self.numero].agenda_nueva_fecha = fecha_str
            sesiones[self.numero].agenda_nueva_hora = hora_str
            sesiones[self.numero].agenda_estado = "crear_confirmar"
            self.sw.enviar(
                f"[{self.config['entorno'].upper()}] Recordatorio en 5 min:\n"
                f"*{descripcion}*\n"
                f"📅 {fecha_str} a las {hora_str}\n\n"
                f"¿Confirmás? (si/no)"
            )
            return

        sesiones[self.numero].agenda_estado = "crear_fecha"
        hora_def = self.config.get("hora_defecto", {}).get(enlatado, "10:00")
        self.sw.enviar(
            f"📅 ¿Para qué día querés el recordatorio? (DD/MM/AAAA)\n"
            f"_Hora por defecto: {hora_def}_"
        )

    def contar_pendientes(self, persona_id):
        """Retorna la cantidad de recordatorios manuales pendientes (para badge en el menú)."""
        return len(self.manager.buscar_por_persona(persona_id, estado=AgendaManager.PENDIENTE, origen="manual"))

    def procesar(self, comando, sesiones):
        estado = getattr(sesiones[self.numero], "agenda_estado", None)
        if estado == "ver":
            self._procesar_ver(comando, sesiones)
        elif estado == "cancelar_lista":
            self._procesar_cancelar_lista(comando, sesiones)
        elif estado == "cancelar_confirmar":
            self._procesar_cancelar_confirmar(comando, sesiones)
        elif estado == "modificar_nueva_fecha":
            self._procesar_modificar_fecha(comando, sesiones)
        elif estado == "modificar_nueva_hora":
            self._procesar_modificar_hora(comando, sesiones)
        elif estado == "modificar_lista":
            self._procesar_modificar_lista(comando, sesiones)
        elif estado == "modificar_confirmar":
            self._procesar_modificar_confirmar(comando, sesiones)
        elif estado == "crear_descripcion":
            self._procesar_crear_descripcion(comando, sesiones)
        elif estado == "crear_fecha":
            self._procesar_crear_fecha(comando, sesiones)
        elif estado == "crear_hora":
            self._procesar_crear_hora(comando, sesiones)
        elif estado == "crear_confirmar":
            self._procesar_crear_confirmar(comando, sesiones)

    # ── VER ───────────────────────────────────────────────────────────────────

    def _mostrar_ver(self, sesiones):
        persona_id = getattr(sesiones[self.numero], "agenda_persona_id", None)
        pendientes = self.manager.buscar_por_persona(persona_id, estado=AgendaManager.PENDIENTE, origen="manual")

        if not pendientes:
            self.sw.enviar("📭 No tenés recordatorios pendientes.")
            self._salir(sesiones)
            return

        sesiones[self.numero].agenda_lista = pendientes
        sesiones[self.numero].agenda_estado = "ver"
        sesiones[self.numero].agenda_reintentos = 0

        lineas = ["⏰ *Mis recordatorios pendientes:*", ""]
        for i, r in enumerate(pendientes, 1):
            lineas.append(f"{i}. {r.get('descripcion', 'Recordatorio')}")
            lineas.append(f"   📅 {r['fecha']} a las {r['hora']}")
            lineas.append("")

        lineas.append("A. ❌ Cancelar un recordatorio")
        lineas.append("B. ✏️ Modificar fecha")
        lineas.append("_Escribí 'salir' para volver_")
        self.sw.enviar("\n".join(lineas))

    def _procesar_ver(self, comando, sesiones):
        c = comando.strip().lower()
        if c == "salir":
            self._salir(sesiones)
            return
        if c == "a":
            sesiones[self.numero].agenda_estado = "cancelar_lista"
            self._mostrar_lista_para_seleccion(sesiones, "cancelar")
        elif c == "b":
            if self._es_entorno_test():
                fecha_str, hora_str = self._get_fecha_hora_test()
                sesiones[self.numero].agenda_nueva_fecha = fecha_str
                sesiones[self.numero].agenda_nueva_hora = hora_str
                sesiones[self.numero].agenda_estado = "modificar_lista"
                self.sw.enviar(
                    f"[{self.config['entorno'].upper()}] Nueva fecha/hora: {fecha_str} a las {hora_str}"
                )
                self._mostrar_lista_para_seleccion(sesiones, "modificar")
                return
            sesiones[self.numero].agenda_estado = "modificar_nueva_fecha"
            sesiones[self.numero].agenda_opciones_fecha = None
            enlatado = getattr(sesiones[self.numero], "agenda_enlatado", "farmacia")
            hora_def = self.config.get("hora_defecto", {}).get(enlatado, "10:00")
            self.sw.enviar(
                f"📅 Ingresá la nueva fecha para el recordatorio (DD/MM/AAAA):\n"
                f"_Hora por defecto: {hora_def}_"
            )
        else:
            reintentos = getattr(sesiones[self.numero], "agenda_reintentos", 0) + 1
            sesiones[self.numero].agenda_reintentos = reintentos
            if reintentos >= 3:
                self._salir(sesiones)
            else:
                self.sw.enviar("❌ Opción no válida. Escribí A, B o 'salir'.")

    # ── CANCELAR ──────────────────────────────────────────────────────────────

    def _mostrar_lista_para_seleccion(self, sesiones, modo):
        lista = getattr(sesiones[self.numero], "agenda_lista", [])
        accion = "cancelar" if modo == "cancelar" else "modificar"
        lineas = [f"¿Cuál querés {accion}? Ingresá el número:", ""]
        for i, r in enumerate(lista, 1):
            lineas.append(f"{i}. {r.get('descripcion', 'Recordatorio')}")
            lineas.append(f"   📅 {r['fecha']} a las {r['hora']}")
        lineas.append("\n_Escribí 'cancelar' para volver_")
        self.sw.enviar("\n".join(lineas))

    def _procesar_cancelar_lista(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._mostrar_ver(sesiones)
            return
        lista = getattr(sesiones[self.numero], "agenda_lista", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(lista):
                raise ValueError
        except ValueError:
            self.sw.enviar(f"❌ Ingresá un número del 1 al {len(lista)} o 'cancelar':")
            return
        seleccionado = lista[idx]
        sesiones[self.numero].agenda_seleccion_id = seleccionado["id"]
        sesiones[self.numero].agenda_estado = "cancelar_confirmar"
        self.sw.enviar(
            f"⚠️ Vas a cancelar:\n"
            f"*{seleccionado.get('descripcion', 'Recordatorio')}*\n"
            f"📅 {seleccionado['fecha']} a las {seleccionado['hora']}\n\n"
            f"¿Confirmás? (si/no)"
        )

    def _procesar_cancelar_confirmar(self, comando, sesiones):
        c = comando.strip().lower()
        if c == "si":
            rid = getattr(sesiones[self.numero], "agenda_seleccion_id", None)
            resultado = self.manager.cancelar(rid)
            if resultado == "ok":
                self.sw.enviar("✅ Recordatorio eliminado.")
            elif resultado == "ya_enviado":
                self.sw.enviar("ℹ️ El recordatorio ya fue enviado, no se puede eliminar.")
            else:
                self.sw.enviar("⚠️ No se encontró el recordatorio.")
            self._mostrar_ver(sesiones)
        elif c == "no":
            self.sw.enviar("↩️ Operación cancelada.")
            self._mostrar_ver(sesiones)
        else:
            self.sw.enviar("❌ Respondé *si* o *no*:")

    # ── MODIFICAR ─────────────────────────────────────────────────────────────

    def _procesar_modificar_fecha(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._mostrar_ver(sesiones)
            return

        # ¿Selección de día sugerido?
        opciones = getattr(sesiones[self.numero], "agenda_opciones_fecha", None)
        if opciones:
            try:
                idx = int(comando.strip()) - 1
                if 0 <= idx < len(opciones):
                    sesiones[self.numero].agenda_nueva_fecha = opciones[idx].strftime("%d/%m/%Y")
                    sesiones[self.numero].agenda_opciones_fecha = None
                    self._pedir_hora(sesiones, "modificar_nueva_hora")
                    return
            except ValueError:
                pass

        fecha_str = comando.strip()
        try:
            fecha_obj = datetime.strptime(fecha_str, "%d/%m/%Y").date()
        except ValueError:
            reintentos = getattr(sesiones[self.numero], "agenda_reintentos", 0) + 1
            sesiones[self.numero].agenda_reintentos = reintentos
            if reintentos >= 3:
                self.sw.enviar("❌ Se canceló por demasiados errores.")
                self._salir(sesiones)
            else:
                self.sw.enviar("⚠️ El formato de fecha debe ser DD/MM/AAAA. Intentá nuevamente:")
            return

        sesiones[self.numero].agenda_reintentos = 0

        if fecha_obj < date.today():
            self.sw.enviar("⚠️ La fecha debe ser hoy o posterior. Intentá nuevamente:")
            return

        if not es_dia_laborable(fecha_obj):
            self._mostrar_sugerencias_no_laborable(sesiones, fecha_obj, fecha_str, None)
            return

        sesiones[self.numero].agenda_nueva_fecha = fecha_str
        sesiones[self.numero].agenda_opciones_fecha = None
        self._pedir_hora(sesiones, "modificar_nueva_hora")

    def _procesar_modificar_hora(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._mostrar_ver(sesiones)
            return
        hora_str = self._validar_hora(comando, sesiones)
        if hora_str is None:
            return
        sesiones[self.numero].agenda_nueva_hora = hora_str
        sesiones[self.numero].agenda_reintentos = 0
        sesiones[self.numero].agenda_estado = "modificar_lista"
        nueva_fecha = getattr(sesiones[self.numero], "agenda_nueva_fecha", "")
        self._mostrar_lista_para_seleccion(sesiones, "modificar")

    def _procesar_modificar_lista(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._mostrar_ver(sesiones)
            return
        lista = getattr(sesiones[self.numero], "agenda_lista", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(lista):
                raise ValueError
        except ValueError:
            self.sw.enviar(f"❌ Ingresá un número del 1 al {len(lista)} o 'cancelar':")
            return
        seleccionado = lista[idx]
        sesiones[self.numero].agenda_seleccion_id = seleccionado["id"]
        nueva_fecha = getattr(sesiones[self.numero], "agenda_nueva_fecha", "")
        nueva_hora = getattr(sesiones[self.numero], "agenda_nueva_hora", "")
        sesiones[self.numero].agenda_estado = "modificar_confirmar"
        self.sw.enviar(
            f"✅ Vas a mover:\n"
            f"*{seleccionado.get('descripcion', 'Recordatorio')}*\n"
            f"📅 De: {seleccionado['fecha']} a las {seleccionado['hora']}\n"
            f"📅 A:  {nueva_fecha} a las {nueva_hora}\n\n"
            f"¿Confirmás? (si/no)"
        )

    def _procesar_modificar_confirmar(self, comando, sesiones):
        c = comando.strip().lower()
        if c == "si":
            rid = getattr(sesiones[self.numero], "agenda_seleccion_id", None)
            nueva_fecha = getattr(sesiones[self.numero], "agenda_nueva_fecha", "")
            nueva_hora = getattr(sesiones[self.numero], "agenda_nueva_hora", "")
            resultado = self.manager.modificar_fecha_hora(rid, nueva_fecha, nueva_hora)
            if resultado == "ok":
                self.sw.enviar(f"✅ Recordatorio actualizado al {nueva_fecha} a las {nueva_hora}.")
            elif resultado == "no_pendiente":
                self.sw.enviar("ℹ️ El recordatorio ya no está pendiente, no se puede modificar.")
            else:
                self.sw.enviar("⚠️ No se encontró el recordatorio.")
            self._mostrar_ver(sesiones)
        elif c == "no":
            self.sw.enviar("↩️ Operación cancelada.")
            self._mostrar_ver(sesiones)
        else:
            self.sw.enviar("❌ Respondé *si* o *no*:")

    # ── CREAR (M7/M14 — acciones receta / staff en_gestion) ──────────────────

    def _procesar_crear_descripcion(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._salir(sesiones)
            return
        descripcion = comando.strip()
        if not descripcion:
            self.sw.enviar("❌ La descripción no puede estar vacía. Intentá de nuevo:")
            return
        sesiones[self.numero].agenda_descripcion = descripcion
        enlatado = getattr(sesiones[self.numero], "agenda_enlatado", "farmacia")
        self._iniciar_crear_fecha(sesiones, descripcion, enlatado)

    def _procesar_crear_fecha(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._salir(sesiones)
            return

        opciones = getattr(sesiones[self.numero], "agenda_opciones_fecha", None)
        if opciones:
            try:
                idx = int(comando.strip()) - 1
                if 0 <= idx < len(opciones):
                    sesiones[self.numero].agenda_nueva_fecha = opciones[idx].strftime("%d/%m/%Y")
                    sesiones[self.numero].agenda_opciones_fecha = None
                    self._pedir_hora(sesiones, "crear_hora")
                    return
            except ValueError:
                pass

        fecha_str = comando.strip()
        try:
            fecha_obj = datetime.strptime(fecha_str, "%d/%m/%Y").date()
        except ValueError:
            reintentos = getattr(sesiones[self.numero], "agenda_reintentos", 0) + 1
            sesiones[self.numero].agenda_reintentos = reintentos
            if reintentos >= 3:
                self.sw.enviar("❌ Se canceló por demasiados errores.")
                self._salir(sesiones)
            else:
                self.sw.enviar("⚠️ El formato de fecha debe ser DD/MM/AAAA. Intentá nuevamente:")
            return

        sesiones[self.numero].agenda_reintentos = 0

        if fecha_obj < date.today():
            self.sw.enviar("⚠️ La fecha debe ser hoy o posterior. Intentá nuevamente:")
            return

        fecha_max = getattr(sesiones[self.numero], "agenda_fecha_max", None)

        if not es_dia_laborable(fecha_obj):
            self._mostrar_sugerencias_no_laborable(sesiones, fecha_obj, fecha_str, fecha_max)
            return

        sesiones[self.numero].agenda_nueva_fecha = fecha_str
        sesiones[self.numero].agenda_opciones_fecha = None
        self._pedir_hora(sesiones, "crear_hora")

    def _procesar_crear_hora(self, comando, sesiones):
        if comando.strip().lower() == "cancelar":
            self._salir(sesiones)
            return
        hora_str = self._validar_hora(comando, sesiones)
        if hora_str is None:
            return
        sesiones[self.numero].agenda_nueva_hora = hora_str
        sesiones[self.numero].agenda_reintentos = 0
        sesiones[self.numero].agenda_estado = "crear_confirmar"
        nueva_fecha = getattr(sesiones[self.numero], "agenda_nueva_fecha", "")
        descripcion = getattr(sesiones[self.numero], "agenda_descripcion", "Recordatorio")
        self.sw.enviar(
            f"✅ Se agendará:\n"
            f"*{descripcion}*\n"
            f"📅 {nueva_fecha} a las {hora_str}\n\n"
            f"¿Confirmás? (si/no)"
        )

    def _procesar_crear_confirmar(self, comando, sesiones):
        c = comando.strip().lower()
        if c == "si":
            persona_id = getattr(sesiones[self.numero], "agenda_persona_id", None)
            enlatado = getattr(sesiones[self.numero], "agenda_enlatado", "farmacia")
            entidad_id = getattr(sesiones[self.numero], "agenda_entidad_id", None)
            descripcion = getattr(sesiones[self.numero], "agenda_descripcion", "Recordatorio")
            nueva_fecha = getattr(sesiones[self.numero], "agenda_nueva_fecha", "")
            nueva_hora = getattr(sesiones[self.numero], "agenda_nueva_hora", "")
            estado_vinculado = getattr(sesiones[self.numero], "agenda_estado_vinculado", None)
            self.manager.crear(persona_id, enlatado, entidad_id, nueva_fecha, nueva_hora, descripcion, estado_vinculado=estado_vinculado)
            self.sw.enviar(f"✅ Recordatorio agendado para el {nueva_fecha} a las {nueva_hora}.")
            self._salir(sesiones)
        elif c == "no":
            self.sw.enviar("↩️ Operación cancelada.")
            self._salir(sesiones)
        else:
            self.sw.enviar("❌ Respondé *si* o *no*:")

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _pedir_hora(self, sesiones, estado_destino):
        enlatado = getattr(sesiones[self.numero], "agenda_enlatado", "farmacia")
        hora_def = self.config.get("hora_defecto", {}).get(enlatado, "10:00")
        sesiones[self.numero].agenda_estado = estado_destino
        self.sw.enviar(
            f"⏰ ¿A qué hora? (HH:MM)\n"
            f"_Por defecto: {hora_def}_\n"
            f"Escribí la hora o 'ok' para usar la hora por defecto:"
        )

    def _validar_hora(self, comando, sesiones):
        """
        Valida la hora ingresada.
        Retorna str HH:MM si válida, None si inválida (ya envió el error).
        """
        enlatado = getattr(sesiones[self.numero], "agenda_enlatado", "farmacia")
        hora_def = self.config.get("hora_defecto", {}).get(enlatado, "10:00")

        if comando.strip().lower() == "ok":
            return hora_def

        hora_str = comando.strip()
        try:
            datetime.strptime(hora_str, "%H:%M")
            return hora_str
        except ValueError:
            reintentos = getattr(sesiones[self.numero], "agenda_reintentos", 0) + 1
            sesiones[self.numero].agenda_reintentos = reintentos
            if reintentos >= 3:
                self.sw.enviar("❌ Se canceló por demasiados errores.")
                self._salir(sesiones)
            else:
                self.sw.enviar("⚠️ El formato de hora debe ser HH:MM (ej: 09:30). Intentá nuevamente:")
            return None

    def _mostrar_sugerencias_no_laborable(self, sesiones, fecha_obj, fecha_str, limite_max):
        sugerencias = dias_laborables_cercanos(fecha_obj, cantidad=3, limite_max=limite_max)
        sesiones[self.numero].agenda_opciones_fecha = sugerencias
        lineas = [
            f"⚠️ El {fecha_str} no es día laborable.",
            "Días disponibles cercanos:",
            ""
        ]
        for i, d in enumerate(sugerencias, 1):
            lineas.append(f"{i}. {d.strftime('%d/%m/%Y')} ({DIAS_ES[d.strftime('%A')]})")
        lineas.append("")
        lineas.append("Elegí un número o ingresá otra fecha (DD/MM/AAAA):")
        self.sw.enviar("\n".join(lineas))

    def _es_entorno_test(self) -> bool:
        return self.config.get("entorno", "pr") in ("dv", "qa")

    def _get_fecha_hora_test(self) -> tuple:
        dt = datetime.now() + timedelta(minutes=5)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")

    def _salir(self, sesiones):
        sesiones[self.numero].agenda_estado = None
        sesiones[self.numero].agenda_persona_id = None
        sesiones[self.numero].agenda_enlatado = None
        sesiones[self.numero].agenda_entidad_id = None
        sesiones[self.numero].agenda_descripcion = None
        sesiones[self.numero].agenda_fecha_max = None
        sesiones[self.numero].agenda_estado_vinculado = None
        sesiones[self.numero].agenda_lista = None
        sesiones[self.numero].agenda_seleccion_id = None
        sesiones[self.numero].agenda_nueva_fecha = None
        sesiones[self.numero].agenda_nueva_hora = None
        sesiones[self.numero].agenda_reintentos = 0
        sesiones[self.numero].agenda_opciones_fecha = None
