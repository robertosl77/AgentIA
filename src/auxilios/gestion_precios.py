# src/auxilios/gestion_precios.py
import json
from src.send_wpp import SendWPP
from src.sesiones.session_manager import SessionManager
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader
from src.registro.validadores import Validadores

class GestionPrecios(Validadores):
    """
    Gestiona la edición de precios y tarifas del módulo de auxilios.
    Responsabilidades:
        - Listar conceptos con sus precios actuales
        - Editar precios de movida, km por tipo de camino y extras
        - Persistir cambios en auxilios_config.json
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = AuxiliosConfigLoader()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)
        return campo is not None and campo.startswith("precio_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el listado de conceptos editables."""
        sesiones[self.numero].auxilios_campo_actual = "precio_menu"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}
        self.sw.enviar(self._armar_menu_precios())

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)

        if campo == "precio_menu":
            self._procesar_seleccion(comando, sesiones)
        elif campo == "precio_editar_ris":
            self._procesar_seleccion_ris(comando, sesiones)
        elif campo == "precio_editar_valor":
            self._procesar_nuevo_valor(comando, sesiones)
        elif campo == "precio_confirmar":
            self._procesar_confirmacion(comando, sesiones)

    # ── MENÚ ──────────────────────────────────────────────────────────────────

    def _get_conceptos(self):
        """
        Retorna lista de conceptos editables con sus precios actuales.
        Incluye: movida, tipos de camino y extras habilitados.
        """
        conceptos = []
        fmt = self._formato_moneda

        # Movida
        movida = self.config.get_movida()
        precios_movida = movida.get("precios", {})
        conceptos.append({
            "clave": "movida",
            "label": "Movida",
            "tipo_precio": "por_ris",
            "precios": precios_movida,
            "display": f"L: {fmt(precios_movida.get('liviano', 0))} | SP: {fmt(precios_movida.get('semi_pesado', 0))} | P: {fmt(precios_movida.get('pesado', 0))}",
            "seccion": "tarifas",
            "campo_precio": "precios"
        })

        # Tipos de camino (km)
        tipos_camino = self.config.get_tipos_camino()
        for tc in tipos_camino:
            precios_km = tc.get("precio_por_km", {})
            conceptos.append({
                "clave": f"km_{tc['nombre']}",
                "label": f"Km {tc['nombre'].capitalize()}",
                "tipo_precio": "por_ris",
                "precios": precios_km,
                "display": f"L: {fmt(precios_km.get('liviano', 0))} | SP: {fmt(precios_km.get('semi_pesado', 0))} | P: {fmt(precios_km.get('pesado', 0))}",
                "seccion": "catalogos_tipo_camino",
                "nombre_camino": tc["nombre"],
                "campo_precio": "precio_por_km"
            })

        # Extras habilitados
        tarifas = self.config.data.get("tarifas", {})
        for nombre, config in tarifas.items():
            if nombre == "movida":
                continue
            if not config.get("habilitado", False):
                continue

            label = nombre.replace("_", " ").capitalize()

            if "precios" in config:
                # Precio por ris (cancelado_activado)
                precios = config["precios"]
                conceptos.append({
                    "clave": nombre,
                    "label": label,
                    "tipo_precio": "por_ris",
                    "precios": precios,
                    "display": f"L: {fmt(precios.get('liviano', 0))} | SP: {fmt(precios.get('semi_pesado', 0))} | P: {fmt(precios.get('pesado', 0))}",
                    "seccion": "tarifas",
                    "campo_precio": "precios"
                })
            elif "precio" in config:
                # Precio fijo (extraccion, hora_espera, custodia)
                conceptos.append({
                    "clave": nombre,
                    "label": label,
                    "tipo_precio": "fijo",
                    "precio": config["precio"],
                    "display": fmt(config["precio"]),
                    "seccion": "tarifas",
                    "campo_precio": "precio"
                })
            elif "precio_movida" in config:
                # Mecánica ligera: precio_movida + precio_por_km
                conceptos.append({
                    "clave": nombre,
                    "label": f"{label} (movida)",
                    "tipo_precio": "fijo",
                    "precio": config["precio_movida"],
                    "display": fmt(config["precio_movida"]),
                    "seccion": "tarifas",
                    "campo_precio": "precio_movida"
                })
                conceptos.append({
                    "clave": f"{nombre}_km",
                    "label": f"{label} (por km)",
                    "tipo_precio": "fijo",
                    "precio": config.get("precio_por_km", 0),
                    "display": fmt(config.get("precio_por_km", 0)),
                    "seccion": "tarifas",
                    "tarifa_padre": nombre,
                    "campo_precio": "precio_por_km"
                })
            elif "precio_por_km" in config:
                # Remis: solo precio por km
                conceptos.append({
                    "clave": nombre,
                    "label": label,
                    "tipo_precio": "fijo",
                    "precio": config["precio_por_km"],
                    "display": f"{fmt(config['precio_por_km'])}/km",
                    "seccion": "tarifas",
                    "campo_precio": "precio_por_km"
                })

        return conceptos

    def _armar_menu_precios(self):
        """Arma el menú con todos los conceptos editables."""
        conceptos = self._get_conceptos()

        if not conceptos:
            return (
                "💰 No hay precios configurados.\n"
                "Escribí *cancelar* para volver:"
            )

        lineas = ["💰 *Gestión de Precios:*\n"]
        for i, c in enumerate(conceptos, 1):
            lineas.append(f"{i}. {c['label']} — {c['display']}")

        lineas.append("\nIngresá el número del concepto a editar")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    # ── SELECCIÓN ─────────────────────────────────────────────────────────────

    def _procesar_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].auxilios_campo_actual = None
            self._volver_menu_auxilios(sesiones)
            return

        conceptos = self._get_conceptos()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(conceptos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        concepto = conceptos[indice]
        sesiones[self.numero].auxilios_dato_temporal = concepto

        if concepto["tipo_precio"] == "por_ris":
            # Hay que elegir qué ris editar
            sesiones[self.numero].auxilios_campo_actual = "precio_editar_ris"
            precios = concepto["precios"]
            fmt = self._formato_moneda
            self.sw.enviar(
                f"📋 *{concepto['label']}* — Precios actuales:\n\n"
                f"1. Liviano: {fmt(precios.get('liviano', 0))}\n"
                f"2. Semi pesado: {fmt(precios.get('semi_pesado', 0))}\n"
                f"3. Pesado: {fmt(precios.get('pesado', 0))}\n\n"
                f"Ingresá el número del RIS a editar o *cancelar*:"
            )
        else:
            # Precio fijo: directo a editar valor
            sesiones[self.numero].auxilios_campo_actual = "precio_editar_valor"
            sesiones[self.numero].auxilios_reintentos = 0
            fmt = self._formato_moneda
            self.sw.enviar(
                f"📋 *{concepto['label']}*\n"
                f"Precio actual: {fmt(concepto.get('precio', 0))}\n\n"
                f"Ingresá el nuevo precio o *cancelar*:"
            )

    # ── SELECCIÓN RIS ─────────────────────────────────────────────────────────

    def _procesar_seleccion_ris(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.iniciar(sesiones)
            return

        opciones_ris = {"1": "liviano", "2": "semi_pesado", "3": "pesado"}
        ris = opciones_ris.get(comando.strip())

        if not ris:
            self.sw.enviar("⚠️ Opción no válida. Elegí 1, 2 o 3:")
            return

        concepto = sesiones[self.numero].auxilios_dato_temporal
        precio_actual = concepto.get("precios", {}).get(ris, 0)
        ris_display = ris.replace("_", " ").capitalize()

        sesiones[self.numero].auxilios_dato_temporal["ris_seleccionado"] = ris
        sesiones[self.numero].auxilios_campo_actual = "precio_editar_valor"
        sesiones[self.numero].auxilios_reintentos = 0

        fmt = self._formato_moneda
        self.sw.enviar(
            f"📋 *{concepto['label']}* — {ris_display}\n"
            f"Precio actual: {fmt(precio_actual)}\n\n"
            f"Ingresá el nuevo precio o *cancelar*:"
        )

    # ── NUEVO VALOR ───────────────────────────────────────────────────────────

    def _procesar_nuevo_valor(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.iniciar(sesiones)
            return

        reintentos_max = self.config.data.get("reintentos_input", 3)
        reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0)

        try:
            nuevo_precio = int(comando.strip())
            if nuevo_precio < 0:
                raise ValueError
        except ValueError:
            reintentos += 1
            sesiones[self.numero].auxilios_reintentos = reintentos
            if reintentos >= reintentos_max:
                sesiones[self.numero].auxilios_campo_actual = None
                sesiones[self.numero].auxilios_dato_temporal = {}
                sesiones[self.numero].auxilios_reintentos = 0
                self.sw.enviar("❌ Se canceló la edición.")
                self.iniciar(sesiones)
            else:
                self.sw.enviar("⚠️ Ingresá un número válido (sin decimales ni símbolos):")
            return

        concepto = sesiones[self.numero].auxilios_dato_temporal
        concepto["nuevo_precio"] = nuevo_precio

        # Confirmación
        sesiones[self.numero].auxilios_campo_actual = "precio_confirmar"
        sesiones[self.numero].auxilios_reintentos = 0

        fmt = self._formato_moneda
        if concepto["tipo_precio"] == "por_ris":
            ris = concepto.get("ris_seleccionado", "")
            ris_display = ris.replace("_", " ").capitalize()
            precio_anterior = concepto.get("precios", {}).get(ris, 0)
            self.sw.enviar(
                f"¿Confirmás el cambio de *{concepto['label']}* ({ris_display})?\n\n"
                f"Anterior: {fmt(precio_anterior)}\n"
                f"Nuevo: {fmt(nuevo_precio)}\n\n"
                f"Respondé *si* o *no*:"
            )
        else:
            precio_anterior = concepto.get("precio", 0)
            self.sw.enviar(
                f"¿Confirmás el cambio de *{concepto['label']}*?\n\n"
                f"Anterior: {fmt(precio_anterior)}\n"
                f"Nuevo: {fmt(nuevo_precio)}\n\n"
                f"Respondé *si* o *no*:"
            )

    # ── CONFIRMACIÓN ──────────────────────────────────────────────────────────

    def _procesar_confirmacion(self, comando, sesiones):
        if comando.strip() == "si":
            self._guardar_precio(sesiones)
        elif comando.strip() == "no":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar("❌ Edición cancelada.")
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

    # ── GUARDAR ───────────────────────────────────────────────────────────────

    def _guardar_precio(self, sesiones):
        """Persiste el nuevo precio en auxilios_config.json."""
        concepto = sesiones[self.numero].auxilios_dato_temporal
        nuevo_precio = concepto["nuevo_precio"]
        seccion = concepto["seccion"]
        campo_precio = concepto["campo_precio"]

        if seccion == "catalogos_tipo_camino":
            # Editar precio de tipo de camino
            nombre_camino = concepto["nombre_camino"]
            ris = concepto.get("ris_seleccionado", "")
            tipos = self.config.data["catalogos"]["tipos_camino"]
            for tc in tipos:
                if tc["nombre"] == nombre_camino:
                    tc["precio_por_km"][ris] = nuevo_precio
                    break

        elif seccion == "tarifas":
            tarifa_padre = concepto.get("tarifa_padre")
            clave = tarifa_padre if tarifa_padre else concepto["clave"]

            if concepto["tipo_precio"] == "por_ris":
                ris = concepto.get("ris_seleccionado", "")
                self.config.data["tarifas"][clave][campo_precio][ris] = nuevo_precio
            else:
                self.config.data["tarifas"][clave][campo_precio] = nuevo_precio

        self._guardar_config()

        sesiones[self.numero].auxilios_campo_actual = None
        sesiones[self.numero].auxilios_dato_temporal = {}
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar(f"✅ Precio de *{concepto['label']}* actualizado correctamente.")
        self.iniciar(sesiones)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _formato_moneda(self, valor):
        """Formatea un número a moneda argentina: $33.392"""
        return f"${valor:,.0f}".replace(",", ".")

    def _guardar_config(self):
        """Persiste los cambios en auxilios_config.json."""
        with open(self.config.PATH, "w", encoding="utf-8") as f:
            json.dump(self.config.data, f, indent=2, ensure_ascii=False)

    def _volver_menu_auxilios(self, sesiones):
        """Vuelve al menú de auxilios."""
        from src.auxilios.submenu_auxilios import SubMenuAuxilios
        auxilios = SubMenuAuxilios(self.numero)
        auxilios.mostrar_menu(sesiones)