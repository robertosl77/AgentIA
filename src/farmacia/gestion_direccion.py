# src/farmacia/gestion_direccion.py
from src.send_wpp import SendWPP
from src.config_loader import ConfigLoader
from src.farmacia.farmacia_config_loader import FarmaciaConfigLoader
from src.cliente.persona_manager import PersonaManager
from src.cliente.direccion_manager import DireccionManager
from src.maps.buscador_direccion import BuscadorDireccion


class GestionDireccion:
    """
    Flujo conversacional para gestionar las direcciones de un beneficiario.
    Usa Maps para resolver la dirección — el usuario escribe texto libre o coordenadas.
    Solo pide piso/depto manualmente (Maps no los conoce).
    Soporta: ver lista, agregar (con deduplicación por place_id), eliminar.
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.config = ConfigLoader()
        self.farmacia_config = FarmaciaConfigLoader()
        self.persona_manager = PersonaManager()
        self.direccion_manager = DireccionManager()
        self.maps = BuscadorDireccion()

    # ── CONFIGURACIÓN ─────────────────────────────────────────────────────────

    def _get_config_campo(self, campo):
        return self.farmacia_config.get_estructura_direccion().get(campo, {})

    def _pedir_campo(self, campo):
        self.sw.enviar(self._get_config_campo(campo).get("msj_pedido", f"Ingresá {campo}:"))

    def _get_mensaje(self, clave, **kwargs):
        msg = self.farmacia_config.get_mensajes_gestion_direccion().get(clave, "")
        return msg.format(**kwargs) if kwargs else msg

    def _get_reintentos_max(self):
        return self.config.data.get("estructura_sesion", {}).get("reintentos_input", 3)

    # ── FLUJO ─────────────────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        return getattr(sesiones[self.numero], "gd_estado", None) is not None

    def iniciar(self, sesiones, beneficiario_id):
        sesiones[self.numero].gd_beneficiario_id = beneficiario_id
        sesiones[self.numero].gd_estado = "menu_principal"
        sesiones[self.numero].gd_reintentos = 0
        self.sw.enviar(self._armar_menu(beneficiario_id))

    def procesar(self, comando, sesiones):
        estado = getattr(sesiones[self.numero], "gd_estado", None)
        dispatch = {
            "menu_principal":        self._proc_menu,
            "agregar_tipo":          self._proc_agregar_tipo,
            "agregar_maps":          self._proc_agregar_maps,
            "agregar_maps_seleccion":  self._proc_agregar_maps_seleccion,
            "agregar_entre_calle_1":  self._proc_agregar_entre_calle_1,
            "agregar_entre_calle_2":  self._proc_agregar_entre_calle_2,
            "agregar_piso":           self._proc_agregar_piso,
            "agregar_depto":          self._proc_agregar_depto,
            "eliminar_seleccion":    self._proc_eliminar_seleccion,
            "eliminar_confirmar":    self._proc_eliminar_confirmar,
        }
        fn = dispatch.get(estado)
        if fn:
            fn(comando, sesiones)

    # ── MENU PRINCIPAL ────────────────────────────────────────────────────────

    def _armar_menu(self, beneficiario_id):
        links = self.persona_manager.get_direcciones(beneficiario_id)
        lineas = [self._get_mensaje("titulo_lista")]

        if not links:
            lineas.append(self._get_mensaje("sin_direcciones"))
        else:
            for i, link in enumerate(links, 1):
                dir_data = self.direccion_manager.get(link["direccion_id"])
                if dir_data:
                    d = dir_data[1]
                    label = d.get("direccion_formateada") or f"{d.get('calle','').title()} {d.get('altura','')}, {d.get('localidad','').title()}"
                    lineas.append(f"{i}. [{link['tipo'].upper()}] {label}")

        lineas.append(self._get_mensaje("opcion_agregar"))
        if links:
            lineas.append(self._get_mensaje("opcion_eliminar"))
        lineas.append(self._get_mensaje("escribi_cancelar"))
        return "\n".join(lineas)

    def _proc_menu(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._salir(sesiones)
            return

        links = self.persona_manager.get_direcciones(
            getattr(sesiones[self.numero], "gd_beneficiario_id")
        )
        if comando.strip() == "1":
            self._iniciar_agregar(sesiones)
        elif comando.strip() == "2" and links:
            self._iniciar_eliminar(sesiones, links)
        else:
            self.sw.enviar(self._get_mensaje("opcion_invalida"))

    # ── AGREGAR — TIPO ────────────────────────────────────────────────────────

    def _iniciar_agregar(self, sesiones):
        catalogo = self.direccion_manager.get_catalogo_tipo()
        lineas = [self._get_mensaje("seleccionar_tipo")]
        for i, tipo in enumerate(catalogo, 1):
            lineas.append(f"{i}. {tipo.capitalize()}")
        lineas.append(self._get_mensaje("escribi_cancelar"))
        sesiones[self.numero].gd_estado = "agregar_tipo"
        sesiones[self.numero].gd_reintentos = 0
        self.sw.enviar("\n".join(lineas))

    def _proc_agregar_tipo(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return

        catalogo = self.direccion_manager.get_catalogo_tipo()
        reintentos = getattr(sesiones[self.numero], "gd_reintentos", 0)

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(catalogo):
                raise ValueError
            tipo = catalogo[idx]
        except ValueError:
            reintentos += 1
            sesiones[self.numero].gd_reintentos = reintentos
            if reintentos >= self._get_reintentos_max():
                self.sw.enviar(self._get_mensaje("operacion_cancelada"))
                sesiones[self.numero].gd_estado = "menu_principal"
                self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            else:
                self.sw.enviar(self._get_mensaje("tipo_invalido"))
            return

        sesiones[self.numero].gd_tipo_nueva = tipo
        sesiones[self.numero].gd_estado = "agregar_maps"
        sesiones[self.numero].gd_reintentos_maps = 0
        self.sw.enviar(self.maps.get_mensaje("pedido_direccion"))

    # ── AGREGAR — MAPS ────────────────────────────────────────────────────────

    def _proc_agregar_maps(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return

        tipo_input = self.maps.detectar_tipo_input(comando)

        if tipo_input == "coordenadas":
            resultado = self.maps.resolver_coordenadas(comando)
            if not resultado:
                self.sw.enviar(self.maps.get_mensaje("geocoding_error"))
                return
            sesiones[self.numero].gd_maps_resultados = [resultado]
            self.sw.enviar(self.maps.armar_mensaje_unico(resultado))
            sesiones[self.numero].gd_estado = "agregar_maps_seleccion"
            return

        resultados = self.maps.buscar(comando)
        reintentos = getattr(sesiones[self.numero], "gd_reintentos_maps", 0)

        if not resultados:
            reintentos += 1
            sesiones[self.numero].gd_reintentos_maps = reintentos
            if reintentos == 1:
                self.sw.enviar(self.maps.get_mensaje("sin_resultados"))
            elif reintentos == 2:
                self.sw.enviar(self.maps.get_mensaje("sin_resultados_fallback"))
            else:
                self.sw.enviar(self._get_mensaje("sin_resultados_cancelado"))
                sesiones[self.numero].gd_estado = "menu_principal"
                self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return

        sesiones[self.numero].gd_maps_resultados = resultados
        sesiones[self.numero].gd_reintentos_maps = 0
        sesiones[self.numero].gd_estado = "agregar_maps_seleccion"

        if len(resultados) == 1:
            self.sw.enviar(self.maps.armar_mensaje_unico(resultados[0]))
        else:
            self.sw.enviar(self.maps.armar_mensaje_opciones(resultados))

    def _proc_agregar_maps_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return

        resultados = getattr(sesiones[self.numero], "gd_maps_resultados", [])
        seleccion = None

        if comando.strip().lower() == "si" and len(resultados) == 1:
            seleccion = resultados[0]
        else:
            try:
                idx = int(comando.strip()) - 1
                if 0 <= idx < len(resultados):
                    seleccion = resultados[idx]
            except ValueError:
                pass

        if seleccion is None:
            # El usuario escribió una nueva dirección — relanzar búsqueda
            sesiones[self.numero].gd_estado = "agregar_maps"
            sesiones[self.numero].gd_reintentos_maps = 0
            self._proc_agregar_maps(comando, sesiones)
            return

        sesiones[self.numero].gd_maps_seleccion = seleccion
        sesiones[self.numero].gd_estado = "agregar_entre_calle_1"
        sesiones[self.numero].gd_reintentos = 0
        self._pedir_campo("entre_calle_1")

    # ── AGREGAR — ENTRE CALLES / PISO / DEPTO ────────────────────────────────

    def _proc_agregar_entre_calle_1(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return
        sesiones[self.numero].gd_entre_calle_1 = "" if comando.strip() == "-" else comando.strip()
        sesiones[self.numero].gd_estado = "agregar_entre_calle_2"
        sesiones[self.numero].gd_reintentos = 0
        self._pedir_campo("entre_calle_2")

    def _proc_agregar_entre_calle_2(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return
        sesiones[self.numero].gd_entre_calle_2 = "" if comando.strip() == "-" else comando.strip()
        sesiones[self.numero].gd_estado = "agregar_piso"
        sesiones[self.numero].gd_reintentos = 0
        self._pedir_campo("piso")

    def _proc_agregar_piso(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return
        sesiones[self.numero].gd_piso = "" if comando.strip() == "-" else comando.strip()
        sesiones[self.numero].gd_estado = "agregar_depto"
        sesiones[self.numero].gd_reintentos = 0
        self._pedir_campo("depto")

    def _proc_agregar_depto(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return
        sesiones[self.numero].gd_depto = "" if comando.strip() == "-" else comando.strip()
        self._finalizar_agregar(sesiones)

    def _finalizar_agregar(self, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "gd_beneficiario_id")
        tipo = getattr(sesiones[self.numero], "gd_tipo_nueva", "casa")
        maps_result = getattr(sesiones[self.numero], "gd_maps_seleccion", {})
        entre_calle_1 = getattr(sesiones[self.numero], "gd_entre_calle_1", "")
        entre_calle_2 = getattr(sesiones[self.numero], "gd_entre_calle_2", "")
        piso = getattr(sesiones[self.numero], "gd_piso", "")
        depto = getattr(sesiones[self.numero], "gd_depto", "")

        componentes = maps_result.get("componentes", {})
        campos = {
            "direccion_formateada": maps_result.get("direccion_formateada", ""),
            "calle":          componentes.get("calle", ""),
            "altura":         componentes.get("altura", ""),
            "entre_calle_1":  entre_calle_1,
            "entre_calle_2":  entre_calle_2,
            "piso":           piso,
            "depto":          depto,
            "localidad":     componentes.get("localidad", ""),
            "codigo_postal": componentes.get("codigo_postal", ""),
            "provincia":     componentes.get("provincia", ""),
            "place_id":      maps_result.get("place_id", ""),
            "coordenadas":   maps_result.get("coordenadas", {"lat": None, "lng": None, "origen": "maps"}),
        }

        existente = self.direccion_manager.buscar_exacta(campos)
        direccion_id = existente[0] if existente else self.direccion_manager.agregar(campos)

        self.persona_manager.agregar_direccion(beneficiario_id, direccion_id, tipo)

        label = campos["direccion_formateada"] or f"{campos['calle'].title()} {campos['altura']}"
        self.sw.enviar(self._get_mensaje("direccion_registrada", label=label, tipo=tipo.upper()))

        sesiones[self.numero].gd_estado = "menu_principal"
        sesiones[self.numero].gd_reintentos = 0
        self.sw.enviar(self._armar_menu(beneficiario_id))

    # ── ELIMINAR ──────────────────────────────────────────────────────────────

    def _iniciar_eliminar(self, sesiones, links):
        lineas = [self._get_mensaje("titulo_eliminar")]
        for i, link in enumerate(links, 1):
            dir_data = self.direccion_manager.get(link["direccion_id"])
            if dir_data:
                d = dir_data[1]
                label = d.get("direccion_formateada") or f"{d.get('calle','').title()} {d.get('altura','')}"
                lineas.append(f"{i}. [{link['tipo'].upper()}] {label}")
        lineas.append(self._get_mensaje("escribi_cancelar"))
        sesiones[self.numero].gd_estado = "eliminar_seleccion"
        sesiones[self.numero].gd_reintentos = 0
        sesiones[self.numero].gd_direcciones_lista = links
        self.sw.enviar("\n".join(lineas))

    def _proc_eliminar_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].gd_estado = "menu_principal"
            self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            return

        links = getattr(sesiones[self.numero], "gd_direcciones_lista", [])
        reintentos = getattr(sesiones[self.numero], "gd_reintentos", 0)

        try:
            idx = int(comando.strip()) - 1
            if idx < 0 or idx >= len(links):
                raise ValueError
        except ValueError:
            reintentos += 1
            sesiones[self.numero].gd_reintentos = reintentos
            if reintentos >= self._get_reintentos_max():
                sesiones[self.numero].gd_estado = "menu_principal"
                self.sw.enviar(self._armar_menu(getattr(sesiones[self.numero], "gd_beneficiario_id")))
            else:
                self.sw.enviar(self._get_mensaje("numero_invalido"))
            return

        link = links[idx]
        sesiones[self.numero].gd_link_eliminar = link
        sesiones[self.numero].gd_estado = "eliminar_confirmar"
        sesiones[self.numero].gd_reintentos = 0

        dir_data = self.direccion_manager.get(link["direccion_id"])
        if dir_data:
            d = dir_data[1]
            label = d.get("direccion_formateada") or f"{d.get('calle','').title()} {d.get('altura','')}"
            self.sw.enviar(self._get_mensaje("confirmar_eliminar", tipo=link['tipo'].upper(), label=label))

    def _proc_eliminar_confirmar(self, comando, sesiones):
        beneficiario_id = getattr(sesiones[self.numero], "gd_beneficiario_id")

        if comando.strip() == "si":
            link = getattr(sesiones[self.numero], "gd_link_eliminar", None)
            if link:
                self.persona_manager.quitar_direccion(
                    beneficiario_id, link["direccion_id"], link["tipo"]
                )
                self.sw.enviar(self._get_mensaje("direccion_eliminada"))
        elif comando.strip() == "no":
            self.sw.enviar(self._get_mensaje("eliminacion_cancelada"))
        else:
            reintentos = getattr(sesiones[self.numero], "gd_reintentos", 0) + 1
            sesiones[self.numero].gd_reintentos = reintentos
            if reintentos < self._get_reintentos_max():
                self.sw.enviar(self._get_mensaje("responder_si_no"))
                return

        sesiones[self.numero].gd_estado = "menu_principal"
        sesiones[self.numero].gd_reintentos = 0
        self.sw.enviar(self._armar_menu(beneficiario_id))

    # ── SALIR ─────────────────────────────────────────────────────────────────

    def _salir(self, sesiones):
        sesiones[self.numero].gd_estado = None
        sesiones[self.numero].gd_beneficiario_id = None
        sesiones[self.numero].gd_reintentos = 0
        sesiones[self.numero].gd_tipo_nueva = None
        sesiones[self.numero].gd_maps_resultados = None
        sesiones[self.numero].gd_maps_seleccion = None
        sesiones[self.numero].gd_reintentos_maps = 0
        sesiones[self.numero].gd_entre_calle_1 = None
        sesiones[self.numero].gd_entre_calle_2 = None
        sesiones[self.numero].gd_piso = None
        sesiones[self.numero].gd_depto = None
        sesiones[self.numero].gd_direcciones_lista = None
        sesiones[self.numero].gd_link_eliminar = None
