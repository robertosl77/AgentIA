# src/farmacia/gestion_recetas.py
import json
import os
from datetime import datetime
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.cliente.persona_manager import PersonaManager
from src.agente_ia.agente_ia import AgenteIA
from src.farmacia.medicamento_manager import MedicamentoManager
from src.farmacia.receta_manager import RecetaManager
from src.farmacia.obra_social_manager import ObraSocialManager
from src.file_services.image_manager import ImageManager
from src.tenant import data_path


class GestionRecetas:
    """
    Flujo conversacional para carga de recetas médicas.
    Todos los mensajes se leen de farmacia_config.json.
    """

    def __init__(self, numero):
        self.CONFIG_PATH = data_path("farmacia", "farmacia_config.json")
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.persona_manager = PersonaManager()
        self.agente_ia = AgenteIA()
        self.med_manager = MedicamentoManager()
        self.receta_manager = RecetaManager()
        self.os_manager = ObraSocialManager()
        self.farm_config = self._cargar_config()

    def _cargar_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _msj(self, clave, **kwargs):
        """Obtiene un mensaje de recetas desde la config, con placeholders."""
        msg = self.farm_config.get("recetas", {}).get("mensajes", {}).get(clave, "")
        if kwargs:
            for k, v in kwargs.items():
                msg = msg.replace(f"{{{k}}}", str(v))
        return msg

    def _msj_error_ia(self, codigo_error):
        """Obtiene el mensaje de error de IA diferenciado por código."""
        errores = self.farm_config.get("agente_ia", {}).get("errores_http", {})
        return errores.get(codigo_error, errores.get("error_generico", "⚠️ Error al interpretar la receta."))

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
        self.sw.enviar(self._msj("pedir_imagen"))

    def procesar(self, comando, sesiones, imagen_base64=None):
        """Dispatcher según estado."""
        estado = getattr(sesiones[self.numero], "rec_estado", None)

        if estado == "esperando_imagen":
            self._procesar_imagen(comando, sesiones, imagen_base64)
        elif estado == "resolver_errores":
            self._procesar_resolver_error(comando, sesiones)
        elif estado == "seleccion_medicamentos":
            self._procesar_seleccion_medicamentos(comando, sesiones)
        elif estado == "menu_modificar_item":
            self._procesar_menu_modificar_item(comando, sesiones)
        elif estado == "modificar_cantidad":
            self._procesar_modificar_cantidad(comando, sesiones)
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
                self.sw.enviar(self._msj("sin_imagen_cancelado"))
                self._salir(sesiones)
            else:
                self.sw.enviar(self._msj("sin_imagen_reintento"))
            return

        self.sw.enviar(self._msj("interpretando"))

        # Interpretar con agente IA
        resultado = self.agente_ia.interpretar_receta(imagen_base64=imagen_base64)
        print(f"🤖 Resultado agente IA: {resultado}")

        # Error de infraestructura (API key, cuota, etc.)
        codigo_error = resultado.get("codigo_error")
        if codigo_error:
            self.sw.enviar(self._msj_error_ia(codigo_error))
            return

        # Error de interpretación (no pudo leer contenido)
        if resultado.get("errores") and not resultado.get("medicamentos"):
            self.sw.enviar(self._msj_error_ia("interpretacion_fallida"))
            return

        sesiones[self.numero].rec_datos["ia_resultado"] = resultado
        sesiones[self.numero].rec_datos["imagen_base64"] = imagen_base64
        sesiones[self.numero].rec_reintentos = 0

        # Validar beneficiario (DNI)
        if not self._validar_beneficiario(resultado, sesiones):
            return

        # Validar credencial obra social (bloqueo)
        if not self._validar_obra_social(resultado, sesiones):
            return

        # Validar vencimiento
        if not self._validar_vencimiento(resultado, sesiones):
            return

        # Validar duplicado (firma: persona + fecha_validez + diagnóstico)
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        fecha_validez = resultado.get("fecha_validez_desde", "")
        diagnostico = resultado.get("diagnostico", "")
        if self._es_receta_duplicada(beneficiario_id, fecha_validez, diagnostico):
            self.sw.enviar(self._msj("receta_duplicada"))
            self._salir(sesiones)
            return

        # Verificar campos faltantes en medicamentos
        medicamentos = resultado.get("medicamentos", [])
        campos_faltantes = []
        for i, med in enumerate(medicamentos):
            if not med.get("cantidad") or med["cantidad"] == 0:
                label = self._get_label_med(med) or f"Medicamento {i+1}"
                campos_faltantes.append({
                    "indice": i,
                    "campo": "cantidad",
                    "medicamento": label
                })

        if campos_faltantes:
            sesiones[self.numero].rec_datos["campos_faltantes"] = campos_faltantes
            sesiones[self.numero].rec_estado = "resolver_errores"
            faltante = campos_faltantes[0]
            self.sw.enviar(self._msj("cantidad_faltante", medicamento=faltante["medicamento"]))
            return

        self._mostrar_seleccion_medicamentos(sesiones)

    # ── VALIDACIONES ──────────────────────────────────────────────────────────

    def _validar_beneficiario(self, resultado, sesiones):
        """Valida DNI beneficiario ↔ DNI receta. Bloquea si no coincide."""
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        persona = self.persona_manager.get_persona(beneficiario_id)
        if not persona:
            return True

        dni_persona = persona[1].get("numero_documento", "")
        dni_receta = resultado.get("paciente", {}).get("dni", "")

        if dni_receta and dni_persona and dni_receta.strip() != dni_persona.strip():
            nombre = self.persona_manager.get_nombre_completo(beneficiario_id) or "el beneficiario"
            self.sw.enviar(self._msj("dni_no_coincide", nombre=nombre))
            self._salir(sesiones)
            return False

        return True

    def _validar_obra_social(self, resultado, sesiones):
        """Valida credencial de obra social. Bloquea si no coincide."""
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        credencial_receta = resultado.get("obra_social", {}).get("credencial", "")

        if not credencial_receta:
            return True

        asociaciones = self.os_manager.buscar_por_persona(beneficiario_id)
        if not asociaciones:
            return True

        for asoc in asociaciones:
            if asoc["numero"].strip() == credencial_receta.strip():
                sesiones[self.numero].rec_datos["obra_social_id"] = asoc["asociacion_id"]
                return True

        # No coincide — bloquear
        self.sw.enviar(self._msj("credencial_no_coincide"))
        self._salir(sesiones)
        return False

    def _validar_vencimiento(self, resultado, sesiones):
        """Valida que la receta no esté vencida. Bloquea si venció."""
        fecha_validez = resultado.get("fecha_validez_desde", "")
        if not fecha_validez:
            return True

        dias_venc = self.farm_config.get("recetas", {}).get("dias_vencimiento", 30)
        try:
            f_validez = datetime.strptime(fecha_validez, "%d/%m/%Y")
        except ValueError:
            return True  # No podemos validar, dejamos pasar

        from datetime import timedelta
        f_vencimiento = f_validez + timedelta(days=dias_venc)

        if datetime.now() > f_vencimiento:
            self.sw.enviar(self._msj("receta_vencida", fecha=f_vencimiento.strftime("%d/%m/%Y")))
            self._salir(sesiones)
            return False

        return True

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
                self.sw.enviar(self._msj("cantidad_invalida"))
                return

            medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]
            medicamentos[faltante["indice"]]["cantidad"] = cantidad

        campos_faltantes.pop(0)

        if campos_faltantes:
            siguiente = campos_faltantes[0]
            self.sw.enviar(self._msj("cantidad_faltante", medicamento=siguiente["medicamento"]))
        else:
            self._mostrar_seleccion_medicamentos(sesiones)

    # ── SELECCIÓN DE MEDICAMENTOS ─────────────────────────────────────────────

    def _get_label_med(self, med):
        """Genera label legible de un medicamento del resultado IA."""
        nombre = med.get("nombre_comercial") or med.get("farmaco", "")
        dosis = med.get("dosis", "")
        presentacion = med.get("presentacion", "")
        partes = [p for p in [nombre, dosis, presentacion] if p]
        return " ".join(partes)

    def _mostrar_seleccion_medicamentos(self, sesiones):
        """Muestra la lista de medicamentos para selección."""
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        if "items_activos" not in sesiones[self.numero].rec_datos:
            sesiones[self.numero].rec_datos["items_activos"] = list(range(len(medicamentos)))

        items_activos = sesiones[self.numero].rec_datos["items_activos"]

        if not items_activos:
            self.sw.enviar(self._msj("sin_medicamentos"))
            self._salir(sesiones)
            return

        if len(items_activos) == 1:
            med = medicamentos[items_activos[0]]
            cantidad = med.get("cantidad_solicitada", med.get("cantidad", 0))
            label = f"{self._get_label_med(med)} — Cantidad: {cantidad}"
            sesiones[self.numero].rec_datos["item_seleccionado_idx"] = 0
            sesiones[self.numero].rec_datos["item_seleccionado_real"] = items_activos[0]
            sesiones[self.numero].rec_estado = "seleccion_medicamentos"
            self.sw.enviar(self._msj("seleccion_medicamentos_uno", medicamento=label))
            return

        lineas = []
        for idx, i in enumerate(items_activos, 1):
            med = medicamentos[i]
            cantidad = med.get("cantidad_solicitada", med.get("cantidad", 0))
            lineas.append(f"{idx}. ✅ {self._get_label_med(med)} — Cantidad: {cantidad}")

        sesiones[self.numero].rec_estado = "seleccion_medicamentos"
        self.sw.enviar(self._msj("seleccion_medicamentos", lista="\n".join(lineas)))

    def _procesar_seleccion_medicamentos(self, comando, sesiones):
        """Procesa la selección de medicamentos."""
        if comando.strip() == "cancelar":
            self.sw.enviar(self._msj("receta_cancelada"))
            self._salir(sesiones)
            return

        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        # Caso: 1 solo medicamento — opciones: 1=enviar, 2=modificar cantidad, cancelar
        if len(items_activos) == 1:
            if comando.strip() in ("1", "enviar"):
                if sesiones[self.numero].rec_datos.get("hubo_cambios"):
                    self._mostrar_confirmacion_final(sesiones)
                else:
                    self._registrar_receta(sesiones)
                return
            elif comando.strip() in ("2", "modificar"):
                i_real = items_activos[0]
                med = medicamentos[i_real]
                max_cantidad = med.get("cantidad", 1)
                label = self._get_label_med(med)
                sesiones[self.numero].rec_datos["item_seleccionado_real"] = i_real
                sesiones[self.numero].rec_datos["max_cantidad"] = max_cantidad
                sesiones[self.numero].rec_estado = "modificar_cantidad"
                self.sw.enviar(self._msj("nueva_cantidad", medicamento=label, max=max_cantidad))
                return
            else:
                self.sw.enviar(self._msj("numero_invalido"))
                return

        # Caso: N medicamentos
        if comando.strip() == "enviar":
            if sesiones[self.numero].rec_datos.get("hubo_cambios"):
                self._mostrar_confirmacion_final(sesiones)
            else:
                self._registrar_receta(sesiones)
            return

        if comando.strip() == "modificar":
            self.sw.enviar(self._msj("seleccionar_para_modificar"))
            return

        if comando.strip() == "no":
            # Compatibilidad: "no" = enviar
            if sesiones[self.numero].rec_datos.get("hubo_cambios"):
                self._mostrar_confirmacion_final(sesiones)
            else:
                self._registrar_receta(sesiones)
            return

        if comando.strip() == "si":
            # Compatibilidad: "si" = modificar
            self.sw.enviar(self._msj("seleccionar_para_modificar"))
            return

        # Esperando número de medicamento a modificar
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(items_activos):
                raise ValueError
        except ValueError:
            self.sw.enviar(self._msj("numero_invalido"))
            return

        i_real = items_activos[idx]
        med = medicamentos[i_real]
        label = self._get_label_med(med)

        sesiones[self.numero].rec_datos["item_seleccionado_idx"] = idx
        sesiones[self.numero].rec_datos["item_seleccionado_real"] = i_real
        sesiones[self.numero].rec_estado = "menu_modificar_item"
        self.sw.enviar(self._msj("menu_modificar_item", medicamento=label))

    # ── MENÚ MODIFICAR ITEM ───────────────────────────────────────────────────

    def _procesar_menu_modificar_item(self, comando, sesiones):
        """Procesa eliminar o modificar cantidad de un medicamento."""
        if comando.strip() == "cancelar":
            self._mostrar_seleccion_medicamentos(sesiones)
            return

        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]
        idx = sesiones[self.numero].rec_datos.get("item_seleccionado_idx", 0)
        i_real = sesiones[self.numero].rec_datos.get("item_seleccionado_real", 0)
        med = medicamentos[i_real]
        label = self._get_label_med(med)

        if comando.strip() == "1":
            # Eliminar
            items_activos.pop(idx)
            sesiones[self.numero].rec_datos["hubo_cambios"] = True
            self.sw.enviar(self._msj("medicamento_eliminado", medicamento=label))
            self._mostrar_seleccion_medicamentos(sesiones)
            return

        if comando.strip() == "2":
            # Modificar cantidad
            max_cantidad = med.get("cantidad", 1)
            sesiones[self.numero].rec_datos["max_cantidad"] = max_cantidad
            sesiones[self.numero].rec_estado = "modificar_cantidad"
            self.sw.enviar(self._msj("nueva_cantidad", medicamento=label, max=max_cantidad))
            return

        self.sw.enviar(self._msj("numero_invalido"))

    def _procesar_modificar_cantidad(self, comando, sesiones):
        """Procesa la nueva cantidad ingresada."""
        if comando.strip() == "cancelar":
            self._mostrar_seleccion_medicamentos(sesiones)
            return

        max_cant = sesiones[self.numero].rec_datos.get("max_cantidad", 1)
        try:
            nueva = int(comando.strip())
            if nueva <= 0 or nueva > max_cant:
                self.sw.enviar(self._msj("cantidad_rango_error", max=max_cant))
                return
        except ValueError:
            self.sw.enviar(self._msj("cantidad_invalida"))
            return

        i_real = sesiones[self.numero].rec_datos.get("item_seleccionado_real")
        medicamentos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]
        medicamentos[i_real]["cantidad_solicitada"] = nueva
        sesiones[self.numero].rec_datos["hubo_cambios"] = True

        self.sw.enviar(self._msj("cantidad_actualizada", cantidad=nueva))
        self._mostrar_seleccion_medicamentos(sesiones)

    # ── CONFIRMACIÓN FINAL ────────────────────────────────────────────────────

    def _mostrar_confirmacion_final(self, sesiones):
        """Muestra resumen final antes de registrar."""
        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        todos = sesiones[self.numero].rec_datos["ia_resultado"]["medicamentos"]

        lineas = []
        for i, med in enumerate(todos):
            label = self._get_label_med(med)
            if i in items_activos:
                cantidad_receta = med.get("cantidad", 0)
                cantidad_sol = med.get("cantidad_solicitada", cantidad_receta)
                if cantidad_sol != cantidad_receta:
                    lineas.append(f"✅ {label} — Cantidad: {cantidad_sol} de {cantidad_receta}")
                else:
                    lineas.append(f"✅ {label} — Cantidad: {cantidad_sol}")
            else:
                lineas.append(f"❌ {label} — Omitido")

        sesiones[self.numero].rec_estado = "confirmacion_final"
        self.sw.enviar(self._msj("confirmacion_final", lista="\n".join(lineas)))

    def _procesar_confirmacion(self, comando, sesiones):
        """Procesa la confirmación final y registra la receta."""
        if comando.strip() == "no" or comando.strip() == "cancelar":
            self.sw.enviar(self._msj("receta_cancelada"))
            self._salir(sesiones)
            return

        if comando.strip() != "si":
            self.sw.enviar(self._msj("responder_si_no"))
            return

        self._registrar_receta(sesiones)

    def _registrar_receta(self, sesiones):
        """Registra la receta en el sistema y envía resumen."""
        resultado_ia = sesiones[self.numero].rec_datos["ia_resultado"]
        medicamentos = resultado_ia.get("medicamentos", [])
        items_activos = sesiones[self.numero].rec_datos.get("items_activos", [])
        beneficiario_id = getattr(sesiones[self.numero], "rec_beneficiario_id", None)
        operador_id = getattr(sesiones[self.numero], "rec_operador_id", None)

        items = []
        for i, med in enumerate(medicamentos):
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

        os_id = sesiones[self.numero].rec_datos.get("obra_social_id", "")
        fecha_validez = resultado_ia.get("fecha_validez_desde", "")
        diagnostico = resultado_ia.get("diagnostico", "")

        imagen_base64 = sesiones[self.numero].rec_datos.get("imagen_base64")
        receta_url = None
        if imagen_base64:
            receta_url = ImageManager().procesar(imagen_base64, proyecto="farmacia")

        receta_id = self.receta_manager.crear_receta(
            persona_id=beneficiario_id,
            obra_social_id=os_id,
            fecha_validez_desde=fecha_validez,
            medico=resultado_ia.get("medico", {}),
            diagnostico=diagnostico,
            items=items,
            operador_id=operador_id,
            fecha_creacion=resultado_ia.get("fecha_creacion", ""),
            credencial_validada=bool(os_id),
            receta_url=receta_url
        )

        # Resumen
        lineas = []
        for item in items:
            label = self.med_manager.get_label(item["medicamento_id"])
            if item["estado_item"] == "pendiente":
                cant_receta = item["cantidad_receta"]
                cant_sol = item["cantidad_solicitada"]
                if cant_sol != cant_receta:
                    lineas.append(f"📦 {label} — Cantidad: {cant_sol} de {cant_receta} (pendiente)")
                else:
                    lineas.append(f"📦 {label} — Cantidad: {cant_sol} (pendiente)")
            else:
                lineas.append(f"❌ {label} — Omitido")

        self.sw.enviar(self._msj("receta_enviada", lista="\n".join(lineas)))
        self._salir(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _es_receta_duplicada(self, persona_id, fecha_validez, diagnostico):
        """
        Detecta si ya existe una receta con la misma 'firma':
        persona_id + fecha_validez_desde + diagnostico.
        """
        recetas = self.receta_manager.buscar_por_persona(persona_id)
        for r in recetas:
            if (r.get("fecha_validez_desde", "") == fecha_validez and
                    r.get("diagnostico", "").lower() == diagnostico.lower()):
                return True
        return False

    def _salir(self, sesiones):
        """Limpia estado del flujo."""
        sesiones[self.numero].rec_estado = None
        sesiones[self.numero].rec_beneficiario_id = None
        sesiones[self.numero].rec_operador_id = None
        sesiones[self.numero].rec_datos = {}
        sesiones[self.numero].rec_reintentos = 0