# src/auxilios/gestion_vehiculos_auxiliados.py
from src.send_wpp import SendWPP
from src.sesiones.session_manager import SessionManager
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader
from src.auxilios.vehiculo_manager import VehiculoManager
from src.registro.validadores import Validadores

class GestionVehiculosAuxiliados(Validadores):
    """
    Gestiona el flujo completo de vehículos auxiliados.
    Responsabilidades:
        - Listar vehículos auxiliados registrados
        - Agregar vehículo con validación campo a campo
        - Eliminar vehículo
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = AuxiliosConfigLoader()
        self.vehiculos = VehiculoManager()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)
        return campo is not None and campo.startswith("vauxiliado_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el listado de vehículos auxiliados."""
        sesiones[self.numero].auxilios_campo_actual = "vauxiliado_menu"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}
        self.sw.enviar(self._armar_menu_vehiculos())

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)

        if campo == "vauxiliado_menu":
            self._procesar_seleccion(comando, sesiones)
        elif campo == "vauxiliado_confirmar_elimina":
            self._procesar_confirmacion_elimina(comando, sesiones)
        elif campo and campo.startswith("vauxiliado_agregar_"):
            self._procesar_campo(comando, sesiones)

    # ── MENÚ ──────────────────────────────────────────────────────────────────

    def _armar_menu_vehiculos(self):
        vehiculos = self.vehiculos.get_por_tipo("auxilio_auxiliado")

        if not vehiculos:
            return (
                "🚗 No hay vehículos auxiliados registrados.\n"
                "Ingresá *nuevo* para agregar uno\n"
                "o *cancelar* para volver:"
            )

        lineas = ["🚗 *Vehículos auxiliados registrados:*\n"]
        for i, (vid, v) in enumerate(vehiculos, 1):
            patente = v.get("patente", "")
            ris = v.get("ris", "").replace("_", " ").capitalize()
            lineas.append(f"{i}. {patente} — {ris}")

        lineas.append("\nIngresá el número para eliminar un vehículo,")
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

        vehiculos = self.vehiculos.get_por_tipo("auxilio_auxiliado")
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(vehiculos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        vehiculo_id, vehiculo_datos = vehiculos[indice]
        patente = vehiculo_datos.get("patente", "")
        ris = vehiculo_datos.get("ris", "").replace("_", " ").capitalize()
        sesiones[self.numero].auxilios_dato_temporal = {
            "_vehiculo_id": vehiculo_id,
            "patente": patente,
            "ris": vehiculo_datos.get("ris", "")
        }
        sesiones[self.numero].auxilios_campo_actual = "vauxiliado_confirmar_elimina"
        self.sw.enviar(
            f"¿Confirmás que querés eliminar el vehículo "
            f"*{patente}* ({ris})?\n"
            f"Respondé *si* o *no*:"
        )

    # ── AGREGAR (campo a campo dinámico) ──────────────────────────────────────

    def _get_campos_ordenados(self):
        """Retorna los campos del vehículo auxiliado en orden."""
        campos = self.config.get_campos("vehiculo_auxiliado")
        return list(campos.keys())

    def _iniciar_agregar(self, sesiones):
        """Inicia el flujo de carga del primer campo."""
        campos = self._get_campos_ordenados()
        if not campos:
            self.sw.enviar("❌ No hay campos configurados para vehículo auxiliado.")
            self.iniciar(sesiones)
            return

        primer_campo = campos[0]
        sesiones[self.numero].auxilios_campo_actual = f"vauxiliado_agregar_{primer_campo}"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}

        config_campo = self.config.get_campos("vehiculo_auxiliado").get(primer_campo, {})
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
        campo = campo_actual.replace("vauxiliado_agregar_", "")
        campos_config = self.config.get_campos("vehiculo_auxiliado")
        config_campo = campos_config.get(campo, {})

        tipo = config_campo.get("tipo", "texto")
        reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0)

        if tipo == "opcion":
            opciones = config_campo.get("opciones", [])
            try:
                indice = int(comando.strip()) - 1
                if indice < 0 or indice >= len(opciones):
                    raise ValueError
                valor = opciones[indice]
            except ValueError:
                reintentos += 1
                sesiones[self.numero].auxilios_reintentos = reintentos
                if reintentos >= self.config.data.get("reintentos_input", 3):
                    sesiones[self.numero].auxilios_campo_actual = None
                    sesiones[self.numero].auxilios_dato_temporal = {}
                    sesiones[self.numero].auxilios_reintentos = 0
                    self.sw.enviar("❌ Se canceló la carga. Volviendo al menú...")
                    self.iniciar(sesiones)
                else:
                    self.sw.enviar(config_campo.get("msj_reintento", "⚠️ Opción no válida."))
                return

            sesiones[self.numero].auxilios_reintentos = 0
            return self._guardar_campo_y_continuar(campo, valor, sesiones)

        if campo == "patente":
            if self.vehiculos.buscar_por_patente(comando.strip(), tipo="auxilio_auxiliado"):
                self.sw.enviar(f"⚠️ Ya existe un vehículo con la patente *{comando.strip().upper()}*.")
                self.iniciar(sesiones)
                return

        validadores_campo = config_campo.get("validadores", [])
        from src.config_loader import ConfigLoader
        config_global = ConfigLoader()
        config_validadores = config_global.data.get("validadores", {})
        resultado = self._validar(tipo, comando, validadores_campo, config_validadores)

        if resultado is True:
            sesiones[self.numero].auxilios_reintentos = 0
            valor = comando.strip().upper() if campo == "patente" else comando.strip()
            return self._guardar_campo_y_continuar(campo, valor, sesiones)
        else:
            reintentos += 1
            sesiones[self.numero].auxilios_reintentos = reintentos
            if reintentos >= self.config.data.get("reintentos_input", 3):
                sesiones[self.numero].auxilios_campo_actual = None
                sesiones[self.numero].auxilios_dato_temporal = {}
                sesiones[self.numero].auxilios_reintentos = 0
                self.sw.enviar("❌ Se canceló la carga. Volviendo al menú...")
                self.iniciar(sesiones)
            else:
                msj = resultado if isinstance(resultado, str) else config_campo.get("msj_reintento", "⚠️ Dato inválido. Intentá nuevamente:")
                self.sw.enviar(msj)

    def _guardar_campo_y_continuar(self, campo, valor, sesiones):
        """Guarda el campo en temporal y avanza al siguiente o finaliza."""
        sesiones[self.numero].auxilios_dato_temporal[campo] = valor

        campos = self._get_campos_ordenados()
        idx_actual = campos.index(campo)

        if idx_actual + 1 < len(campos):
            siguiente = campos[idx_actual + 1]
            sesiones[self.numero].auxilios_campo_actual = f"vauxiliado_agregar_{siguiente}"
            sesiones[self.numero].auxilios_reintentos = 0
            config_siguiente = self.config.get_campos("vehiculo_auxiliado").get(siguiente, {})
            self.sw.enviar(config_siguiente.get("msj_pedido", f"Ingresá {siguiente}:"))
        else:
            datos = sesiones[self.numero].auxilios_dato_temporal
            self.vehiculos.agregar("auxilio_auxiliado", datos)
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            sesiones[self.numero].auxilios_reintentos = 0

            patente = datos.get("patente", "")
            ris = datos.get("ris", "").replace("_", " ").capitalize()
            self.sw.enviar(f"✅ Vehículo *{patente}* ({ris}) registrado correctamente.")
            self.iniciar(sesiones)

    # ── ELIMINAR ──────────────────────────────────────────────────────────────

    def _procesar_confirmacion_elimina(self, comando, sesiones):
        if comando.strip() == "si":
            vehiculo = sesiones[self.numero].auxilios_dato_temporal
            self.vehiculos.borrar(vehiculo.get("_vehiculo_id"))
            patente = vehiculo.get("patente", "")
            ris = vehiculo.get("ris", "").replace("_", " ").capitalize()
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar(f"✅ Vehículo *{patente}* ({ris}) eliminado correctamente.")
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

    # ── HELPER ────────────────────────────────────────────────────────────────

    def _volver_menu_auxilios(self, sesiones):
        """Vuelve al menú de auxilios."""
        from src.auxilios.submenu_auxilios import SubMenuAuxilios
        auxilios = SubMenuAuxilios(self.numero)
        auxilios.mostrar_menu(sesiones)
