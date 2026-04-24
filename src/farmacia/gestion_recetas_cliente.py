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


class GestionRecetasCliente:
    """
    Flujo de gestión de recetas desde el lado del cliente.
    Responsabilidades:
        - Notificaciones: ver notas pendientes de la farmacia, responder
        - Ver mis recetas: resumen del estado de cada receta activa
        - Mis recordatorios: placeholder
    Las notificaciones se muestran una por una en orden cronológico.
    Tipos de nota:
        - Informativa (cambio estado, aviso genérico): se marca como leída
        - Alternativa ofrecida: aceptar/rechazar/esperar
        - Sin stock: rechazar/esperar
        - Token: ingresar token
    """

    CONFIG_PATH = os.path.join("data", "farmacia", "farmacia_config.json")

    def __init__(self, numero):
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
        """Punto de entrada — muestra submenú de recetas del cliente."""
        sesiones[self.numero].cliente_receta_estado = "menu"
        sesiones[self.numero].cliente_receta_beneficiario_id = beneficiario_id
        self._mostrar_menu(sesiones)

    def procesar(self, comando, sesiones):
        """Dispatcher según estado."""
        estado = getattr(sesiones[self.numero], "cliente_receta_estado", None)

        if estado == "menu":
            self._procesar_menu(comando, sesiones)
        elif estado == "notificacion":
            self._procesar_notificacion(comando, sesiones)
        elif estado == "escribir_token":
            self._procesar_escribir_token(comando, sesiones)
        elif estado == "ver_recetas":
            self._procesar_ver_recetas(comando, sesiones)

    # ── SUBMENÚ ───────────────────────────────────────────────────────────────

    def _mostrar_menu(self, sesiones):
        """Muestra submenú de gestión de recetas del cliente."""
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        cant_notif = self.receta_manager.contar_notificaciones_usuario(beneficiario_id)

        notif_label = f" ({cant_notif} pendientes)" if cant_notif > 0 else ""

        lineas = [
            "📬 *Gestión de recetas*\n",
            f"1. 🔔 Notificaciones{notif_label}",
            "2. 📋 Ver mis recetas",
            "3. ⏰ Mis recordatorios",
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
        else:
            self.sw.enviar("❌ Opción no válida.")

    # ── NOTIFICACIONES (una por una) ──────────────────────────────────────────

    def _mostrar_siguiente_notificacion(self, sesiones):
        """Muestra la siguiente nota pendiente o avisa que no hay más."""
        beneficiario_id = getattr(sesiones[self.numero], "cliente_receta_beneficiario_id", None)
        resultado = self.receta_manager.get_primera_notificacion_usuario(beneficiario_id)

        if not resultado:
            self.sw.enviar("✅ No tenés notificaciones pendientes.")
            self._mostrar_menu(sesiones)
            return

        receta_id, nota = resultado
        sesiones[self.numero].cliente_receta_nota_id = nota["id"]
        sesiones[self.numero].cliente_receta_nota_receta_id = receta_id

        # Obtener contexto de la receta
        rec_resultado = self.receta_manager.get_receta(receta_id)
        if not rec_resultado:
            self.receta_manager.marcar_nota_leida(receta_id, nota["id"])
            self._mostrar_siguiente_notificacion(sesiones)
            return

        _, receta = rec_resultado
        estado_id = receta.get("estado", "pendiente")
        estados_config = self.farm_config.get("recetas", {}).get("estados_receta", {})
        estado_config = estados_config.get(estado_id, {})
        estado_label = estado_config.get("label", estado_id)
        estado_icono = estado_config.get("icono", "")

        # Determinar tipo de notificación
        mensaje = nota.get("mensaje", "")
        tipo = self._detectar_tipo_nota(mensaje, receta, estado_id)

        cant_restantes = self.receta_manager.contar_notificaciones_usuario(beneficiario_id) - 1

        lineas = [
            f"🔔 *Notificación de la farmacia*",
            f"📊 Receta en estado: {estado_icono} {estado_label}",
            f"",
            f"💬 {mensaje}",
            ""
        ]

        if tipo == "alternativa":
            lineas.append("1. ✅ Aceptar cambio")
            lineas.append("2. ❌ Rechazar medicamento")
            lineas.append("3. ⏳ Esperar / agendar")
            sesiones[self.numero].cliente_receta_estado = "notificacion"
            sesiones[self.numero].cliente_receta_nota_tipo = "alternativa"

        elif tipo == "sin_stock":
            lineas.append("1. ❌ Rechazar medicamento")
            lineas.append("2. ⏳ Esperar / agendar")
            sesiones[self.numero].cliente_receta_estado = "notificacion"
            sesiones[self.numero].cliente_receta_nota_tipo = "sin_stock"

        elif tipo == "token":
            lineas.append("Escribí el *token de autorización*:")
            sesiones[self.numero].cliente_receta_estado = "escribir_token"
            sesiones[self.numero].cliente_receta_nota_tipo = "token"

        else:
            # Informativa — marcar como leída y avanzar
            self.receta_manager.marcar_nota_leida(receta_id, nota["id"])
            if cant_restantes > 0:
                lineas.append(f"📬 Quedan {cant_restantes} notificación(es) más.")
                self.sw.enviar("\n".join(lineas))
                self._mostrar_siguiente_notificacion(sesiones)
            else:
                lineas.append("✅ No tenés más notificaciones pendientes.")
                self.sw.enviar("\n".join(lineas))
                self._mostrar_menu(sesiones)
            return

        if cant_restantes > 0:
            lineas.append(f"\n📬 Quedan {cant_restantes} notificación(es) más.")
        lineas.append("Escribí *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_notificacion(self, comando, sesiones):
        """Procesa respuesta a una notificación accionable."""
        if comando.strip() == "cancelar":
            self._mostrar_menu(sesiones)
            return

        tipo = getattr(sesiones[self.numero], "cliente_receta_nota_tipo", "")
        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        nota_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)

        if tipo == "alternativa":
            self._responder_alternativa(comando, receta_id, nota_id, sesiones)
        elif tipo == "sin_stock":
            self._responder_sin_stock(comando, receta_id, nota_id, sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    def _responder_alternativa(self, comando, receta_id, nota_id, sesiones):
        """Respuesta a oferta de alternativa: aceptar/rechazar/esperar."""
        if comando.strip() == "1":
            # Aceptar cambio
            self.receta_manager.responder_nota(receta_id, nota_id, "aceptada")
            # Buscar item con alternativa_ofrecida y cambiar a alternativa_aceptada
            self._cambiar_item_por_nota(receta_id, nota_id, "alternativa_aceptada")
            self.sw.enviar("✅ Alternativa aceptada.")
            self._evaluar_estado_post_respuesta(receta_id, sesiones)

        elif comando.strip() == "2":
            # Rechazar medicamento
            self.receta_manager.responder_nota(receta_id, nota_id, "rechazada")
            self._cambiar_item_por_nota(receta_id, nota_id, "rechazado_usuario")
            self.sw.enviar("❌ Medicamento rechazado.")
            self._evaluar_estado_post_respuesta(receta_id, sesiones)

        elif comando.strip() == "3":
            # Esperar / agendar
            self.receta_manager.responder_nota(receta_id, nota_id, "esperar")
            self.sw.enviar("⏳ Registrado. La farmacia será notificada.")
            # TODO: agendar recordatorio
            print(f"[PLACEHOLDER] Agendar recordatorio para receta {receta_id}")
            self._mostrar_siguiente_notificacion(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida. Respondé 1, 2 o 3.")

    def _responder_sin_stock(self, comando, receta_id, nota_id, sesiones):
        """Respuesta a notificación de sin stock: rechazar/esperar."""
        if comando.strip() == "1":
            # Rechazar medicamento
            self.receta_manager.responder_nota(receta_id, nota_id, "rechazada")
            self._cambiar_item_por_nota(receta_id, nota_id, "rechazado_usuario")
            self.sw.enviar("❌ Medicamento rechazado.")
            self._evaluar_estado_post_respuesta(receta_id, sesiones)

        elif comando.strip() == "2":
            # Esperar / agendar
            self.receta_manager.responder_nota(receta_id, nota_id, "esperar")
            self.sw.enviar("⏳ Registrado. La farmacia será notificada.")
            print(f"[PLACEHOLDER] Agendar recordatorio para receta {receta_id}")
            self._mostrar_siguiente_notificacion(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida. Respondé 1 o 2.")

    # ── TOKEN ─────────────────────────────────────────────────────────────────

    def _procesar_escribir_token(self, comando, sesiones):
        """Procesa el token escrito por el usuario."""
        if comando.strip() == "cancelar":
            self._mostrar_menu(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "cliente_receta_nota_receta_id", None)
        nota_id = getattr(sesiones[self.numero], "cliente_receta_nota_id", None)

        # Registrar token como respuesta a la nota
        self.receta_manager.responder_nota(receta_id, nota_id, f"TOKEN: {comando.strip()}")

        # Cambiar estado de la receta a token_enviado
        self.receta_manager.cambiar_estado(receta_id, "token_enviado", f"Token enviado por paciente")

        # Notificar a la farmacia con una nota
        self.receta_manager.agregar_nota(receta_id, "usuario", "farmacia", f"Token de autorización: {comando.strip()}")

        self.sw.enviar("✅ Token enviado a la farmacia. Te avisaremos cuando sea procesado.")
        self._mostrar_siguiente_notificacion(sesiones)

    # ── VER MIS RECETAS ───────────────────────────────────────────────────────

    def _mostrar_mis_recetas(self, sesiones):
        """Muestra resumen de recetas activas del beneficiario."""
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

            # Detalle de items
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
        """Ver recetas es solo lectura — cualquier input vuelve al menú."""
        self._mostrar_menu(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _detectar_tipo_nota(self, mensaje, receta, estado_id):
        """
        Detecta el tipo de nota según contenido y contexto.
        - Si el mensaje menciona "alternativa" → alternativa
        - Si el mensaje menciona "stock" → sin_stock
        - Si el estado es requiere_autorizacion y menciona "token" → token
        - Caso contrario → informativa
        """
        mensaje_lower = mensaje.lower()

        if "alternativa" in mensaje_lower:
            return "alternativa"
        if "stock" in mensaje_lower or "no tenemos" in mensaje_lower:
            return "sin_stock"
        if estado_id in ("requiere_autorizacion",) and "token" in mensaje_lower:
            return "token"
        return "informativa"

    def _cambiar_item_por_nota(self, receta_id, nota_id, nuevo_estado):
        """
        Busca el item asociado a una nota (por contenido del medicamento) y cambia su estado.
        Heurística: la nota menciona el nombre del medicamento en el mensaje.
        """
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return

        _, receta = resultado
        # Buscar la nota para obtener el mensaje
        nota_msg = ""
        for nota in receta.get("notas", []):
            if nota["id"] == nota_id:
                nota_msg = nota.get("mensaje", "")
                break

        if not nota_msg:
            return

        # Buscar item cuyo nombre está mencionado en la nota
        for i, item in enumerate(receta.get("items", [])):
            if item["estado_item"] == "omitido_usuario":
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            if label and label.lower() in nota_msg.lower():
                self.receta_manager.cambiar_estado_item(receta_id, i, nuevo_estado)
                return

    def _evaluar_estado_post_respuesta(self, receta_id, sesiones):
        """
        Evalúa si después de la respuesta del cliente hay que cambiar el estado de la receta.
        - Si todos los items están en disponible/alternativa_aceptada/rechazado_usuario → receta vuelve a en_gestion
        - Si todos fueron rechazados → queda para que la farmacia cierre
        Después muestra la siguiente notificación.
        """
        resultado = self.receta_manager.get_receta(receta_id)
        if resultado:
            _, receta = resultado
            items_activos = [it for it in receta["items"] if it["estado_item"] != "omitido_usuario"]
            estados_resueltos = ("disponible", "alternativa_aceptada", "rechazado_usuario")
            todos_resueltos = all(it["estado_item"] in estados_resueltos for it in items_activos)

            if todos_resueltos and receta["estado"] in ("a_la_espera", "confirmando"):
                self.receta_manager.cambiar_estado(receta_id, "en_gestion", "Cliente confirmó — vuelve a farmacia")
                self.receta_manager.agregar_nota(receta_id, "usuario", "farmacia",
                    "El paciente respondió a todas las novedades. La receta está lista para continuar.")
                self.sw.enviar("📤 Tus respuestas fueron enviadas a la farmacia.")

        self._mostrar_siguiente_notificacion(sesiones)

    def contar_notificaciones(self, beneficiario_id):
        """Retorna la cantidad de notificaciones pendientes para un beneficiario."""
        return self.receta_manager.contar_notificaciones_usuario(beneficiario_id)

    def _salir(self, sesiones):
        """Limpia estado del flujo."""
        sesiones[self.numero].cliente_receta_estado = None
        sesiones[self.numero].cliente_receta_beneficiario_id = None
        sesiones[self.numero].cliente_receta_nota_id = None
        sesiones[self.numero].cliente_receta_nota_receta_id = None
        sesiones[self.numero].cliente_receta_nota_tipo = None