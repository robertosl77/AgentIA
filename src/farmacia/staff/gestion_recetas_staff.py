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
    Estados, transiciones y opciones leídos de farmacia_config.json.
    Opciones del detalle se arman dinámicamente según opciones_staff del estado actual.
    """

    CONFIG_PATH = os.path.join("data", "farmacia", "farmacia_config.json")

    # Mapeo de opciones_staff → (label para menú, método handler)
    OPCIONES_HANDLERS = {
        "avanzar":              None,  # Se arma dinámicamente con el label del camino_feliz
        "confirmar_todos":      ("✅ Confirmar todos los medicamentos como disponibles", "_confirmar_todos_disponibles"),
        "cambiar_estado_item":  ("💊 Cambiar estado de un medicamento", "_iniciar_cambiar_estado_item"),
        "enviar_nota":          ("💬 Enviar nota al paciente", "_iniciar_escribir_nota"),
        "cambiar_estado_receta":("📊 Cambiar estado de la receta", "_iniciar_cambiar_estado_receta"),
        "agendar_recordatorio": ("🔔 Agendar recordatorio", "_placeholder_agendar_recordatorio"),
        "cerrar_y_notificar":   ("📤 Cerrar y notificar al cliente", "_placeholder_cerrar_y_notificar"),
        "validar_token":        ("🔑 Validar token recibido", "_placeholder_validar_token"),
    }

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
        elif estado == "confirmar_token":
            self._procesar_confirmar_token(comando, sesiones)

    # ── LISTA DE RECETAS PENDIENTES ───────────────────────────────────────────

    def _mostrar_lista(self, sesiones):
        """Muestra recetas pendientes ordenadas por vencimiento."""
        pendientes = self.receta_manager.buscar_pendientes()

        if not pendientes:
            self.sw.enviar("📋 No hay recetas pendientes de procesar.")
            self._salir(sesiones)
            return

        # Si hay 1 sola receta, ir directo al detalle
        if len(pendientes) == 1:
            sesiones[self.numero].staff_receta_lista = pendientes
            receta = pendientes[0]
            sesiones[self.numero].staff_receta_id = receta["receta_id"]
            if receta["estado"] == "pendiente":
                self.receta_manager.cambiar_estado(receta["receta_id"], "en_gestion", "Farmacia procesando")
            self._mostrar_detalle(sesiones)
            return

        sesiones[self.numero].staff_receta_lista = pendientes

        lineas = ["📋 *Recetas pendientes:*\n"]
        for i, rec in enumerate(pendientes, 1):
            persona_id = rec.get("persona_id", "")
            nombre = self.persona_manager.get_nombre_completo(persona_id) or "Desconocido"
            cant_items = len([it for it in rec.get("items", []) if it["estado_item"] != "omitido_usuario"])
            vencimiento = rec.get("fecha_vencimiento", "—")
            estado = rec.get("estado", "pendiente")
            estado_config = self._get_estado_receta_config(estado)

            linea = f"{i}. {nombre} — {cant_items} medicamento(s) — Vence: {vencimiento}"
            if estado != "pendiente":
                linea += f" {estado_config.get('icono', '')}"

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

        if receta["estado"] == "pendiente":
            self.receta_manager.cambiar_estado(receta["receta_id"], "en_gestion", "Farmacia procesando")

        self._mostrar_detalle(sesiones)

    # ── DETALLE DE RECETA ─────────────────────────────────────────────────────

    def _mostrar_detalle(self, sesiones):
        """Muestra el detalle completo de una receta con opciones dinámicas por estado."""
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self.sw.enviar("⚠️ Receta no encontrada.")
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

        # Items — viñeta
        lineas.append("*Medicamentos:*")
        items = receta.get("items", [])
        items_visibles_idx = []
        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})
        for i, item in enumerate(items):
            if item["estado_item"] == "omitido_usuario":
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            cant_rec = item.get("cantidad_receta", 0)
            cant_sol = item.get("cantidad_solicitada", cant_rec)
            item_config = estados_item_config.get(item["estado_item"], {})
            icono = item_config.get("icono", "❓")
            estado_label_item = item_config.get("label", item["estado_item"])

            cant_str = f"{cant_sol}" if cant_sol == cant_rec else f"{cant_sol} de {cant_rec}"
            lineas.append(f"• {icono} {label} — Cant: {cant_str} ({estado_label_item})")
            items_visibles_idx.append(i)

        # Notas pendientes dirigidas a farmacia
        notas_farmacia = self.receta_manager.get_notas_pendientes(receta_id, "farmacia")
        if notas_farmacia:
            lineas.append(f"\n📬 *{len(notas_farmacia)} nota(s) pendiente(s) del paciente*")

        # Opciones dinámicas según estado actual
        opciones_staff = estado_config.get("opciones_staff", [])
        camino_feliz = estado_config.get("camino_feliz")
        opciones_activas = []  # lista de keys de OPCIONES_HANDLERS
        lineas.append("")

        num = 1
        for opcion_key in opciones_staff:
            if opcion_key == "avanzar":
                # Opción dinámica: avanzar al camino feliz
                if camino_feliz:
                    cf_config = self._get_estado_receta_config(camino_feliz)
                    cf_label = cf_config.get("label", camino_feliz)
                    cf_icono = cf_config.get("icono", "➡️")
                    lineas.append(f"{num}. {cf_icono} Avanzar a {cf_label}")
                    opciones_activas.append("avanzar")
                    num += 1
                continue

            handler_info = self.OPCIONES_HANDLERS.get(opcion_key)
            if handler_info:
                label_opcion, _ = handler_info
                lineas.append(f"{num}. {label_opcion}")
                opciones_activas.append(opcion_key)
                num += 1

        lineas.append("Escribí *cancelar* para volver:")

        sesiones[self.numero].staff_receta_estado = "detalle"
        sesiones[self.numero].staff_receta_items_visibles = items_visibles_idx
        sesiones[self.numero].staff_receta_opciones_activas = opciones_activas
        self.sw.enviar("\n".join(lineas))

    def _procesar_detalle(self, comando, sesiones):
        """Procesa opciones dinámicas del detalle de receta."""
        if comando.strip() == "cancelar":
            # Fix cancelar: con 1 sola receta, cancelar vuelve al menú staff
            pendientes = self.receta_manager.buscar_pendientes()
            if len(pendientes) <= 1:
                self._salir(sesiones)
            else:
                self.iniciar(sesiones)
            return

        opciones_activas = getattr(sesiones[self.numero], "staff_receta_opciones_activas", [])

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(opciones_activas):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        opcion_key = opciones_activas[idx]

        # Avanzar al camino feliz
        if opcion_key == "avanzar":
            self._avanzar_camino_feliz(sesiones)
            return

        handler_info = self.OPCIONES_HANDLERS.get(opcion_key)
        if handler_info:
            _, method_name = handler_info
            method = getattr(self, method_name, None)
            if method:
                method(sesiones)
            else:
                self.sw.enviar(f"🚧 Función '{method_name}' — próximamente...")
                self._mostrar_detalle(sesiones)

    # ── CONFIRMAR TODOS DISPONIBLES ───────────────────────────────────────────

    def _confirmar_todos_disponibles(self, sesiones):
        """
        Marca TODOS los items activos como disponibles.
        Desestima notas de alternativa pendientes (placeholder).
        Cancela recordatorios (placeholder).
        Pregunta si requiere token de autorización.
        Si ya están todos disponibles, salta directo a la pregunta de token.
        """
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            self._mostrar_detalle(sesiones)
            return

        _, receta = resultado
        items = receta.get("items", [])
        count = 0
        for i, item in enumerate(items):
            if item["estado_item"] in ("pendiente", "sin_stock", "alternativa_ofrecida"):
                self.receta_manager.cambiar_estado_item(receta_id, i, "disponible")
                count += 1

        if count > 0:
            self.sw.enviar(f"✅ {count} medicamento(s) confirmado(s) como disponibles.")

        # TODO: desestimar notas de alternativa pendientes
        print(f"[PLACEHOLDER] Desestimar notas de alternativa para receta {receta_id}")

        # TODO: cancelar recordatorios pendientes
        print(f"[PLACEHOLDER] Cancelar recordatorios para receta {receta_id}")

        # Preguntar si requiere token
        sesiones[self.numero].staff_receta_estado = "confirmar_token"
        self.sw.enviar(
            "🔐 ¿Requiere token de autorización de obra social?\n\n"
            "1. Sí, solicitar token al paciente\n"
            "2. No, avanzar sin token\n\n"
            "Escribí *cancelar* para volver:"
        )

    def _procesar_confirmar_token(self, comando, sesiones):
        """Procesa la respuesta de si requiere token o no."""
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)

        if comando.strip() == "1":
            # Requiere token → estado requiere_autorizacion
            self.receta_manager.cambiar_estado(receta_id, "requiere_autorizacion", "Farmacia solicita token")
            self.sw.enviar("🔐 Receta cambiada a *Requiere autorización*.")
            # TODO: notificar al paciente que debe enviar token
            print(f"[PLACEHOLDER] Notificar al paciente que envíe token para receta {receta_id}")
            self._mostrar_detalle(sesiones)

        elif comando.strip() == "2":
            # No requiere token → estado procesando
            self.receta_manager.cambiar_estado(receta_id, "procesando", "No requiere token — avance directo")
            self.sw.enviar("⚙️ Receta cambiada a *Procesando*.")
            self._mostrar_detalle(sesiones)

        else:
            self.sw.enviar("❌ Opción no válida. Respondé *1* o *2*.")

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
        estados_item_config = self.farm_config.get("recetas", {}).get("estados_item", {})
        for i, item in enumerate(items):
            if item["estado_item"] == "omitido_usuario":
                continue
            label = self.med_manager.get_label(item["medicamento_id"])
            items_visibles.append(i)
            item_config = estados_item_config.get(item["estado_item"], {})
            icono = item_config.get("icono", "❓")
            estado_label = item_config.get("label", item["estado_item"])
            lineas.append(f"{len(items_visibles)}. {icono} {label} ({estado_label})")

        lineas.append("\nEscribí *cancelar* para volver:")
        sesiones[self.numero].staff_receta_estado = "cambiar_estado_item"
        sesiones[self.numero].staff_receta_items_visibles = items_visibles
        sesiones[self.numero].staff_receta_esperando_estado = False
        self.sw.enviar("\n".join(lineas))

    def _procesar_cambiar_estado_item(self, comando, sesiones):
        """Procesa selección de item y nuevo estado."""
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        items_visibles = getattr(sesiones[self.numero], "staff_receta_items_visibles", [])
        esperando_estado = getattr(sesiones[self.numero], "staff_receta_esperando_estado", False)

        if not esperando_estado:
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
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        item_idx = getattr(sesiones[self.numero], "staff_receta_item_idx", 0)

        self.receta_manager.cambiar_estado_item(receta_id, item_idx, "alternativa_ofrecida")

        resultado = self.receta_manager.get_receta(receta_id)
        if resultado:
            _, receta = resultado
            item = receta["items"][item_idx]
            label_original = self.med_manager.get_label(item["medicamento_id"])
        else:
            label_original = "el medicamento"

        mensaje_nota = (
            f"No tenemos *{label_original}* disponible. "
            f"Ofrecemos como alternativa: *{comando.strip()}*. "
            f"¿Lo aceptás?"
        )
        self.receta_manager.agregar_nota(receta_id, "farmacia", "usuario", mensaje_nota)

        self.sw.enviar("✅ Alternativa ofrecida. Se envió nota al paciente.")
        # TODO: notificar al paciente
        print(f"[PLACEHOLDER] Notificar al paciente sobre alternativa para receta {receta_id}")
        self._mostrar_detalle(sesiones)

    # ── ESCRIBIR NOTA ─────────────────────────────────────────────────────────

    def _iniciar_escribir_nota(self, sesiones):
        sesiones[self.numero].staff_receta_estado = "escribir_nota"
        self.sw.enviar(
            "💬 Escribí el mensaje que querés enviarle al paciente\n"
            "o *cancelar* para volver:"
        )

    def _procesar_escribir_nota(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.receta_manager.agregar_nota(receta_id, "farmacia", "usuario", comando.strip())

        self.sw.enviar("✅ Nota enviada al paciente.")
        # TODO: notificar al paciente
        print(f"[PLACEHOLDER] Notificar al paciente sobre nota para receta {receta_id}")
        self._mostrar_detalle(sesiones)

    # ── CAMBIAR ESTADO DE RECETA (dinámico desde outflow) ─────────────────────

    def _iniciar_cambiar_estado_receta(self, sesiones):
        """Arma menú dinámico basado en outflow, filtrando automáticos."""
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

        # Construir opciones: outflow no automáticos + inflow (volver atrás)
        estados_config = self.receta_manager._get_estados_receta()
        opciones = []

        # Outflow — solo los no automáticos
        for estado_id in outflow:
            config = estados_config.get(estado_id, {})
            if not config.get("automatico", False):
                opciones.append(estado_id)

        # Inflow — para poder volver atrás (siempre manual)
        for estado_id in inflow:
            if estado_id not in opciones:
                opciones.append(estado_id)

        if not opciones:
            self.sw.enviar("ℹ️ No hay cambios de estado disponibles desde este punto.")
            self._mostrar_detalle(sesiones)
            return

        lineas = ["📊 Seleccioná el nuevo estado de la receta:\n"]
        for i, estado_id in enumerate(opciones, 1):
            config = estados_config.get(estado_id, {})
            icono = config.get("icono", "")
            label = config.get("label", estado_id)
            # Marcar si es volver atrás
            if estado_id in inflow and estado_id not in outflow:
                label += " (volver atrás)"
            lineas.append(f"{i}. {icono} {label}")

        lineas.append("\nEscribí *cancelar* para volver:")

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

            self.receta_manager.cambiar_estado(receta_id, nuevo_estado, comando.strip())

            config = self._get_estado_receta_config(nuevo_estado)
            label = config.get("label", nuevo_estado)
            self.sw.enviar(f"✅ Receta cambiada a estado: *{label}*")

            # TODO: notificar al paciente si notifica_usuario es true
            if config.get("notifica_usuario", False):
                print(f"[PLACEHOLDER] Notificar al paciente: receta {receta_id} → {nuevo_estado}")

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
            self.sw.enviar("❌ Opción no válida.")
            return

        nuevo_estado = opciones[idx]
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        config = self._get_estado_receta_config(nuevo_estado)

        if config.get("requiere_motivo", False):
            sesiones[self.numero].staff_receta_esperando_motivo = True
            sesiones[self.numero].staff_receta_nuevo_estado = nuevo_estado
            label = config.get("label", nuevo_estado)
            self.sw.enviar(f"📝 Ingresá el motivo para *{label}*:")
            return

        self.receta_manager.cambiar_estado(receta_id, nuevo_estado, config.get("label", ""))

        label = config.get("label", nuevo_estado)
        self.sw.enviar(f"✅ Receta cambiada a estado: *{label}*")

        if config.get("notifica_usuario", False):
            print(f"[PLACEHOLDER] Notificar al paciente: receta {receta_id} → {nuevo_estado}")

        if config.get("es_final", False):
            self.iniciar(sesiones)
        else:
            self._mostrar_detalle(sesiones)

    # ── AVANZAR CAMINO FELIZ ─────────────────────────────────────────────────

    def _avanzar_camino_feliz(self, sesiones):
        """Avanza la receta al estado definido como camino_feliz."""
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
            self.sw.enviar("ℹ️ No hay avance disponible desde este estado.")
            self._mostrar_detalle(sesiones)
            return

        cf_config = self._get_estado_receta_config(camino_feliz)
        cf_label = cf_config.get("label", camino_feliz)

        # Si requiere motivo, pedirlo
        if cf_config.get("requiere_motivo", False):
            sesiones[self.numero].staff_receta_estado = "cambiar_estado_receta"
            sesiones[self.numero].staff_receta_esperando_motivo = True
            sesiones[self.numero].staff_receta_nuevo_estado = camino_feliz
            self.sw.enviar(f"📝 Ingresá el motivo para *{cf_label}*:")
            return

        self.receta_manager.cambiar_estado(receta_id, camino_feliz, f"Avance → {cf_label}")
        self.sw.enviar(f"✅ Receta avanzada a: *{cf_label}*")

        if cf_config.get("notifica_usuario", False):
            # TODO: notificar al paciente
            print(f"[PLACEHOLDER] Notificar al paciente: receta {receta_id} → {camino_feliz}")

        if cf_config.get("es_final", False):
            self.iniciar(sesiones)
        else:
            self._mostrar_detalle(sesiones)

    # ── PLACEHOLDERS ──────────────────────────────────────────────────────────

    def _placeholder_agendar_recordatorio(self, sesiones):
        self.sw.enviar("🚧 Agendar recordatorio — próximamente...")
        self._mostrar_detalle(sesiones)

    def _placeholder_cerrar_y_notificar(self, sesiones):
        """Enviar resumen consolidado al cliente en vez de notificar cada cambio."""
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.sw.enviar("🚧 Cerrar y notificar al cliente — próximamente...")
        print(f"[PLACEHOLDER] Cerrar y notificar resumen consolidado al cliente para receta {receta_id}")
        self._mostrar_detalle(sesiones)

    def _placeholder_validar_token(self, sesiones):
        """Opciones de token: correcto / solicitar nuevo / no requiere."""
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.sw.enviar(
            "🔑 *Validación de token:*\n\n"
            "1. ✅ Token correcto — avanzar\n"
            "2. 🔄 Solicitar nuevo token\n"
            "3. ⏭️ No requiere token — avanzar\n\n"
            "Escribí *cancelar* para volver:"
        )
        # TODO: implementar flujo completo de validación de token
        print(f"[PLACEHOLDER] Validar token para receta {receta_id}")
        # Por ahora queda como placeholder, no cambia estado
        # Cuando se implemente, opciones 1 y 3 cambian a procesando,
        # opción 2 vuelve a requiere_autorizacion

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _get_estado_receta_config(self, estado_id):
        """Retorna la config de un estado de receta desde farmacia_config."""
        return self.farm_config.get("recetas", {}).get("estados_receta", {}).get(estado_id, {})

    def _verificar_todos_resueltos(self, receta_id, sesiones):
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
                "Podés usar *Confirmar todos* o *Cambiar estado de la receta* para avanzar."
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
        sesiones[self.numero].staff_receta_opciones_estado = None
        sesiones[self.numero].staff_receta_esperando_motivo = False
        sesiones[self.numero].staff_receta_nuevo_estado = None
        sesiones[self.numero].staff_receta_opciones_activas = None