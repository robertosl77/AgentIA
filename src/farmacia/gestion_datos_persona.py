# src/farmacia/gestion_datos_persona.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.cliente.persona_manager import PersonaManager


class GestionDatosPersona:
    """
    Flujo conversacional dinámico para completar/editar datos de persona.
    Campos simples se leen de configuracion.json (estructura_sesion.persona).
    Contactos se gestionan como CRUD aparte (agregar/eliminar).
    """

    SECCION = "persona"
    # Campos simples (excluye contactos que tienen flujo propio)
    CAMPO_CONTACTOS = "contactos"

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.persona_manager = PersonaManager()

    # ── CONFIGURACIÓN DINÁMICA ────────────────────────────────────────────────

    def _get_campos(self):
        """Retorna el dict de campos simples (sin contactos)."""
        todos = self.config.data.get("estructura_sesion", {}).get(self.SECCION, {})
        return {k: v for k, v in todos.items() if k != self.CAMPO_CONTACTOS}

    def _get_campos_ordenados(self):
        """Retorna la lista de nombres de campos simples en orden."""
        return list(self._get_campos().keys())

    def _get_config_campo(self, campo):
        """Retorna la config de un campo específico."""
        return self._get_campos().get(campo, {})

    def _get_config_contactos(self):
        """Retorna la config de la subestructura contactos."""
        return self.config.data.get("estructura_sesion", {}).get(self.SECCION, {}).get(self.CAMPO_CONTACTOS, {})

    def _get_config_validadores(self):
        """Retorna el catálogo de validadores globales."""
        return self.config.data.get("validadores", {})

    def _get_reintentos_max(self):
        return self.config.data.get("estructura_sesion", {}).get("reintentos_input", 3)

    # ── VALIDACIÓN ────────────────────────────────────────────────────────────

    def _validar_campo(self, campo, valor, config_campo=None):
        """Valida un campo según tipo y validadores. Retorna True o msj_error."""
        if config_campo is None:
            config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        validadores = config_campo.get("validadores", [])
        config_validadores = self._get_config_validadores()

        # Tipo catálogo
        if tipo == "catalogo":
            catalogo_nombre = config_campo.get("catalogo", "")
            catalogo = self.persona_manager.data.get(catalogo_nombre, [])
            try:
                idx = int(valor.strip()) - 1
                if 0 <= idx < len(catalogo):
                    return True
            except ValueError:
                pass
            return False

        # Tipo base
        if tipo == "texto":
            if not valor.strip() or not all(c.isalpha() or c.isspace() for c in valor.strip()):
                return False
        elif tipo == "numero":
            if not valor.strip().isdigit():
                return False
        elif tipo == "fecha":
            from datetime import datetime
            try:
                datetime.strptime(valor.strip(), "%d/%m/%Y")
            except ValueError:
                return False
        elif tipo == "telefono":
            v = valor.strip()
            if not v.isdigit() or len(v) < 8:
                return False
        elif tipo == "email":
            v = valor.strip()
            if "@" not in v or "." not in v.split("@")[-1]:
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
            elif tipo_v == "fecha_pasada":
                from datetime import datetime
                try:
                    f = datetime.strptime(valor.strip(), "%d/%m/%Y")
                    if f >= datetime.now():
                        return config_v.get("msj_error", "⚠️ La fecha debe ser pasada.")
                except ValueError:
                    return False

        return True

    def _resolver_catalogo(self, campo, valor):
        """Resuelve valor de catálogo. Retorna el valor real o None."""
        config_campo = self._get_config_campo(campo)
        catalogo_nombre = config_campo.get("catalogo", "")
        catalogo = self.persona_manager.data.get(catalogo_nombre, [])
        try:
            idx = int(valor.strip()) - 1
            if 0 <= idx < len(catalogo):
                return catalogo[idx]
        except ValueError:
            pass
        return None

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        """Retorna True si el usuario está en el flujo de datos persona."""
        campo = getattr(sesiones[self.numero], "dp_estado", None)
        return campo is not None

    def iniciar(self, sesiones, beneficiario_id):
        """Punto de entrada — muestra resumen de datos y opciones."""
        sesiones[self.numero].dp_beneficiario_id = beneficiario_id
        sesiones[self.numero].dp_estado = "menu_principal"
        sesiones[self.numero].dp_reintentos = 0
        self.sw.enviar(self._armar_resumen(beneficiario_id))

    def procesar(self, comando, sesiones):
        """Dispatcher según estado."""
        estado = getattr(sesiones[self.numero], "dp_estado", None)

        if estado == "menu_principal":
            self._procesar_menu_principal(comando, sesiones)
        elif estado == "editar_seleccion":
            self._procesar_editar_seleccion(comando, sesiones)
        elif estado == "editar_valor":
            self._procesar_editar_valor(comando, sesiones)
        elif estado == "contactos_menu":
            self._procesar_contactos_menu(comando, sesiones)
        elif estado == "contacto_tipo":
            self._procesar_contacto_tipo(comando, sesiones)
        elif estado == "contacto_valor":
            self._procesar_contacto_valor(comando, sesiones)
        elif estado == "contacto_etiqueta":
            self._procesar_contacto_etiqueta(comando, sesiones)
        elif estado == "contacto_confirmar_eliminar":
            self._procesar_contacto_confirmar_eliminar(comando, sesiones)

    # ── RESUMEN ───────────────────────────────────────────────────────────────

    def _armar_resumen(self, beneficiario_id):
        """Arma el resumen dinámico de datos de la persona."""
        persona = self.persona_manager.get_persona(beneficiario_id)
        if not persona:
            return "⚠️ No se encontró la persona."

        datos = persona[1]
        campos = self._get_campos()
        contactos = datos.get("contactos", [])

        lineas = ["📋 *Datos registrados:*\n"]

        for campo, config in campos.items():
            label = config.get("label", campo.capitalize())
            valor = datos.get(campo, "")
            if valor:
                lineas.append(f"  {label}: {valor} ✅")
            else:
                lineas.append(f"  {label}: — ❌")

        # Contactos
        cant = len(contactos)
        if cant > 0:
            lineas.append(f"  📇 Contactos: {cant} registrado(s) ✅")
        else:
            lineas.append(f"  📇 Contactos: ninguno ❌")

        lineas.append("")
        lineas.append("1. ✏️ Editar un campo")
        lineas.append("2. 📇 Gestionar contactos")
        lineas.append("Escribí *cancelar* para volver:")
        return "\n".join(lineas)

    def _procesar_menu_principal(self, comando, sesiones):
        """Procesa opción del menú principal de datos."""
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        if comando.strip() == "1":
            self._iniciar_editar(sesiones)
        elif comando.strip() == "2":
            self._iniciar_contactos(sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    # ── EDITAR CAMPOS SIMPLES ─────────────────────────────────────────────────

    def _iniciar_editar(self, sesiones):
        """Muestra lista dinámica de campos para editar."""
        campos = self._get_campos()
        beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)
        persona = self.persona_manager.get_persona(beneficiario_id)
        datos = persona[1] if persona else {}

        lineas = ["¿Qué dato querés editar?\n"]
        for i, (campo, config) in enumerate(campos.items(), 1):
            label = config.get("label", campo.capitalize())
            valor = datos.get(campo, "")
            estado = f"({valor})" if valor else "(vacío)"
            lineas.append(f"{i}. {label} {estado}")
        lineas.append("\nEscribí *cancelar* para volver:")

        sesiones[self.numero].dp_estado = "editar_seleccion"
        sesiones[self.numero].dp_reintentos = 0
        self.sw.enviar("\n".join(lineas))

    def _procesar_editar_seleccion(self, comando, sesiones):
        """Procesa selección del campo a editar."""
        if comando.strip() == "cancelar":
            beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)
            sesiones[self.numero].dp_estado = "menu_principal"
            self.sw.enviar(self._armar_resumen(beneficiario_id))
            return

        campos = self._get_campos_ordenados()
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(campos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        campo = campos[idx]
        sesiones[self.numero].dp_campo_editar = campo
        sesiones[self.numero].dp_estado = "editar_valor"
        sesiones[self.numero].dp_reintentos = 0
        self._pedir_campo(campo)

    def _pedir_campo(self, campo):
        """Envía el mensaje de pedido adaptado al tipo."""
        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")

        if tipo == "catalogo":
            catalogo_nombre = config_campo.get("catalogo", "")
            catalogo = self.persona_manager.data.get(catalogo_nombre, [])
            lineas = [config_campo.get("msj_pedido", f"Seleccioná {campo}:"), ""]
            for i, item in enumerate(catalogo, 1):
                lineas.append(f"{i}. {item}")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá {campo}:"))

    def _procesar_editar_valor(self, comando, sesiones):
        """Procesa el nuevo valor para el campo seleccionado."""
        if comando.strip() == "cancelar":
            beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)
            sesiones[self.numero].dp_estado = "menu_principal"
            self.sw.enviar(self._armar_resumen(beneficiario_id))
            return

        campo = getattr(sesiones[self.numero], "dp_campo_editar", None)
        config_campo = self._get_config_campo(campo)
        tipo = config_campo.get("tipo", "texto")
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "dp_reintentos", 0)
        beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)

        # Validar
        resultado = self._validar_campo(campo, comando)
        if resultado is not True:
            reintentos += 1
            sesiones[self.numero].dp_reintentos = reintentos
            if reintentos >= reintentos_max:
                self.sw.enviar("❌ Se canceló la operación.")
                sesiones[self.numero].dp_estado = "menu_principal"
                self.sw.enviar(self._armar_resumen(beneficiario_id))
            else:
                msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido.")
                self.sw.enviar(msj)
            return

        # Resolver valor
        if tipo == "catalogo":
            valor = self._resolver_catalogo(campo, comando)
            if not valor:
                self.sw.enviar(config_campo.get("msj_reintento", "⚠️ Opción no válida."))
                return
        else:
            valor = comando.strip()

        # Verificar duplicado si es documento
        if campo == "numero_documento":
            persona_actual = self.persona_manager.get_persona(beneficiario_id)
            tipo_doc = persona_actual[1].get("tipo_documento", "DNI") if persona_actual else "DNI"
            existente = self.persona_manager.buscar_por_documento(tipo_doc, valor)
            if existente and existente[0] != beneficiario_id:
                nombre = self.persona_manager.get_nombre_completo(existente[0]) or "otra persona"
                self.sw.enviar(
                    f"⚠️ Ya existe un registro con ese documento ({nombre}). "
                    f"No se puede asignar el mismo documento a dos personas."
                )
                sesiones[self.numero].dp_estado = "menu_principal"
                self.sw.enviar(self._armar_resumen(beneficiario_id))
                return

        # Persistir
        self.persona_manager.editar_campo(beneficiario_id, campo, valor)
        label = config_campo.get("label", campo.capitalize())
        self.sw.enviar(f"✅ *{label}* actualizado correctamente.")

        sesiones[self.numero].dp_estado = "menu_principal"
        self.sw.enviar(self._armar_resumen(beneficiario_id))

    # ── GESTIÓN DE CONTACTOS ──────────────────────────────────────────────────

    def _iniciar_contactos(self, sesiones):
        """Muestra lista de contactos con opciones."""
        beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)
        contactos = self.persona_manager.get_contactos(beneficiario_id)

        sesiones[self.numero].dp_estado = "contactos_menu"
        sesiones[self.numero].dp_contactos_lista = contactos
        self.sw.enviar(self._armar_menu_contactos(contactos))

    def _armar_menu_contactos(self, contactos):
        """Arma la lista de contactos con opciones."""
        if not contactos:
            return (
                "📇 No hay contactos registrados.\n"
                "Ingresá *nuevo* para agregar uno\n"
                "o *cancelar* para volver:"
            )

        lineas = ["📇 *Contactos registrados:*\n"]
        for i, c in enumerate(contactos, 1):
            icono = "📱" if c["tipo"] == "telefono" else "📧"
            etiqueta = f" ({c['etiqueta']})" if c.get("etiqueta") else ""
            lineas.append(f"{i}. {icono} {c['tipo']}: {c['valor']}{etiqueta}")

        lineas.append("\nIngresá el número para eliminar,")
        lineas.append("*nuevo* para agregar uno nuevo")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    def _procesar_contactos_menu(self, comando, sesiones):
        """Procesa comandos del menú de contactos."""
        if comando.strip() == "cancelar":
            beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)
            sesiones[self.numero].dp_estado = "menu_principal"
            self.sw.enviar(self._armar_resumen(beneficiario_id))
            return

        if comando.strip().lower() == "nuevo":
            self._iniciar_agregar_contacto(sesiones)
            return

        # Eliminar por número
        contactos = getattr(sesiones[self.numero], "dp_contactos_lista", [])
        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(contactos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        contacto = contactos[idx]
        sesiones[self.numero].dp_contacto_eliminar = contacto
        sesiones[self.numero].dp_estado = "contacto_confirmar_eliminar"
        sesiones[self.numero].dp_reintentos = 0
        icono = "📱" if contacto["tipo"] == "telefono" else "📧"
        self.sw.enviar(
            f"¿Confirmás que querés eliminar el contacto "
            f"{icono} {contacto['tipo']}: {contacto['valor']}?\n"
            f"Respondé *si* o *no*:"
        )

    # ── AGREGAR CONTACTO ──────────────────────────────────────────────────────

    def _iniciar_agregar_contacto(self, sesiones):
        """Inicia el flujo de agregar contacto — pide tipo."""
        config_contactos = self._get_config_contactos()
        config_tipo = config_contactos.get("tipo_contacto", {})
        catalogo_nombre = config_tipo.get("catalogo", "catalogo_tipo_contacto")
        catalogo = self.persona_manager.data.get(catalogo_nombre, [])

        lineas = [config_tipo.get("msj_pedido", "Seleccioná el tipo de contacto:"), ""]
        for i, item in enumerate(catalogo, 1):
            lineas.append(f"{i}. {item}")

        sesiones[self.numero].dp_estado = "contacto_tipo"
        sesiones[self.numero].dp_contacto_datos = {}
        sesiones[self.numero].dp_reintentos = 0
        self.sw.enviar("\n".join(lineas))

    def _procesar_contacto_tipo(self, comando, sesiones):
        """Procesa selección de tipo de contacto."""
        if comando.strip() == "cancelar":
            self._iniciar_contactos(sesiones)
            return

        config_contactos = self._get_config_contactos()
        config_tipo = config_contactos.get("tipo_contacto", {})
        catalogo_nombre = config_tipo.get("catalogo", "catalogo_tipo_contacto")
        catalogo = self.persona_manager.data.get(catalogo_nombre, [])
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "dp_reintentos", 0)

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(catalogo):
                raise ValueError
            tipo_contacto = catalogo[idx]
        except ValueError:
            reintentos += 1
            sesiones[self.numero].dp_reintentos = reintentos
            if reintentos >= reintentos_max:
                self.sw.enviar("❌ Se canceló la operación.")
                self._iniciar_contactos(sesiones)
            else:
                self.sw.enviar(config_tipo.get("msj_reintento", "⚠️ Opción no válida."))
            return

        sesiones[self.numero].dp_contacto_datos["tipo"] = tipo_contacto
        sesiones[self.numero].dp_estado = "contacto_valor"
        sesiones[self.numero].dp_reintentos = 0

        # Pedir valor con mensaje específico al tipo
        config_valor = config_contactos.get("valor", {})
        validadores_tipo = config_valor.get("validadores_por_tipo", {}).get(tipo_contacto, {})
        msj = validadores_tipo.get("msj_pedido", f"Ingresá el {tipo_contacto}:")
        self.sw.enviar(msj)

    def _procesar_contacto_valor(self, comando, sesiones):
        """Procesa valor del contacto con validación dinámica según tipo."""
        if comando.strip() == "cancelar":
            self._iniciar_contactos(sesiones)
            return

        tipo_contacto = sesiones[self.numero].dp_contacto_datos.get("tipo", "")
        config_contactos = self._get_config_contactos()
        config_valor = config_contactos.get("valor", {})
        validadores_tipo = config_valor.get("validadores_por_tipo", {}).get(tipo_contacto, {})
        tipo_base = validadores_tipo.get("tipo_base", "texto")
        reintentos_max = self._get_reintentos_max()
        reintentos = getattr(sesiones[self.numero], "dp_reintentos", 0)

        # Validar según tipo base
        resultado = self._validar_campo(None, comando, {"tipo": tipo_base, "validadores": validadores_tipo.get("validadores", [])})

        if resultado is not True:
            reintentos += 1
            sesiones[self.numero].dp_reintentos = reintentos
            if reintentos >= reintentos_max:
                self.sw.enviar("❌ Se canceló la operación.")
                self._iniciar_contactos(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else validadores_tipo.get("msj_reintento", "⚠️ Dato inválido.")
                self.sw.enviar(msj)
            return

        sesiones[self.numero].dp_contacto_datos["valor"] = comando.strip()
        sesiones[self.numero].dp_estado = "contacto_etiqueta"
        sesiones[self.numero].dp_reintentos = 0

        config_etiqueta = config_contactos.get("etiqueta", {})
        self.sw.enviar(config_etiqueta.get("msj_pedido", "Ingresá una etiqueta o '-' para omitir:"))

    def _procesar_contacto_etiqueta(self, comando, sesiones):
        """Procesa etiqueta y crea el contacto."""
        if comando.strip() == "cancelar":
            self._iniciar_contactos(sesiones)
            return

        etiqueta = "" if comando.strip() == "-" else comando.strip()

        # Validar longitud si hay validadores
        config_contactos = self._get_config_contactos()
        config_etiqueta = config_contactos.get("etiqueta", {})
        if etiqueta:
            resultado = self._validar_campo(None, etiqueta, config_etiqueta)
            if resultado is not True:
                reintentos = getattr(sesiones[self.numero], "dp_reintentos", 0) + 1
                sesiones[self.numero].dp_reintentos = reintentos
                if reintentos >= self._get_reintentos_max():
                    self.sw.enviar("❌ Se canceló la operación.")
                    self._iniciar_contactos(sesiones)
                else:
                    msj = resultado if isinstance(resultado, str) else config_etiqueta.get("msj_reintento", "⚠️ Dato inválido.")
                    self.sw.enviar(msj)
                return

        datos = sesiones[self.numero].dp_contacto_datos
        beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)

        ok = self.persona_manager.agregar_contacto(
            persona_id=beneficiario_id,
            tipo=datos["tipo"],
            valor=datos["valor"],
            etiqueta=etiqueta
        )

        if ok:
            icono = "📱" if datos["tipo"] == "telefono" else "📧"
            self.sw.enviar(f"✅ Contacto {icono} {datos['valor']} agregado correctamente.")
        else:
            self.sw.enviar(f"⚠️ Ya existe un contacto con ese tipo y valor.")

        self._iniciar_contactos(sesiones)

    # ── ELIMINAR CONTACTO ─────────────────────────────────────────────────────

    def _procesar_contacto_confirmar_eliminar(self, comando, sesiones):
        """Procesa confirmación de eliminación de contacto."""
        if comando.strip() == "si":
            contacto = getattr(sesiones[self.numero], "dp_contacto_eliminar", None)
            beneficiario_id = getattr(sesiones[self.numero], "dp_beneficiario_id", None)
            if contacto and beneficiario_id:
                self.persona_manager.quitar_contacto(
                    persona_id=beneficiario_id,
                    tipo=contacto["tipo"],
                    valor=contacto["valor"]
                )
                self.sw.enviar(f"✅ Contacto eliminado correctamente.")
            self._iniciar_contactos(sesiones)
        elif comando.strip() == "no":
            self.sw.enviar("❌ Eliminación cancelada.")
            self._iniciar_contactos(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "dp_reintentos", 0) + 1
            sesiones[self.numero].dp_reintentos = reintentos
            if reintentos >= self._get_reintentos_max():
                self.sw.enviar("❌ Se canceló la operación.")
                self._iniciar_contactos(sesiones)
            else:
                self.sw.enviar("⚠️ Respondé *si* o *no*:")

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _salir(self, sesiones):
        """Limpia estado del flujo."""
        sesiones[self.numero].dp_estado = None
        sesiones[self.numero].dp_beneficiario_id = None
        sesiones[self.numero].dp_campo_editar = None
        sesiones[self.numero].dp_contacto_datos = {}
        sesiones[self.numero].dp_contacto_eliminar = None
        sesiones[self.numero].dp_contactos_lista = None
        sesiones[self.numero].dp_reintentos = 0