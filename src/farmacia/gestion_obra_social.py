# src/farmacia/gestion_obra_social.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.farmacia.obra_social_manager import ObraSocialManager


class GestionObraSocial:
    """
    Flujo conversacional dinámico para administrar obras sociales del beneficiario.
    Los campos, orden, validadores y mensajes se leen de configuracion.json
    (estructura_sesion.obra_social). Agregar un campo al JSON lo incorpora
    automáticamente tanto en la carga como en la actualización.
    """

    SECCION = "obra_social"

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.os_manager = ObraSocialManager()

    # ── CONFIGURACIÓN DINÁMICA ────────────────────────────────────────────────

    def _get_campos(self):
        """Retorna el dict ordenado de campos desde configuracion.json."""
        return self.config.data.get("estructura_sesion", {}).get(self.SECCION, {})

    def _get_campos_ordenados(self):
        """Retorna la lista de nombres de campo en orden."""
        return list(self._get_campos().keys())

    def _get_config_campo(self, campo):
        """Retorna la config de un campo específico."""
        return self._get_campos().get(campo, {})

    def _get_config_validadores(self):
        """Retorna el catálogo de validadores globales."""
        return self.config.data.get("validadores", {})

    def _get_reintentos_max(self):
        """Retorna el máximo de reintentos."""
        return self.config.data.get("estructura_sesion", {}).get("reintentos_input", 3)

    # ── VALIDACIÓN DINÁMICA ───────────────────────────────────────────────────

    def _validar_campo(self, campo, valor):
        """
        Valida un campo según su tipo y validadores.
        Retorna True si válido, o string con mensaje de error.
        """
        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        validadores = config_campo.get("validadores", [])
        config_validadores = self._get_config_validadores()
        es_obligatorio = config_campo.get("obligatorio", True)

        # Campo no obligatorio: '-' se acepta como vacío
        if not es_obligatorio and valor.strip() == "-":
            return True

        # Tipo catálogo: se resuelve aparte (resolver_entidad)
        if tipo == "catalogo":
            return True

        # Tipo base
        if tipo == "texto":
            if not valor.strip():
                return False
        elif tipo == "numero":
            if not valor.strip().isdigit():
                return False

        # Validadores adicionales
        for nombre_v in validadores:
            config_v = config_validadores.get(nombre_v, {})
            if not config_v:
                continue
            tipo_v = config_v.get("tipo")

            if tipo_v == "longitud_minima":
                if len(valor.strip()) < config_v.get("parametro", 3):
                    return config_v.get("msj_error", "⚠️ Dato inválido.")
            elif tipo_v == "longitud_maxima":
                if len(valor.strip()) > config_v.get("parametro", 50):
                    return config_v.get("msj_error", "⚠️ Dato inválido.")

        return True

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en el flujo de obra social."""
        campo = getattr(sesiones[self.numero], "os_estado", None)
        return campo is not None

    def iniciar(self, sesiones, beneficiario_id):
        """
        Punto de entrada. Busca asociaciones del beneficiario y decide el flujo.
        """
        sesiones[self.numero].os_beneficiario_id = beneficiario_id
        asociaciones = self.os_manager.buscar_por_persona(beneficiario_id)

        if not asociaciones:
            # 0 registros → carga directa
            self._iniciar_carga(sesiones)
            return

        if len(asociaciones) == 1:
            # 1 registro → detalle + opciones
            sesiones[self.numero].os_asociacion_id = asociaciones[0]["asociacion_id"]
            sesiones[self.numero].os_estado = "menu_acciones"
            self.sw.enviar(self._armar_detalle_y_opciones(asociaciones[0]))
            return

        # N registros → listar para seleccionar
        sesiones[self.numero].os_estado = "seleccion_os"
        sesiones[self.numero].os_lista = asociaciones
        self.sw.enviar(self._armar_lista_obras_sociales(asociaciones))

    def procesar(self, comando, sesiones):
        """Dispatcher según estado actual."""
        estado = getattr(sesiones[self.numero], "os_estado", None)

        if estado == "seleccion_os":
            self._procesar_seleccion_os(comando, sesiones)
        elif estado == "menu_acciones":
            self._procesar_menu_acciones(comando, sesiones)
        elif estado == "carga_campo":
            self._procesar_carga_campo(comando, sesiones)
        elif estado == "confirmar_eliminar":
            self._procesar_confirmar_eliminar(comando, sesiones)
        elif estado == "actualizar_seleccion":
            self._procesar_actualizar_seleccion(comando, sesiones)
        elif estado == "actualizar_valor":
            self._procesar_actualizar_valor(comando, sesiones)

    # ── LISTADO Y SELECCIÓN ───────────────────────────────────────────────────

    def _armar_lista_obras_sociales(self, asociaciones):
        """Arma la lista de obras sociales para selección."""
        lineas = ["🏥 *Obras sociales registradas:*\n"]
        for i, a in enumerate(asociaciones, 1):
            lineas.append(f"{i}. {a['entidad']} — Nro: {a['numero']}")
        lineas.append("\nIngresá el número para ver detalle,")
        lineas.append("*nuevo* para agregar otra")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    def _procesar_seleccion_os(self, comando, sesiones):
        """Procesa la selección de una obra social de la lista."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        if comando.strip().lower() == "nuevo":
            self._iniciar_carga(sesiones)
            return

        asociaciones = getattr(sesiones[self.numero], "os_lista", [])
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(asociaciones):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        seleccion = asociaciones[indice]
        sesiones[self.numero].os_asociacion_id = seleccion["asociacion_id"]
        sesiones[self.numero].os_estado = "menu_acciones"
        self.sw.enviar(self._armar_detalle_y_opciones(seleccion))

    # ── DETALLE Y ACCIONES ────────────────────────────────────────────────────

    def _armar_detalle_y_opciones(self, asociacion):
        """Muestra detalle dinámico de la obra social con opciones."""
        campos = self._get_campos()
        lineas = ["🏥 *Detalle de obra social:*\n"]

        for campo, config in campos.items():
            label = config.get("label", campo.capitalize())
            valor = asociacion.get(campo, "")
            valor_display = valor if valor else "No especificado"
            lineas.append(f"📋 {label}: {valor_display}")

        lineas.append("")
        lineas.append("1. ✏️ Actualizar datos")
        lineas.append("2. 🗑️ Eliminar")
        lineas.append("3. ➕ Agregar otra obra social")
        lineas.append("Escribí *cancelar* para volver:")
        return "\n".join(lineas)

    def _procesar_menu_acciones(self, comando, sesiones):
        """Procesa las acciones sobre una obra social seleccionada."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        if comando.strip() == "1":
            self._iniciar_actualizar(sesiones)
        elif comando.strip() == "2":
            sesiones[self.numero].os_estado = "confirmar_eliminar"
            sesiones[self.numero].os_reintentos = 0
            self.sw.enviar("¿Confirmás que querés eliminar esta obra social?\nRespondé *si* o *no*:")
        elif comando.strip() == "3":
            self._iniciar_carga(sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    # ── CARGA DINÁMICA ────────────────────────────────────────────────────────

    def _iniciar_carga(self, sesiones):
        """Inicia la carga del primer campo."""
        campos = self._get_campos_ordenados()
        if not campos:
            self.sw.enviar("❌ No hay campos configurados para obra social.")
            self._salir(sesiones)
            return

        sesiones[self.numero].os_estado = "carga_campo"
        sesiones[self.numero].os_datos = {}
        sesiones[self.numero].os_campo_actual = campos[0]
        sesiones[self.numero].os_reintentos = 0

        self.sw.enviar("🏥 Vamos a registrar tu obra social.\n")
        self._pedir_campo(campos[0])

    def _pedir_campo(self, campo):
        """Envía el mensaje de pedido para un campo, adaptado al tipo."""
        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")

        if tipo == "catalogo":
            # Mostrar destacadas + opción texto libre
            destacadas = self.os_manager.get_destacadas()
            lineas = [config_campo.get("msj_pedido", f"Seleccioná {campo}:"), ""]
            for i, nombre in enumerate(destacadas, 1):
                lineas.append(f"{i}. {nombre}")
            lineas.append("\nSi no está en la lista, escribí el nombre para buscar.")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá {campo}:"))

    def _procesar_carga_campo(self, comando, sesiones):
        """Procesa la respuesta del usuario para el campo actual en carga."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        campo = getattr(sesiones[self.numero], "os_campo_actual", None)
        if not campo:
            self._salir(sesiones)
            return

        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "os_reintentos", 0)

        # Resolver valor según tipo
        if tipo == "catalogo":
            valor, es_valido = self._resolver_catalogo(comando, sesiones)
            if valor is None:
                return  # Esperando más input o error manejado
            if es_valido == "nueva":
                self.sw.enviar(f"📝 Se registrará *{valor}* como nueva obra social.")
        else:
            # Campo no obligatorio: '-' como vacío
            es_obligatorio = config_campo.get("obligatorio", True)
            if not es_obligatorio and comando.strip() == "-":
                valor = ""
            else:
                resultado = self._validar_campo(campo, comando)
                if resultado is not True:
                    reintentos += 1
                    sesiones[self.numero].os_reintentos = reintentos
                    if reintentos >= reintentos_max:
                        self.sw.enviar("❌ Se canceló la operación.")
                        self._salir(sesiones)
                    else:
                        msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:")
                        self.sw.enviar(msj)
                    return
                valor = comando.strip()

        # Guardar y avanzar
        sesiones[self.numero].os_datos[campo] = valor
        sesiones[self.numero].os_reintentos = 0
        self._siguiente_campo(campo, sesiones)

    def _siguiente_campo(self, campo_actual, sesiones):
        """Avanza al siguiente campo o finaliza la carga."""
        campos = self._get_campos_ordenados()
        idx = campos.index(campo_actual)

        if idx + 1 < len(campos):
            siguiente = campos[idx + 1]
            sesiones[self.numero].os_campo_actual = siguiente
            self._pedir_campo(siguiente)
        else:
            self._finalizar_carga(sesiones)

    def _finalizar_carga(self, sesiones):
        """Crea la asociación con los datos recolectados."""
        datos = sesiones[self.numero].os_datos
        beneficiario_id = getattr(sesiones[self.numero], "os_beneficiario_id", None)

        asociacion_id = self.os_manager.crear_asociacion(
            persona_id=beneficiario_id,
            entidad=datos.get("entidad", ""),
            numero=datos.get("numero", ""),
            plan=datos.get("plan", "")
        )

        if asociacion_id:
            entidad = datos.get("entidad", "")
            numero = datos.get("numero", "")
            self.sw.enviar(f"✅ Obra social *{entidad}* (Nro: {numero}) registrada correctamente.")
        else:
            self.sw.enviar(f"⚠️ Ya tenés registrada *{datos.get('entidad', '')}*.")

        self._salir(sesiones)

    # ── ACTUALIZACIÓN DINÁMICA ────────────────────────────────────────────────

    def _iniciar_actualizar(self, sesiones):
        """Muestra la lista dinámica de campos para elegir cuál actualizar."""
        campos = self._get_campos()
        lineas = ["¿Qué dato querés actualizar?\n"]
        for i, (campo, config) in enumerate(campos.items(), 1):
            label = config.get("label", campo.capitalize())
            lineas.append(f"{i}. {label}")
        lineas.append("\nEscribí *cancelar* para volver:")

        sesiones[self.numero].os_estado = "actualizar_seleccion"
        sesiones[self.numero].os_reintentos = 0
        self.sw.enviar("\n".join(lineas))

    def _procesar_actualizar_seleccion(self, comando, sesiones):
        """Procesa la selección del campo a actualizar."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        campos = self._get_campos_ordenados()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(campos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        campo = campos[indice]
        sesiones[self.numero].os_campo_editar = campo
        sesiones[self.numero].os_estado = "actualizar_valor"
        sesiones[self.numero].os_reintentos = 0
        self._pedir_campo(campo)

    def _procesar_actualizar_valor(self, comando, sesiones):
        """Procesa el nuevo valor para el campo seleccionado."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        campo = getattr(sesiones[self.numero], "os_campo_editar", None)
        asociacion_id = getattr(sesiones[self.numero], "os_asociacion_id", None)
        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "os_reintentos", 0)

        if tipo == "catalogo":
            valor, es_valido = self._resolver_catalogo(comando, sesiones)
            if valor is None:
                return
            if es_valido == "nueva":
                self.sw.enviar(f"📝 Se registrará *{valor}* como nueva obra social.")
        else:
            es_obligatorio = config_campo.get("obligatorio", True)
            if not es_obligatorio and comando.strip() == "-":
                valor = ""
            else:
                resultado = self._validar_campo(campo, comando)
                if resultado is not True:
                    reintentos += 1
                    sesiones[self.numero].os_reintentos = reintentos
                    if reintentos >= reintentos_max:
                        self.sw.enviar("❌ Se canceló la operación.")
                        self._salir(sesiones)
                    else:
                        msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido.")
                        self.sw.enviar(msj)
                    return
                valor = comando.strip()

        self.os_manager.editar_asociacion(asociacion_id, campo, valor)
        label = config_campo.get("label", campo.capitalize())
        self.sw.enviar(f"✅ *{label}* actualizado correctamente.")
        self._salir(sesiones)

    # ── ELIMINAR ──────────────────────────────────────────────────────────────

    def _procesar_confirmar_eliminar(self, comando, sesiones):
        """Procesa la confirmación de eliminación."""
        if comando.strip() == "si":
            asociacion_id = getattr(sesiones[self.numero], "os_asociacion_id", None)
            if asociacion_id:
                asociacion = self.os_manager.get_asociacion(asociacion_id)
                self.os_manager.borrar_asociacion(asociacion_id)
                if asociacion:
                    self.sw.enviar(f"✅ Obra social *{asociacion[1]['entidad']}* eliminada correctamente.")
                else:
                    self.sw.enviar("✅ Obra social eliminada correctamente.")
            self._salir(sesiones)
        elif comando.strip() == "no":
            self.sw.enviar("❌ Eliminación cancelada.")
            self._salir(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "os_reintentos", 0) + 1
            sesiones[self.numero].os_reintentos = reintentos
            reintentos_max = self._get_reintentos_max()
            if reintentos >= reintentos_max:
                self.sw.enviar("❌ Se canceló la operación.")
                self._salir(sesiones)
            else:
                self.sw.enviar("⚠️ Respondé *si* o *no*:")

    # ── RESOLVER CATÁLOGO ─────────────────────────────────────────────────────

    def _resolver_catalogo(self, comando, sesiones):
        """
        Resuelve selección de catálogo: número de destacada, búsqueda, o nueva.
        Retorna (valor, tipo) donde tipo es "existente", "nueva", o (None, None) si falla.
        """
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "os_reintentos", 0)
        destacadas = self.os_manager.get_destacadas()

        # Resolver coincidencias pendientes
        coincidencias = getattr(sesiones[self.numero], "os_datos", {}).get("_coincidencias")
        if coincidencias:
            try:
                idx = int(comando.strip()) - 1
                if 0 <= idx < len(coincidencias):
                    sesiones[self.numero].os_datos.pop("_coincidencias", None)
                    return (coincidencias[idx], "existente")
            except ValueError:
                pass
            self.sw.enviar("❌ Opción no válida. Ingresá el número de la opción:")
            return (None, None)

        entidad, es_nueva = self.os_manager.resolver_entidad(comando, destacadas)

        if entidad is None:
            # Múltiples coincidencias
            coincidencias = self.os_manager.buscar_en_catalogo(comando)
            if coincidencias:
                lineas = ["Se encontraron varias coincidencias:\n"]
                for i, c in enumerate(coincidencias, 1):
                    lineas.append(f"{i}. {c}")
                lineas.append("\nIngresá el número de la opción:")
                if not hasattr(sesiones[self.numero], "os_datos") or sesiones[self.numero].os_datos is None:
                    sesiones[self.numero].os_datos = {}
                sesiones[self.numero].os_datos["_coincidencias"] = coincidencias
                self.sw.enviar("\n".join(lineas))
                return (None, None)
            else:
                reintentos += 1
                sesiones[self.numero].os_reintentos = reintentos
                if reintentos >= reintentos_max:
                    self.sw.enviar("❌ Se canceló la operación.")
                    self._salir(sesiones)
                else:
                    self.sw.enviar("⚠️ Nombre no válido (mín. 3 caracteres). Intentá nuevamente:")
                return (None, None)

        return (entidad, "nueva" if es_nueva else "existente")

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _salir(self, sesiones):
        """Limpia estado del flujo de obra social."""
        sesiones[self.numero].os_estado = None
        sesiones[self.numero].os_beneficiario_id = None
        sesiones[self.numero].os_asociacion_id = None
        sesiones[self.numero].os_datos = {}
        sesiones[self.numero].os_campo_actual = None
        sesiones[self.numero].os_campo_editar = None
        sesiones[self.numero].os_lista = None
        sesiones[self.numero].os_reintentos = 0