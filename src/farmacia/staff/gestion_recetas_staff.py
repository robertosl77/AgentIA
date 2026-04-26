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
    Estados, transiciones, opciones y mensajes leídos de farmacia_config.json.
    """

    CONFIG_PATH = os.path.join("data", "farmacia", "farmacia_config.json")

    OPCIONES_HANDLERS = {
        "avanzar":              None,
        "confirmar_todos":      "_confirmar_todos_disponibles",
        "cambiar_estado_item":  "_iniciar_cambiar_estado_item",
        "enviar_nota":          "_iniciar_escribir_nota",
        "cambiar_estado_receta":"_iniciar_cambiar_estado_receta",
        "agendar_recordatorio": "_placeholder_agendar_recordatorio",
        "validar_token":        "_placeholder_validar_token",
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
        elif estado == "escribir_nota":
            self._procesar_escribir_nota(comando, sesiones)
        elif estado == "cambiar_estado_receta":
            self._procesar_cambiar_estado_receta(comando, sesiones)
        elif estado == "confirmar_token":
            self._procesar_confirmar_token(comando, sesiones)

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

        lineas.append(f"\nIngresá el número para gestionar")
        lineas.append(f"o *cancelar* para volver:")
        self.sw.enviar("\n".join(lineas))

    def _procesar_lista(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
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

        if receta["estado"] == "pendiente":
            self.receta_manager.cambiar_estado(receta["receta_id"], "en_gestion", "Farmacia procesando")

        self._mostrar_detalle(sesiones)

    # ── DETALLE DE RECETA ─────────────────────────────────────────────────────

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

        notas_farmacia = self.receta_manager.get_notas_pendientes(receta_id, "farmacia")
        if notas_farmacia:
            lineas.append(f"\n📬 *{len(notas_farmacia)} nota(s) pendiente(s) del paciente*")

        # Opciones dinámicas según estado actual
        opciones_staff = list(estado_config.get("opciones_staff", []))
        camino_feliz = estado_config.get("camino_feliz")
        opciones_activas = []
        lineas.append("")

        # Detectar si todos los items están resueltos
        items_activos = [it for it in items if it["estado_item"] != "omitido_usuario"]
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
        count = 0
        for i, item in enumerate(items):
            if item["estado_item"] in ("pendiente", "sin_stock", "alternativa_ofrecida"):
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

        if comando.strip() == "1":
            self.receta_manager.cambiar_estado(receta_id, "requiere_autorizacion", "Farmacia solicita token")
            self.receta_manager.agregar_nota(
                receta_id, "farmacia", "usuario",
                self._msg("nota_solicitar_token")
            )
            self.sw.enviar(self._msg("token_si"))
            self._enviar_notificacion_push(receta_id, "requiere_autorizacion")
            self._mostrar_detalle(sesiones)

        elif comando.strip() == "2":
            self.receta_manager.cambiar_estado(receta_id, "procesando", "No requiere token — avance directo")
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
            self.sw.enviar(self._msg("seleccionar_estado_item"))
        else:
            sesiones[self.numero].staff_receta_esperando_estado = False
            receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
            item_idx = getattr(sesiones[self.numero], "staff_receta_item_idx", 0)

            if comando.strip() == "1":
                self.receta_manager.cambiar_estado_item(receta_id, item_idx, "disponible")
                self._desestimar_notas_item(receta_id, item_idx)
                self.sw.enviar(self._msg("item_disponible"))
                self._evaluar_estado_post_cambio_item(receta_id, sesiones)
                self._mostrar_detalle(sesiones)

            elif comando.strip() == "2":
                self.receta_manager.cambiar_estado_item(receta_id, item_idx, "sin_stock")
                resultado = self.receta_manager.get_receta(receta_id)
                if resultado:
                    _, receta = resultado
                    item = receta["items"][item_idx]
                    label = self.med_manager.get_label(item["medicamento_id"])
                    self.receta_manager.agregar_nota(
                        receta_id, "farmacia", "usuario",
                        self._msg("nota_sin_stock", medicamento=label)
                    )
                self.sw.enviar(self._msg("item_sin_stock"))
                self._evaluar_estado_post_cambio_item(receta_id, sesiones)
                self._mostrar_detalle(sesiones)

            elif comando.strip() == "3":
                sesiones[self.numero].staff_receta_estado = "ofrecer_alternativa"
                self.sw.enviar(self._msg("pedir_alternativa"))

            else:
                self.sw.enviar(self._msg("opcion_invalida"))
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
        label_original = "el medicamento"
        if resultado:
            _, receta = resultado
            item = receta["items"][item_idx]
            label_original = self.med_manager.get_label(item["medicamento_id"])

        mensaje_nota = self._msg("nota_alternativa", original=label_original, alternativa=comando.strip())
        self.receta_manager.agregar_nota(receta_id, "farmacia", "usuario", mensaje_nota)

        self.sw.enviar(self._msg("alternativa_ofrecida"))
        self._evaluar_estado_post_cambio_item(receta_id, sesiones)
        self._mostrar_detalle(sesiones)

    # ── ESCRIBIR NOTA ─────────────────────────────────────────────────────────

    def _iniciar_escribir_nota(self, sesiones):
        sesiones[self.numero].staff_receta_estado = "escribir_nota"
        self.sw.enviar(self._msg("pedir_nota"))

    def _procesar_escribir_nota(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._mostrar_detalle(sesiones)
            return

        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.receta_manager.agregar_nota(receta_id, "farmacia", "usuario", comando.strip())

        self.sw.enviar(self._msg("nota_enviada"))
        self._mostrar_detalle(sesiones)

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
            if not config.get("automatico", False):
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

            self.receta_manager.cambiar_estado(receta_id, nuevo_estado, comando.strip())

            config = self._get_estado_receta_config(nuevo_estado)
            label = config.get("label", nuevo_estado)
            self.sw.enviar(self._msg("estado_cambiado", label=label))

            self._enviar_notificacion_push(receta_id, nuevo_estado)

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

        self.receta_manager.cambiar_estado(receta_id, nuevo_estado, config.get("label", ""))

        label = config.get("label", nuevo_estado)
        self.sw.enviar(self._msg("estado_cambiado", label=label))

        self._enviar_notificacion_push(receta_id, nuevo_estado)

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

        # Desde en_gestion, el avance pasa por la pregunta de token
        if estado_actual == "en_gestion":
            # Desestimar notas pendientes
            self._desestimar_notas_items(receta_id)
            print(f"[PLACEHOLDER] Cancelar recordatorios para receta {receta_id}")
            sesiones[self.numero].staff_receta_estado = "confirmar_token"
            self.sw.enviar(self._msg("pregunta_token"))
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

        self._enviar_notificacion_push(receta_id, camino_feliz)

        if cf_config.get("es_final", False):
            self.iniciar(sesiones)
        else:
            self._mostrar_detalle(sesiones)

    # ── PLACEHOLDERS ──────────────────────────────────────────────────────────

    def _placeholder_agendar_recordatorio(self, sesiones):
        self.sw.enviar(self._msg("agendar_recordatorio"))
        self._mostrar_detalle(sesiones)

    def _placeholder_validar_token(self, sesiones):
        receta_id = getattr(sesiones[self.numero], "staff_receta_id", None)
        self.sw.enviar(self._msg("validar_token"))
        print(f"[PLACEHOLDER] Validar token para receta {receta_id}")

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _get_estado_receta_config(self, estado_id):
        return self.farm_config.get("recetas", {}).get("estados_receta", {}).get(estado_id, {})

    def _enviar_notificacion_push(self, receta_id, estado_id):
        """
        Si el estado tiene notificacion_push configurada, envía mensaje real
        al WhatsApp del cliente usando SendWPP.
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

        # Obtener LIDs del cliente
        persona_data = self.persona_manager.get_persona(persona_id)
        if not persona_data:
            return

        _, persona = persona_data
        lids = persona.get("lids", [])
        if not lids:
            print(f"[NOTIFICACION_PUSH] Sin LID para persona {persona_id} — no se puede enviar")
            return

        # Enviar a todos los LIDs del cliente (puede tener varios dispositivos)
        from src.send_wpp import SendWPP
        for lid in lids:
            sw_cliente = SendWPP(lid)
            sw_cliente.enviar(mensaje)
            print(f"[NOTIFICACION_PUSH] Enviado a {lid} | Estado: {estado_id}")

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

        # Evaluar solo desde en_gestion o a_la_espera
        if estado_actual not in ("en_gestion", "a_la_espera"):
            return

        items_activos = [it for it in receta["items"] if it["estado_item"] != "omitido_usuario"]

        hay_pendientes = any(it["estado_item"] == "pendiente" for it in items_activos)
        hay_sin_resolver = any(
            it["estado_item"] in ("sin_stock", "alternativa_ofrecida")
            for it in items_activos
        )
        todos_resueltos = all(
            it["estado_item"] in ("disponible", "alternativa_aceptada", "rechazado_usuario")
            for it in items_activos
        ) if items_activos else False

        if hay_pendientes:
            # Escenario 1: aún hay items por procesar
            # Si estábamos en a_la_espera, volver a en_gestion
            if estado_actual == "a_la_espera":
                self.receta_manager.cambiar_estado(receta_id, "en_gestion", "Farmacia retomó gestión")
            return

        if hay_sin_resolver:
            # Escenario 2: no hay pendientes pero hay sin_stock/alternativa → a_la_espera
            if estado_actual != "a_la_espera":
                self.receta_manager.cambiar_estado(receta_id, "a_la_espera", "Items procesados — esperando respuesta del cliente")
                self.sw.enviar(self._msg("cambio_automatico_a_la_espera"))
                self._enviar_notificacion_push(receta_id, "a_la_espera")
            return

        if todos_resueltos:
            # Escenario 3: todos resueltos
            # Si estábamos en a_la_espera, volver a en_gestion
            if estado_actual == "a_la_espera":
                self.receta_manager.cambiar_estado(receta_id, "en_gestion", "Todos los items resueltos — listo para avanzar")
            self.sw.enviar(self._msg("todos_resueltos"))

    def _desestimar_notas_items(self, receta_id):
        """Desestima todas las notas pendientes de sin_stock/alternativa dirigidas al usuario."""
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return
        _, receta = resultado
        for nota in receta.get("notas", []):
            if nota["estado"] == "pendiente" and nota["dirigida_a"] == "usuario":
                msg_lower = nota["mensaje"].lower()
                if "stock" in msg_lower or "alternativa" in msg_lower:
                    self.receta_manager.responder_nota(
                        receta_id, nota["id"],
                        self._msg("nota_desestimada_auto")
                    )

    def _desestimar_notas_item(self, receta_id, item_idx):
        """Desestima notas pendientes relacionadas con un item específico al marcarlo como disponible."""
        resultado = self.receta_manager.get_receta(receta_id)
        if not resultado:
            return
        _, receta = resultado
        item = receta["items"][item_idx]
        label = self.med_manager.get_label(item["medicamento_id"])
        if not label:
            return

        for nota in receta.get("notas", []):
            if nota["estado"] == "pendiente" and nota["dirigida_a"] == "usuario":
                if label.lower() in nota["mensaje"].lower():
                    self.receta_manager.responder_nota(
                        receta_id, nota["id"],
                        self._msg("nota_desestimada_auto")
                    )

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

    def _volver_menu_staff(self, sesiones):
        rol = self.session_manager.get_rol(self.numero)
        submenu_data = self.config.get_submenu("staff")
        self.sw.enviar(self.config.armar_menu(submenu_data, rol))