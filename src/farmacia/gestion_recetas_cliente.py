# src/farmacia/gestion_recetas_cliente.py
import json
import os
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.cliente.persona_manager import PersonaManager
from src.farmacia.receta_manager import RecetaManager
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

    def iniciar(self, sesiones, beneficiario_id):
        """Punto de entrada — migra datos legacy y muestra submenú."""
        sesiones[self.numero].cliente_receta_estado = "menu"
        sesiones[self.numero].cliente_receta_beneficiario_id = beneficiario_id
        for rec in self.receta_manager.buscar_recetas_activas(beneficiario_id):
            self.receta_manager.migrar_notas_a_chat(rec["receta_id"])
        self._mostrar_menu(sesiones)

    def procesar(self, comando, sesiones):
        estado = getattr(sesiones[self.numero], "cliente_receta_estado", None)

        if estado == "menu":
            self._procesar_menu(comando, sesiones)
        elif estado == "notificacion":
            self._procesar_notificacion(comando, sesiones)
        elif estado == "chat_notificacion":
            self._procesar_chat_notificacion(comando, sesiones)
        elif estado == "escribir_token":
            self._procesar_escribir_token(comando, sesiones)
        elif estado == "ver_recetas":
            self._procesar_ver_recetas(comando, sesiones)
        elif estado == "ver_chat_lista":
            self._procesar_ver_chat_lista(comando, sesiones)
        elif estado == "chat_libre":
            self._procesar_chat_libre(comando, sesiones)

    # ── SUBMENÚ ───────────────────────────────────────────────────────────────

    def _mostrar_menu(self, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        cant_notif = self.receta_manager.contar_chat_no_leidos_usuario(beneficiario_id)

        notif_label = f" ({cant_notif} nuevos)" if cant_notif > 0 else ""

        lineas = [
            "📬 *Gestión de recetas*\n",
            f"1. 🔔 Notificaciones{notif_label}",
            "2. 📋 Ver mis recetas",
            "3. ⏰ Mis recordatorios",
            "4. 💬 Chat",
            "Escribí *cancelar* para volver:"
        ]
        sesiones[self.numero].cliente_receta_estado = "menu"
        self.sw.enviar("\n".join(lineas))

    def _procesar_menu(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        if comando.strip() == "1":
            self._mostrar_siguiente_notificacion(sesiones)
        elif comando.strip() == "2":
            self._mostrar_mis_recetas(sesiones)
        elif comando.strip() == "3":
            self.sw.enviar("🚧 Mis recordatorios — próximamente...")
            self._mostrar_menu(sesiones)
        elif comando.strip() == "4":
            self._mostrar_lista_chat(sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    # ── NOTIFICACIONES (una por una) ──────────────────────────────────────────

    def _mostrar_siguiente_notificacion(self, sesiones):
        """Muestra el siguiente mensaje no leído o avisa que no hay más."""
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        resultado = self.receta_manager.get_primer_chat_no_leido_usuario(beneficiario_id)

        if not resultado:
            self.sw.enviar("✅ No tenés notificaciones pendientes.")
            self._mostrar_menu(sesiones)
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
        cant_restantes = self.receta_manager.contar_chat_no_leidos_usuario(beneficiario_id) - 1

        lineas = [
            "🔔 *Notificación de la farmacia*",
            f"📊 Receta en estado: {estado_icono} {estado_label}",
            "",
            f"💬 {msg.get('mensaje', '')}",
            ""
        ]

        if tipo == "alternativa":
            lineas.append("1. ✅ Aceptar cambio")
            lineas.append("2. ❌ Rechazar medicamento")
            lineas.append("3. ⏳ Esperar / agendar")
            lineas.append("4. 💬 Consultar antes de decidir")
            sesiones[self.numero].cliente_receta_estado = "notificacion"

        elif tipo == "sin_stock":
            lineas.append("1. ❌ Rechazar medicamento")
            lineas.append("2. ⏳ Esperar / agendar")
            lineas.append("3. 💬 Consultar antes de decidir")
            sesiones[self.numero].cliente_receta_estado = "notificacion"

        elif tipo == "solicitud_token":
            lineas.append("Escribí el *token de autorización*:")
            sesiones[self.numero].cliente_receta_estado = "escribir_token"

        else:
            # Mensaje genérico de farmacia — ofrecer Entendido o Responder
            lineas.append("1. ✅ Entendido")
            lineas.append("2. 💬 Responder")
            sesiones[self.numero].cliente_receta_estado = "notificacion"

        if cant_restantes > 0:
            lineas.append(f"\n📬 Quedan {cant_restantes} notificación(es) más.")
        lineas.append("Escribí *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_notificacion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_menu(sesiones)
            return

        tipo = getattr(sesiones[self.numero], "cliente_receta_nota_tipo", "")
        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        msg_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)

        if tipo == "alternativa":
            if comando.strip() == "4":
                sesiones[self.numero].cliente_receta_estado = "chat_notificacion"
                self.sw.enviar("💬 Escribí tu consulta o *cancelar* para volver:")
            else:
                self._responder_alternativa(comando, receta_id, msg_id, sesiones)

        elif tipo == "sin_stock":
            if comando.strip() == "3":
                sesiones[self.numero].cliente_receta_estado = "chat_notificacion"
                self.sw.enviar("💬 Escribí tu consulta o *cancelar* para volver:")
            else:
                self._responder_sin_stock(comando, receta_id, msg_id, sesiones)

        else:
            # Mensaje genérico
            if comando.strip() == "1":
                self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
                self._mostrar_siguiente_notificacion(sesiones)
            elif comando.strip() == "2":
                sesiones[self.numero].cliente_receta_estado = "chat_notificacion"
                self.sw.enviar("💬 Escribí tu respuesta o *cancelar* para volver:")
            else:
                self.sw.enviar("❌ Opción no válida. Respondé 1 o 2.")

    def _procesar_chat_notificacion(self, comando, sesiones):
        """Mensaje libre enviado durante una notificación, antes de tomar acción."""
        if comando.strip() == "cancelar":
            # Vuelve a mostrar la misma notificación (sigue sin leerse)
            self._mostrar_siguiente_notificacion(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        msg_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        med_id = getattr(sesiones[self.numero], "cliente_receta_nota_medicamento_id", None)
        tipo = getattr(sesiones[self.numero], "cliente_receta_nota_tipo", "")

        self.receta_manager.agregar_mensaje_chat(
            receta_id, beneficiario_id, comando.strip(),
            tipo="mensaje", medicamento_id=med_id
        )

        # El cliente atendió esta notificación (consultó): se descuenta del contador.
        # Cuando farmacia responda, el nuevo mensaje volverá a aparecer como pendiente.
        self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)

        self.sw.enviar("✅ Mensaje enviado. La farmacia te responderá pronto.")
        self._mostrar_siguiente_notificacion(sesiones)

    def _responder_alternativa(self, comando, receta_id, msg_id, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        med_id = getattr(sesiones[self.numero], "cliente_receta_nota_medicamento_id", None)

        if comando.strip() == "1":
            self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
            self.receta_manager.agregar_mensaje_chat(receta_id, beneficiario_id, "Acepto el cambio.", tipo="accion", medicamento_id=med_id)
            self._cambiar_item_por_medicamento_id(receta_id, med_id, "alternativa_aceptada")
            self.sw.enviar("✅ Alternativa aceptada.")
            self._evaluar_estado_post_respuesta(receta_id, sesiones)

        elif comando.strip() == "2":
            self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
            self.receta_manager.agregar_mensaje_chat(receta_id, beneficiario_id, "Rechazo el medicamento.", tipo="accion", medicamento_id=med_id)
            self._cambiar_item_por_medicamento_id(receta_id, med_id, "rechazado_usuario")
            self.sw.enviar("❌ Medicamento rechazado.")
            self._evaluar_estado_post_respuesta(receta_id, sesiones)

        elif comando.strip() == "3":
            self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
            self.receta_manager.agregar_mensaje_chat(receta_id, beneficiario_id, "Voy a esperar.", tipo="accion", medicamento_id=med_id)
            self.sw.enviar("⏳ Registrado. La farmacia será notificada.")
            print(f"[PLACEHOLDER] Agendar recordatorio para receta {receta_id}")
            self._mostrar_siguiente_notificacion(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida. Respondé 1, 2, 3 o 4.")

    def _responder_sin_stock(self, comando, receta_id, msg_id, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        med_id = getattr(sesiones[self.numero], "cliente_receta_nota_medicamento_id", None)

        if comando.strip() == "1":
            self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
            self.receta_manager.agregar_mensaje_chat(receta_id, beneficiario_id, "Rechazo el medicamento.", tipo="accion", medicamento_id=med_id)
            self._cambiar_item_por_medicamento_id(receta_id, med_id, "rechazado_usuario")
            self.sw.enviar("❌ Medicamento rechazado.")
            self._evaluar_estado_post_respuesta(receta_id, sesiones)

        elif comando.strip() == "2":
            self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
            self.receta_manager.agregar_mensaje_chat(receta_id, beneficiario_id, "Voy a esperar.", tipo="accion", medicamento_id=med_id)
            self.sw.enviar("⏳ Registrado. La farmacia será notificada.")
            print(f"[PLACEHOLDER] Agendar recordatorio para receta {receta_id}")
            self._mostrar_siguiente_notificacion(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida. Respondé 1, 2 o 3.")

    # ── TOKEN ─────────────────────────────────────────────────────────────────

    def _procesar_escribir_token(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_menu(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        msg_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)

        self.receta_manager.marcar_mensaje_leido(receta_id, msg_id, beneficiario_id)
        self.receta_manager.cambiar_estado(receta_id, "token_enviado", "Token enviado por paciente")
        self.receta_manager.agregar_mensaje_chat(
            receta_id, beneficiario_id,
            f"Token de autorización: {comando.strip()}",
            tipo="token_respuesta"
        )

        self.sw.enviar("✅ Token enviado a la farmacia. Te avisaremos cuando sea procesado.")
        self._mostrar_siguiente_notificacion(sesiones)

    # ── VER MIS RECETAS ───────────────────────────────────────────────────────

    def _mostrar_mis_recetas(self, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        recetas = self.receta_manager.buscar_recetas_activas(beneficiario_id)

        if not recetas:
            self.sw.enviar("📋 No tenés recetas activas en este momento.")
            self._mostrar_menu(sesiones)
            return

        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})

        lineas = ["📋 *Mis recetas activas:*\n"]
        for i, rec in enumerate(recetas, 1):
            estado_id = rec.get("estado", "pendiente")
            estado_cfg = estados_config.get(estado_id, {})
            estado_label = estado_cfg.get("label", estado_id)
            estado_icono = estado_cfg.get("icono", "")
            vencimiento = rec.get("fecha_vencimiento", "—")
            cant_items = len([it for it in rec.get("items", []) if it["estado_item"] != "omitido_usuario"])

            lineas.append(f"{i}. {estado_icono} *{estado_label}* — {cant_items} medicamento(s) — Vence: {vencimiento}")

            for item in rec.get("items", []):
                if item["estado_item"] == "omitido_usuario":
                    continue
                label = self.med_manager.get_label(item["medicamento_id"])
                item_cfg = estados_item_config.get(item["estado_item"], {})
                item_icono = item_cfg.get("icono", "❓")
                item_label = item_cfg.get("label", item["estado_item"])
                lineas.append(f"   • {item_icono} {label} ({item_label})")

            lineas.append("")

        lineas.append("Escribí *cancelar* para volver:")
        sesiones[self.numero].cliente_receta_estado = "ver_recetas"
        self.sw.enviar("\n".join(lineas))

    def _procesar_ver_recetas(self, comando, sesiones):
        self._mostrar_menu(sesiones)

    # ── CHAT POR RECETA ───────────────────────────────────────────────────────

    def _mostrar_lista_chat(self, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        recetas = self.receta_manager.buscar_recetas_activas(beneficiario_id)

        if not recetas:
            self.sw.enviar("📋 No tenés recetas activas.")
            self._mostrar_menu(sesiones)
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
            self._mostrar_menu(sesiones)
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
            self._mostrar_menu(sesiones)
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
            consumed = set()
            for idx, msg in enumerate(chat):
                if msg["id"] in consumed:
                    continue
                tipo = msg.get("tipo", "mensaje")
                autor = msg["autor"]
                med_id = msg.get("medicamento_id")

                if autor == "farmacia" and med_id and tipo in ("sin_stock", "alternativa", "solicitud_token"):
                    lineas.append(f"🏥 {msg['mensaje']}")
                    # Muestra todos los mensajes del cliente para este medicamento
                    # hasta el próximo mensaje de farmacia con el mismo med_id
                    for reply in chat[idx + 1:]:
                        if reply["autor"] == "farmacia" and reply.get("medicamento_id") == med_id:
                            break
                        if (reply["autor"] != "farmacia"
                                and reply.get("tipo") in ("accion", "mensaje")
                                and reply.get("medicamento_id") == med_id
                                and reply["id"] not in consumed):
                            lineas.append(f"└ 👤 {reply['mensaje']}")
                            consumed.add(reply["id"])
                else:
                    prefix = "🏥" if autor == "farmacia" else "👤"
                    lineas.append(f"{prefix} {msg['mensaje']}")

        lineas.append("")
        lineas.append("Escribí tu consulta o *cancelar* para volver:")

        # Solo marcar como leídos los mensajes informativos — los accionables
        # (sin_stock, alternativa, solicitud_token) siguen pendientes hasta que
        # el cliente decida explícitamente desde el flujo de notificaciones.
        TIPOS_ACCIONABLES = {"sin_stock", "alternativa", "solicitud_token"}
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
            if item["estado_item"] != "omitido_usuario" and item["medicamento_id"] == medicamento_id:
                self.receta_manager.cambiar_estado_item(receta_id, i, nuevo_estado)
                return

    def _evaluar_estado_post_respuesta(self, receta_id, sesiones):
        """Avanza la receta a en_gestion si todos los items están resueltos, luego muestra siguiente."""
        resultado = self.receta_manager.get_receta(receta_id)
        if resultado:
            _, receta = resultado
            beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
            items_activos = [it for it in receta["items"] if it["estado_item"] != "omitido_usuario"]
            estados_resueltos = ("disponible", "alternativa_aceptada", "rechazado_usuario")
            todos_resueltos = all(it["estado_item"] in estados_resueltos for it in items_activos)

            if todos_resueltos and receta["estado"] in ("a_la_espera", "confirmando"):
                self.receta_manager.cambiar_estado(receta_id, "en_gestion", "Cliente confirmó — vuelve a farmacia")
                self.receta_manager.agregar_mensaje_chat(
                    receta_id, beneficiario_id,
                    "Respondí a todas las novedades. La receta está lista para continuar.",
                    tipo="accion"
                )
                self.sw.enviar("📤 Tus respuestas fueron enviadas a la farmacia.")

        self._mostrar_siguiente_notificacion(sesiones)

    def contar_notificaciones(self, beneficiario_id):
        """Retorna la cantidad de mensajes no leídos para un beneficiario."""
        return self.receta_manager.contar_chat_no_leidos_usuario(beneficiario_id)

    def _salir(self, sesiones):
        sesiones[self.numero].cliente_receta_estado = None
        sesiones[self.numero].cliente_receta_beneficiario_id = None
        sesiones[self.numero].cliente_receta_nota_id = None
        sesiones[self.numero].cliente_receta_nota_receta_id = None
        sesiones[self.numero].cliente_receta_nota_tipo = None
        sesiones[self.numero].cliente_receta_nota_medicamento_id = None
        sesiones[self.numero].cliente_receta_lista = None
        sesiones[self.numero].cliente_receta_chat_receta_id = None
