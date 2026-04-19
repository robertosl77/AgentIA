# src/farmacia/agente_ia.py
import json
import os
import base64


class AgenteIA:
    """
    Adaptador configurable para interpretar recetas médicas con IA.
    El proveedor (gemini, openai, anthropic) se configura desde farmacia_config.json.
    Todos los proveedores implementan la misma interfaz: interpretar_receta(imagen) → dict.
    
    Retorna un dict con la estructura:
    {
        "paciente": { "nombre", "dni", "cuil", "sexo", "fecha_nacimiento" },
        "obra_social": { "entidad", "plan", "credencial" },
        "medico": { "nombre", "matricula", "especialidad" },
        "diagnostico": "",
        "fecha_creacion": "",
        "fecha_validez_desde": "",
        "medicamentos": [
            { "farmaco", "nombre_comercial", "dosis", "presentacion", "cantidad" }
        ],
        "errores": [ "campo X no pudo leerse" ]
    }
    """

    CONFIG_PATH = os.path.join("data", "farmacia", "farmacia_config.json")

    def __init__(self):
        self.config = self._cargar_config()
        self.proveedor = self.config.get("agente_ia", {}).get("proveedor", "gemini")
        self.modelo = self.config.get("agente_ia", {}).get("modelo", "gemini-2.0-flash")
        self.api_key = self._cargar_api_key()

    def _cargar_config(self):
        """Carga la configuración de farmacia."""
        if not os.path.exists(self.CONFIG_PATH):
            return {}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cargar_api_key(self):
        """Lee la API key desde la variable de entorno configurada."""
        env_var = self.config.get("agente_ia", {}).get("env_api_key", "GEMINI_API_KEY")
        return os.environ.get(env_var, "")

    # ── INTERFAZ PÚBLICA ──────────────────────────────────────────────────────

    def interpretar_receta(self, imagen_path=None, imagen_base64=None):
        """
        Interpreta una receta médica desde imagen o PDF.
        Acepta ruta de archivo o base64.
        Retorna dict estructurado con los datos extraídos.
        """
        if not self.api_key:
            return {"errores": ["API key no configurada para el agente IA."], "codigo_error": "sin_api_key"}

        # Preparar imagen en base64
        if imagen_path and not imagen_base64:
            imagen_base64 = self._archivo_a_base64(imagen_path)

        if not imagen_base64:
            return {"errores": ["No se recibió imagen para interpretar."], "codigo_error": "sin_imagen"}

        # Limpiar prefijo data:image/...;base64, si viene
        if "," in imagen_base64 and imagen_base64.startswith("data:"):
            imagen_base64 = imagen_base64.split(",", 1)[1]

        # Despachar al proveedor correspondiente
        adaptadores = {
            "gemini": self._interpretar_gemini,
            "openai": self._interpretar_openai,
            "anthropic": self._interpretar_anthropic
        }

        adaptador = adaptadores.get(self.proveedor)
        if not adaptador:
            return {"errores": [f"Proveedor '{self.proveedor}' no soportado."], "codigo_error": "proveedor_no_soportado"}

        try:
            return adaptador(imagen_base64)
        except Exception as e:
            return {"errores": [f"Error al interpretar receta: {str(e)}"], "codigo_error": "error_generico"}

    # ── PROMPT COMPARTIDO ─────────────────────────────────────────────────────

    def _get_prompt(self):
        """Prompt único para todos los proveedores — garantiza misma estructura de respuesta."""
        return """Analizá esta receta médica y extraé los datos en formato JSON estricto.
Respondé SOLO con el JSON, sin texto adicional, sin backticks, sin explicaciones.

Estructura requerida:
{
    "paciente": {
        "nombre": "",
        "dni": "",
        "cuil": "",
        "sexo": "",
        "fecha_nacimiento": ""
    },
    "obra_social": {
        "entidad": "",
        "plan": "",
        "credencial": ""
    },
    "medico": {
        "nombre": "",
        "matricula": "",
        "especialidad": ""
    },
    "diagnostico": "",
    "fecha_creacion": "",
    "fecha_validez_desde": "",
    "medicamentos": [
        {
            "farmaco": "",
            "nombre_comercial": "",
            "dosis": "",
            "presentacion": "",
            "cantidad": 0
        }
    ],
    "errores": []
}

Reglas:
- Si un campo no puede leerse, dejalo como string vacío o 0 para cantidad
- Agregá en "errores" una descripción de cada campo que no pudiste leer
- "farmaco" es el principio activo (ej: Hidrocortisona)
- "nombre_comercial" es la marca (ej: Hidrotisona). Si no aparece, dejá vacío
- "dosis" incluye unidad (ej: "10 mg")
- "presentacion" es la forma farmacéutica (ej: "comp. x 30")
- "cantidad" es el número de cajas/envases indicados
- Las fechas en formato DD/MM/AAAA
- DNI solo números, sin puntos"""

    # ── ADAPTADOR GEMINI ──────────────────────────────────────────────────────

    def _interpretar_gemini(self, imagen_base64):
        """Interpreta receta usando Google Gemini."""
        import requests

        # url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent"
        url = f"https://generativelanguage.googleapis.com/v1/models/{self.modelo}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        payload = {
            "contents": [{
                "parts": [
                    {"text": self._get_prompt()},
                    {
                        "inline_data": {
                            "mime_type": self._detectar_mime(imagen_base64),
                            "data": imagen_base64
                        }
                    }
                ]
            }]
        }

        response = requests.post(url, headers=headers, params=params, json=payload, timeout=30)

        if response.status_code != 200:
            return {
                "errores": [f"Gemini API error: {response.status_code}"],
                "codigo_error": str(response.status_code)
            }

        data = response.json()
        texto = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return self._parsear_respuesta(texto)

    # ── ADAPTADOR OPENAI ──────────────────────────────────────────────────────

    def _interpretar_openai(self, imagen_base64):
        """Interpreta receta usando OpenAI GPT-4o."""
        import requests

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        mime = self._detectar_mime(imagen_base64)
        payload = {
            "model": self.modelo,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": self._get_prompt()},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{imagen_base64}"
                        }
                    }
                ]
            }],
            "max_tokens": 2000
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            return {
                "errores": [f"OpenAI API error: {response.status_code}"],
                "codigo_error": str(response.status_code)
            }

        data = response.json()
        texto = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._parsear_respuesta(texto)

    # ── ADAPTADOR ANTHROPIC ───────────────────────────────────────────────────

    def _interpretar_anthropic(self, imagen_base64):
        """Interpreta receta usando Claude."""
        import requests

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

        mime = self._detectar_mime(imagen_base64)
        payload = {
            "model": self.modelo,
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": imagen_base64
                        }
                    },
                    {"type": "text", "text": self._get_prompt()}
                ]
            }]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            return {
                "errores": [f"Anthropic API error: {response.status_code}"],
                "codigo_error": str(response.status_code)
            }

        data = response.json()
        texto = data.get("content", [{}])[0].get("text", "")
        return self._parsear_respuesta(texto)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _archivo_a_base64(self, path):
        """Convierte un archivo a base64."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _detectar_mime(self, base64_data):
        """Detecta el tipo MIME a partir de los primeros bytes del base64."""
        try:
            header = base64.b64decode(base64_data[:32])
            if header[:4] == b'%PDF':
                return "application/pdf"
            elif header[:8] == b'\x89PNG\r\n\x1a\n':
                return "image/png"
            elif header[:2] == b'\xff\xd8':
                return "image/jpeg"
        except Exception:
            pass
        return "image/jpeg"  # default

    def _parsear_respuesta(self, texto):
        """Parsea la respuesta JSON del agente IA."""
        try:
            # Limpiar posibles backticks o texto extra
            texto = texto.strip()
            if texto.startswith("```"):
                texto = texto.split("\n", 1)[1] if "\n" in texto else texto[3:]
            if texto.endswith("```"):
                texto = texto[:-3]
            texto = texto.strip()
            if texto.startswith("json"):
                texto = texto[4:].strip()

            return json.loads(texto)
        except json.JSONDecodeError as e:
            return {"errores": [f"No se pudo interpretar la respuesta del agente IA: {str(e)}"]}