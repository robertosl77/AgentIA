# src/auxilios/calculo_tarifas.py
from src.auxilios.auxilios_config_loader import AuxiliosConfigLoader

class CalculoTarifas:
    """
    Calcula el costo total de un servicio de auxilio mecánico.
    Responsabilidades:
        - Determinar si aplica movida
        - Calcular km excedentes por tipo de camino
        - Descontar radio de movida del asfalto
        - Calcular subtotales por tramo
        - Sumar extras habilitados
        - Generar desglose para confirmación
    """

    def __init__(self):
        self.config = AuxiliosConfigLoader()

    # ── CÁLCULO PRINCIPAL ─────────────────────────────────────────────────────

    def calcular(self, ris, tramos, extras=None):
        """
        Calcula el total del servicio.
        ris: 'liviano', 'semi_pesado', 'pesado'
        tramos: [{"tipo_camino": "asfalto", "km": 25}, ...]
        extras: {"extraccion": True, "custodia": True, ...} o None
        Retorna dict con desglose completo.
        """
        movida = self._calcular_movida(ris, tramos)
        tramos_calculados = self._calcular_tramos(ris, tramos, movida["aplica"])
        extras_calculados = self._calcular_extras(ris, extras or {})

        total = movida["monto"] + tramos_calculados["subtotal"] + extras_calculados["subtotal"]

        return {
            "movida": movida,
            "tramos": tramos_calculados,
            "extras": extras_calculados,
            "total": total
        }

    # ── MOVIDA ────────────────────────────────────────────────────────────────

    def _calcular_movida(self, ris, tramos):
        """Determina si aplica movida y su monto."""
        config_movida = self.config.get_movida()
        radio = config_movida.get("radio_km", 15)
        km_maximo = config_movida.get("km_maximo", 200)
        precios = config_movida.get("precios", {})

        km_total = sum(t.get("km", 0) for t in tramos)
        aplica = km_total < km_maximo
        monto = precios.get(ris, 0) if aplica else 0

        return {
            "aplica": aplica,
            "radio_km": radio,
            "km_total": km_total,
            "km_maximo": km_maximo,
            "monto": monto
        }

    # ── TRAMOS ────────────────────────────────────────────────────────────────

    def _calcular_tramos(self, ris, tramos, aplica_movida):
        """
        Calcula km excedentes por tramo.
        Si aplica movida, descuenta el radio del asfalto.
        """
        config_movida = self.config.get_movida()
        radio = config_movida.get("radio_km", 15) if aplica_movida else 0
        tipos_camino = self.config.get_tipos_camino()

        # Índice de precios por tipo de camino
        precios_por_tipo = {}
        for tc in tipos_camino:
            precios_por_tipo[tc["nombre"]] = tc.get("precio_por_km", {}).get(ris, 0)

        km_descontados = radio
        detalle = []

        for tramo in tramos:
            tipo = tramo.get("tipo_camino", "")
            km = tramo.get("km", 0)
            precio_km = precios_por_tipo.get(tipo, 0)

            # Descontar radio solo del asfalto
            if tipo == "asfalto" and km_descontados > 0:
                km_excedente = max(0, km - km_descontados)
                km_descontados = max(0, km_descontados - km)
            else:
                km_excedente = km

            subtotal = km_excedente * precio_km

            detalle.append({
                "tipo_camino": tipo,
                "km_original": km,
                "km_excedente": km_excedente,
                "precio_km": precio_km,
                "subtotal": subtotal
            })

        subtotal_tramos = sum(d["subtotal"] for d in detalle)

        return {
            "detalle": detalle,
            "subtotal": subtotal_tramos
        }

    # ── EXTRAS ────────────────────────────────────────────────────────────────

    def _calcular_extras(self, ris, extras):
        """Calcula los montos de extras aplicados."""
        detalle = []
        subtotal = 0

        for nombre, aplicar in extras.items():
            if not aplicar:
                continue

            tarifa = self.config.get_tarifa(nombre)
            if not tarifa or not tarifa.get("habilitado"):
                continue

            # Precio fijo
            if "precio" in tarifa:
                monto = tarifa["precio"]
            # Precio por ris
            elif "precios" in tarifa:
                monto = tarifa["precios"].get(ris, 0)
            # Precio movida (mecánica ligera)
            elif "precio_movida" in tarifa:
                monto = tarifa["precio_movida"]
            else:
                monto = 0

            detalle.append({
                "nombre": nombre,
                "monto": monto
            })
            subtotal += monto

        return {
            "detalle": detalle,
            "subtotal": subtotal
        }

    # ── DESGLOSE PARA CONFIRMACIÓN ────────────────────────────────────────────

    def generar_desglose(self, resultado):
        """
        Genera el texto de desglose para mostrar en la confirmación.
        resultado: dict retornado por calcular()
        """
        lineas = ["📋 *Desglose del servicio:*\n"]

        # Movida
        movida = resultado["movida"]
        if movida["aplica"]:
            lineas.append(f"🚛 Movida ({movida['radio_km']}km incluidos): ${movida['monto']:,.0f}")
        else:
            lineas.append(f"🚛 Movida: No aplica (recorrido ≥ {movida['km_maximo']}km)")

        # Tramos
        for t in resultado["tramos"]["detalle"]:
            if t["km_excedente"] > 0:
                lineas.append(
                    f"🛣️ {t['tipo_camino'].capitalize()}: "
                    f"{t['km_excedente']}km × ${t['precio_km']:,.0f} = ${t['subtotal']:,.0f}"
                )
            elif t["km_original"] > 0:
                lineas.append(
                    f"🛣️ {t['tipo_camino'].capitalize()}: "
                    f"{t['km_original']}km (cubiertos por movida)"
                )

        # Extras
        for e in resultado["extras"]["detalle"]:
            nombre_display = e["nombre"].replace("_", " ").capitalize()
            lineas.append(f"➕ {nombre_display}: ${e['monto']:,.0f}")

        # Total
        lineas.append(f"\n💰 *TOTAL: ${resultado['total']:,.0f}*")

        return "\n".join(lineas)