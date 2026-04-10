# src/maps/buscador_direccion.py
import re
from src.maps.maps_client import MapsClient
from src.maps.maps_config_loader import MapsConfigLoader

class BuscadorDireccion:
    """
    Proveedor de servicios de geolocalización para enlatados.
    Responsabilidades:
        - Detectar tipo de input (texto, coordenadas)
        - Buscar direcciones por texto (Places API)
        - Resolver coordenadas (Geocoding inverso)
        - Armar mensaje con opciones numeradas para WhatsApp
    No tiene estado propio ni maneja sesiones. Es una herramienta que los enlatados consumen.
    """

    REGEX_COORDENADAS = re.compile(
        r"^-?\d{1,3}\.\d+[,\s]+-?\d{1,3}\.\d+$"
    )

    def __init__(self):
        self.client = MapsClient()
        self.config = MapsConfigLoader()

    # ── DETECCIÓN DE TIPO DE INPUT ────────────────────────────────────────────

    def detectar_tipo_input(self, texto):
        """
        Detecta el tipo de input del usuario.
        Retorna: 'coordenadas', 'texto'
        A futuro: 'link', 'ubicacion_wpp'
        """
        limpio = texto.strip().replace(" ", "")
        if self.REGEX_COORDENADAS.match(limpio):
            return "coordenadas"
        return "texto"

    # ── BÚSQUEDA ──────────────────────────────────────────────────────────────

    def buscar(self, texto):
        """
        Busca direcciones por texto libre.
        Retorna lista de dicts con estructura JSON unificada, o lista vacía.
        """
        return self.client.buscar_direccion(texto)

    def resolver_coordenadas(self, texto):
        """
        Parsea coordenadas del texto y hace geocoding inverso.
        Retorna dict con estructura JSON unificada, o None si falla.
        """
        try:
            limpio = texto.strip().replace(" ", "")
            partes = re.split(r"[,\s]+", limpio)
            lat = float(partes[0])
            lng = float(partes[1])
            return self.client.geocoding_inverso(lat, lng)
        except (ValueError, IndexError):
            return None

    # ── FORMATO PARA WHATSAPP ─────────────────────────────────────────────────

    def armar_mensaje_opciones(self, resultados):
        """
        Arma el mensaje con opciones numeradas para enviar por WhatsApp.
        Usa los mensajes configurados en maps_config.json.
        """
        titulo = self.config.get_mensaje("opciones_encontradas")
        pie = self.config.get_mensaje("opcion_ninguna")

        lineas = [f"{titulo}\n"]
        for i, r in enumerate(resultados, 1):
            lineas.append(f"{i}. {r['direccion_formateada']}")
        lineas.append(f"\n{pie}")

        return "\n".join(lineas)

    def armar_mensaje_unico(self, resultado):
        """
        Arma el mensaje de confirmación cuando hay un solo resultado.
        """
        titulo = self.config.get_mensaje("direccion_detectada")
        confirmar = self.config.get_mensaje("confirmar_unica")

        return f"{titulo}\n\n{resultado['direccion_formateada']}\n\n{confirmar}"

    def get_mensaje(self, clave):
        """Proxy a config para acceder a mensajes desde el enlatado."""
        return self.config.get_mensaje(clave)