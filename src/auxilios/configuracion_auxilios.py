# src/auxilios/configuracion_auxilios.py
import json
from src.send_wpp import SendWPP
from src.session_manager import SessionManager
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader

class ConfiguracionAuxilios:
    """
    Gestiona la habilitación/deshabilitación de objetos y extras.
    Responsabilidades:
        - Listar objetos no reglamentales con su estado
        - Listar extras con su estado
        - Cambiar estado habilitado/deshabilitado
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
        return campo is not None and campo.startswith("config_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el menú de configuración."""
        sesiones[self.numero].auxilios_campo_actual = "config_menu"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}
        self.sw.enviar(self._armar_menu_config())

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)

        if campo == "config_menu":
            self._procesar_seleccion(comando, sesiones)
        elif campo == "config_confirmar":
            self._procesar_confirmacion(comando, sesiones)

    # ── MENÚ ──────────────────────────────────────────────────────────────────

    def _armar_menu_config(self):
        items = self._get_items_configurables()

        if not items:
            return "⚙️ No hay elementos configurables."

        lineas = ["⚙️ *Configuración del módulo:*\n"]
        for i, item in enumerate(items, 1):
            estado = "✅ Habilitado" if item["habilitado"] else "❌ Deshabilitado"
            lineas.append(f"{i}. {item['label']} — {estado}")

        lineas.append("\nIngresá el número para cambiar el estado")
        lineas.append("o *cancelar* para volver:")
        return "\n".join(lineas)

    def _get_items_configurables(self):
        """
        Retorna lista de objetos y extras no reglamentales.
        Cada item: {seccion, clave, label, habilitado}
        """
        items = []

        # Objetos no reglamentales
        objetos = self.config.data.get("objetos", {})
        for nombre, config in objetos.items():
            if not config.get("reglamental", True):
                items.append({
                    "seccion": "objetos",
                    "clave": nombre,
                    "label": nombre.replace("_", " ").capitalize(),
                    "habilitado": config.get("habilitado", False)
                })

        # Tarifas extras no reglamentales (excluyendo movida)
        tarifas = self.config.data.get("tarifas", {})
        for nombre, config in tarifas.items():
            if nombre == "movida":
                continue
            if not config.get("reglamental", True):
                items.append({
                    "seccion": "tarifas",
                    "clave": nombre,
                    "label": nombre.replace("_", " ").capitalize(),
                    "habilitado": config.get("habilitado", False)
                })

        return items

    # ── SELECCIÓN ─────────────────────────────────────────────────────────────

    def _procesar_seleccion(self, comando, sesiones):
        if comando.strip() == "cancelar":
            sesiones[self.numero].auxilios_campo_actual = None
            self._volver_menu_auxilios(sesiones)
            return

        items = self._get_items_configurables()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(items):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        item = items[indice]
        nuevo_estado = not item["habilitado"]
        estado_str = "habilitarlo" if nuevo_estado else "deshabilitarlo"

        sesiones[self.numero].auxilios_dato_temporal = {
            "item": item,
            "nuevo_estado": nuevo_estado
        }
        sesiones[self.numero].auxilios_campo_actual = "config_confirmar"
        self.sw.enviar(
            f"¿Confirmás que querés *{estado_str}* "
            f"*{item['label']}*?\n"
            f"Respondé *si* o *no*:"
        )

    # ── CONFIRMACIÓN ──────────────────────────────────────────────────────────

    def _procesar_confirmacion(self, comando, sesiones):
        if comando.strip() == "si":
            datos = sesiones[self.numero].auxilios_dato_temporal
            item = datos["item"]
            nuevo_estado = datos["nuevo_estado"]

            # Aplicar cambio
            self.config.data[item["seccion"]][item["clave"]]["habilitado"] = nuevo_estado
            self._guardar_config()

            estado_str = "habilitado" if nuevo_estado else "deshabilitado"
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar(f"✅ *{item['label']}* {estado_str} correctamente.")
            self.iniciar(sesiones)

        elif comando.strip() == "no":
            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar("❌ Operación cancelada.")
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

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _guardar_config(self):
        """Persiste los cambios en auxilios_config.json."""
        with open(self.config.PATH, "w", encoding="utf-8") as f:
            json.dump(self.config.data, f, indent=2, ensure_ascii=False)

    def _volver_menu_auxilios(self, sesiones):
        """Vuelve al menú de auxilios."""
        from src.auxilios.submenu_auxilios import SubMenuAuxilios
        auxilios = SubMenuAuxilios(self.numero)
        auxilios.mostrar_menu(sesiones)