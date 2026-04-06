# src/auxilios/gestion_recorridos.py
from src.send_wpp import SendWPP
from src.session_manager import SessionManager
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader
from src.auxilios.auxilios_data_loader import AuxiliosDataLoader
from src.registro.validadores import Validadores

class GestionRecorridos(Validadores):
    """
    Gestiona el flujo completo de recorridos establecidos.
    Responsabilidades:
        - Listar recorridos establecidos
        - Agregar recorrido (origen, destino, km)
        - Eliminar recorrido
        - Los puntos nuevos se agregan automáticamente al catálogo de puntos frecuentes
    """

    def __init__(self, numero):
        self.numero = numero
        self.sw = SendWPP(numero)
        self.session_manager = SessionManager()
        self.config = AuxiliosConfigLoader()
        self.datos = AuxiliosDataLoader()

    # ── FLUJO PRINCIPAL ───────────────────────────────────────────────────────

    def esta_en_flujo(self, sesiones):
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)
        return campo is not None and campo.startswith("recorrido_")

    def iniciar(self, sesiones):
        """Punto de entrada — muestra el listado de recorridos."""
        sesiones[self.numero].auxilios_campo_actual = "recorrido_menu"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}
        self.sw.enviar(self._armar_menu_recorridos())

    def procesar(self, comando, sesiones):
        """Dispatcher interno según estado actual."""
        campo = getattr(sesiones[self.numero], "auxilios_campo_actual", None)

        if campo == "recorrido_menu":
            self._procesar_seleccion(comando, sesiones)
        elif campo == "recorrido_agregar_origen":
            self._procesar_origen(comando, sesiones)
        elif campo == "recorrido_agregar_destino":
            self._procesar_destino(comando, sesiones)
        elif campo == "recorrido_agregar_km":
            self._procesar_km(comando, sesiones)
        elif campo == "recorrido_confirmar_elimina":
            self._procesar_confirmacion_elimina(comando, sesiones)

    # ── MENÚ ──────────────────────────────────────────────────────────────────

    def _armar_menu_recorridos(self):
        recorridos = self.config.get_recorridos_establecidos()

        if not recorridos:
            return (
                "🛣️ No hay recorridos establecidos.\n"
                "Ingresá *nuevo* para agregar uno\n"
                "o *cancelar* para volver:"
            )

        lineas = ["🛣️ *Recorridos establecidos:*\n"]
        for i, r in enumerate(recorridos, 1):
            lineas.append(f"{i}. {r['origen']} → {r['destino']} ({r['km']}km)")

        lineas.append("\nIngresá el número para eliminar un recorrido,")
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

        recorridos = self.config.get_recorridos_establecidos()
        try:
            indice = int(comando.strip()) - 1
            if indice < 0 or indice >= len(recorridos):
                raise ValueError
        except ValueError:
            self.sw.enviar("❌ Opción no válida.")
            return

        recorrido = recorridos[indice]
        sesiones[self.numero].auxilios_dato_temporal = recorrido
        sesiones[self.numero].auxilios_campo_actual = "recorrido_confirmar_elimina"
        self.sw.enviar(
            f"¿Confirmás que querés eliminar el recorrido "
            f"*{recorrido['origen']} → {recorrido['destino']}*?\n"
            f"Respondé *si* o *no*:"
        )

    # ── AGREGAR ───────────────────────────────────────────────────────────────

    def _iniciar_agregar(self, sesiones):
        """Inicia el flujo de carga: origen → destino → km."""
        sesiones[self.numero].auxilios_campo_actual = "recorrido_agregar_origen"
        sesiones[self.numero].auxilios_reintentos = 0
        sesiones[self.numero].auxilios_dato_temporal = {}

        puntos = self.config.get_puntos_frecuentes()
        msj = "📍 Ingresá el *origen* del recorrido"
        if puntos:
            lineas = [msj + " (o elegí de la lista):\n"]
            for i, p in enumerate(puntos, 1):
                lineas.append(f"{i}. {p}")
            lineas.append("\nO escribí el nombre del punto:")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(msj + ":")

    def _procesar_origen(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        origen = self._resolver_punto(comando)
        if not origen:
            self.sw.enviar("⚠️ Origen no válido. Intentá nuevamente:")
            return

        sesiones[self.numero].auxilios_dato_temporal["origen"] = origen

        # Pedir destino
        sesiones[self.numero].auxilios_campo_actual = "recorrido_agregar_destino"
        sesiones[self.numero].auxilios_reintentos = 0

        puntos = self.config.get_puntos_frecuentes()
        msj = "📍 Ingresá el *destino* del recorrido"
        if puntos:
            lineas = [msj + " (o elegí de la lista):\n"]
            for i, p in enumerate(puntos, 1):
                lineas.append(f"{i}. {p}")
            lineas.append("\nO escribí el nombre del punto:")
            self.sw.enviar("\n".join(lineas))
        else:
            self.sw.enviar(msj + ":")

    def _procesar_destino(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        destino = self._resolver_punto(comando)
        if not destino:
            self.sw.enviar("⚠️ Destino no válido. Intentá nuevamente:")
            return

        origen = sesiones[self.numero].auxilios_dato_temporal.get("origen", "")
        if destino.lower() == origen.lower():
            self.sw.enviar("⚠️ El destino no puede ser igual al origen. Intentá nuevamente:")
            return

        # Verificar duplicado
        recorridos = self.config.get_recorridos_establecidos()
        for r in recorridos:
            if r["origen"].lower() == origen.lower() and r["destino"].lower() == destino.lower():
                self.sw.enviar(
                    f"⚠️ Ya existe el recorrido *{origen} → {destino}*."
                )
                self._cancelar(sesiones)
                return

        sesiones[self.numero].auxilios_dato_temporal["destino"] = destino
        sesiones[self.numero].auxilios_campo_actual = "recorrido_agregar_km"
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar("📏 Ingresá la *distancia en km* del recorrido:")

    def _procesar_km(self, comando, sesiones):
        if comando.strip() == "cancelar":
            self._cancelar(sesiones)
            return

        reintentos = getattr(sesiones[self.numero], "auxilios_reintentos", 0)

        try:
            km = int(comando.strip())
            if km <= 0:
                raise ValueError
        except ValueError:
            reintentos += 1
            sesiones[self.numero].auxilios_reintentos = reintentos
            if reintentos >= self.config.data.get("reintentos_input", 3):
                self.sw.enviar("❌ Se canceló la carga. Volviendo al menú de recorridos...")
                self._cancelar(sesiones)
            else:
                self.sw.enviar("⚠️ Ingresá un número válido mayor a 0:")
            return

        datos = sesiones[self.numero].auxilios_dato_temporal
        datos["km"] = km

        # Guardar recorrido en config
        self.config.data["catalogos"]["recorridos_establecidos"].append({
            "origen": datos["origen"],
            "destino": datos["destino"],
            "km": datos["km"]
        })

        # Agregar puntos nuevos al catálogo de puntos frecuentes
        self._agregar_punto_frecuente(datos["origen"])
        self._agregar_punto_frecuente(datos["destino"])

        # Persistir config
        self._guardar_config()

        sesiones[self.numero].auxilios_campo_actual = None
        sesiones[self.numero].auxilios_dato_temporal = {}
        sesiones[self.numero].auxilios_reintentos = 0
        self.sw.enviar(
            f"✅ Recorrido *{datos['origen']} → {datos['destino']} ({datos['km']}km)* "
            f"registrado correctamente."
        )
        self.iniciar(sesiones)

    # ── ELIMINAR ──────────────────────────────────────────────────────────────

    def _procesar_confirmacion_elimina(self, comando, sesiones):
        if comando.strip() == "si":
            recorrido = sesiones[self.numero].auxilios_dato_temporal
            recorridos = self.config.data["catalogos"]["recorridos_establecidos"]
            # Buscamos por coincidencia exacta
            self.config.data["catalogos"]["recorridos_establecidos"] = [
                r for r in recorridos
                if not (r["origen"] == recorrido["origen"] and
                        r["destino"] == recorrido["destino"] and
                        r["km"] == recorrido["km"])
            ]
            self._guardar_config()

            sesiones[self.numero].auxilios_campo_actual = None
            sesiones[self.numero].auxilios_dato_temporal = {}
            self.sw.enviar(
                f"✅ Recorrido *{recorrido['origen']} → {recorrido['destino']}* "
                f"eliminado correctamente."
            )
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

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _resolver_punto(self, comando):
        """
        Resuelve el punto ingresado.
        Si es un número, busca en puntos frecuentes.
        Si es texto, lo toma como punto nuevo.
        """
        puntos = self.config.get_puntos_frecuentes()

        try:
            indice = int(comando.strip()) - 1
            if 0 <= indice < len(puntos):
                return puntos[indice]
            return None
        except ValueError:
            # Texto libre: lo tomamos como punto nuevo
            texto = comando.strip().title()
            if len(texto) < 2:
                return None
            return texto

    def _agregar_punto_frecuente(self, punto):
        """Agrega un punto al catálogo de puntos frecuentes si no existe."""
        puntos = self.config.data["catalogos"]["puntos_frecuentes"]
        if punto.lower() not in [p.lower() for p in puntos]:
            puntos.append(punto)

    def _guardar_config(self):
        """Persiste los cambios en auxilios_config.json."""
        import json
        with open(self.config.PATH, "w", encoding="utf-8") as f:
            json.dump(self.config.data, f, indent=2, ensure_ascii=False)

    def _cancelar(self, sesiones):
        sesiones[self.numero].auxilios_campo_actual = None
        sesiones[self.numero].auxilios_dato_temporal = {}
        sesiones[self.numero].auxilios_reintentos = 0
        self.iniciar(sesiones)

    def _volver_menu_auxilios(self, sesiones):
        """Vuelve al menú de auxilios."""
        from src.auxilios.submenu_auxilios import SubMenuAuxilios
        auxilios = SubMenuAuxilios(self.numero)
        auxilios.mostrar_menu(sesiones)