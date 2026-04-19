# src/farmacia/staff/gestion_recetas_staff.py
import json
import os
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.sesiones.session_manager import SessionManager
from src.cliente.persona_manager import PersonaManager
from src.farmacia.receta_manager import RecetaManager
from src.farmacia.medicamento_manager import MedicamentoManager
from src.farmacia.obra_social_manager import ObraSocialManager


class GestionRecetasStaff:
    """
    Flujo de gestión de recetas pendientes desde el panel de staff.
    Permite a la farmacia:
        - Ver recetas pendientes ordenadas por vencimiento
        - Ver detalle de una receta
        - Cambiar estado de items (disponible, sin_stock, alternativa)
        - Enviar notas al paciente
        - Cambiar estado global de la receta
    Mensajes leídos de farmacia_config.json.
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
        estado = getattr(sesiones[self.numero], "staff_receta_estado", None)
        return estado is not None

    def iniciar(self, sesiones):
        """Punto de entrada — muestra recetas pendientes."""
        sesiones[self.numero].staff_receta_estado = "lista"
        sesiones[self.numero].staff_receta_id = None
        sesiones[self.numero].staff_receta_reintentos = 0
        self._mostrar_lista(sesiones)

    def procesar(self, comando, sesiones):
        """Dispatcher según estado."""
        estado = getattr(sesiones[self.numero], "staff_receta_estado", None)

        if estado == "lista":
            self._procesar_lista(comando, sesiones)
        elif estado == "detalle":
            self._procesar_detalle(comando, sesiones)
        elif estado == "cambiar_estado_item":
            self._procesar_cambiar_estado_item(comando, sesiones)
        elif estado == "ofrecer_alternativa":
            self._procesar_ofrecer_alternativa(comando, sesiones)
        elif estado == "escribir_nota":
            self._procesar_escribir_nota(comando, sesiones)
        elif estado == "cambiar_estado_receta":
            self._procesar_cambiar_estado_receta(comando, sesiones)

    # ── LISTA DE RECETAS PENDIENTES ───────────────────────────────────────────

    def _mostrar_lista(self, sesiones):
        """Muestra recetas pendientes ordenadas por vencimiento."""
        pendientes = self.receta_manager.buscar_pendientes()

        if not pendientes:
            self.sw.enviar("📋 No hay recetas pendientes de procesar.")
            self._salir(sesiones)
            return

        sesiones[self.numero].staff_receta_lista = pendientes

        lineas = ["📋 *Recetas pendientes:*\n"]
        for i, rec in enumerate(pendientes, 1):
            persona_id = rec.get("persona_id", "")
            nombre = self.persona_manager.get_nombre_completo(persona_id) or "Desconocido"
            cant_items = len([it for it in rec.get("items", []) if it["estado_item"] != "omitido_usuario"])
            vencimiento = rec.get("fecha_vencimiento", "—")
            estado = rec.get("estado", "pendiente")

            linea = f"{i}. {nombre} — {cant_items} medicamento(s) — Vence: {vencimiento}"
            if estado == "en_gestion":
                linea += " 🔄"

            credencial = rec.get("credencial_validada", True)
            if not credencial:
                linea += "\n   ⚠️ Credencial no validada"

            lineas.append(linea)

        lineas.append("\nIngresá el número para gestionar")
        lineas.append("o *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_lista(self, comando, sesiones):
        """Procesa selección de receta de la lista."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        pendientes = getattr(sesiones[self.numero], "staff_receta_lista", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(pendientes):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Número no válido.")
            return

        receta = pendientes[idx]
        sesiones[self.numero].staff_receta_id = receta["receta_id"]

        # Cambiar a en_gestion si estaba pendiente
        if receta["estado"] == "pendiente":
            self.receta_manager.cambiar_estado(receta["receta_id"], "en_gestion", "Farmacia procesando")

        self._mostrar_detalle(sesiones)

    # ── DETALLE DE RECETA ─────────────────────────────────────────────────────

    def _mostrar_detalle(self, sesiones):
        """Muestra el detalle completo de una receta."""
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self.sw.enviar("⚠️ Receta no encontrada.")
            self._salir(sesiones)
            return

        _, receta = resultado
        persona_id = receta.get("persona_id", "")
        nombre = self.persona_manager.get_nombre_completo(persona_id) or "Desconocido"
        fecha_validez = receta.get("fecha_validez_desde", "—")
        fecha_venc = receta.get("fecha_vencimiento", "—")
        estado = receta.get("estado", "pendiente")
        diagnostico = receta.get("diagnostico", "—")
        credencial = receta.get("credencial_validada", True)
        os_id = receta.get("obra_social_id", "")

        # Info obra social
        os_info = ""
        if os_id:
            os_data = self.os_manager.get_asociacion(os_id)
            if os_data:
                os_info = f"🏥 {os_data[1]['entidad']} — Nro: {os_data[1]['numero']}"

        credencial_str = "✅ Credencial validada" if credencial else "⚠️ Credencial NO validada"

        # Medico
        medico = receta.get("medico", {})
        medico_str = medico.get("nombre", "—")
        if medico.get("especialidad"):
            medico_str += f" ({medico['especialidad']})"

        lineas = [
            f"📋 *Receta de {nombre}*",
            f"📅 Válida: {fecha_validez} — Vence: {fecha_venc}",
            f"📊 Estado: *{estado}*",
        ]
        if os_info:
            lineas.append(os_info)
        lineas.append(credencial_str)
        lineas.append(f"🩺 Diagnóstico: {diagnostico}")
        lineas.append(f"👨‍⚕️ Médico: {medico_str}")
        lineas.append("")

        # Items
        ICONOS_ESTADO = {
            "pendiente": "⏳",
            "disponible": "✅",
            "sin_stock": "❌",
            "alternativa_ofrecida": "🔄",
            "alternativa_aceptada": "🔄✅",
            "rechazado_usuario": "🚫",
            "omitido_usuario": "⏭️"
        }

        lineas.append("*Medicamentos:*")
        items = receta.get("items", [])
        for i, item in enumerate(items, 1):
            if item["estado_item"] == "omitido_usuario":
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            cant_rec = item.get("cantidad_receta", 0)
            cant_sol = item.get("cantidad_solicitada", cant_rec)
            icono = ICONOS_ESTADO.get(item["estado_item"], "❓")

            cant_str = f"{cant_sol}" if cant_sol == cant_rec else f"{cant_sol} de {cant_rec}"
            lineas.append(f"{i}. {icono} {label} — Cant: {cant_str} ({item['estado_item']})")

        # Notas pendientes dirigidas a farmacia
        notas_farmacia = self.receta_manager.get_notas_pendientes(receta_id, "farmacia")
        if notas_farmacia:
            lineas.append(f"\n📬 *{len(notas_farmacia)} nota(s) pendiente(s) del paciente*")

        lineas.append("")
        lineas.append("1. 💊 Cambiar estado de un medicamento")
        lineas.append("2. 💬 Enviar nota al paciente")
        lineas.append("3. 📊 Cambiar estado de la receta")
        lineas.append("Escribí *cancelar* para volver:")

        sesiones[self.numero].staff_receta_estado = "detalle"
        self.sw.enviar("\n".join(lineas))

    def _procesar_detalle(self, comando, sesiones):
        """Procesa opciones del detalle de receta."""
        if comando.strip() == "cancelar":
            self.iniciar(sesiones)
            return

        if comando.strip() == "1":
            self._iniciar_cambiar_estado_item(sesiones)
        elif comando.strip() == "2":
            self._iniciar_escribir_nota(sesiones)
        elif comando.strip() == "3":
            self._iniciar_cambiar_estado_receta(sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    # ── CAMBIAR ESTADO DE ITEM ────────────────────────────────────────────────

    def _iniciar_cambiar_estado_item(self, sesiones):
        """Muestra items para seleccionar cuál cambiar."""
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        items = receta.get("items", [])

        lineas = ["¿Qué medicamento querés actualizar?\n"]
        items_visibles = []
        for i, item in enumerate(items):
            if item["estado_item"] == "omitido_usuario":
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            items_visibles.append(i)
            lineas.append(f"{len(items_visibles)}. {label} ({item['estado_item']})")

        lineas.append("\nEscribí *cancelar* para volver:")
        sesiones[self.numero].staff_receta_estado = "cambiar_estado_item"
        sesiones[self.numero].staff_receta_items_visibles = items_visibles
        self.sw.enviar("\n".join(lineas))

    def _procesar_cambiar_estado_item(self, comando, sesiones):
        """Procesa selección de item y nuevo estado."""
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        items_visibles = getattr(sesiones[self.numero], "staff_receta_items_visibles", [])
        esperando_estado = getattr(sesiones[self.numero], "staff_receta_esperando_estado", False)

        if not esperando_estado:
            # Seleccionando item
            try:
                idx = int(comando.strip()) - 1
                if idx < 0 or idx >= len(items_visibles):
                    raise ValueError
            except ValueError:
                self.sw.enviar("❌ Número no válido.")
                return

            item_real_idx = items_visibles[idx]
            sesiones[self.numero].staff_receta_item_idx = item_real_idx
            sesiones[self.numero].staff_receta_esperando_estado = True

            self.sw.enviar(
                "Seleccioná el nuevo estado:\n\n"
                "1. ✅ Disponible (hay stock)\n"
                "2. ❌ Sin stock\n"
                "3. 🔄 Ofrecer alternativa\n\n"
                "Escribí *cancelar* para volver:"
            )
        else:
            # Seleccionando estado
            sesiones[self.numero].staff_receta_esperando_estado = False
            receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
            item_idx = getattr(sesiones[self.numero], "staff_receta_item_idx", 0)

            if comando.strip() == "1":
                self.receta_manager.cambiar_estado_item(receta_id, item_idx, "disponible")
                self.sw.enviar("✅ Medicamento marcado como disponible.")
                self._verificar_todos_resueltos(receta_id, sesiones)
                self._mostrar_detalle(sesiones)

            elif comando.strip() == "2":
                self.receta_manager.cambiar_estado_item(receta_id, item_idx, "sin_stock")
                self.sw.enviar("❌ Medicamento marcado como sin stock.")
                self._mostrar_detalle(sesiones)

            elif comando.strip() == "3":
                sesiones[self.numero].staff_receta_estado = "ofrecer_alternativa"
                self.sw.enviar(
                    "Escribí el nombre del medicamento alternativo\n"
                    "o *cancelar* para volver:"
                )

            else:
                self.sw.enviar("❌ Opción no válida.")
                sesiones[self.numero].staff_receta_esperando_estado = True

    # ── OFRECER ALTERNATIVA ───────────────────────────────────────────────────

    def _procesar_ofrecer_alternativa(self, comando, sesiones):
        """Procesa el nombre de la alternativa y envía nota al paciente."""
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        item_idx = getattr(sesiones[self.numero], "staff_receta_item_idx", 0)

        # Marcar item como alternativa_ofrecida
        self.receta_manager.cambiar_estado_item(receta_id, item_idx, "alternativa_ofrecida")

        # Obtener label del medicamento original
        resultado = self.receta_manager.get_receta(receta_id)
        if resultado:
            _, receta = resultado
            item = receta["items"][item_idx]
            label_original = self.med_manager.get_label(item["medicamento_id"])
        else:
            label_original = "el medicamento"

        # Crear nota para el paciente
        mensaje_nota = (
            f"No tenemos *{label_original}* disponible. "
            f"Ofrecemos como alternativa: *{comando.strip()}*. "
            f"¿Lo aceptás?"
        )
        self.receta_manager.agregar_nota(receta_id, "farmacia", "usuario", mensaje_nota)

        self.sw.enviar(f"✅ Alternativa ofrecida. Se envió nota al paciente.")
        self._mostrar_detalle(sesiones)

    # ── ESCRIBIR NOTA ─────────────────────────────────────────────────────────

    def _iniciar_escribir_nota(self, sesiones):
        """Pide el texto de la nota."""
        sesiones[self.numero].staff_receta_estado = "escribir_nota"
        self.sw.enviar(
            "💬 Escribí el mensaje que querés enviarle al paciente\n"
            "o *cancelar* para volver:"
        )

    def _procesar_escribir_nota(self, comando, sesiones):
        """Registra la nota y notifica."""
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.receta_manager.agregar_nota(receta_id, "farmacia", "usuario", comando.strip())

        # TODO: enviar notificación push al paciente por WhatsApp
        # Por ahora solo se registra la nota

        self.sw.enviar("✅ Nota enviada al paciente.")
        self._mostrar_detalle(sesiones)

    # ── CAMBIAR ESTADO DE RECETA ──────────────────────────────────────────────

    def _iniciar_cambiar_estado_receta(self, sesiones):
        """Muestra opciones de estado para la receta."""
        sesiones[self.numero].staff_receta_estado = "cambiar_estado_receta"
        self.sw.enviar(
            "📊 Seleccioná el nuevo estado de la receta:\n\n"
            "1. ✅ Lista para retiro\n"
            "2. 🔐 Requiere autorización\n"
            "3. ❌ Rechazada\n"
            "4. 📦 Cerrada (retirada y firmada)\n\n"
            "Escribí *cancelar* para volver:"
        )

    def _procesar_cambiar_estado_receta(self, comando, sesiones):
        """Procesa el cambio de estado de la receta."""
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)

        estados_map = {
            "1": ("lista_retiro", "Todos los items disponibles — lista para retiro"),
            "2": ("autorizada", "Requiere autorización de obra social"),
            "3": ("rechazada", "Rechazada por la farmacia"),
            "4": ("cerrada", "Retirada y firmada por paciente")
        }

        if comando.strip() not in estados_map:
            self.sw.enviar("❌ Opción no válida.")
            return

        nuevo_estado, motivo = estados_map[comando.strip()]
        self.receta_manager.cambiar_estado(receta_id, nuevo_estado, motivo)

        # TODO: enviar notificación al paciente según el estado

        self.sw.enviar(f"✅ Receta cambiada a estado: *{nuevo_estado}*")

        if nuevo_estado in ("cerrada", "rechazada"):
            self.iniciar(sesiones)  # Volver a la lista
        else:
            self._mostrar_detalle(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _verificar_todos_resueltos(self, receta_id, sesiones):
        """Si todos los items activos están resueltos, sugiere cambiar estado."""
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return

        _, receta = resultado
        items_activos = [it for it in receta["items"] if it["estado_item"] != "omitido_usuario"]
        todos_resueltos = all(
            it["estado_item"] in ("disponible", "alternativa_aceptada", "rechazado_usuario")
            for it in items_activos
        )

        if todos_resueltos:
            self.sw.enviar(
                "🔔 Todos los medicamentos están resueltos.\n"
                "Podés cambiar el estado de la receta a *Lista para retiro*."
            )

    def _salir(self, sesiones):
        """Limpia estado del flujo."""
        sesiones[self.numero].staff_receta_estado = None
        sesiones[self.numero].staff_receta_id = None
        sesiones[self.numero].staff_receta_lista = None
        sesiones[self.numero].staff_receta_reintentos = 0
        sesiones[self.numero].staff_receta_items_visibles = None
        sesiones[self.numero].staff_receta_esperando_estado = False
        sesiones[self.numero].staff_receta_item_idx = None