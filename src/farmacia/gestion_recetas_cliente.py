# src/farmacia/gestion_recetas_cliente.py
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


from src.tenant import data_path


class GestionRecetasCliente:
    """
    Flujo de gestión de recetas desde el lado del cliente.
    Estados:
        - menu: submenú principal
        - notificacion: mensaje accionable de farmacia (alternativa/sin_stock/mensaje)
        - chat_notificacion: escribir consulta durante una notificación antes de decidir
        - escribir_token: ingresar token de autorización
        - ver_recetas: listado de recetas activas (solo lectura)
        - ver_chat_lista: elegir receta para ver el hilo de chat
        - chat_libre: escribir en el hilo de una receta
    Tipos de mensaje (campo tipo en chat):
        - mensaje: informativo genérico — opciones Entendido/Responder
        - alternativa: oferta de cambio — aceptar/rechazar/esperar/consultar
        - sin_stock: sin stock — rechazar/esperar/consultar
        - solicitud_token: solicitud de token — ingresar token
        - accion: respuesta del cliente (no genera notificación nueva)
        - token_respuesta: token enviado por el cliente
    """

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
        self.farm_config = self._cargar_config()

    def _cargar_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        estado = getattr(sesiones[self.numero], "cliente_receta_estado", None)
        return estado is not None

    def _setup(self, sesiones, beneficiario_id):
        """Prepara estado común y migra datos legacy."""
        sesiones[self.numero].cliente_receta_beneficiario_id = beneficiario_id
        for rec in self.receta_manager.buscar_recetas_activas(beneficiario_id):
            self.receta_manager.migrar_notas_a_chat(rec["receta_id"])

    def iniciar_acciones(self, sesiones, beneficiario_id):
        self._setup(sesiones, beneficiario_id)
        self._mostrar_siguiente_notificacion(sesiones)

    def iniciar_ver_recetas(self, sesiones, beneficiario_id):
        self._setup(sesiones, beneficiario_id)
        self._mostrar_mis_recetas(sesiones)

    def iniciar_recordatorios(self, sesiones, beneficiario_id):
        self._setup(sesiones, beneficiario_id)
        self.sw.enviar("🚧 Mis recordatorios — próximamente...")
        self._salir(sesiones)

    def iniciar_chat(self, sesiones, beneficiario_id):
        self._setup(sesiones, beneficiario_id)
        self._mostrar_lista_chat(sesiones)

    def procesar(self, comando, sesiones):
        estado = getattr(sesiones[self.numero], "cliente_receta_estado", None)

        if estado == "notificacion":
            self._procesar_notificacion(comando, sesiones)
        elif estado == "escribir_consulta":
            self._procesar_escribir_consulta(comando, sesiones)
        elif estado == "escribir_token":
            self._procesar_escribir_token(comando, sesiones)
        elif estado == "ver_recetas":
            self._procesar_ver_recetas(comando, sesiones)
        elif estado == "ver_chat_lista":
            self._procesar_ver_chat_lista(comando, sesiones)
        elif estado == "chat_libre":
            self._procesar_chat_libre(comando, sesiones)

    # ── ACCIONES (una por una) ────────────────────────────────────────────────

    def _mostrar_siguiente_notificacion(self, sesiones):
        """Muestra la siguiente acción pendiente o avisa que no hay más."""
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        resultado = self.receta_manager.get_primer_chat_no_leido_usuario(beneficiario_id)

        if not resultado:
            self.sw.enviar("✅ No tenés acciones pendientes para esta receta.")
            self._salir(sesiones)
            return

        receta_id, msg = resultado
        sesiones[self.numero].cliente_receta_nota_id = msg["id"]
        sesiones[self.numero].cliente_receta_nota_receta_id = receta_id
        sesiones[self.numero].cliente_receta_nota_tipo = msg.get("tipo", "mensaje")
        sesiones[self.numero].cliente_receta_nota_medicamento_id = msg.get("medicamento_id")

        rec_resultado = self.receta_manager.get_receta(receta_id)
        if not rec_resultado:
            self.receta_manager.marcar_mensaje_leido(receta_id, msg["id"], beneficiario_id)
            self._mostrar_siguiente_notificacion(sesiones)
            return

        _, receta = rec_resultado
        estado_id = receta.get("estado", "pendiente")
        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        estado_config = estados_config.get(estado_id, {})
        estado_label = estado_config.get("label", estado_id)
        estado_icono = estado_config.get("icono", "")

        tipo = msg.get("tipo", "mensaje")
        med_id = msg.get("medicamento_id")

        med_label = self.med_manager.get_label(med_id) if med_id else None
        lineas = [
            "🔔 *Acción pendiente*",
            f"📊 Receta en estado: {estado_icono} {estado_label}",
            "",
        ]
        if med_label:
            lineas.append(f"💊 *{med_label}*")

        if tipo == "respuesta_consulta" and med_id:
            # Buscar la consulta original del cliente para este medicamento
            chat = receta.get("chat", [])
            consulta_original = next(
                (m for m in chat
                 if m.get("tipo") == "consulta" and m.get("medicamento_id") == med_id),
                None
            )
            if consulta_original:
                lineas.append(f" └ 👤 {consulta_original['mensaje']}")
                lineas.append(f"    └ 🏥 {msg.get('mensaje', '')}")
            else:
                lineas.append(f"💬 {msg.get('mensaje', '')}")
        else:
            lineas.append(f"💬 {msg.get('mensaje', '')}")
        lineas.append("")

        # solicitud_token: flujo especial de texto libre
        if tipo == "solicitud_token":
            lineas.append("Escribí el *token de autorización*:")
            sesiones[self.numero].cliente_receta_opciones_keys = []
            sesiones[self.numero].cliente_receta_estado = "escribir_token"
            cant_restantes = self.receta_manager.contar_chat_no_leidos_usuario(beneficiario_id) - 1
            if cant_restantes > 0:
                lineas.append(f"\n📬 Quedan {cant_restantes} acción(es) más.")
            lineas.append("Escribí *cancelar* para volver:")
            self.sw.enviar("\n".join(lineas))
            return

        # Opciones desde config según tipo de notificación
        opciones_config = self.farm_config.get("recetas", {}).get("opciones_cliente", {})

        if tipo == "respuesta_consulta" and med_id:
            item = next(
                (it for it in receta.get("items", []) if it["medicamento_id"] == med_id),
                None
            )
            estado_item = item.get("estado_item", "sin_stock") if item else "sin_stock"
            opciones = opciones_config.get("respuesta_consulta", {}).get(estado_item, [])
        else:
            opciones = opciones_config.get(tipo, [])

        for i, op in enumerate(opciones, 1):
            lineas.append(f"{i}. {op['label']}")

        sesiones[self.numero].cliente_receta_opciones_keys = [op["key"] for op in opciones]
        sesiones[self.numero].cliente_receta_estado = "notificacion"

        cant_restantes = self.receta_manager.contar_chat_no_leidos_usuario(beneficiario_id) - 1
        if cant_restantes > 0:
            lineas.append(f"\n📬 Quedan {cant_restantes} acción(es) más.")
        lineas.append("Escribí *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_notificacion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        opciones_keys = getattr(sesiones[self.numero], "cliente_receta_opciones_keys", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(opciones_keys):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        key = opciones_keys[idx]
        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        msg_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        med_id = getattr(sesiones[self.numero], "cliente_receta_nota_medicamento_id", None)
        tipo = getattr(sesiones[self.numero], "cliente_receta_nota_tipo", "mensaje")

        opciones_config = self.farm_config.get("recetas", {}).get("opciones_cliente", {})
        if tipo == "respuesta_consulta" and med_id:
            rec_resultado = self.receta_manager.get_receta(receta_id)
            if rec_resultado:
                _, receta = rec_resultado
                item = next((it for it in receta.get("items", []) if it["medicamento_id"] == med_id), None)
                estado_item = item.get("estado_item", "sin_stock") if item else "sin_stock"
            else:
                estado_item = "sin_stock"
            lista_opciones = opciones_config.get("respuesta_consulta", {}).get(estado_item, [])
        else:
            lista_opciones = opciones_config.get(tipo, [])

        opcion = next((op for op in lista_opciones if op["key"] == key), None)
        if not opcion:
            self.sw.enviar("❌ Opción no válida.")
            return

        post_accion = opcion.get("post_accion", "siguiente")

        if post_accion != "sub_flujo":
            self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)

        if opcion.get("texto_accion"):
            self.receta_manager.agregar_mensaje_chat(
                receta_id, beneficiario_id, opcion["texto_accion"],
                tipo="accion", medicamento_id=med_id
            )

        if opcion.get("estado_item_destino"):
            self._cambiar_item_por_medicamento_id(receta_id, med_id, opcion["estado_item_destino"])

        if opcion.get("msg_confirmacion"):
            self.sw.enviar(opcion["msg_confirmacion"])

        if post_accion == "evaluar_y_siguiente":
            self._evaluar_estado_post_respuesta(receta_id, sesiones)
        elif post_accion == "recordatorio_y_siguiente":
            self._iniciar_recordatorio_m7(sesiones, receta_id, med_id, beneficiario_id, opcion)
        elif post_accion == "siguiente":
            self._mostrar_siguiente_notificacion(sesiones)
        elif post_accion == "sub_flujo":
            flujo = opcion.get("flujo", "")
            if flujo == "escribir_consulta":
                med_label = self.med_manager.get_label(med_id) if med_id else "el medicamento"
                msj = self.farm_config.get("recetas", {}).get("mensajes", {}).get(
                    "pedir_texto_consulta", "✍️ Escribí tu consulta:\n\nO escribí *cancelar* para volver:"
                ).replace("{medicamento}", med_label)
                sesiones[self.numero].cliente_receta_estado = flujo
                self.sw.enviar(msj)

    def _iniciar_recordatorio_m7(self, sesiones, receta_id, med_id, beneficiario_id, opcion=None):
        """M7 — inicia el flujo de creación de recordatorio desde esperar/agendar."""
        from src.agenda.recordatorio_service import RecordatorioService
        resultado_receta = self.receta_manager.get_receta(receta_id)
        fecha_venc = ""
        receta_data = {}
        if resultado_receta:
            _, receta_data = resultado_receta
            fecha_venc = receta_data.get("fecha_vencimiento", "")

        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        estado_actual_cfg = estados_config.get(receta_data.get("estado", ""), {})
        estado_vinculado = estado_actual_cfg.get("camino_feliz", "")
        condicion_item = (opcion or {}).get("estado_item_destino", "")
        dest_recs = estados_config.get(estado_vinculado, {}).get("recordatorio", [])
        rec_cfg = next((r for r in dest_recs if r.get("condicion_item") == condicion_item), {})
        origen = rec_cfg.get("generacion")

        med_label = self.med_manager.get_label(med_id) if med_id else "el medicamento"
        rs = RecordatorioService(self.numero)
        rs.iniciar_crear(
            sesiones=sesiones,
            persona_id=beneficiario_id,
            enlatado="farmacia",
            entidad_id=receta_id,
            descripcion=f"🔔 {med_label} — revisá si llegó al stock",
            fecha_max=fecha_venc,
            estado_vinculado=estado_vinculado,
            origen=origen,
        )
        if not rs.esta_en_flujo(sesiones):
            self._evaluar_estado_post_respuesta(receta_id, sesiones)
        else:
            sesiones[self.numero].agenda_receta_id_pendiente = receta_id
            sesiones[self.numero].agenda_post_flujo_accion = "siguiente_notificacion_cliente"

    def continuar_siguiente_notificacion(self, sesiones):
        """Permite a submenu_farmacia reanudar las acciones tras un subflujo de agenda."""
        receta_id = getattr(sesiones[self.numero], "agenda_receta_id_pendiente", None)
        sesiones[self.numero].agenda_receta_id_pendiente = None
        if receta_id:
            self._evaluar_estado_post_respuesta(receta_id, sesiones)
        else:
            self._mostrar_siguiente_notificacion(sesiones)

    def _procesar_escribir_consulta(self, comando, sesiones):
        """El cliente escribe su consulta sobre un medicamento — transiciona H→M."""
        if comando.strip() == "cancelar":
            self._mostrar_siguiente_notificacion(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        msg_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        med_id = getattr(sesiones[self.numero], "cliente_receta_nota_medicamento_id", None)

        flujo = self.farm_config.get("recetas", {}).get("flujos_input_cliente", {}).get("escribir_consulta", {})
        estado_destino = flujo.get("estado_receta_destino", "en_consulta")
        notificacion_staff = flujo.get("notificacion_staff", estado_destino)
        msg_key = flujo.get("msg_confirmacion", "consulta_enviada")

        self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
        self.receta_manager.agregar_mensaje_chat(
            receta_id, beneficiario_id, comando.strip(),
            tipo="consulta", medicamento_id=med_id
        )
        self.receta_manager.cambiar_estado(receta_id, estado_destino, "Cliente consulta sobre medicamento")
        self._enviar_notificacion_push_staff(notificacion_staff)

        msj = self.farm_config.get("recetas", {}).get("mensajes", {}).get(
            msg_key, "✅ Consulta enviada."
        )
        self.sw.enviar(msj)
        self._mostrar_siguiente_notificacion(sesiones)

    # ── TOKEN ─────────────────────────────────────────────────────────────────

    def _procesar_escribir_token(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        msg_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)

        flujo = self.farm_config.get("recetas", {}).get("flujos_input_cliente", {}).get("escribir_token", {})
        estado_destino = flujo.get("estado_receta_destino", "token_enviado")
        prefijo_chat = flujo.get("prefijo_chat", "Token de autorización: ")
        msg_key = flujo.get("msg_confirmacion", "token_enviado_cliente")

        self.receta_manager.marcar_tipo_como_leido(receta_id, "solicitud_token", beneficiario_id)
        self.receta_manager.cambiar_estado(receta_id, estado_destino, "Token enviado por paciente")
        self.receta_manager.agregar_mensaje_chat(
            receta_id, beneficiario_id,
            f"{prefijo_chat}{comando.strip()}",
            tipo="token_respuesta"
        )

        msj = self.farm_config.get("recetas", {}).get("mensajes", {}).get(
            msg_key, "✅ Token enviado a la farmacia. Te avisaremos cuando sea procesado."
        )
        self.sw.enviar(msj)
        self._mostrar_siguiente_notificacion(sesiones)

    # ── VER MIS RECETAS ───────────────────────────────────────────────────────

    def _mostrar_mis_recetas(self, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        recetas = self.receta_manager.buscar_recetas_activas(beneficiario_id)

        if not recetas:
            self.sw.enviar("📋 No tenés recetas activas en este momento.")
            self._salir(sesiones)
            return

        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})

        lineas = ["📋 *Mis recetas activas:*"]
        for i, rec in enumerate(recetas, 1):
            estado_id = rec.get("estado", "pendiente")
            estado_cfg = estados_config.get(estado_id, {})
            estado_label = estado_cfg.get("label", estado_id)
            estado_icono = estado_cfg.get("icono", "")
            vencimiento = rec.get("fecha_vencimiento", "—")

            lineas.append("")
            lineas.append(f"*Receta {i}* — Vence: {vencimiento}")
            lineas.append(f"{estado_icono} {estado_label}")

            for item in rec.get("items", []):
                if item["estado_item"] == ESTADO_OMITIDO:
                    continue
                label = self.med_manager.get_label(item["medicamento_id"])
                item_cfg = estados_item_config.get(item["estado_item"], {})
                item_icono = item_cfg.get("icono", "❓")
                item_label = item_cfg.get("label", item["estado_item"])
                lineas.append(f"   {item_icono} {label} ({item_label})")

        lineas.append("Escribí *cancelar* para volver:")
        sesiones[self.numero].cliente_receta_estado = "ver_recetas"
        self.sw.enviar("\n".join(lineas))

    def _procesar_ver_recetas(self, comando, sesiones):
        self._salir(sesiones)

    # ── CHAT POR RECETA ───────────────────────────────────────────────────────

    def _mostrar_lista_chat(self, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        recetas = self.receta_manager.buscar_recetas_activas(beneficiario_id)

        if not recetas:
            self.sw.enviar("📋 No tenés recetas activas.")
            self._salir(sesiones)
            return

        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        lineas = ["💬 *Seleccioná una receta:*\n"]
        for i, rec in enumerate(recetas, 1):
            estado_id = rec.get("estado", "pendiente")
            estado_cfg = estados_config.get(estado_id, {})
            icono = estado_cfg.get("icono", "")
            vencimiento = rec.get("fecha_vencimiento", "—")
            no_leidos = self.receta_manager.contar_no_leidos_chat(rec["receta_id"], beneficiario_id)
            linea = f"{i}. {icono} Vence: {vencimiento}"
            if no_leidos:
                linea += f" 💬 {no_leidos} nuevos"
            lineas.append(linea)

        lineas.append(f"\nEscribí el número o *cancelar* para volver:")
        sesiones[self.numero].cliente_receta_estado = "ver_chat_lista"
        sesiones[self.numero].cliente_receta_lista = recetas
        self.sw.enviar("\n".join(lineas))

    def _procesar_ver_chat_lista(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        recetas = getattr(sesiones[self.numero], "cliente_receta_lista", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(recetas):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        sesiones[self.numero].cliente_receta_chat_receta_id = recetas[idx]["receta_id"]
        self._mostrar_hilo_chat(sesiones)

    def _mostrar_hilo_chat(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "cliente_receta_chat_receta_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)

        rec_resultado = self.receta_manager.get_receta(receta_id)
        if not rec_resultado:
            self.sw.enviar("❌ Receta no encontrada.")
            self._salir(sesiones)
            return

        _, receta = rec_resultado
        estado_id = receta.get("estado", "pendiente")
        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        estado_config = estados_config.get(estado_id, {})
        estado_label = estado_config.get("label", estado_id)
        estado_icono = estado_config.get("icono", "")
        vencimiento = receta.get("fecha_vencimiento", "—")

        chat = self.receta_manager.get_chat(receta_id)

        lineas = [
            f"💬 *Chat — Receta vence: {vencimiento}*",
            f"Estado: {estado_icono} {estado_label}",
            ""
        ]

        if not chat:
            lineas.append("_(Sin mensajes aún)_")
        else:
            # Agrupar por medicamento_id; mensajes sin med_id van a generales
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

            TIPOS_ACCIONABLES_HILO = {"sin_stock", "alternativa", "solicitud_token"}
            TIPOS_RESPUESTA_DIRECTA = {"accion", "token_respuesta"}

            # Hilo por medicamento
            for mid in meds_order:
                med_label = self.med_manager.get_label(mid)
                lineas.append(f"💊 *{med_label}*")

                msgs = meds_msgs[mid]
                n = len(msgs)

                # Último índice de cada tipo accionable
                ultimo_idx_por_tipo = {}
                for i, msg in enumerate(msgs):
                    if msg.get("tipo") in TIPOS_ACCIONABLES_HILO:
                        ultimo_idx_por_tipo[msg["tipo"]] = i

                # Ocultar accionables no-últimos y su respuesta inmediata
                ids_ocultar = set()
                for i, msg in enumerate(msgs):
                    tipo = msg.get("tipo")
                    if tipo in TIPOS_ACCIONABLES_HILO and ultimo_idx_por_tipo.get(tipo) != i:
                        ids_ocultar.add(msg["id"])
                        if i + 1 < n and msgs[i + 1].get("tipo") in TIPOS_RESPUESTA_DIRECTA:
                            ids_ocultar.add(msgs[i + 1]["id"])

                consumed = set()
                for i, msg in enumerate(msgs):
                    if msg["id"] in consumed or msg["id"] in ids_ocultar:
                        continue
                    tipo = msg.get("tipo", "mensaje")
                    autor = msg["autor"]
                    if tipo in TIPOS_ACCIONABLES_HILO:
                        lineas.append(f" 🏥 {msg['mensaje']}")
                    elif tipo == "consulta":
                        lineas.append(f"  └ 👤 {msg['mensaje']}")
                        respuesta = next(
                            (r for r in msgs[i + 1:]
                             if r.get("tipo") == "respuesta_consulta" and r["id"] not in consumed),
                            None
                        )
                        if respuesta:
                            lineas.append(f"     └ 🏥 {respuesta['mensaje']}")
                            consumed.add(respuesta["id"])
                    elif tipo == "respuesta_consulta":
                        pass  # ya mostrado bajo su consulta
                    elif tipo in TIPOS_RESPUESTA_DIRECTA:
                        lineas.append(f"  └ 👤 {msg['mensaje']}")
                    else:
                        prefix = "🏥" if autor == "farmacia" else "👤"
                        lineas.append(f"  {prefix} {msg['mensaje']}")
                lineas.append("")

            # Mensajes generales (sin medicamento_id) en orden cronológico
            for msg in generales:
                prefix = "🏥" if msg["autor"] == "farmacia" else "👤"
                lineas.append(f"{prefix} {msg['mensaje']}")

        lineas.append("")
        lineas.append("Escribí tu consulta o *cancelar* para volver:")

        # Solo marcar como leídos los mensajes informativos — los accionables
        # (sin_stock, alternativa, solicitud_token) siguen pendientes hasta que
        # el cliente decida explícitamente desde el flujo de notificaciones.
        TIPOS_ACCIONABLES = {"sin_stock", "alternativa", "solicitud_token", "respuesta_consulta"}
        for msg in chat:
            if (msg["autor"] != beneficiario_id
                    and beneficiario_id not in msg["leido_por"]
                    and msg.get("tipo", "mensaje") not in TIPOS_ACCIONABLES):
                self.receta_manager.marcar_mensaje_leido(receta_id, msg["id"], beneficiario_id)

        sesiones[self.numero].cliente_receta_estado = "chat_libre"
        self.sw.enviar("\n".join(lineas))

    def _procesar_chat_libre(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_lista_chat(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "cliente_receta_chat_receta_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)

        self.receta_manager.agregar_mensaje_chat(
            receta_id, beneficiario_id, comando.strip(), tipo="mensaje"
        )
        flujo = self.farm_config.get("recetas", {}).get("flujos_input_cliente", {}).get("chat_libre", {})
        push_msg = flujo.get("notificacion_push_staff")
        if push_msg:
            operadores = self.farm_config.get("operadores_notificacion", [])
            from src.send_wpp import SendWPP
            for lid in operadores:
                SendWPP(lid).enviar(push_msg)
        self.sw.enviar("✅ Mensaje enviado.")
        self._mostrar_hilo_chat(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _cambiar_item_por_medicamento_id(self, receta_id, medicamento_id, nuevo_estado):
        """Cambia el estado del item con el medicamento_id dado."""
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado or not medicamento_id:
            return
        _, receta = resultado
        for i, item in enumerate(receta.get("items", [])):
            if item["estado_item"] != ESTADO_OMITIDO and item["medicamento_id"] == medicamento_id:
                self.receta_manager.cambiar_estado_item(receta_id, i, nuevo_estado)
                return

    def _evaluar_estado_post_respuesta(self, receta_id, sesiones):
        """Avanza la receta a en_gestion si todos los items están resueltos, luego muestra siguiente."""
        resultado = self.receta_manager.get_receta(receta_id)
        if resultado:
            _, receta = resultado
            beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
            items_activos = [it for it in receta["items"] if it["estado_item"] != ESTADO_OMITIDO]
            items_cfg = self.farm_config.get("recetas", {}).get("estados_item", {})
            todos_resueltos = all(
                not items_cfg.get(it["estado_item"], {}).get("es_pendiente") and
                not items_cfg.get(it["estado_item"], {}).get("requiere_respuesta_cliente")
                for it in items_activos
            )

            estado_receta_id = receta["estado"]
            estado_receta_cfg = self.farm_config.get("recetas", {}).get("estados_receta", {}).get(estado_receta_id, {})
            if todos_resueltos and estado_receta_cfg.get("evaluar_items"):
                from src.agenda.agenda_manager import AgendaManager
                AgendaManager().cancelar_por_entidad_y_vinculo(receta_id, [estado_receta_id], origen="automatico")
                cf = estado_receta_cfg.get("camino_feliz")
                self.receta_manager.cambiar_estado(receta_id, cf, "Cliente respondió todas las novedades")
                self.receta_manager.crear_recordatorio_automatico(receta_id, cf)
                self.receta_manager.agregar_mensaje_chat(
                    receta_id, beneficiario_id,
                    "Respondí a todas las novedades. La receta está lista para continuar.",
                    tipo="accion"
                )
                self.sw.enviar("📤 Tus respuestas fueron enviadas a la farmacia.")

        self._mostrar_siguiente_notificacion(sesiones)

    def _enviar_notificacion_push_staff(self, estado_id):
        """Envía notificacion_push_staff a los operadores configurados."""
        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        mensaje = estados_config.get(estado_id, {}).get("notificacion_push_staff")
        if not mensaje:
            return
        operadores = self.farm_config.get("operadores_notificacion", [])
        if not operadores:
            print(f"[PUSH_STAFF] Sin operadores configurados — no se puede enviar")
            return
        from src.send_wpp import SendWPP
        for lid in operadores:
            SendWPP(lid).enviar(mensaje)
            print(f"[PUSH_STAFF] Enviado a {lid} | Estado: {estado_id}")

    def contar_notificaciones(self, beneficiario_id):
        """Retorna la cantidad de acciones pendientes para un beneficiario."""
        return self.receta_manager.contar_chat_no_leidos_usuario(beneficiario_id)

    def contar_chat_nuevos(self, beneficiario_id):
        """Retorna la cantidad de mensajes de chat no leídos para un beneficiario."""
        return self.receta_manager.contar_mensajes_no_leidos_usuario(beneficiario_id)

    def _salir(self, sesiones):
        sesiones[self.numero].cliente_receta_estado = None
        sesiones[self.numero].cliente_receta_beneficiario_id = None
        sesiones[self.numero].cliente_receta_nota_id = None
        sesiones[self.numero].cliente_receta_nota_receta_id = None
        sesiones[self.numero].cliente_receta_nota_tipo = None
        sesiones[self.numero].cliente_receta_nota_medicamento_id = None
        sesiones[self.numero].cliente_receta_opciones_keys = None
        sesiones[self.numero].cliente_receta_lista = None
        sesiones[self.numero].cliente_receta_chat_receta_id = None
        sesiones[self.numero].agenda_receta_id_pendiente = None
