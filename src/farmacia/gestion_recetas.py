# src/farmacia/gestion_recetas.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.cliente.persona_manager import PersonaManager
from src.agente_ia.agente_ia import AgenteIA
from src.farmacia.medicamento_manager import MedicamentoManager
from src.farmacia.receta_manager import RecetaManager
from src.farmacia.obra_social_manager import ObraSocialManager


class GestionRecetas:
    """
    Flujo conversacional para carga de recetas médicas.
    Pasos:
        1. Usuario sube imagen/PDF de receta
        2. Agente IA interpreta → extrae datos
        3. Validación automática: DNI beneficiario ↔ DNI receta
        4. Validación credencial obra social (alerta, no bloqueo)
        5. Resolución de campos que la IA no pudo leer
        6. Selección de medicamentos (quitar de a uno)
        7. Ajuste de cantidades
        8. Confirmación y registro
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.persona_manager = PersonaManager()
        self.agente_ia = AgenteIA()
        self.med_manager = MedicamentoManager()
        self.receta_manager = RecetaManager()
        self.os_manager = ObraSocialManager()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        estado = getattr(sesiones[self.numero], "rec_estado", None)
        return estado is not None

    def iniciar(self, sesiones, beneficiario_id, operador_id):
        """Punto de entrada — pide subir receta."""
        sesiones[self.numero].rec_estado = "esperando_imagen"
        sesiones[self.numero].rec_beneficiario_id = beneficiario_id
        sesiones[self.numero].rec_operador_id = operador_id
        sesiones[self.numero].rec_datos = {}
        sesiones[self.numero].rec_reintentos = 0

        self.sw.enviar(
            "📤 Enviá la *imagen o PDF* de la receta médica.\n"
            "Podés sacarle una foto o adjuntar el archivo.\n\n"
            "Escribí *cancelar* para volver."
        )

    def procesar(self, comando, sesiones, imagen_base64=None):
        """Dispatcher según estado."""
        estado = getattr(sesiones[self.numero], "rec_estado", None)

        if estado == "esperando_imagen":
            self._procesar_imagen(comando, sesiones, imagen_base64)
        elif estado == "resolver_errores":
            self._procesar_resolver_error(comando, sesiones)
        elif estado == "seleccion_medicamentos":
            self._procesar_seleccion_medicamentos(comando, sesiones)
        elif estado == "ajuste_cantidades":
            self._procesar_ajuste_cantidades(comando, sesiones)
        elif estado == "ajuste_cantidad_item":
            self._procesar_cantidad_item(comando, sesiones)
        elif estado == "confirmacion_final":
            self._procesar_confirmacion(comando, sesiones)

    # ── RECEPCIÓN DE IMAGEN ───────────────────────────────────────────────────

    def _procesar_imagen(self, comando, sesiones, imagen_base64):
        """Recibe la imagen y la envía al agente IA."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        if not imagen_base64:
            reintentos = getattr(sesiones[self.numero], "rec_reintentos", 0) + 1
            sesiones[self.numero].rec_reintentos = reintentos
            if reintentos >= 3:
                self.sw.enviar("❌ No se recibió imagen. Operación cancelada.")
                self._salir(sesiones)
            else:
                self.sw.enviar("⚠️ Necesito que envíes una *imagen o PDF* de la receta.")
            return

        self.sw.enviar("🔍 Interpretando receta... un momento por favor.")

        # Interpretar con agente IA
        resultado = self.agente_ia.interpretar_receta(imagen_base64=imagen_base64)

        # DEBUG: ver qué retorna el agente
        print(f"🤖 Resultado agente IA: {resultado}")

        if resultado.get("errores") and not resultado.get("medicamentos"):
            self.sw.enviar(
                "⚠️ No pude interpretar la receta. "
                "Intentá con una foto más nítida o un PDF.\n\n"
                "Enviá la imagen nuevamente o escribí *cancelar*:"
            )
            return

        sesiones[self.numero].rec_datos["ia_resultado"] = resultado
        sesiones[self.numero].rec_reintentos = 0

        # Validar beneficiario
        if not self._validar_beneficiario(resultado, sesiones):
            return

        # Validar obra social (alerta, no bloqueo)
        self._validar_obra_social(resultado, sesiones)

        # Verificar errores de la IA
        errores = resultado.get("errores", [])
        medicamentos = resultado.get("medicamentos", [])

        # Buscar campos faltantes en medicamentos
        campos_faltantes = []
        for i, med in enumerate(medicamentos):
            if not med.get("cantidad") or med["cantidad"] == 0:
                campos_faltantes.append({
                    "indice": i,
                    "campo": "cantidad",
                    "medicamento": med.get("farmaco", f"Medicamento {i+1}")
                })

        if campos_faltantes:
            sesiones[self.numero].rec_datos["campos_faltantes"] = campos_faltantes
            sesiones[self.numero].rec_estado = "resolver_errores"
            faltante = campos_faltantes[0]
            self.sw.enviar(
                f"⚠️ No pude identificar la cantidad de *{faltante['medicamento']}*.\n"
                f"¿Cuántas cajas/envases necesitás?"
            )
            return

        # Todo bien → ir a selección de medicamentos
        self._mostrar_seleccion_medicamentos(sesiones)

    # ── VALIDACIONES ──────────────────────────────────────────────────────────

    def _validar_beneficiario(self, resultado, sesiones):
        """Valida que el DNI de la receta coincida con el beneficiario activo."""
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        persona = self.persona_manager.get_persona(beneficiario_id)
        if not persona:
            return True  # Sin persona, no podemos validar

        dni_persona = persona[1].get("numero_documento", "")
        dni_receta = resultado.get("paciente", {}).get("dni", "")

        if dni_receta and dni_persona and dni_receta.strip() != dni_persona.strip():
            nombre = self.persona_manager.get_nombre_completo(beneficiario_id) or "el beneficiario"
            self.sw.enviar(
                f"⚠️ La receta no corresponde al beneficiario activo (*{nombre}*).\n"
                f"El DNI de la receta no coincide.\n"
                f"Verificá que estés gestionando para la persona correcta.\n\n"
                f"Operación cancelada."
            )
            self._salir(sesiones)
            return False

        return True

    def _validar_obra_social(self, resultado, sesiones):
        """Valida credencial de obra social (alerta, no bloqueo)."""
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        credencial_receta = resultado.get("obra_social", {}).get("credencial", "")

        if not credencial_receta:
            return

        # Buscar obra social del beneficiario
        asociaciones = self.os_manager.buscar_por_persona(beneficiario_id)
        if not asociaciones:
            return

        # Verificar si alguna credencial coincide
        for asoc in asociaciones:
            if asoc["numero"].strip() == credencial_receta.strip():
                sesiones[self.numero].rec_datos["obra_social_id"] = asoc["asociacion_id"]
                return

        # No coincide — alerta
        self.sw.enviar(
            "⚠️ *Atención*: el número de credencial de la receta no coincide "
            "con la obra social registrada. Esto puede ser un error del médico. "
            "La receta se procesará igualmente."
        )

    # ── RESOLVER ERRORES DE IA ────────────────────────────────────────────────

    def _procesar_resolver_error(self, comando, sesiones):
        """Resuelve campos que la IA no pudo interpretar."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        campos_faltantes = sesiones[self.numero].rec_datos.get("campos_faltantes", [])
        if not campos_faltantes:
            self._mostrar_seleccion_medicamentos(sesiones)
            return

        faltante = campos_faltantes[0]

        if faltante["campo"] == "cantidad":
            try:
                cantidad = int(comando.strip())
                if cantidad <= 0:
                    raise ValueError
            except ValueError:
                self.sw.enviar("⚠️ Ingresá un número válido mayor a 0:")
                return

            # Actualizar cantidad en el resultado de la IA
            medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]
            medicamentos[faltante["indice"]]["cantidad"] = cantidad

        # Remover faltante resuelto y seguir
        campos_faltantes.pop(0)

        if campos_faltantes:
            siguiente = campos_faltantes[0]
            self.sw.enviar(
                f"⚠️ No pude identificar la cantidad de *{siguiente['medicamento']}*.\n"
                f"¿Cuántas cajas/envases necesitás?"
            )
        else:
            self._mostrar_seleccion_medicamentos(sesiones)

    # ── SELECCIÓN DE MEDICAMENTOS ─────────────────────────────────────────────

    def _mostrar_seleccion_medicamentos(self, sesiones):
        """Muestra la lista de medicamentos para selección."""
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        # Inicializar items activos (todos activos por defecto)
        if "items_activos" not in sesiones[self.numero].rec_datos:
            sesiones[self.numero].rec_datos["items_activos"] = list(range(len(medicamentos)))

        items_activos = sesiones[self.numero].rec_datos["items_activos"]

        if not items_activos:
            self.sw.enviar("❌ No quedaron medicamentos para procesar. Receta cancelada.")
            self._salir(sesiones)
            return

        if len(items_activos) == 1:
            # Solo queda uno
            med = medicamentos[items_activos[0]]
            nombre = med.get("nombre_comercial") or med.get("farmaco", "Medicamento")
            sesiones[self.numero].rec_estado = "seleccion_medicamentos"
            self.sw.enviar(
                f"📋 Queda 1 medicamento:\n\n"
                f"• {nombre} {med.get('dosis', '')} — Cantidad: {med.get('cantidad', 0)}\n\n"
                f"¿Deseas procesarlo? (*si*/*no* o *cancelar*):"
            )
            return

        lineas = ["📋 Medicamentos de la receta:\n"]
        for idx, i in enumerate(items_activos, 1):
            med = medicamentos[i]
            nombre = med.get("nombre_comercial") or med.get("farmaco", "")
            lineas.append(f"{idx}. ✅ {nombre} {med.get('dosis', '')} — Cantidad: {med.get('cantidad', 0)}")

        lineas.append("\n¿Querés procesar todos? (*si*/*no* o *cancelar*):")
        sesiones[self.numero].rec_estado = "seleccion_medicamentos"
        self.sw.enviar("\n".join(lineas))

    def _procesar_seleccion_medicamentos(self, comando, sesiones):
        """Procesa la selección/descarte de medicamentos."""
        if comando.strip() == "cancelar":
            self.sw.enviar("❌ Receta cancelada.")
            self._salir(sesiones)
            return

        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        if comando.strip() == "si":
            # Procesar todos los activos → ir a ajuste de cantidades
            self._mostrar_ajuste_cantidades(sesiones)
            return

        if comando.strip() == "no":
            if len(items_activos) == 1:
                # Era el último, cancelar receta
                self.sw.enviar("❌ No quedaron medicamentos para procesar. Receta cancelada.")
                self._salir(sesiones)
                return

            self.sw.enviar("Ingresá el *número* del medicamento que querés quitar:")
            sesiones[self.numero].rec_estado = "seleccion_medicamentos"
            sesiones[self.numero].rec_datos["esperando_quitar"] = True
            return

        # Esperando número para quitar
        if sesiones[self.numero].rec_datos.get("esperando_quitar"):
            try:
                idx = int(comando.strip()) - 1
                if idx < 0 or idx >= len(items_activos):
                    raise ValueError
            except ValueError:
                self.sw.enviar("❌ Número no válido.")
                return

            items_activos.pop(idx)
            sesiones[self.numero].rec_datos["esperando_quitar"] = False
            self._mostrar_seleccion_medicamentos(sesiones)

    # ── AJUSTE DE CANTIDADES ──────────────────────────────────────────────────

    def _mostrar_ajuste_cantidades(self, sesiones):
        """Pregunta si quiere mantener las cantidades."""
        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        lineas = ["📋 Cantidades a solicitar:\n"]
        for idx, i in enumerate(items_activos, 1):
            med = medicamentos[i]
            nombre = med.get("nombre_comercial") or med.get("farmaco", "")
            lineas.append(f"{idx}. {nombre} {med.get('dosis', '')} — Cantidad: {med.get('cantidad', 0)}")

        lineas.append("\n¿Querés mantener las cantidades? (*si*/*no*):")
        sesiones[self.numero].rec_estado = "ajuste_cantidades"
        self.sw.enviar("\n".join(lineas))

    def _procesar_ajuste_cantidades(self, comando, sesiones):
        """Procesa ajuste de cantidades."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        if comando.strip() == "si":
            self._mostrar_confirmacion_final(sesiones)
            return

        if comando.strip() == "no":
            items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
            medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

            lineas = ["¿Cuál querés modificar?\n"]
            for idx, i in enumerate(items_activos, 1):
                med = medicamentos[i]
                nombre = med.get("nombre_comercial") or med.get("farmaco", "")
                lineas.append(f"{idx}. {nombre} — Cantidad actual: {med.get('cantidad', 0)}")

            lineas.append("\nIngresá el número:")
            self.sw.enviar("\n".join(lineas))
            sesiones[self.numero].rec_estado = "ajuste_cantidad_item"
            sesiones[self.numero].rec_datos["esperando_seleccion_cantidad"] = True
            return

        self.sw.enviar("⚠️ Respondé *si* o *no*:")

    def _procesar_cantidad_item(self, comando, sesiones):
        """Procesa la modificación de cantidad de un item específico."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        if sesiones[self.numero].rec_datos.get("esperando_seleccion_cantidad"):
            try:
                idx = int(comando.strip()) - 1
                if idx < 0 or idx >= len(items_activos):
                    raise ValueError
            except ValueError:
                self.sw.enviar("❌ Número no válido.")
                return

            i_real = items_activos[idx]
            med = medicamentos[i_real]
            max_cantidad = med.get("cantidad", 1)
            nombre = med.get("nombre_comercial") or med.get("farmaco", "")

            sesiones[self.numero].rec_datos["item_modificando"] = i_real
            sesiones[self.numero].rec_datos["max_cantidad"] = max_cantidad
            sesiones[self.numero].rec_datos["esperando_seleccion_cantidad"] = False
            self.sw.enviar(f"Ingresá la nueva cantidad para *{nombre}* (máx: {max_cantidad}):")
            return

        # Esperando nueva cantidad
        try:
            nueva = int(comando.strip())
            max_cant = sesiones[self.numero].rec_datos.get("max_cantidad", 1)
            if nueva <= 0 or nueva > max_cant:
                self.sw.enviar(f"⚠️ La cantidad debe ser entre 1 y {max_cant}:")
                return
        except ValueError:
            self.sw.enviar("⚠️ Ingresá un número válido:")
            return

        i_real = sesiones[self.numero].rec_datos.get("item_modificando")
        medicamentos[i_real]["cantidad_solicitada"] = nueva

        self.sw.enviar(f"✅ Cantidad actualizada a {nueva}.")
        self._mostrar_ajuste_cantidades(sesiones)

    # ── CONFIRMACIÓN FINAL ────────────────────────────────────────────────────

    def _mostrar_confirmacion_final(self, sesiones):
        """Muestra resumen final antes de registrar."""
        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]
        todos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        lineas = ["📋 *Resumen de tu solicitud:*\n"]
        for i, med in enumerate(todos):
            nombre = med.get("nombre_comercial") or med.get("farmaco", "")
            dosis = med.get("dosis", "")
            if i in items_activos:
                cantidad = med.get("cantidad_solicitada", med.get("cantidad", 0))
                lineas.append(f"✅ {nombre} {dosis} — Cantidad: {cantidad}")
            else:
                lineas.append(f"❌ {nombre} {dosis} — Omitido")

        lineas.append("\n¿Confirmás el envío a la farmacia? (*si*/*no*):")
        sesiones[self.numero].rec_estado = "confirmacion_final"
        self.sw.enviar("\n".join(lineas))

    def _procesar_confirmacion(self, comando, sesiones):
        """Procesa la confirmación final y registra la receta."""
        if comando.strip() == "no" or comando.strip() == "cancelar":
            self.sw.enviar("❌ Receta cancelada.")
            self._salir(sesiones)
            return

        if comando.strip() != "si":
            self.sw.enviar("⚠️ Respondé *si* o *no*:")
            return

        # Registrar medicamentos en catálogo y armar items
        resultado_ia = sesiones[self.numero].rec_datos["ia_resultado"]
        medicamentos = resultado_ia.get("medicamentos", [])
        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        operador_id = getattr(sesiones[self.numero], "rec_operador_id", None)

        items = []
        for i, med in enumerate(medicamentos):
            # Crear o encontrar medicamento en catálogo
            med_id, _ = self.med_manager.crear_o_encontrar(
                farmaco=med.get("farmaco", ""),
                nombre_comercial=med.get("nombre_comercial", ""),
                dosis=med.get("dosis", ""),
                presentacion=med.get("presentacion", "")
            )

            if i in items_activos:
                cantidad_max = med.get("cantidad", 0)
                cantidad_solicitada = med.get("cantidad_solicitada", cantidad_max)
                estado = "pendiente"
            else:
                cantidad_max = med.get("cantidad", 0)
                cantidad_solicitada = 0
                estado = "omitido_usuario"

            items.append({
                "medicamento_id": med_id,
                "cantidad_receta": cantidad_max,
                "cantidad_solicitada": cantidad_solicitada,
                "estado_item": estado
            })

        # Obtener obra social id si se validó
        os_id = sesiones[self.numero].rec_datos.get("obra_social_id", "")

        # Crear receta
        receta_id = self.receta_manager.crear_receta(
            persona_id=beneficiario_id,
            obra_social_id=os_id,
            fecha_validez_desde=resultado_ia.get("fecha_validez_desde", ""),
            medico=resultado_ia.get("medico", {}),
            diagnostico=resultado_ia.get("diagnostico", ""),
            items=items,
            operador_id=operador_id,
            fecha_creacion=resultado_ia.get("fecha_creacion", "")
        )

        # Resumen enviado
        lineas = ["✅ *Receta enviada a la farmacia.*\n"]
        for item in items:
            label = self.med_manager.get_label(item["medicamento_id"])
            if item["estado_item"] == "pendiente":
                lineas.append(f"📦 {label} — Cantidad: {item['cantidad_solicitada']} (pendiente)")
            else:
                lineas.append(f"⏭️ {label} — Omitido")

        lineas.append(f"\n📋 Estado: *Pendiente de procesar por farmacia*")
        self.sw.enviar("\n".join(lineas))
        self._salir(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _salir(self, sesiones):
        """Limpia estado del flujo."""
        sesiones[self.numero].rec_estado = None
        sesiones[self.numero].rec_beneficiario_id = None
        sesiones[self.numero].rec_operador_id = None
        sesiones[self.numero].rec_datos = {}
        sesiones[self.numero].rec_reintentos = 0