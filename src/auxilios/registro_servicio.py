# src/auxilios/registro_servicio.py
from src.send_wpp import SendWPP
from src.sesiones.session_manager import SessionManager
from src.config_loader import ConfigLoader
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader
from src.auxilios.auxilios_data_loader import AuxiliosDataLoader
from src.auxilios.calculo_tarifas import CalculoTarifas
from src.registro.validadores import Validadores
from src.maps.buscador_direccion import BuscadorDireccion
from src.cliente.persona_manager import PersonaManager
from src.cliente.direccion_manager import DireccionManager
from src.auxilios.vehiculo_manager import VehiculoManager
from datetime import datetime

class RegistroServicio(Validadores):
    """
    Gestiona el flujo completo de registro de un servicio de auxilio.
    Flujo:
        1. nro_movimiento
        2. fecha
        3. conductor (si habilitado: 0→carga, 1→auto, >1→selección)
        4. vehículo propio (si habilitado: 0→carga, 1→auto, >1→selección)
        5. vehículo auxiliado (patente → si existe trae datos, si no pide campos)
        6. recorrido (seleccionar establecido o cargar origen+destino con Maps)
        7. tramos (tipo_camino + km, puede agregar varios)
        8. extras (si hay habilitados)
        9. info_extra (opcional)
        10. confirmación con desglose
        11. guardar
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config_global = ConfigLoader()
        self.config = AuxiliosConfigLoader()
        self.datos = AuxiliosDataLoader()
        self.personas = PersonaManager()
        self.direccion_manager = DireccionManager()
        self.vehiculos = VehiculoManager()
        self.tarifas = CalculoTarifas()
        self.maps = BuscadorDireccion()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)
        return campo is not None and campo.startswith("servicio_")

    def iniciar(self, sesiones):
        """Punto de entrada — arranca pidiendo nro_movimiento."""
        sesiones[self.numero].auxilios_campo_actual = "servicio_nro_movimiento"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {
            "tramos": [],
            "extras": {}
        }
        campos = self.config.get_campos("servicio")
        config_campo = campos.get("nro_movimiento", {})
        self.sw.enviar(config_campo.get("msj_pedido", "🔢 Ingresá el N° de movimiento:"))

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)

        dispatch = {
            "servicio_nro_movimiento": self._procesar_nro_movimiento,
            "servicio_fecha": self._procesar_fecha,
            "servicio_conductor_seleccion": self._procesar_conductor_seleccion,
            "servicio_conductor_carga_nombre": self._procesar_conductor_campo,
            "servicio_conductor_carga_telefono": self._procesar_conductor_campo,
            "servicio_conductor_carga_dni": self._procesar_conductor_campo,
            "servicio_vpropio_seleccion": self._procesar_vpropio_seleccion,
            "servicio_vpropio_carga_patente": self._procesar_vpropio_campo,
            "servicio_vpropio_carga_alias": self._procesar_vpropio_campo,
            "servicio_patente_auxiliado": self._procesar_patente_auxiliado,
            "servicio_ris": self._procesar_ris,
            "servicio_recorrido": self._procesar_recorrido,
            "servicio_origen": self._procesar_origen,
            "servicio_origen_maps_seleccion": self._procesar_origen_maps_seleccion,
            "servicio_destino": self._procesar_destino,
            "servicio_destino_maps_seleccion": self._procesar_destino_maps_seleccion,
            "servicio_tramo_tipo": self._procesar_tramo_tipo,
            "servicio_tramo_km": self._procesar_tramo_km,
            "servicio_tramo_otro": self._procesar_tramo_otro,
            "servicio_extras": self._procesar_extras,
            "servicio_info_extra": self._procesar_info_extra,
            "servicio_confirmar": self._procesar_confirmacion,
        }

        handler = dispatch.get(campo)
        if handler:
            handler(comando, sesiones)

    # ── 1. NRO MOVIMIENTO ─────────────────────────────────────────────────────

    def _procesar_nro_movimiento(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        if self.datos.existe_nro_movimiento(comando.strip()):
            self.sw.enviar("⚠️ Ya existe un servicio con ese N° de movimiento. Ingresá otro:")
            return

        campos = self.config.get_campos("servicio")
        config_campo = campos.get("nro_movimiento", {})
        validadores_campo = config_campo.get("validadores", [])
        config_validadores = self.config_global.data.get("validadores", {})

        tipo = config_campo.get("tipo", "texto")
        resultado = self._validar(tipo, comando, validadores_campo, config_validadores)
        if resultado is True:
            sesiones[self.numero].auxilios_dato_temporal["nro_movimiento"] = comando.strip()
            self._ir_a_fecha(sesiones)
        else:
            self._manejar_reintento(comando, sesiones, config_campo, resultado)

    # ── 2. FECHA ──────────────────────────────────────────────────────────────

    def _ir_a_fecha(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_fecha"
        sesiones[self.numero].auxilios_reintentos = 0
        campos = self.config.get_campos("servicio")
        config_campo = campos.get("fecha", {})
        self.sw.enviar(config_campo.get("msj_pedido", "📅 Ingresá la fecha (DD/MM/AAAA) o *hoy*:"))

    def _procesar_fecha(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        # Atajo "hoy"
        if comando.strip().lower() == "hoy":
            fecha_iso = datetime.now().strftime("%Y-%m-%d")
            sesiones[self.numero].auxilios_dato_temporal["fecha"] = fecha_iso
            self._ir_a_conductor(sesiones)
            return

        campos = self.config.get_campos("servicio")
        config_campo = campos.get("fecha", {})
        validadores_campo = config_campo.get("validadores", [])
        config_validadores = self.config_global.data.get("validadores", {})

        resultado = self._validar("fecha", comando, validadores_campo, config_validadores)
        if resultado is True:
            fecha_iso = datetime.strptime(comando.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            sesiones[self.numero].auxilios_dato_temporal["fecha"] = fecha_iso
            self._ir_a_conductor(sesiones)
        else:
            self._manejar_reintento(comando, sesiones, config_campo, resultado)

    # ── 3. CONDUCTOR ──────────────────────────────────────────────────────────

    def _ir_a_conductor(self, sesiones):
        if not self.config.esta_habilitado("conductor"):
            self._ir_a_vpropio(sesiones)
            return

        conductores = self.personas.buscar_por_tipo_persona("auxilio_conductor")

        if len(conductores) == 0:
            sesiones[self.numero].auxilios_campo_actual = "servicio_conductor_carga_nombre"
            sesiones[self.numero].auxilios_reintentos = 0
            campos_conductor = self.config.get_campos("conductor")
            msj_nombre = campos_conductor.get("nombre", {}).get("msj_pedido", "Ingresá el nombre:")
            self.sw.enviar(
                f"👤 No hay conductores registrados. Vamos a cargar uno.\n\n"
                f"{msj_nombre}"
            )
        elif len(conductores) == 1:
            pid, conductor_datos = conductores[0]
            nombre_display = f"{conductor_datos.get('nombre', '')} {conductor_datos.get('apellido', '')}".strip().title()
            sesiones[self.numero].auxilios_dato_temporal["conductor"] = nombre_display
            self.sw.enviar(f"👤 Conductor: *{nombre_display}*")
            self._ir_a_vpropio(sesiones)
        else:
            sesiones[self.numero].auxilios_campo_actual = "servicio_conductor_seleccion"
            lineas = ["👤 Seleccioná el conductor:\n"]
            for i, (pid, c) in enumerate(conductores, 1):
                nombre_display = f"{c.get('nombre', '')} {c.get('apellido', '')}".strip().title()
                lineas.append(f"{i}. {nombre_display}")
            self.sw.enviar("\n".join(lineas))

    def _procesar_conductor_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        conductores = self.personas.buscar_por_tipo_persona("auxilio_conductor")
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(conductores):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        pid, conductor_datos = conductores[indice]
        nombre_display = f"{conductor_datos.get('nombre', '')} {conductor_datos.get('apellido', '')}".strip().title()
        sesiones[self.numero].auxilios_dato_temporal["conductor"] = nombre_display
        self._ir_a_vpropio(sesiones)

    def _procesar_conductor_campo(self, comando, sesiones):
        """Procesa campos de carga de conductor inline."""
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        campo_actual = getattr(sesiones[self.numero], "auxilios_campo_actual", "")

        if campo_actual == "servicio_conductor_carga_nombre":
            if not self.valida_texto(comando):
                campos_conductor = self.config.get_campos("conductor")
                msj = campos_conductor.get("nombre", {}).get("msj_reintento", "⚠️ Nombre no válido. Intentá nuevamente:")
                self.sw.enviar(msj)
                return
            sesiones[self.numero].auxilios_dato_temporal["_conductor_temp"] = {"nombre": comando.strip()}
            campos_conductor = self.config.get_campos("conductor")
            if "telefono" in campos_conductor:
                sesiones[self.numero].auxilios_campo_actual = "servicio_conductor_carga_telefono"
                config = campos_conductor["telefono"]
                self.sw.enviar(config.get("msj_pedido", "📱 Ingresá el teléfono:"))
            elif "dni" in campos_conductor:
                sesiones[self.numero].auxilios_campo_actual = "servicio_conductor_carga_dni"
                config = campos_conductor["dni"]
                self.sw.enviar(config.get("msj_pedido", "🪪 Ingresá el DNI:"))
            else:
                self._finalizar_carga_conductor(sesiones)

        elif campo_actual == "servicio_conductor_carga_telefono":
            temp = sesiones[self.numero].auxilios_dato_temporal.get("_conductor_temp", {})
            config_campo = self.config.get_campos("conductor").get("telefono", {})
            es_obligatorio = config_campo.get("obligatorio", False)

            if not es_obligatorio and comando.strip() == "-":
                temp["telefono"] = ""
            elif self.valida_telefono(comando):
                temp["telefono"] = comando.strip()
            else:
                self.sw.enviar("⚠️ Teléfono no válido. Intentá nuevamente:")
                return

            sesiones[self.numero].auxilios_dato_temporal["_conductor_temp"] = temp
            campos_conductor = self.config.get_campos("conductor")
            if "dni" in campos_conductor:
                sesiones[self.numero].auxilios_campo_actual = "servicio_conductor_carga_dni"
                config = campos_conductor["dni"]
                self.sw.enviar(config.get("msj_pedido", "🪪 Ingresá el DNI:"))
            else:
                self._finalizar_carga_conductor(sesiones)

        elif campo_actual == "servicio_conductor_carga_dni":
            temp = sesiones[self.numero].auxilios_dato_temporal.get("_conductor_temp", {})
            if not self.valida_numero(comando):
                campos_conductor = self.config.get_campos("conductor")
                msj = campos_conductor.get("dni", {}).get("msj_reintento", "⚠️ DNI no válido. Ingresá solo números:")
                self.sw.enviar(msj)
                return
            temp["dni"] = comando.strip()
            sesiones[self.numero].auxilios_dato_temporal["_conductor_temp"] = temp
            self._finalizar_carga_conductor(sesiones)

    def _finalizar_carga_conductor(self, sesiones):
        """Guarda el conductor cargado inline y continúa."""
        temp = sesiones[self.numero].auxilios_dato_temporal.pop("_conductor_temp", {})
        nombre = temp.get("nombre", "")
        dni = temp.get("dni", "")
        telefono = temp.get("telefono", "")
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
        sesiones[self.numero].auxilios_dato_temporal["conductor"] = nombre
        self.sw.enviar(f"✅ Conductor *{nombre}* registrado.")
        self._ir_a_vpropio(sesiones)

    # ── 4. VEHÍCULO PROPIO ────────────────────────────────────────────────────

    def _ir_a_vpropio(self, sesiones):
        if not self.config.esta_habilitado("vehiculo_propio"):
            self._ir_a_patente_auxiliado(sesiones)
            return

        vehiculos = self.vehiculos.get_por_tipo("auxilio_propio")

        if len(vehiculos) == 0:
            sesiones[self.numero].auxilios_campo_actual = "servicio_vpropio_carga_patente"
            sesiones[self.numero].auxilios_reintentos = 0
            campos_vpropio = self.config.get_campos("vehiculo_propio")
            msj_patente = campos_vpropio.get("patente", {}).get("msj_pedido", "Ingresá la patente:")
            self.sw.enviar(
                f"🚛 No hay vehículos propios registrados. Vamos a cargar uno.\n\n"
                f"{msj_patente}"
            )
        elif len(vehiculos) == 1:
            vid, v = vehiculos[0]
            alias = v.get("alias", "")
            patente = v.get("patente", "")
            label = f"{patente} ({alias})" if alias else patente
            sesiones[self.numero].auxilios_dato_temporal["vehiculo_propio"] = patente
            self.sw.enviar(f"🚛 Vehículo: *{label}*")
            self._ir_a_patente_auxiliado(sesiones)
        else:
            sesiones[self.numero].auxilios_campo_actual = "servicio_vpropio_seleccion"
            lineas = ["🚛 Seleccioná el vehículo propio:\n"]
            for i, (vid, v) in enumerate(vehiculos, 1):
                alias = v.get("alias", "")
                patente = v.get("patente", "")
                label = f"{patente} ({alias})" if alias else patente
                lineas.append(f"{i}. {label}")
            self.sw.enviar("\n".join(lineas))

    def _procesar_vpropio_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        vehiculos = self.vehiculos.get_por_tipo("auxilio_propio")
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(vehiculos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        vid, v = vehiculos[indice]
        sesiones[self.numero].auxilios_dato_temporal["vehiculo_propio"] = v.get("patente", "")
        self._ir_a_patente_auxiliado(sesiones)

    def _procesar_vpropio_campo(self, comando, sesiones):
        """Procesa campos de carga de vehículo propio inline."""
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        campo_actual = getattr(sesiones[self.numero], "auxilios_campo_actual", "")

        if campo_actual == "servicio_vpropio_carga_patente":
            if len(comando.strip()) < 2:
                self.sw.enviar("⚠️ Patente no válida. Intentá nuevamente:")
                return
            sesiones[self.numero].auxilios_dato_temporal["_vpropio_temp"] = {
                "patente": comando.strip().upper()
            }
            sesiones[self.numero].auxilios_campo_actual = "servicio_vpropio_carga_alias"
            campos_vpropio = self.config.get_campos("vehiculo_propio")
            msj_alias = campos_vpropio.get("alias", {}).get("msj_pedido", "Ingresá un alias:")
            self.sw.enviar(msj_alias)

        elif campo_actual == "servicio_vpropio_carga_alias":
            temp = sesiones[self.numero].auxilios_dato_temporal.get("_vpropio_temp", {})
            temp["alias"] = "" if comando.strip() == "-" else comando.strip()
            self.vehiculos.agregar("auxilio_propio", temp)

            alias = temp.get("alias", "")
            patente = temp.get("patente", "")
            label = f"{patente} ({alias})" if alias else patente

            sesiones[self.numero].auxilios_dato_temporal.pop("_vpropio_temp", None)
            sesiones[self.numero].auxilios_dato_temporal["vehiculo_propio"] = patente
            self.sw.enviar(f"✅ Vehículo *{label}* registrado.")
            self._ir_a_patente_auxiliado(sesiones)

    # ── 5. VEHÍCULO AUXILIADO ─────────────────────────────────────────────────

    def _ir_a_patente_auxiliado(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_patente_auxiliado"
        sesiones[self.numero].auxilios_reintentos = 0
        campos = self.config.get_campos("vehiculo_auxiliado")
        config_campo = campos.get("patente", {})
        self.sw.enviar(config_campo.get("msj_pedido", "🚗 Ingresá la patente del vehículo auxiliado:"))

    def _procesar_patente_auxiliado(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        if len(comando.strip()) < 2:
            self.sw.enviar("⚠️ Patente no válida. Intentá nuevamente:")
            return

        patente = comando.strip().upper()
        existente = self.vehiculos.buscar_por_patente(patente, tipo="auxilio_auxiliado")

        if existente:
            vid, existente_datos = existente
            ris = existente_datos.get("ris", "")
            sesiones[self.numero].auxilios_dato_temporal["vehiculo_auxiliado"] = {
                "patente": patente,
                "ris": ris
            }
            ris_display = ris.replace("_", " ").capitalize()
            self.sw.enviar(f"🚗 Vehículo *{patente}* encontrado — RIS: *{ris_display}*")
            self._ir_a_recorrido(sesiones)
        else:
            sesiones[self.numero].auxilios_dato_temporal["vehiculo_auxiliado"] = {"patente": patente}
            # Si la patente existe bajo otro tipo, guardamos su ID para no duplicar el registro
            existente_otro = self.vehiculos.buscar_por_patente(patente)
            if existente_otro:
                sesiones[self.numero].auxilios_dato_temporal["_vehiculo_auxiliado_id"] = existente_otro[0]
            self._ir_a_ris(sesiones)

    # ── 5b. RIS (solo si vehículo auxiliado nuevo) ────────────────────────────

    def _ir_a_ris(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_ris"
        sesiones[self.numero].auxilios_reintentos = 0
        campos = self.config.get_campos("vehiculo_auxiliado")
        config_campo = campos.get("ris", {})
        self.sw.enviar(config_campo.get("msj_pedido", "⚖️ Seleccioná la categoría RIS:"))

    def _procesar_ris(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        opciones_ris = {"1": "liviano", "2": "semi_pesado", "3": "pesado"}
        ris = opciones_ris.get(comando.strip())

        if not ris:
            self.sw.enviar("⚠️ Opción no válida. Elegí 1, 2 o 3:")
            return

        va = sesiones[self.numero].auxilios_dato_temporal["vehiculo_auxiliado"]
        va["ris"] = ris

        # Si la patente ya existe bajo otro tipo, agregar auxilio_auxiliado al registro existente
        vehiculo_id_existente = sesiones[self.numero].auxilios_dato_temporal.pop("_vehiculo_auxiliado_id", None)
        if vehiculo_id_existente:
            self.vehiculos.agregar_tipo(vehiculo_id_existente, "auxilio_auxiliado")
            self.vehiculos.actualizar_campo(vehiculo_id_existente, "ris", ris)
        else:
            self.vehiculos.agregar("auxilio_auxiliado", {"patente": va["patente"], "ris": ris})

        self._ir_a_recorrido(sesiones)

    # ── 6. RECORRIDO ──────────────────────────────────────────────────────────

    def _ir_a_recorrido(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_recorrido"
        sesiones[self.numero].auxilios_reintentos = 0

        recorridos = self.config.get_recorridos_establecidos()

        if recorridos:
            lineas = ["🛣️ Seleccioná un recorrido o ingresá *manual*:\n"]
            for i, r in enumerate(recorridos, 1):
                lineas.append(f"{i}. {r['origen']} → {r['destino']} ({r['km']}km)")
            lineas.append("\nO escribí *manual* para cargar origen y destino:")
            self.sw.enviar("\n".join(lineas))
        else:
            # Sin recorridos establecidos → directo a manual
            self._ir_a_origen(sesiones)

    def _procesar_recorrido(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        if comando.strip().lower() == "manual":
            self._ir_a_origen(sesiones)
            return

        recorridos = self.config.get_recorridos_establecidos()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(recorridos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        r = recorridos[indice]
        sesiones[self.numero].auxilios_dato_temporal["origen"] = r["origen"]
        sesiones[self.numero].auxilios_dato_temporal["destino"] = r["destino"]
        self._ir_a_tramo_tipo(sesiones)

    # ── 6b. ORIGEN CON MAPS ──────────────────────────────────────────────────

    def _ir_a_origen(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_origen"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal["_maps_resultados"] = []

        puntos = self.config.get_puntos_frecuentes()
        msj_maps = self.maps.get_mensaje("pedido_direccion")

        if puntos:
            lineas = ["📍 *Origen* — Elegí de la lista o ingresá una dirección:\n"]
            for i, p in enumerate(puntos, 1):
                lineas.append(f"{i}. {p}")
            lineas.append(f"\n{msj_maps}")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(f"📍 *Origen*\n\n{msj_maps}")

    def _procesar_origen(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        # Intentar resolver como punto frecuente (número de lista)
        punto = self._resolver_punto_frecuente(comando)
        if punto:
            sesiones[self.numero].auxilios_dato_temporal["origen"] = punto
            self._ir_a_destino(sesiones)
            return

        # Detectar tipo de input
        tipo_input = self.maps.detectar_tipo_input(comando)

        if tipo_input == "coordenadas":
            resultado = self.maps.resolver_coordenadas(comando)
            if resultado:
                sesiones[self.numero].auxilios_dato_temporal["_maps_resultados"] = [resultado]
                sesiones[self.numero].auxilios_campo_actual = "servicio_origen_maps_seleccion"
                self.sw.enviar(self.maps.armar_mensaje_unico(resultado))
            else:
                self.sw.enviar(self.maps.get_mensaje("geocoding_error"))
            return

        # Texto libre → buscar en Maps
        resultados = self.maps.buscar(comando)
        if resultados:
            sesiones[self.numero].auxilios_dato_temporal["_maps_resultados"] = resultados
            sesiones[self.numero].auxilios_campo_actual = "servicio_origen_maps_seleccion"
            if len(resultados) == 1:
                self.sw.enviar(self.maps.armar_mensaje_unico(resultados[0]))
            else:
                self.sw.enviar(self.maps.armar_mensaje_opciones(resultados))
        else:
            self._manejar_reintento_maps(sesiones, "origen")

    def _procesar_origen_maps_seleccion(self, comando, sesiones):
        """Procesa la selección del usuario sobre resultados de Maps para origen."""
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        resultados = sesiones[self.numero].auxilios_dato_temporal.get("_maps_resultados", [])

        # "si" confirma resultado único
        if comando.strip().lower() == "si" and len(resultados) >= 1:
            self._seleccionar_direccion_origen(resultados[0], sesiones)
            return

        # Número de selección
        try:
            indice = int(comando.strip()) - 1
            if 0 <= indice < len(resultados):
                self._seleccionar_direccion_origen(resultados[indice], sesiones)
                return
        except ValueError:
            pass

        # Si no es número ni "si", es una nueva búsqueda
        sesiones[self.numero].auxilios_campo_actual = "servicio_origen"
        self._procesar_origen(comando, sesiones)

    def _seleccionar_direccion_origen(self, direccion, sesiones):
        """Guarda la dirección seleccionada como origen y avanza a destino."""
        sesiones[self.numero].auxilios_dato_temporal["origen"] = direccion
        sesiones[self.numero].auxilios_dato_temporal.pop("_maps_resultados", None)
        self.sw.enviar(f"✅ Origen: {direccion['direccion_formateada']}")
        self._ir_a_destino(sesiones)

    # ── 6c. DESTINO CON MAPS ─────────────────────────────────────────────────

    def _ir_a_destino(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_destino"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal["_maps_resultados"] = []

        puntos = self.config.get_puntos_frecuentes()
        msj_maps = self.maps.get_mensaje("pedido_direccion")

        if puntos:
            lineas = ["📍 *Destino* — Elegí de la lista o ingresá una dirección:\n"]
            for i, p in enumerate(puntos, 1):
                lineas.append(f"{i}. {p}")
            lineas.append(f"\n{msj_maps}")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(f"📍 *Destino*\n\n{msj_maps}")

    def _procesar_destino(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        # Intentar resolver como punto frecuente
        punto = self._resolver_punto_frecuente(comando)
        if punto:
            # Validar que no sea igual al origen
            origen = sesiones[self.numero].auxilios_dato_temporal.get("origen", "")
            origen_str = origen if isinstance(origen, str) else origen.get("direccion_formateada", "")
            if punto.lower() == origen_str.lower():
                self.sw.enviar("⚠️ El destino no puede ser igual al origen. Intentá nuevamente:")
                return
            sesiones[self.numero].auxilios_dato_temporal["destino"] = punto
            self._ir_a_tramo_tipo(sesiones)
            return

        # Detectar tipo de input
        tipo_input = self.maps.detectar_tipo_input(comando)

        if tipo_input == "coordenadas":
            resultado = self.maps.resolver_coordenadas(comando)
            if resultado:
                sesiones[self.numero].auxilios_dato_temporal["_maps_resultados"] = [resultado]
                sesiones[self.numero].auxilios_campo_actual = "servicio_destino_maps_seleccion"
                self.sw.enviar(self.maps.armar_mensaje_unico(resultado))
            else:
                self.sw.enviar(self.maps.get_mensaje("geocoding_error"))
            return

        # Texto libre → buscar en Maps
        resultados = self.maps.buscar(comando)
        if resultados:
            sesiones[self.numero].auxilios_dato_temporal["_maps_resultados"] = resultados
            sesiones[self.numero].auxilios_campo_actual = "servicio_destino_maps_seleccion"
            if len(resultados) == 1:
                self.sw.enviar(self.maps.armar_mensaje_unico(resultados[0]))
            else:
                self.sw.enviar(self.maps.armar_mensaje_opciones(resultados))
        else:
            self._manejar_reintento_maps(sesiones, "destino")

    def _procesar_destino_maps_seleccion(self, comando, sesiones):
        """Procesa la selección del usuario sobre resultados de Maps para destino."""
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        resultados = sesiones[self.numero].auxilios_dato_temporal.get("_maps_resultados", [])

        # "si" confirma resultado único
        if comando.strip().lower() == "si" and len(resultados) >= 1:
            self._seleccionar_direccion_destino(resultados[0], sesiones)
            return

        # Número de selección
        try:
            indice = int(comando.strip()) - 1
            if 0 <= indice < len(resultados):
                self._seleccionar_direccion_destino(resultados[indice], sesiones)
                return
        except ValueError:
            pass

        # Si no es número ni "si", es una nueva búsqueda
        sesiones[self.numero].auxilios_campo_actual = "servicio_destino"
        self._procesar_destino(comando, sesiones)

    def _seleccionar_direccion_destino(self, direccion, sesiones):
        """Guarda la dirección seleccionada como destino y avanza a tramos."""
        # Validar que no sea igual al origen
        origen = sesiones[self.numero].auxilios_dato_temporal.get("origen", "")
        if isinstance(origen, dict):
            origen_str = origen.get("direccion_formateada", "")
        else:
            origen_str = origen
        if direccion["direccion_formateada"].lower() == origen_str.lower():
            self.sw.enviar("⚠️ El destino no puede ser igual al origen. Intentá nuevamente:")
            return

        sesiones[self.numero].auxilios_dato_temporal["destino"] = direccion
        sesiones[self.numero].auxilios_dato_temporal.pop("_maps_resultados", None)
        self.sw.enviar(f"✅ Destino: {direccion['direccion_formateada']}")
        self._ir_a_tramo_tipo(sesiones)

    # ── HELPERS MAPS ──────────────────────────────────────────────────────────

    def _resolver_punto_frecuente(self, comando):
        """
        Si el comando es un número válido de la lista de puntos frecuentes,
        retorna el punto. Si no, retorna None (para que siga el flujo de Maps).
        """
        puntos = self.config.get_puntos_frecuentes()
        if not puntos:
            return None
        try:
            indice = int(comando.strip()) - 1
            if 0 <= indice < len(puntos):
                return puntos[indice]
        except ValueError:
            pass
        return None

    def _manejar_reintento_maps(self, sesiones, contexto):
        """Maneja reintentos cuando Maps no encuentra resultados."""
        reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0) + 1
        sesiones[self.numero].auxilios_reintentos = reintentos
        reintentos_max = self.config.data.get("reintentos_input", 3)

        if reintentos >= reintentos_max:
            self._cancelar(sesiones)
        elif reintentos >= 2:
            # Al 2do reintento, sugerimos formato entre calles
            self.sw.enviar(self.maps.get_mensaje("sin_resultados_fallback"))
        else:
            self.sw.enviar(self.maps.get_mensaje("sin_resultados"))

    # ── 7. TRAMOS ─────────────────────────────────────────────────────────────

    def _ir_a_tramo_tipo(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_tramo_tipo"
        sesiones[self.numero].auxilios_reintentos = 0

        tipos = self.config.get_tipos_camino()
        lineas = ["🛣️ Seleccioná el *tipo de camino* del tramo:\n"]
        for i, t in enumerate(tipos, 1):
            lineas.append(f"{i}. {t['nombre'].capitalize()}")
        self.sw.enviar("\n".join(lineas))

    def _procesar_tramo_tipo(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        tipos = self.config.get_tipos_camino()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(tipos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        tipo = tipos[indice]
        sesiones[self.numero].auxilios_dato_temporal["_tramo_actual"] = {
            "tipo_camino": tipo["nombre"]
        }
        sesiones[self.numero].auxilios_campo_actual = "servicio_tramo_km"
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar(f"📏 Ingresá los *km* de {tipo['nombre']}:")

    def _procesar_tramo_km(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        try:
            km = int(comando.strip())
            if km <= 0:
                raise ValueError
        except ValueError:
            self.sw.enviar("⚠️ Ingresá un número válido mayor a 0:")
            return

        tramo = sesiones[self.numero].auxilios_dato_temporal.pop("_tramo_actual", {})
        tramo["km"] = km
        sesiones[self.numero].auxilios_dato_temporal["tramos"].append(tramo)

        # ¿Otro tramo?
        sesiones[self.numero].auxilios_campo_actual = "servicio_tramo_otro"
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar("¿Agregar otro tramo? Respondé *si* o *no*:")

    def _procesar_tramo_otro(self, comando, sesiones):
        if comando.strip() == "si":
            self._ir_a_tramo_tipo(sesiones)
        elif comando.strip() == "no":
            self._ir_a_extras(sesiones)
        else:
            self.sw.enviar("⚠️ Respondé *si* o *no*:")

    # ── 8. EXTRAS ─────────────────────────────────────────────────────────────

    def _ir_a_extras(self, sesiones):
        extras_habilitados = self.config.get_tarifas_extras_habilitadas()

        if not extras_habilitados:
            self._ir_a_info_extra(sesiones)
            return

        sesiones[self.numero].auxilios_campo_actual = "servicio_extras"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal["_extras_pendientes"] = list(extras_habilitados.keys())
        self._preguntar_extra_siguiente(sesiones)

    def _preguntar_extra_siguiente(self, sesiones):
        pendientes = sesiones[self.numero].auxilios_dato_temporal.get("_extras_pendientes", [])

        if not pendientes:
            sesiones[self.numero].auxilios_dato_temporal.pop("_extras_pendientes", None)
            self._ir_a_info_extra(sesiones)
            return

        extra = pendientes[0]
        label = extra.replace("_", " ").capitalize()
        self.sw.enviar(f"➕ ¿Aplica *{label}*? Respondé *si* o *no*:")

    def _procesar_extras(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        pendientes = sesiones[self.numero].auxilios_dato_temporal.get("_extras_pendientes", [])
        if not pendientes:
            self._ir_a_info_extra(sesiones)
            return

        extra_actual = pendientes[0]

        if comando.strip() == "si":
            sesiones[self.numero].auxilios_dato_temporal["extras"][extra_actual] = True
        elif comando.strip() == "no":
            sesiones[self.numero].auxilios_dato_temporal["extras"][extra_actual] = False
        else:
            self.sw.enviar("⚠️ Respondé *si* o *no*:")
            return

        # Avanzar al siguiente extra
        pendientes.pop(0)
        sesiones[self.numero].auxilios_dato_temporal["_extras_pendientes"] = pendientes
        self._preguntar_extra_siguiente(sesiones)

    # ── 9. INFO EXTRA ─────────────────────────────────────────────────────────

    def _ir_a_info_extra(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_info_extra"
        sesiones[self.numero].auxilios_reintentos = 0
        campos = self.config.get_campos("servicio")
        config_campo = campos.get("info_extra", {})
        self.sw.enviar(config_campo.get("msj_pedido", "📝 ¿Info extra? (o *-* para omitir):"))

    def _procesar_info_extra(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        info = "" if comando.strip() == "-" else comando.strip()
        sesiones[self.numero].auxilios_dato_temporal["info_extra"] = info
        self._ir_a_confirmacion(sesiones)

    # ── 10. CONFIRMACIÓN ──────────────────────────────────────────────────────

    def _ir_a_confirmacion(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = "servicio_confirmar"
        sesiones[self.numero].auxilios_reintentos = 0

        datos = sesiones[self.numero].auxilios_dato_temporal
        ris = datos.get("vehiculo_auxiliado", {}).get("ris", "liviano")

        # Calcular tarifas
        resultado = self.tarifas.calcular(ris, datos.get("tramos", []), datos.get("extras", {}))
        sesiones[self.numero].auxilios_dato_temporal["_calculo"] = resultado

        # Armar resumen
        fecha_display = datetime.strptime(datos["fecha"], "%Y-%m-%d").strftime("%d/%m/%Y")
        va = datos.get("vehiculo_auxiliado", {})
        ris_display = va.get("ris", "").replace("_", " ").capitalize()

        # Resolver display de origen/destino (puede ser string o dict de Maps)
        origen_display = self._display_direccion(datos.get("origen", ""))
        destino_display = self._display_direccion(datos.get("destino", ""))

        lineas = ["📋 *Resumen del servicio:*\n"]
        lineas.append(f"🔢 N° Movimiento: *{datos.get('nro_movimiento', '')}*")
        lineas.append(f"📅 Fecha: *{fecha_display}*")

        if datos.get("conductor"):
            lineas.append(f"👤 Conductor: *{datos['conductor']}*")
        if datos.get("vehiculo_propio"):
            lineas.append(f"🚛 Grúa: *{datos['vehiculo_propio']}*")

        lineas.append(f"🚗 Auxiliado: *{va.get('patente', '')}* ({ris_display})")
        lineas.append(f"📍 Recorrido: *{origen_display} → {destino_display}*")

        if datos.get("info_extra"):
            lineas.append(f"📝 Info extra: {datos['info_extra']}")

        lineas.append("")
        lineas.append(self.tarifas.generar_desglose(resultado))
        lineas.append("\n¿Confirmás el registro? Respondé *si* o *no*:")

        self.sw.enviar("\n".join(lineas))

    def _procesar_confirmacion(self, comando, sesiones):
        if comando.strip() == "si":
            self._guardar_servicio(sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar("❌ Registro cancelado.")
            self._volver_menu_auxilios(sesiones)
        else:
            reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0) + 1
            sesiones[self.numero].auxilios_reintentos = reintentos
            if reintentos >= self.config.data.get("reintentos_input", 3):
                sesiones[self.numero].auxilios_campo_actual = None
                sesiones[self.numero].auxilios_dato_temporal = {}
                sesiones[self.numero].auxilios_reintentos = 0
                self.sw.enviar("❌ Se canceló la operación.")
                self._volver_menu_auxilios(sesiones)
            else:
                self.sw.enviar("⚠️ Respondé *si* o *no*:")

    # ── 11. GUARDAR ───────────────────────────────────────────────────────────

    def _guardar_servicio(self, sesiones):
        datos = sesiones[self.numero].auxilios_dato_temporal
        calculo = datos.pop("_calculo", {})

        # Si origen/destino vienen de Maps (dict con place_id), normalizar a direccion_id.
        # Si es string (punto frecuente como "Salliquelo"), dejar como está.
        origen = datos.get("origen", "")
        if isinstance(origen, dict) and origen.get("place_id"):
            origen = {"direccion_id": self.direccion_manager.guardar_desde_maps(origen)}

        destino = datos.get("destino", "")
        if isinstance(destino, dict) and destino.get("place_id"):
            destino = {"direccion_id": self.direccion_manager.guardar_desde_maps(destino)}

        servicio = {
            "timestamp": datetime.now().isoformat(),
            "nro_movimiento": datos.get("nro_movimiento", ""),
            "fecha": datos.get("fecha", ""),
            "conductor": datos.get("conductor", ""),
            "vehiculo_propio": datos.get("vehiculo_propio", ""),
            "vehiculo_auxiliado": datos.get("vehiculo_auxiliado", {}),
            "origen": origen,
            "destino": destino,
            "tramos": calculo.get("tramos", {}).get("detalle", []),
            "movida": calculo.get("movida", {}),
            "extras": calculo.get("extras", {}).get("detalle", []),
            "info_extra": datos.get("info_extra", ""),
            "total": calculo.get("total", 0)
        }

        self.datos.agregar_servicio(servicio)

        sesiones[self.numero].auxilios_campo_actual = None
        sesiones[self.numero].auxilios_dato_temporal = {}
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar("✅ Servicio registrado correctamente.")
        self._volver_menu_auxilios(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _display_direccion(self, direccion):
        """Retorna string de display para origen/destino (string, dict Maps, o {direccion_id})."""
        if isinstance(direccion, dict):
            if "direccion_id" in direccion:
                result = self.direccion_manager.get(direccion["direccion_id"])
                return result[1].get("direccion_formateada", "") if result else ""
            return direccion.get("direccion_formateada", "")
        return direccion

    def _manejar_reintento(self, comando, sesiones, config_campo, resultado):
        """Maneja reintentos con mensaje de error."""
        reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0) + 1
        sesiones[self.numero].auxilios_reintentos = reintentos
        reintentos_max = self.config.data.get("reintentos_input", 3)

        if reintentos >= reintentos_max:
            self._cancelar(sesiones)
        else:
            msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:")
            self.sw.enviar(msj)

    def _cancelar(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = None
        sesiones[self.numero].auxilios_dato_temporal = {}
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar("❌ Registro cancelado.")
        self._volver_menu_auxilios(sesiones)

    def _volver_menu_auxilios(self, sesiones):
        """Vuelve al menú de auxilios."""
        from src.auxilios.submenu_auxilios import SubMenuAuxilios
        auxilios = SubMenuAuxilios(self.numero)
        auxilios.mostrar_menu(sesiones)