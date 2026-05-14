# src/farmacia/staff/gestion_recetas_staff.py
import json
import os
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.persona.persona_manager import PersonaManager
from src.farmacia.receta_manager import RecetaManager
from src.farmacia.constants import ESTADO_OMITIDO
from src.farmacia.medicamento_manager import MedicamentoManager
from src.farmacia.obra_social_manager import ObraSocialManager
from src.farmacia.vinculacion_manager import VinculacionManager
from src.agenda.agenda_manager import AgendaManager

from src.tenant import data_path


class GestionRecetasStaff:
    """
    Flujo de gestión de recetas pendientes desde el panel de staff.
    Estados, transiciones, opciones y mensajes leídos de farmacia_config.json.
    """

    OPCIONES_HANDLERS = {
        "avanzar":              None,
        "confirmar_todos":      "_confirmar_todos_disponibles",
        "cambiar_estado_item":  "_iniciar_cambiar_estado_item",
        "ver_chat":             "_iniciar_ver_chat",
        "cambiar_estado_receta":"_iniciar_cambiar_estado_receta",
        "responder_consulta":   "_iniciar_responder_consulta",
        "agendar_recordatorio": "_placeholder_agendar_recordatorio",
        "validar_token":        "_iniciar_validar_token",
    }

    def __init__(self, numero):
        self.CONFIG_PATH = data_path("farmacia", "farmacia_config.json")
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.session_manager = SessionManager()
        self.persona_manager = PersonaManager()
        self.receta_manager = RecetaManager()
        self.med_manager = MedicamentoManager()
        self.os_manager = ObraSocialManager()
        self.vinculacion_manager = VinculacionManager()
        self.farm_config = self._cargar_config()

    def _cargar_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _msg(self, clave, **kwargs):
        """Retorna un mensaje de mensajes_staff, con placeholders resueltos."""
        msg = self.farm_config.get("recetas", {}).get("mensajes_staff", {}).get(clave, "")
        if kwargs:
            msg = msg.format(**kwargs)
        return msg

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        estado = getattr(sesiones[self.numero], "staff_receta_estado", None)
        return estado is not None

    def iniciar(self, sesiones):
        sesiones[self.numero].staff_receta_estado = "lista"
        sesiones[self.numero].staff_receta_id = None
        sesiones[self.numero].staff_receta_reintentos = 0
        self._mostrar_lista(sesiones)

    def procesar(self, comando, sesiones):
        estado = getattr(sesiones[self.numero], "staff_receta_estado", None)

        if estado == "lista":
            self._procesar_lista(comando, sesiones)
        elif estado == "detalle":
            self._procesar_detalle(comando, sesiones)
        elif estado == "cambiar_estado_item":
            self._procesar_cambiar_estado_item(comando, sesiones)
        elif estado == "ofrecer_alternativa":
            self._procesar_ofrecer_alternativa(comando, sesiones)
        elif estado == "chat_receta":
            self._procesar_chat_receta(comando, sesiones)
        elif estado == "cambiar_estado_receta":
            self._procesar_cambiar_estado_receta(comando, sesiones)
        elif estado == "confirmar_token":
            self._procesar_confirmar_token(comando, sesiones)
        elif estado == "responder_consulta":
            self._procesar_responder_consulta(comando, sesiones)
        elif estado == "validar_token_resp":
            self._procesar_validar_token_resp(comando, sesiones)
        elif estado == "secuencial_item":
            self._procesar_item_secuencial(comando, sesiones)

    # ── LISTA DE RECETAS PENDIENTES ───────────────────────────────────────────

    def _mostrar_lista(self, sesiones):
        pendientes = self.receta_manager.buscar_pendientes()

        if not pendientes:
            self.sw.enviar(self._msg("sin_recetas_pendientes"))
            self._salir(sesiones)
            return

        if len(pendientes) == 1:
            sesiones[self.numero].staff_receta_lista = pendientes
            receta = pendientes[0]
            sesiones[self.numero].staff_receta_id = receta["receta_id"]
            config = self._get_estado_receta_config(receta["estado"])
            if config.get("auto_avanzar_al_abrir"):
                self.receta_manager.cambiar_estado(receta["receta_id"], config["camino_feliz"], "Farmacia procesando")
            self._mostrar_detalle(sesiones)
            return

        sesiones[self.numero].staff_receta_lista = pendientes

        lineas = ["📋 *Recetas pendientes:*\n"]
        for i, rec in enumerate(pendientes, 1):
            persona_id = rec.get("persona_id", "")
            nombre = self.persona_manager.get_nombre_completo(persona_id) or "Desconocido"
            cant_items = len([it for it in rec.get("items", []) if it["estado_item"] != ESTADO_OMITIDO])
            vencimiento = rec.get("fecha_vencimiento", "—")
            estado = rec.get("estado", "pendiente")
            estado_config = self._get_estado_receta_config(estado)

            no_leidos = self.receta_manager.contar_no_leidos_chat(rec["receta_id"], "farmacia")
            linea = f"{i}. {nombre} — {cant_items} medicamento(s) — Vence: {vencimiento}"
            if estado != "pendiente":
                linea += f" {estado_config.get('icono', '')}"
            if no_leidos:
                linea += f" 💬 {no_leidos}"

            credencial = rec.get("credencial_validada", True)
            if not credencial:
                linea += "\n   ⚠️ Credencial no validada"

            lineas.append(linea)

        lineas.append(f"\nIngresá el número para gestionar")
        lineas.append(f"o *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_lista(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            self._volver_menu_staff(sesiones)
            return

        pendientes = getattr(sesiones[self.numero], "staff_receta_lista", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(pendientes):
                raise ValueError
        except ValueError:
            self.sw.enviar(self._msg("numero_invalido"))
            return

        receta = pendientes[idx]
        sesiones[self.numero].staff_receta_id = receta["receta_id"]

        config = self._get_estado_receta_config(receta["estado"])
        if config.get("auto_avanzar_al_abrir"):
            self.receta_manager.cambiar_estado(receta["receta_id"], config["camino_feliz"], "Farmacia procesando")

        self._mostrar_detalle(sesiones)

    # ── DETALLE DE RECETA ─────────────────────────────────────────────────────

    def mostrar_detalle_receta_activa(self, sesiones):
        """Público — permite que el orquestador retome el detalle tras un subflujo externo."""
        self._mostrar_detalle(sesiones)

    def _mostrar_detalle(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self.sw.enviar(self._msg("receta_no_encontrada"))
            self._salir(sesiones)
            return

        _, receta = resultado
        persona_id = receta.get("persona_id", "")
        nombre = self.persona_manager.get_nombre_completo(persona_id) or "Desconocido"
        fecha_validez = receta.get("fecha_validez_desde", "")
        fecha_venc = receta.get("fecha_vencimiento", "—")
        estado_id = receta.get("estado", "pendiente")
        estado_config = self._get_estado_receta_config(estado_id)
        estado_label = estado_config.get("label", estado_id)
        estado_icono = estado_config.get("icono", "")
        diagnostico = receta.get("diagnostico", "") or "—"
        credencial = receta.get("credencial_validada", True)
        os_id = receta.get("obra_social_id", "")

        os_info = ""
        if os_id:
            os_data = self.os_manager.get_asociacion(os_id)
            if os_data:
                os_info = f"🏥 {os_data[1]['entidad']} — Nro: {os_data[1]['numero']}"

        credencial_str = "✅ Credencial validada" if credencial else "⚠️ Credencial NO validada"

        medico = receta.get("medico", {})
        medico_str = medico.get("nombre", "—")
        if medico.get("especialidad"):
            medico_str += f" ({medico['especialidad']})"

        lineas = [f"📋 *Receta de {nombre}*"]
        if fecha_validez:
            lineas.append(f"📅 Válida: {fecha_validez} — Vence: {fecha_venc}")
        else:
            lineas.append(f"📅 Vence: {fecha_venc}")
        lineas.append(f"📊 Estado: {estado_icono} *{estado_label}*")

        if os_info:
            lineas.append(os_info)
        lineas.append(credencial_str)
        lineas.append(f"🩺 Diagnóstico: {diagnostico}")
        lineas.append(f"👨‍⚕️ Médico: {medico_str}")
        lineas.append("")

        self.receta_manager.migrar_notas_a_chat(receta_id)
        chat = self.receta_manager.get_chat(receta_id)

        # Último mensaje del cliente por medicamento (accion o consulta vinculada al ítem)
        # Solo se consideran mensajes posteriores al último mensaje de farmacia para ese ítem.
        ultimo_farmacia_idx = {}
        for i, msg in enumerate(chat):
            if (msg["autor"] == "farmacia"
                    and msg.get("medicamento_id")
                    and msg.get("tipo") in ("sin_stock", "alternativa")):
                ultimo_farmacia_idx[msg["medicamento_id"]] = i

        ultimo_cliente_por_med = {}
        for i, msg in enumerate(chat):
            if (msg["autor"] != "farmacia"
                    and msg.get("tipo") in ("accion", "consulta")
                    and msg.get("medicamento_id")):
                med_id = msg["medicamento_id"]
                if i > ultimo_farmacia_idx.get(med_id, -1):
                    ultimo_cliente_por_med[med_id] = msg

        # Consultas genéricas sin respuesta (sin medicamento_id — van al pie, no bajo el ítem)
        consultas_sin_respuesta = []
        for idx, msg in enumerate(chat):
            if msg.get("tipo") == "consulta" and not msg.get("medicamento_id"):
                tiene_respuesta = any(
                    r.get("tipo") == "respuesta_consulta" and not r.get("medicamento_id")
                    for r in chat[idx + 1:]
                )
                if not tiene_respuesta:
                    consultas_sin_respuesta.append(msg)

        lineas.append("*Medicamentos:*")
        items = receta.get("items", [])
        items_visibles_idx = []
        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})
        for i, item in enumerate(items):
            if item["estado_item"] == ESTADO_OMITIDO:
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            cant_rec = item.get("cantidad_receta", 0)
            cant_sol = item.get("cantidad_solicitada", cant_rec)
            item_config = estados_item_config.get(item["estado_item"], {})
            icono = item_config.get("icono", "❓")
            estado_label_item = item_config.get("label", item["estado_item"])

            cant_str = f"{cant_sol}" if cant_sol == cant_rec else f"{cant_sol} de {cant_rec}"
            lineas.append(f"• {icono} {label} — Cant: {cant_str} ({estado_label_item})")
            if item_config.get("mostrar_acciones_cliente"):
                ultimo = ultimo_cliente_por_med.get(item["medicamento_id"])
                if ultimo:
                    lineas.append(f"   └ 👤 {ultimo['mensaje']}")
                    if ultimo.get("tipo") == "consulta":
                        med_id = item["medicamento_id"]
                        idx_ultimo = next((i for i, m in enumerate(chat) if m["id"] == ultimo["id"]), -1)
                        respuesta = next(
                            (m for m in chat[idx_ultimo + 1:]
                             if m.get("tipo") == "respuesta_consulta" and m.get("medicamento_id") == med_id),
                            None
                        )
                        if respuesta:
                            lineas.append(f"      └ 🏥 {respuesta['mensaje']}")
            items_visibles_idx.append(i)

        if consultas_sin_respuesta:
            lineas.append(f"\n{self._msg('consulta_pendiente_header')}")
            for msg in consultas_sin_respuesta:
                med_id = msg.get("medicamento_id")
                med_label = self.med_manager.get_label(med_id) if med_id else "Receta"
                lineas.append(f"   💬 *{med_label}:* {msg['mensaje']}")

        self.receta_manager.marcar_chat_leido(receta_id, "farmacia")

        # Token enviado: mostrar el valor recibido del cliente
        if estado_id == "token_enviado":
            token_msg = next(
                (m for m in reversed(chat) if m.get("tipo") == "token_respuesta"),
                None
            )
            if token_msg:
                lineas.append(f"\n🔑 *Token recibido:* {token_msg['mensaje']}")

        # Opciones dinámicas según estado actual
        opciones_staff = list(estado_config.get("opciones_staff", []))
        camino_feliz = estado_config.get("camino_feliz")
        opciones_activas = []
        lineas.append("")

        # Detectar si todos los items están resueltos
        items_activos = [it for it in items if it["estado_item"] != ESTADO_OMITIDO]
        todos_resueltos = all(
            it["estado_item"] in ("disponible", "alternativa_aceptada", "rechazado_usuario")
            for it in items_activos
        ) if items_activos else False

        # Lógica de reemplazo dinámico de la opción 1
        if todos_resueltos and "confirmar_todos" in opciones_staff:
            # Items resueltos → reemplazar confirmar_todos por avanzar
            idx_ct = opciones_staff.index("confirmar_todos")
            opciones_staff[idx_ct] = "avanzar"

        num = 1
        opciones_labels = self.farm_config.get("recetas", {}).get("opciones_staff_labels", {})
        for opcion_key in opciones_staff:
            if opcion_key == "avanzar":
                if camino_feliz:
                    cf_config = self._get_estado_receta_config(camino_feliz)
                    cf_label = cf_config.get("label", camino_feliz)
                    cf_icono = cf_config.get("icono", "➡️")
                    lineas.append(f"{num}. {cf_icono} Avanzar a {cf_label}")
                    opciones_activas.append("avanzar")
                    num += 1
                continue

            method_name = self.OPCIONES_HANDLERS.get(opcion_key)
            if method_name is not None:
                label_opcion = opciones_labels.get(opcion_key, opcion_key)
                lineas.append(f"{num}. {label_opcion}")
                opciones_activas.append(opcion_key)
                num += 1

        lineas.append(self._msg("escribi_cancelar"))

        sesiones[self.numero].staff_receta_estado = "detalle"
        sesiones[self.numero].staff_receta_items_visibles = items_visibles_idx
        sesiones[self.numero].staff_receta_opciones_activas = opciones_activas
        self.sw.enviar("\n".join(lineas))

    def _procesar_detalle(self, comando, sesiones):
        if comando.strip() == "cancelar":
            pendientes = self.receta_manager.buscar_pendientes()
            if len(pendientes) <= 1:
                self._salir(sesiones)
                self._volver_menu_staff(sesiones)
            else:
                self.iniciar(sesiones)
            return

        opciones_activas = getattr(sesiones[self.numero], "staff_receta_opciones_activas", [])

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(opciones_activas):
                raise ValueError
        except ValueError:
            self.sw.enviar(self._msg("opcion_invalida"))
            return

        opcion_key = opciones_activas[idx]

        if opcion_key == "avanzar":
            self._avanzar_camino_feliz(sesiones)
            return

        method_name = self.OPCIONES_HANDLERS.get(opcion_key)
        if method_name:
            method = getattr(self, method_name, None)
            if method:
                method(sesiones)
            else:
                self.sw.enviar(self._msg("funcion_proximamente", nombre=method_name))
                self._mostrar_detalle(sesiones)

    # ── CONFIRMAR TODOS DISPONIBLES ───────────────────────────────────────────

    def _confirmar_todos_disponibles(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        items = receta.get("items", [])
        estados_item_cfg = self.farm_config.get("recetas", {}).get("estados_item", {})
        count = 0
        for i, item in enumerate(items):
            if estados_item_cfg.get(item["estado_item"], {}).get("confirmable_staff"):
                self.receta_manager.cambiar_estado_item(receta_id, i, "disponible")
                count += 1

        if count > 0:
            self.sw.enviar(self._msg("todos_confirmados", count=count))

        # Desestimar notas pendientes de sin_stock/alternativa
        self._desestimar_notas_items(receta_id)

        # TODO: cancelar recordatorios pendientes
        print(f"[PLACEHOLDER] Cancelar recordatorios para receta {receta_id}")

        # Preguntar si requiere token
        sesiones[self.numero].staff_receta_estado = "confirmar_token"
        self.sw.enviar(self._msg("pregunta_token"))

    def _procesar_confirmar_token(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)

        en_gestion_cfg = self._get_estado_receta_config("en_gestion")
        if comando.strip() == "1":
            destino = en_gestion_cfg.get("camino_feliz")
            self.receta_manager.cambiar_estado(receta_id, destino, "Farmacia solicita token")
            self.sw.enviar(self._msg("token_si"))
            self._acciones_al_entrar(receta_id, destino)
            self._mostrar_detalle(sesiones)

        elif comando.strip() == "2":
            destino = en_gestion_cfg.get("camino_feliz_sin_token")
            self.receta_manager.cambiar_estado(receta_id, destino, "No requiere token — avance directo")
            self.sw.enviar(self._msg("token_no"))
            self._mostrar_detalle(sesiones)

        else:
            self.sw.enviar(self._msg("token_opcion_invalida"))

    # ── CAMBIAR ESTADO DE ITEM ────────────────────────────────────────────────

    def _iniciar_cambiar_estado_item(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        items = receta.get("items", [])

        lineas = [self._msg("seleccionar_medicamento")]
        lineas.append(f"0. {self._msg('procesar_en_secuencia')}\n")
        items_visibles = []
        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})
        for i, item in enumerate(items):
            if item["estado_item"] == ESTADO_OMITIDO:
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            items_visibles.append(i)
            item_config = estados_item_config.get(item["estado_item"], {})
            icono = item_config.get("icono", "❓")
            estado_label = item_config.get("label", item["estado_item"])
            lineas.append(f"{len(items_visibles)}. {icono} {label} ({estado_label})")

        lineas.append(f"\n{self._msg('escribi_cancelar')}")
        sesiones[self.numero].staff_receta_estado = "cambiar_estado_item"
        sesiones[self.numero].staff_receta_items_visibles = items_visibles
        sesiones[self.numero].staff_receta_esperando_estado = False
        self.sw.enviar("\n".join(lineas))

    def _procesar_cambiar_estado_item(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        items_visibles = getattr(sesiones[self.numero], "staff_receta_items_visibles", [])
        esperando_estado = getattr(sesiones[self.numero], "staff_receta_esperando_estado", False)

        if not esperando_estado:
            if comando.strip() == "0":
                sesiones[self.numero].staff_receta_sec_items = items_visibles
                sesiones[self.numero].staff_receta_sec_cursor = 0
                sesiones[self.numero].staff_receta_sec_activo = False
                sesiones[self.numero].staff_receta_estado = "secuencial_item"
                self._mostrar_item_secuencial(sesiones)
                return

            try:
                idx = int(comando.strip()) - 1
                if idx < 0 or idx >= len(items_visibles):
                    raise ValueError
            except ValueError:
                self.sw.enviar(self._msg("numero_invalido"))
                return

            item_real_idx = items_visibles[idx]
            sesiones[self.numero].staff_receta_item_idx = item_real_idx
            sesiones[self.numero].staff_receta_esperando_estado = True
            opciones = self.farm_config.get("recetas", {}).get("opciones_cambiar_estado_item", [])
            lineas = [self._msg("seleccionar_estado_item")]
            for i, op in enumerate(opciones, 1):
                lineas.append(f"{i}. {op['label']}")
            lineas.append(f"\n{self._msg('escribi_cancelar')}")
            self.sw.enviar("\n".join(lineas))
        else:
            sesiones[self.numero].staff_receta_esperando_estado = False
            receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
            item_idx = getattr(sesiones[self.numero], "staff_receta_item_idx", 0)
            opciones = self.farm_config.get("recetas", {}).get("opciones_cambiar_estado_item", [])

            try:
                idx = int(comando.strip()) - 1
                if idx < 0 or idx >= len(opciones):
                    raise ValueError
            except ValueError:
                self.sw.enviar(self._msg("opcion_invalida"))
                sesiones[self.numero].staff_receta_esperando_estado = True
                return

            opcion = opciones[idx]

            if "accion" in opcion:
                sesiones[self.numero].staff_receta_estado = opcion["accion"]
                self.sw.enviar(self._msg(opcion["msg_inicio"]))
            else:
                estado_destino = opcion["estado_destino"]
                self.receta_manager.cambiar_estado_item(receta_id, item_idx, estado_destino)

                if opcion.get("desestimar"):
                    self._desestimar_notas_item(receta_id, item_idx)

                if opcion.get("agregar_chat"):
                    resultado = self.receta_manager.get_receta(receta_id)
                    if resultado:
                        _, receta = resultado
                        item = receta["items"][item_idx]
                        label = self.med_manager.get_label(item["medicamento_id"])
                        self.receta_manager.agregar_mensaje_chat(
                            receta_id, "farmacia",
                            self._msg(opcion["agregar_chat"], medicamento=label),
                            tipo=estado_destino,
                            medicamento_id=item["medicamento_id"]
                        )

                if opcion.get("msg_confirmacion"):
                    self.sw.enviar(self._msg(opcion["msg_confirmacion"]))

                self._evaluar_estado_post_cambio_item(receta_id, sesiones)
                self._mostrar_detalle(sesiones)

    # ── MODO SECUENCIAL DE ITEMS ──────────────────────────────────────────────

    def _mostrar_item_secuencial(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        sec_items = getattr(sesiones[self.numero], "staff_receta_sec_items", [])
        cursor = getattr(sesiones[self.numero], "staff_receta_sec_cursor", 0)

        if cursor >= len(sec_items):
            self._mostrar_detalle(sesiones)
            return

        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        item_idx = sec_items[cursor]
        item = receta["items"][item_idx]
        label = self.med_manager.get_label(item["medicamento_id"])

        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})
        item_config = estados_item_config.get(item["estado_item"], {})
        icono = item_config.get("icono", "❓")
        estado_label = item_config.get("label", item["estado_item"])

        opciones = self.farm_config.get("recetas", {}).get("opciones_cambiar_estado_item", [])
        lineas = [
            f"💊 *{label}* ({cursor + 1}/{len(sec_items)})",
            f"Estado actual: {icono} {estado_label}",
            "",
            self._msg("seleccionar_estado_item"),
        ]
        for i, op in enumerate(opciones, 1):
            lineas.append(f"{i}. {op['label']}")
        lineas.append(f"\n{self._msg('escribi_cancelar')}")
        self.sw.enviar("\n".join(lineas))

    def _procesar_item_secuencial(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        sec_items = getattr(sesiones[self.numero], "staff_receta_sec_items", [])
        cursor = getattr(sesiones[self.numero], "staff_receta_sec_cursor", 0)
        item_idx = sec_items[cursor]
        opciones = self.farm_config.get("recetas", {}).get("opciones_cambiar_estado_item", [])

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(opciones):
                raise ValueError
        except ValueError:
            self.sw.enviar(self._msg("opcion_invalida"))
            self._mostrar_item_secuencial(sesiones)
            return

        opcion = opciones[idx]

        if "accion" in opcion:
            sesiones[self.numero].staff_receta_item_idx = item_idx
            sesiones[self.numero].staff_receta_sec_activo = True
            sesiones[self.numero].staff_receta_estado = opcion["accion"]
            self.sw.enviar(self._msg(opcion["msg_inicio"]))
        else:
            estado_destino = opcion["estado_destino"]
            self.receta_manager.cambiar_estado_item(receta_id, item_idx, estado_destino)

            if opcion.get("desestimar"):
                self._desestimar_notas_item(receta_id, item_idx)

            if opcion.get("agregar_chat"):
                resultado = self.receta_manager.get_receta(receta_id)
                if resultado:
                    _, receta = resultado
                    item = receta["items"][item_idx]
                    label = self.med_manager.get_label(item["medicamento_id"])
                    self.receta_manager.agregar_mensaje_chat(
                        receta_id, "farmacia",
                        self._msg(opcion["agregar_chat"], medicamento=label),
                        tipo=estado_destino,
                        medicamento_id=item["medicamento_id"]
                    )

            if opcion.get("msg_confirmacion"):
                self.sw.enviar(self._msg(opcion["msg_confirmacion"]))

            self._evaluar_estado_post_cambio_item(receta_id, sesiones)
            sesiones[self.numero].staff_receta_sec_cursor = cursor + 1
            sesiones[self.numero].staff_receta_estado = "secuencial_item"
            self._mostrar_item_secuencial(sesiones)

    # ── OFRECER ALTERNATIVA ───────────────────────────────────────────────────

    def _procesar_ofrecer_alternativa(self, comando, sesiones):
        if comando.strip() == "cancelar":
            if getattr(sesiones[self.numero], "staff_receta_sec_activo", False):
                sesiones[self.numero].staff_receta_sec_activo = False
                sesiones[self.numero].staff_receta_estado = "secuencial_item"
                self._mostrar_item_secuencial(sesiones)
            else:
                self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        item_idx = getattr(sesiones[self.numero], "staff_receta_item_idx", 0)

        self.receta_manager.cambiar_estado_item(receta_id, item_idx, "alternativa_ofrecida")
        self._desestimar_notas_item(receta_id, item_idx)

        resultado = self.receta_manager.get_receta(receta_id)
        label_original = "el medicamento"
        med_id = None
        if resultado:
            _, receta = resultado
            item = receta["items"][item_idx]
            label_original = self.med_manager.get_label(item["medicamento_id"])
            med_id = item["medicamento_id"]

        mensaje_nota = self._msg("nota_alternativa", original=label_original, alternativa=comando.strip())
        self.receta_manager.agregar_mensaje_chat(
            receta_id, "farmacia", mensaje_nota,
            tipo="alternativa", medicamento_id=med_id
        )

        self.sw.enviar(self._msg("alternativa_ofrecida"))
        self._evaluar_estado_post_cambio_item(receta_id, sesiones)

        if getattr(sesiones[self.numero], "staff_receta_sec_activo", False):
            sesiones[self.numero].staff_receta_sec_activo = False
            cursor = getattr(sesiones[self.numero], "staff_receta_sec_cursor", 0)
            sesiones[self.numero].staff_receta_sec_cursor = cursor + 1
            sesiones[self.numero].staff_receta_estado = "secuencial_item"
            self._mostrar_item_secuencial(sesiones)
        else:
            self._mostrar_detalle(sesiones)

    # ── CHAT ──────────────────────────────────────────────────────────────────

    def _iniciar_ver_chat(self, sesiones):
        sesiones[self.numero].staff_receta_estado = "chat_receta"
        self._mostrar_chat_receta(sesiones)

    def _mostrar_chat_receta(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        vencimiento = receta.get("fecha_vencimiento", "—")
        estado_id = receta.get("estado", "pendiente")
        estado_config = self._get_estado_receta_config(estado_id)
        estado_label = estado_config.get("label", estado_id)
        estado_icono = estado_config.get("icono", "")

        chat = self.receta_manager.get_chat(receta_id)

        lineas = [
            f"💬 *Chat — Receta vence: {vencimiento}*",
            f"Estado: {estado_icono} {estado_label}",
            ""
        ]

        if not chat:
            lineas.append("_(Sin mensajes aún)_")
        else:
            meds_order = []
            meds_msgs = {}
            generales = []
            for msg in chat:
                mid = msg.get("medicamento_id")
                if mid:
                    if mid not in meds_msgs:
                        meds_order.append(mid)
                        meds_msgs[mid] = []
                    meds_msgs[mid].append(msg)
                else:
                    generales.append(msg)

            for mid in meds_order:
                med_label = self.med_manager.get_label(mid)
                lineas.append(f"💊 *{med_label}*")
                consumed = set()
                for i, msg in enumerate(meds_msgs[mid]):
                    if msg["id"] in consumed:
                        continue
                    tipo = msg.get("tipo", "mensaje")
                    autor = msg["autor"]
                    if tipo in ("sin_stock", "alternativa", "solicitud_token"):
                        lineas.append(f" 🏥 {msg['mensaje']}")
                    elif tipo == "consulta":
                        lineas.append(f"  └ 👤 {msg['mensaje']}")
                        respuesta = next(
                            (r for r in meds_msgs[mid][i + 1:]
                             if r.get("tipo") == "respuesta_consulta" and r["id"] not in consumed),
                            None
                        )
                        if respuesta:
                            lineas.append(f"     └ 🏥 {respuesta['mensaje']}")
                            consumed.add(respuesta["id"])
                    elif tipo == "respuesta_consulta":
                        pass
                    elif tipo in ("accion", "token_respuesta"):
                        lineas.append(f"  └ 👤 {msg['mensaje']}")
                    else:
                        prefix = "🏥" if autor == "farmacia" else "👤"
                        lineas.append(f"  {prefix} {msg['mensaje']}")
                lineas.append("")

            for msg in generales:
                prefix = "🏥" if msg["autor"] == "farmacia" else "👤"
                lineas.append(f"{prefix} {msg['mensaje']}")

        self.receta_manager.marcar_chat_leido(receta_id, "farmacia")

        lineas.append("")
        lineas.append("Escribí un mensaje o *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_chat_receta(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.receta_manager.agregar_mensaje_chat(receta_id, "farmacia", comando.strip(), tipo="mensaje")
        self._mostrar_chat_receta(sesiones)

    # ── CAMBIAR ESTADO DE RECETA (dinámico desde outflow) ─────────────────────

    def _iniciar_cambiar_estado_receta(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        estado_actual = receta.get("estado", "pendiente")
        estado_config = self._get_estado_receta_config(estado_actual)
        outflow = estado_config.get("outflow", [])
        inflow = estado_config.get("inflow", [])

        estados_config = self.receta_manager._get_estados_receta()
        opciones = []

        for estado_id in outflow:
            config = estados_config.get(estado_id, {})
            if config.get("transicion") != "automatico":
                opciones.append(estado_id)

        for estado_id in inflow:
            if estado_id not in opciones:
                opciones.append(estado_id)

        if not opciones:
            self.sw.enviar(self._msg("sin_cambios_estado"))
            self._mostrar_detalle(sesiones)
            return

        lineas = [self._msg("seleccionar_estado_receta")]
        for i, estado_id in enumerate(opciones, 1):
            config = estados_config.get(estado_id, {})
            icono = config.get("icono", "")
            label = config.get("label", estado_id)
            if estado_id in inflow and estado_id not in outflow:
                label += self._msg("volver_atras_label")
            lineas.append(f"{i}. {icono} {label}")

        lineas.append(f"\n{self._msg('escribi_cancelar')}")

        sesiones[self.numero].staff_receta_estado = "cambiar_estado_receta"
        sesiones[self.numero].staff_receta_opciones_estado = opciones
        self.sw.enviar("\n".join(lineas))

    def _procesar_cambiar_estado_receta(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        opciones = getattr(sesiones[self.numero], "staff_receta_opciones_estado", [])
        esperando_motivo = getattr(sesiones[self.numero], "staff_receta_esperando_motivo", False)

        if esperando_motivo:
            receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
            nuevo_estado = getattr(sesiones[self.numero], "staff_receta_nuevo_estado", "")
            sesiones[self.numero].staff_receta_esperando_motivo = False

            resultado_previo = self.receta_manager.get_receta(receta_id)
            estado_previo = resultado_previo[1]["estado"] if resultado_previo else ""

            self._limpiar_si_rollback(receta_id, estado_previo, nuevo_estado)
            self.receta_manager.cambiar_estado(receta_id, nuevo_estado, comando.strip())
            self._reset_items_si_corresponde(receta_id, nuevo_estado)
            self._desestimar_si_rollback(receta_id, estado_previo, nuevo_estado)

            config = self._get_estado_receta_config(nuevo_estado)
            label = config.get("label", nuevo_estado)
            self.sw.enviar(self._msg("estado_cambiado", label=label))

            self._acciones_al_entrar(receta_id, nuevo_estado)

            if config.get("es_final", False):
                self.iniciar(sesiones)
            else:
                self._mostrar_detalle(sesiones)
            return

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(opciones):
                raise ValueError
        except ValueError:
            self.sw.enviar(self._msg("opcion_invalida"))
            return

        nuevo_estado = opciones[idx]
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        config = self._get_estado_receta_config(nuevo_estado)

        if config.get("requiere_motivo", False):
            sesiones[self.numero].staff_receta_esperando_motivo = True
            sesiones[self.numero].staff_receta_nuevo_estado = nuevo_estado
            label = config.get("label", nuevo_estado)
            self.sw.enviar(self._msg("pedir_motivo", label=label))
            return

        resultado_previo = self.receta_manager.get_receta(receta_id)
        estado_previo = resultado_previo[1]["estado"] if resultado_previo else ""

        self._limpiar_si_rollback(receta_id, estado_previo, nuevo_estado)
        self.receta_manager.cambiar_estado(receta_id, nuevo_estado, config.get("label", ""))
        self._reset_items_si_corresponde(receta_id, nuevo_estado)
        self._desestimar_si_rollback(receta_id, estado_previo, nuevo_estado)

        label = config.get("label", nuevo_estado)
        self.sw.enviar(self._msg("estado_cambiado", label=label))

        self._acciones_al_entrar(receta_id, nuevo_estado)

        if config.get("es_final", False):
            self.iniciar(sesiones)
        else:
            self._mostrar_detalle(sesiones)

    # ── AVANZAR CAMINO FELIZ ─────────────────────────────────────────────────

    def _avanzar_camino_feliz(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        estado_actual = receta.get("estado", "pendiente")
        estado_config = self._get_estado_receta_config(estado_actual)
        camino_feliz = estado_config.get("camino_feliz")

        if not camino_feliz:
            self.sw.enviar(self._msg("sin_avance"))
            self._mostrar_detalle(sesiones)
            return

        # Si el estado tiene bifurcacion_token, el avance pasa por la pregunta de token
        if estado_config.get("bifurcacion_token"):
            self._desestimar_notas_items(receta_id)
            sesiones[self.numero].staff_receta_estado = "confirmar_token"
            self.sw.enviar(self._msg("pregunta_token"))
            return

        # Si el estado tiene es_reintento_token, reintento limitado → vuelve al camino_feliz
        if estado_config.get("es_reintento_token"):
            max_reintentos = self.farm_config.get("recetas", {}).get("max_reintentos_token", 3)
            historial = receta.get("historial_estados", [])
            ultimo_req = next(
                (i for i in range(len(historial) - 1, -1, -1)
                 if historial[i]["estado"] == camino_feliz),
                0
            )
            reintentos = sum(1 for h in historial[ultimo_req:] if h["estado"] == estado_actual)

            if reintentos >= max_reintentos:
                self.sw.enviar(self._msg("reintentos_agotados", max=max_reintentos))
                self._mostrar_detalle(sesiones)
                return

            self.receta_manager.cambiar_estado(
                receta_id, camino_feliz,
                f"Reintento {reintentos}/{max_reintentos} — solicitud de nuevo token"
            )
            self.sw.enviar(self._msg("reintento_token", reintento=reintentos, max=max_reintentos))
            self._acciones_al_entrar(receta_id, camino_feliz)
            self._mostrar_detalle(sesiones)
            return

        cf_config = self._get_estado_receta_config(camino_feliz)
        cf_label = cf_config.get("label", camino_feliz)

        if cf_config.get("requiere_motivo", False):
            sesiones[self.numero].staff_receta_estado = "cambiar_estado_receta"
            sesiones[self.numero].staff_receta_esperando_motivo = True
            sesiones[self.numero].staff_receta_nuevo_estado = camino_feliz
            self.sw.enviar(self._msg("pedir_motivo", label=cf_label))
            return

        self.receta_manager.cambiar_estado(receta_id, camino_feliz, f"Avance → {cf_label}")
        self.sw.enviar(self._msg("avance_exitoso", label=cf_label))

        self._acciones_al_entrar(receta_id, camino_feliz)
        self._evaluar_estado_post_cambio_item(receta_id, sesiones)

        if cf_config.get("es_final", False):
            self.iniciar(sesiones)
        else:
            self._mostrar_detalle(sesiones)

    # ── RESPONDER CONSULTA ────────────────────────────────────────────────────

    def _iniciar_responder_consulta(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        chat = self.receta_manager.get_chat(receta_id)

        consulta = None
        for idx, msg in enumerate(chat):
            if msg.get("tipo") == "consulta":
                med_id = msg.get("medicamento_id")
                tiene_respuesta = any(
                    r.get("tipo") == "respuesta_consulta" and r.get("medicamento_id") == med_id
                    for r in chat[idx + 1:]
                )
                if not tiene_respuesta:
                    consulta = msg
                    break

        if not consulta:
            self.sw.enviar(self._msg("sin_cambios_estado"))
            self._mostrar_detalle(sesiones)
            return

        med_id = consulta.get("medicamento_id")
        med_label = self.med_manager.get_label(med_id) if med_id else "Receta"
        sesiones[self.numero].staff_consulta_medicamento_id = med_id

        lineas = [
            self._msg("consulta_pendiente_header"),
            f"   💬 *{med_label}:* {consulta['mensaje']}",
            "",
            self._msg("pedir_respuesta_consulta"),
        ]
        sesiones[self.numero].staff_receta_estado = "responder_consulta"
        self.sw.enviar("\n".join(lineas))

    def _procesar_responder_consulta(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        med_id = getattr(sesiones[self.numero], "staff_consulta_medicamento_id", None)

        self.receta_manager.agregar_mensaje_chat(
            receta_id, "farmacia", comando.strip(),
            tipo="respuesta_consulta", medicamento_id=med_id
        )

        # Notificar al cliente por esta respuesta (usa config del estado actual)
        resultado_actual = self.receta_manager.get_receta(receta_id)
        estado_consulta = resultado_actual[1]["estado"] if resultado_actual else "en_consulta"
        self._acciones_al_entrar(receta_id, estado_consulta)

        # Transición M→H solo si no quedan más consultas sin respuesta
        chat = self.receta_manager.get_chat(receta_id)
        meds_en_consulta = self.receta_manager._get_meds_en_consulta(chat)
        if not meds_en_consulta:
            cf = self._get_estado_receta_config(estado_consulta).get("camino_feliz")
            self.receta_manager.cambiar_estado(receta_id, cf, "Farmacia respondió todas las consultas")

        self.sw.enviar(self._msg("respuesta_consulta_enviada"))
        self._mostrar_detalle(sesiones)

    # ── M14 — AGENDAR RECORDATORIO DESDE EN_GESTION ───────────────────────────

    def _placeholder_agendar_recordatorio(self, sesiones):
        """M14 — inicia el flujo de creación de recordatorio libre para el staff."""
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        if not receta_id:
            self._mostrar_detalle(sesiones)
            return

        resultado_receta = self.receta_manager.get_receta(receta_id)
        fecha_venc = ""
        if resultado_receta:
            _, receta_data = resultado_receta
            fecha_venc = receta_data.get("fecha_vencimiento", "")
            cliente_nombre = receta_data.get("persona_id", "")
        else:
            cliente_nombre = ""

        from src.agenda.recordatorio_service import RecordatorioService
        rs = RecordatorioService(self.numero)
        rs.iniciar_crear(
            sesiones=sesiones,
            persona_id=self.numero,
            enlatado="farmacia",
            entidad_id=receta_id,
            descripcion=f"🔔 Seguimiento — Receta de {cliente_nombre}, vence {fecha_venc}.",
            fecha_max=fecha_venc,
            pedir_descripcion=True,
        )
        if not rs.esta_en_flujo(sesiones):
            self._mostrar_detalle(sesiones)
        else:
            sesiones[self.numero].agenda_post_flujo_accion = "detalle_receta_staff"

    def _iniciar_validar_token(self, sesiones):
        sesiones[self.numero].staff_receta_estado = "validar_token_resp"
        self.sw.enviar(self._msg("validar_token"))

    def _procesar_validar_token_resp(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)

        token_cfg = self._get_estado_receta_config("token_enviado")
        if comando.strip() == "1":
            destino = token_cfg.get("camino_feliz")
            self.receta_manager.cambiar_estado(receta_id, destino, "Token validado")
            self.sw.enviar(self._msg("token_validado"))
            self._mostrar_detalle(sesiones)

        elif comando.strip() == "2":
            destino = token_cfg.get("destino_token_invalido")
            self.receta_manager.cambiar_estado(receta_id, destino, "Token inválido")
            self._avanzar_camino_feliz(sesiones)

        else:
            self.sw.enviar(self._msg("opcion_invalida"))

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _resolver_lids(self, persona_id):
        """
        Retorna la lista de LIDs a los que enviar push para una persona.
        Si la persona tiene titulares, usa los lids de todos ellos.
        Si no tiene titulares, usa sus propios lids.
        """
        titulares = self.vinculacion_manager.buscar_titulares(persona_id)
        if titulares:
            lids = []
            for titular_id in titulares:
                titular_data = self.persona_manager.get_persona(titular_id)
                if titular_data:
                    lids.extend(titular_data[1].get("lids", []))
            return lids
        persona_data = self.persona_manager.get_persona(persona_id)
        if not persona_data:
            return []
        return persona_data[1].get("lids", [])

    def _get_estado_receta_config(self, estado_id):
        return self.farm_config.get("recetas", {}).get("estados_receta", {}).get(estado_id, {})

    def _acciones_al_entrar(self, receta_id, estado_id):
        """
        Ejecuta las acciones declaradas en la config al entrar a un estado:
        1. Cancela recordatorios vinculados al estado saliente (B13).
        2. Crea recordatorios automáticos de seguimiento (B11/B12/B14/B16).
        3. Agrega mensaje al chat si mensaje_al_entrar está definido.
        4. Envía push al cliente si notificacion_push está definida.
        """
        config = self._get_estado_receta_config(estado_id)

        inflow = config.get("inflow", [])
        es_final = config.get("es_final", False)
        manager = AgendaManager()
        manager.cancelar_por_entidad_y_vinculo(receta_id, inflow, es_final)
        manager.cancelar_por_entidad_y_vinculo(receta_id, inflow, es_final, origen="manual")
        manager.cancelar_por_entidad_y_vinculo(receta_id, [estado_id], origen="manual")

        self._crear_recordatorio_automatico(receta_id, estado_id)

        msg_config = config.get("mensaje_al_entrar")
        if msg_config:
            texto = self._msg(msg_config["clave_texto"])
            tipo = msg_config["tipo"]
            self.receta_manager.agregar_mensaje_chat(receta_id, "farmacia", texto, tipo=tipo)
        self._enviar_notificacion_push(receta_id, estado_id)

    def _crear_recordatorio_automatico(self, receta_id, estado_id):
        """Crea recordatorio automático de seguimiento según el estado (B11/B12/B14/B16)."""
        self.receta_manager.crear_recordatorio_automatico(receta_id, estado_id)

    def _enviar_notificacion_push(self, receta_id, estado_id):
        """
        Envía notificacion_push al cliente si el estado la tiene configurada.
        Resuelve el LID del cliente desde persona_id de la receta.
        """
        config = self._get_estado_receta_config(estado_id)
        mensaje = config.get("notificacion_push")
        if not mensaje:
            return

        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return

        _, receta = resultado
        persona_id = receta.get("persona_id", "")
        if not persona_id:
            return

        lids = self._resolver_lids(persona_id)
        if not lids:
            print(f"[NOTIFICACION_PUSH] Sin LID para persona {persona_id} ni titulares — no se puede enviar")
            return

        from src.send_wpp import SendWPP
        for lid in lids:
            SendWPP(lid).enviar(mensaje)
            print(f"[NOTIFICACION_PUSH] Enviado a {lid} | Estado: {estado_id}")

    def _enviar_notificacion_push_staff(self, estado_id):
        """
        Envía notificacion_push_staff a los operadores configurados en
        farmacia_config.operadores_notificacion si el estado la tiene.
        """
        config = self._get_estado_receta_config(estado_id)
        mensaje = config.get("notificacion_push_staff")
        if not mensaje:
            return

        operadores = self.farm_config.get("operadores_notificacion", [])
        if not operadores:
            print(f"[NOTIFICACION_PUSH_STAFF] Sin operadores configurados — no se puede enviar")
            return

        from src.send_wpp import SendWPP
        for lid in operadores:
            SendWPP(lid).enviar(mensaje)
            print(f"[NOTIFICACION_PUSH_STAFF] Enviado a {lid} | Estado: {estado_id}")

    def _evaluar_estado_post_cambio_item(self, receta_id, sesiones):
        """
        Evalúa automáticamente después de cada cambio de estado de item:
        1. ¿Hay items en pendiente? → queda en en_gestion, farmacéutico sigue
        2. ¿No hay pendientes pero hay sin_stock/alternativa_ofrecida? → cambia a a_la_espera (H)
        3. ¿Todos resueltos? → sugiere avanzar
        """
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return

        _, receta = resultado
        estado_actual = receta.get("estado", "")

        estado_config = self._get_estado_receta_config(estado_actual)
        if not estado_config.get("evaluar_items"):
            return

        items_activos = [it for it in receta["items"] if it["estado_item"] != ESTADO_OMITIDO]
        items_cfg = self.farm_config.get("recetas", {}).get("estados_item", {})

        hay_pendientes = any(items_cfg.get(it["estado_item"], {}).get("es_pendiente") for it in items_activos)
        hay_sin_resolver = any(items_cfg.get(it["estado_item"], {}).get("sin_resolver") for it in items_activos)
        todos_resueltos = bool(items_activos) and not hay_pendientes and not hay_sin_resolver

        destino_retorno = estado_config.get("destino_retorno_gestion")
        destino_espera = estado_config.get("destino_sin_resolver")

        if hay_pendientes:
            # Escenario 1: aún hay items por procesar — si aplica, retornar a gestión
            if destino_retorno and estado_actual != destino_retorno:
                self.receta_manager.cambiar_estado(receta_id, destino_retorno, "Farmacia retomó gestión")
            return

        if hay_sin_resolver:
            # Escenario 2: items sin resolver → estado espera cliente
            if destino_espera and estado_actual != destino_espera:
                self.receta_manager.desestimar_solicitud_token(receta_id)
                self.receta_manager.cambiar_estado(receta_id, destino_espera, "Items procesados — esperando respuesta del cliente")
                self.sw.enviar(self._msg("cambio_automatico_a_la_espera"))
                self._acciones_al_entrar(receta_id, destino_espera)
            return

        if todos_resueltos:
            # Escenario 3: todos resueltos — si aplica, retornar a gestión
            if destino_retorno and estado_actual != destino_retorno:
                self.receta_manager.cambiar_estado(receta_id, destino_retorno, "Todos los items resueltos — listo para avanzar")
            self.sw.enviar(self._msg("todos_resueltos"))

    def _desestimar_notas_items(self, receta_id):
        """Marca como leídos por el cliente los mensajes de sin_stock/alternativa del chat."""
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return
        _, receta = resultado
        persona_id = receta.get("persona_id", "")
        for msg in receta.get("chat", []):
            if (msg["autor"] == "farmacia"
                    and msg.get("tipo") in ("sin_stock", "alternativa")
                    and persona_id not in msg.get("leido_por", [])):
                self.receta_manager.marcar_mensaje_leido(receta_id, msg["id"], persona_id)

    def _desestimar_notas_item(self, receta_id, item_idx):
        """Marca como leídos por el cliente los mensajes del chat vinculados a un item confirmado."""
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return
        _, receta = resultado
        persona_id = receta.get("persona_id", "")
        med_id = receta["items"][item_idx]["medicamento_id"]
        for msg in receta.get("chat", []):
            if (msg["autor"] == "farmacia"
                    and msg.get("tipo") in ("sin_stock", "alternativa")
                    and msg.get("medicamento_id") == med_id
                    and persona_id not in msg.get("leido_por", [])):
                self.receta_manager.marcar_mensaje_leido(receta_id, msg["id"], persona_id)

    def _reset_items_si_corresponde(self, receta_id, nuevo_estado):
        """Resetea ítems a 'pendiente' si el estado destino lo requiere según config."""
        config = self._get_estado_receta_config(nuevo_estado)
        if config.get("reset_items_al_entrar", False):
            self.receta_manager.reset_items(receta_id, "pendiente")

    def _limpiar_si_rollback(self, receta_id, estado_previo, nuevo_estado):
        """Si es retroceso (nuevo_estado en inflow de estado_previo), cancela todos los
        recordatorios del nodo actual antes de transicionar."""
        config_previo = self._get_estado_receta_config(estado_previo)
        if nuevo_estado not in config_previo.get("inflow", []):
            return
        manager = AgendaManager()
        manager.cancelar_por_entidad_y_vinculo(receta_id, [estado_previo], origen="automatico")
        manager.cancelar_por_entidad_y_vinculo(receta_id, [estado_previo], origen="manual")

    def _desestimar_si_rollback(self, receta_id, estado_previo, nuevo_estado):
        """Si la transición es un retroceso (nuevo_estado en inflow de estado_previo),
        desestima todas las notas pendientes del usuario y envía push de cancelación."""
        config_previo = self._get_estado_receta_config(estado_previo)
        if nuevo_estado not in config_previo.get("inflow", []):
            return
        self.receta_manager.desestimar_todas_notas(receta_id)
        msg = self.farm_config.get("recetas", {}).get("notificacion_push_rollback")
        if not msg:
            return
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return
        _, receta = resultado
        persona_id = receta.get("persona_id", "")
        if self.receta_manager.contar_chat_no_leidos_usuario(persona_id) > 0:
            print(f"[ROLLBACK_PUSH] Omitido — hay mensajes no leídos pendientes para {persona_id}")
            return
        lids = self._resolver_lids(persona_id)
        from src.send_wpp import SendWPP
        for lid in lids:
            SendWPP(lid).enviar(msg)
            print(f"[ROLLBACK_PUSH] Enviado a {lid} | {estado_previo} → {nuevo_estado}")

    def _salir(self, sesiones):
        sesiones[self.numero].staff_receta_estado = None
        sesiones[self.numero].staff_receta_id = None
        sesiones[self.numero].staff_receta_lista = None
        sesiones[self.numero].staff_receta_reintentos = 0
        sesiones[self.numero].staff_receta_items_visibles = None
        sesiones[self.numero].staff_receta_esperando_estado = False
        sesiones[self.numero].staff_receta_item_idx = None
        sesiones[self.numero].staff_receta_opciones_estado = None
        sesiones[self.numero].staff_receta_esperando_motivo = False
        sesiones[self.numero].staff_receta_nuevo_estado = None
        sesiones[self.numero].staff_receta_opciones_activas = None
        sesiones[self.numero].staff_consulta_medicamento_id = None
        sesiones[self.numero].staff_receta_sec_items = None
        sesiones[self.numero].staff_receta_sec_cursor = 0
        sesiones[self.numero].staff_receta_sec_activo = False

    def _volver_menu_staff(self, sesiones):
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))