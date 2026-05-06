# src/auxilios/gestion_conductores.py
from src.send_wpp import SendWPP
from src.sesiones.session_manager import SessionManager
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader
from src.persona.persona_manager import PersonaManager
from src.registro.validadores import Validadores
from src.persona import telefono_manager
from src.config_loader import ConfigLoader

class GestionConductores(Validadores):
    """
    Gestiona el flujo completo de conductores.
    Responsabilidades:
        - Listar conductores
        - Agregar conductor con validación campo a campo
        - Eliminar conductor
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = AuxiliosConfigLoader()
        self.personas = PersonaManager()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)
        return campo is not None and campo.startswith("conductor_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el listado de conductores."""
        sesiones[self.numero].auxilios_campo_actual = "conductor_menu"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}
        self.sw.enviar(self._armar_menu_conductores())

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)

        if campo == "conductor_menu":
            self._procesar_seleccion(comando, sesiones)
        elif campo == "conductor_confirmar_elimina":
            self._procesar_confirmacion_elimina(comando, sesiones)
        elif campo == "conductor_telefono_confirmar":
            self._procesar_conductor_telefono_confirmar(comando, sesiones)
        elif campo == "conductor_telefono_pais":
            self._procesar_conductor_telefono_pais(comando, sesiones)
        elif campo == "conductor_telefono_pais_iso":
            self._procesar_conductor_telefono_pais_iso(comando, sesiones)
        elif campo and campo.startswith("conductor_agregar_"):
            self._procesar_campo(comando, sesiones)

    # ── MENÚ ──────────────────────────────────────────────────────────────────

    def _armar_menu_conductores(self):
        conductores = self.personas.buscar_por_tipo_persona("auxilio_conductor")

        if not conductores:
            return (
                "👤 No hay conductores registrados.\n"
                "Ingresá *nuevo* para agregar uno\n"
                "o *cancelar* para volver:"
            )

        lineas = ["👤 *Conductores registrados:*\n"]
        for i, (pid, c) in enumerate(conductores, 1):
            nombre = f"{c.get('nombre', '')} {c.get('apellido', '')}".strip().title()
            lineas.append(f"{i}. {nombre} - DNI: {c.get('numero_documento', '')}")

        lineas.append("\nIngresá el número para eliminar un conductor,")
        lineas.append("*nuevo* para agregar uno nuevo")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    # ── SELECCIÓN ─────────────────────────────────────────────────────────────

    def _procesar_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].auxilios_campo_actual = None
            self._volver_menu_auxilios(sesiones)
            return

        if comando.strip().lower() == "nuevo":
            self._iniciar_agregar(sesiones)
            return

        conductores = self.personas.buscar_por_tipo_persona("auxilio_conductor")
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(conductores):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        conductor_id, conductor_datos = conductores[indice]
        nombre = f"{conductor_datos.get('nombre', '')} {conductor_datos.get('apellido', '')}".strip().title()
        sesiones[self.numero].auxilios_dato_temporal = {"_persona_id": conductor_id, "_nombre": nombre}
        sesiones[self.numero].auxilios_campo_actual = "conductor_confirmar_elimina"
        self.sw.enviar(
            f"¿Confirmás que querés eliminar al conductor "
            f"*{nombre}*?\n"
            f"Respondé *si* o *no*:"
        )

    # ── AGREGAR (campo a campo dinámico) ──────────────────────────────────────

    def _get_campos_ordenados(self):
        """Retorna los campos del conductor en orden."""
        campos = self.config.get_campos("conductor")
        return list(campos.keys())

    def _iniciar_agregar(self, sesiones):
        """Inicia el flujo de carga del primer campo."""
        campos = self._get_campos_ordenados()
        if not campos:
            self.sw.enviar("❌ No hay campos configurados para conductor.")
            self.iniciar(sesiones)
            return

        primer_campo = campos[0]
        sesiones[self.numero].auxilios_campo_actual = f"conductor_agregar_{primer_campo}"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}

        config_campo = self.config.get_campos("conductor").get(primer_campo, {})
        self.sw.enviar(config_campo.get("msj_pedido", f"Ingresá {primer_campo}:"))

    def _procesar_campo(self, comando, sesiones):
        """Procesa la respuesta del usuario para el campo actual."""
        if comando.strip() == "cancelar":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            sesiones[self.numero].auxilios_reintentos = 0
            self.sw.enviar("❌ Carga cancelada.")
            self.iniciar(sesiones)
            return

        campo_actual = getattr(sesiones[self.numero], "auxilios_campo_actual", "")
        campo = campo_actual.replace("conductor_agregar_", "")
        campos_config = self.config.get_campos("conductor")
        config_campo = campos_config.get(campo, {})

        tipo = config_campo.get("tipo", "texto")
        validadores_campo = config_campo.get("validadores", [])
        es_obligatorio = config_campo.get("obligatorio", True)
        reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0)

        # Campos no obligatorios: aceptamos guión como vacío
        if not es_obligatorio and comando.strip() == "-":
            return self._guardar_campo_y_continuar(campo, "", sesiones)

        # Intercepción especial para teléfono
        if campo == "telefono":
            config_global = ConfigLoader()
            pais_defecto = config_global.get("telefonia", {}).get("pais_defecto", "AR")
            e164 = telefono_manager.parse_e164(comando.strip(), pais_defecto)
            if not e164:
                reintentos += 1
                sesiones[self.numero].auxilios_reintentos = reintentos
                if reintentos >= self.config.data.get("reintentos_input", 3):
                    sesiones[self.numero].auxilios_campo_actual = None
                    sesiones[self.numero].auxilios_dato_temporal = {}
                    sesiones[self.numero].auxilios_reintentos = 0
                    self.sw.enviar("❌ Se canceló la carga. Volviendo al menú de conductores...")
                    self.iniciar(sesiones)
                else:
                    self.sw.enviar("⚠️ Número no reconocido. Ingresá solo el número local (ej: 1155557777):")
                return
            sesiones[self.numero].auxilios_telefono_raw = comando.strip()
            sesiones[self.numero].auxilios_telefono_e164 = e164
            sesiones[self.numero].auxilios_reintentos = 0
            self._mostrar_preview_telefono_conductor(sesiones)
            return

        # Validación estándar
        config_global = ConfigLoader()
        config_validadores = config_global.data.get("validadores", {})
        resultado = self._validar(tipo, comando, validadores_campo, config_validadores)

        if resultado is True:
            sesiones[self.numero].auxilios_reintentos = 0
            return self._guardar_campo_y_continuar(campo, comando.strip(), sesiones)
        else:
            reintentos += 1
            sesiones[self.numero].auxilios_reintentos = reintentos
            if reintentos >= self.config.data.get("reintentos_input", 3):
                sesiones[self.numero].auxilios_campo_actual = None
                sesiones[self.numero].auxilios_dato_temporal = {}
                sesiones[self.numero].auxilios_reintentos = 0
                self.sw.enviar("❌ Se canceló la carga. Volviendo al menú de conductores...")
                self.iniciar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:")
                self.sw.enviar(msj)

    def _guardar_campo_y_continuar(self, campo, valor, sesiones):
        """Guarda el campo en temporal y avanza al siguiente o finaliza."""
        sesiones[self.numero].auxilios_dato_temporal[campo] = valor

        campos = self._get_campos_ordenados()
        idx_actual = campos.index(campo)

        # ¿Hay más campos?
        if idx_actual + 1 < len(campos):
            siguiente = campos[idx_actual + 1]
            sesiones[self.numero].auxilios_campo_actual = f"conductor_agregar_{siguiente}"
            sesiones[self.numero].auxilios_reintentos = 0
            config_siguiente = self.config.get_campos("conductor").get(siguiente, {})
            self.sw.enviar(config_siguiente.get("msj_pedido", f"Ingresá {siguiente}:"))
        else:
            # Todos los campos completos → guardar
            datos = sesiones[self.numero].auxilios_dato_temporal
            nombre = datos.get("nombre", "")
            dni = datos.get("dni", "")
            telefono = datos.get("telefono", "")
            contactos = [{"tipo": "telefono", "valor": telefono, "etiqueta": ""}] if telefono else []
            persona_id = self.personas.crear_persona(
                tipo_documento="DNI",
                numero_documento=dni,
                nombre=nombre,
                apellido="",
                contactos=contactos
            )
            if persona_id:
                self.personas.agregar_tipo_persona(persona_id, "auxilio_conductor")
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            sesiones[self.numero].auxilios_reintentos = 0
            self.sw.enviar(f"✅ Conductor *{nombre}* registrado correctamente.")
            self.iniciar(sesiones)

    # ── ELIMINAR ──────────────────────────────────────────────────────────────

    def _procesar_confirmacion_elimina(self, comando, sesiones):
        if comando.strip() == "si":
            conductor = sesiones[self.numero].auxilios_dato_temporal
            self.personas.borrar_persona(conductor.get("_persona_id"))
            nombre = conductor.get("_nombre", "")
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar(f"✅ Conductor *{nombre}* eliminado correctamente.")
            self.iniciar(sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar("❌ Eliminación cancelada.")
            self.iniciar(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0) + 1
            sesiones[self.numero].auxilios_reintentos = reintentos
            if reintentos >= self.config.data.get("reintentos_input", 3):
                sesiones[self.numero].auxilios_campo_actual = None
                sesiones[self.numero].auxilios_dato_temporal = {}
                sesiones[self.numero].auxilios_reintentos = 0
                self.sw.enviar("❌ Se canceló la operación.")
                self.iniciar(sesiones)
            else:
                self.sw.enviar("⚠️ Respondé *si* o *no*:")

    # ── FLUJO TELÉFONO ────────────────────────────────────────────────────────

    def _mostrar_preview_telefono_conductor(self, sesiones):
        e164 = getattr(sesiones[self.numero], "auxilios_telefono_e164", "")
        display = telefono_manager.format_display(e164)
        lineas = [
            f"📱 {display} — ¿es correcto?\n",
            "1. ✅ Confirmar",
            "2. 🔄 Cambiar número",
            "3. 🌍 Cambiar país",
            "4. ❌ Cancelar"
        ]
        sesiones[self.numero].auxilios_campo_actual = "conductor_telefono_confirmar"
        self.sw.enviar("\n".join(lineas))

    def _procesar_conductor_telefono_confirmar(self, comando, sesiones):
        c = comando.strip()
        if c == "1":
            e164 = getattr(sesiones[self.numero], "auxilios_telefono_e164", "")
            self._guardar_campo_y_continuar("telefono", e164, sesiones)
        elif c == "2":
            config_campo = self.config.get_campos("conductor").get("telefono", {})
            self.sw.enviar(config_campo.get("msj_pedido", "📱 Ingresá el teléfono del conductor:"))
            sesiones[self.numero].auxilios_campo_actual = "conductor_agregar_telefono"
        elif c == "3":
            self._mostrar_lista_paises_conductor(sesiones)
        elif c == "4":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar("❌ Carga cancelada.")
            self.iniciar(sesiones)
        else:
            self.sw.enviar("❌ Opción no válida.")

    def _mostrar_lista_paises_conductor(self, sesiones):
        config_global = ConfigLoader()
        paises = config_global.get("telefonia", {}).get("paises_frecuentes", [])
        lineas = ["🌍 Seleccioná el país:\n"]
        for i, p in enumerate(paises, 1):
            lineas.append(f"{i}. {p['label']}")
        lineas.append(f"{len(paises) + 1}. Otro (escribí el código ISO, ej: DE, IT, MX)")
        sesiones[self.numero].auxilios_campo_actual = "conductor_telefono_pais"
        sesiones[self.numero].auxilios_telefono_paises_lista = paises
        self.sw.enviar("\n".join(lineas))

    def _procesar_conductor_telefono_pais(self, comando, sesiones):
        paises = getattr(sesiones[self.numero], "auxilios_telefono_paises_lista", [])
        c = comando.strip()
        try:
            idx = int(c) - 1
            if idx < 0 or idx > len(paises):
                raise ValueError
            if idx == len(paises):
                self.sw.enviar("Escribí el código ISO del país (ej: DE, IT, MX):")
                sesiones[self.numero].auxilios_campo_actual = "conductor_telefono_pais_iso"
                return
            nuevo_pais = paises[idx]["codigo"]
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return
        self._reparsear_conductor_con_pais(nuevo_pais, sesiones)

    def _procesar_conductor_telefono_pais_iso(self, comando, sesiones):
        codigo = comando.strip().upper()
        if len(codigo) != 2 or not codigo.isalpha():
            self.sw.enviar("⚠️ Código inválido. Ingresá un código ISO de 2 letras (ej: DE, IT, MX):")
            return
        self._reparsear_conductor_con_pais(codigo, sesiones)

    def _reparsear_conductor_con_pais(self, pais, sesiones):
        raw = getattr(sesiones[self.numero], "auxilios_telefono_raw", "")
        e164 = telefono_manager.parse_e164(raw, pais)
        if not e164:
            self.sw.enviar(f"⚠️ El número no es válido para {pais}. Intentá con otro país o cambiá el número.")
            self._mostrar_lista_paises_conductor(sesiones)
            return
        sesiones[self.numero].auxilios_telefono_e164 = e164
        self._mostrar_preview_telefono_conductor(sesiones)

    # ── HELPER ────────────────────────────────────────────────────────────────

    def _volver_menu_auxilios(self, sesiones):
        """Vuelve al menú de auxilios."""
        from src.auxilios.submenu_auxilios import SubMenuAuxilios
        auxilios = SubMenuAuxilios(self.numero)
        auxilios.mostrar_menu(sesiones)