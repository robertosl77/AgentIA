# src/maps/maps_client.py
import requests
from src.maps.maps_config_loader import MapsConfigLoader

class MapsClient:
    """
    Cliente de Google Maps Platform.
    Responsabilidades:
        - Buscar direcciones por texto (Places API - Text Search)
        - Geocoding inverso (coordenadas → dirección)
    No tiene lógica de flujo ni de WhatsApp. Solo habla con Google y retorna datos.
    """

    PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
    GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(self):
        self.config = MapsConfigLoader()

    # ── BÚSQUEDA POR TEXTO (Places API v2) ────────────────────────────────────

    def buscar_direccion(self, texto):
        """
        Busca direcciones usando Places API (New) Text Search.
        Retorna lista de dicts con datos estructurados, o lista vacía si no hay resultados.
        """
        api_key = self.config.get_api_key()
        max_resultados = self.config.get_max_resultados()

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": (
                "places.displayName,"
                "places.formattedAddress,"
                "places.location,"
                "places.id,"
                "places.addressComponents,"
                "places.plusCode"
            )
        }

        body = {
            "textQuery": texto,
            "languageCode": self.config.get_idioma(),
            "regionCode": self.config.get_pais(),
            "maxResultCount": max_resultados
        }

        try:
            response = requests.post(self.PLACES_URL, json=body, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"❌ [Maps] Error HTTP {response.status_code}: {response.text}")
                return []

            data = response.json()
            places = data.get("places", [])
            return [self._parsear_place(p) for p in places]

        except Exception as e:
            print(f"❌ [Maps] Error de conexión: {e}")
            return []

    # ── GEOCODING INVERSO ─────────────────────────────────────────────────────

    def geocoding_inverso(self, lat, lng):
        """
        Convierte coordenadas a dirección usando Geocoding API.
        Retorna dict con datos estructurados, o None si falla.
        """
        api_key = self.config.get_api_key()

        params = {
            "latlng": f"{lat},{lng}",
            "language": self.config.get_idioma(),
            "key": api_key
        }

        try:
            response = requests.get(self.GEOCODING_URL, params=params, timeout=10)
            if response.status_code != 200:
                print(f"❌ [Maps] Error HTTP {response.status_code}: {response.text}")
                return None

            data = response.json()
            results = data.get("results", [])
            if not results:
                return None

            resultado = results[0]
            return self._parsear_geocoding(resultado, lat, lng)

        except Exception as e:
            print(f"❌ [Maps] Error de conexión: {e}")
            return None

    # ── PARSERS ───────────────────────────────────────────────────────────────

    def _parsear_place(self, place):
        """Convierte un resultado de Places API a la estructura JSON unificada."""
        location = place.get("location", {})
        componentes = self._extraer_componentes_places(place.get("addressComponents", []))
        plus_code = place.get("plusCode", {})

        return {
            "direccion_formateada": place.get("formattedAddress", ""),
            "coordenadas": {
                "lat": location.get("latitude"),
                "lng": location.get("longitude")
            },
            "place_id": place.get("id"),
            "componentes": componentes,
            "plus_code": plus_code.get("globalCode") or plus_code.get("compoundCode"),
            "origen_input": "texto"
        }

    def _parsear_geocoding(self, resultado, lat, lng):
        """Convierte un resultado de Geocoding API a la estructura JSON unificada."""
        componentes = self._extraer_componentes_geocoding(resultado.get("address_components", []))
        plus_code = resultado.get("plus_code", {})

        return {
            "direccion_formateada": resultado.get("formatted_address", ""),
            "coordenadas": {
                "lat": lat,
                "lng": lng
            },
            "place_id": resultado.get("place_id"),
            "componentes": componentes,
            "plus_code": plus_code.get("global_code") or plus_code.get("compound_code"),
            "origen_input": "coordenadas"
        }

    def _extraer_componentes_places(self, address_components):
        """Extrae componentes de dirección del formato Places API (New)."""
        componentes = {
            "calle": None,
            "altura": None,
            "localidad": None,
            "provincia": None,
            "codigo_postal": None
        }

        for comp in address_components:
            tipos = comp.get("types", [])
            texto = comp.get("longText", "") or comp.get("shortText", "")

            if "route" in tipos:
                componentes["calle"] = texto
            elif "street_number" in tipos:
                componentes["altura"] = texto
            elif "locality" in tipos:
                componentes["localidad"] = texto
            elif "sublocality" in tipos or "sublocality_level_1" in tipos:
                if not componentes["localidad"]:
                    componentes["localidad"] = texto
            elif "administrative_area_level_1" in tipos:
                componentes["provincia"] = texto
            elif "postal_code" in tipos:
                componentes["codigo_postal"] = texto

        return componentes

    def _extraer_componentes_geocoding(self, address_components):
        """Extrae componentes de dirección del formato Geocoding API."""
        componentes = {
            "calle": None,
            "altura": None,
            "localidad": None,
            "provincia": None,
            "codigo_postal": None
        }

        for comp in address_components:
            tipos = comp.get("types", [])
            texto = comp.get("long_name", "")

            if "route" in tipos:
                componentes["calle"] = texto
            elif "street_number" in tipos:
                componentes["altura"] = texto
            elif "locality" in tipos:
                componentes["localidad"] = texto
            elif "sublocality" in tipos or "sublocality_level_1" in tipos:
                if not componentes["localidad"]:
                    componentes["localidad"] = texto
            elif "administrative_area_level_1" in tipos:
                componentes["provincia"] = texto
            elif "postal_code" in tipos:
                componentes["codigo_postal"] = texto

        return componentes