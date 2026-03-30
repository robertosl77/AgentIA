import pywhatkit
import requests # Para la opción de API/WPPConnect
from src.config_loader import ConfigLoader

class SendPyWhatKit:
    """Implementación mediante simulación de navegador (pywhatkit)"""
    def enviar(self, numero, texto):
        try:
            pywhatkit.sendwhatmsg_instantly(numero, texto, wait_time=15, tab_close=True)
            print(f"✅ [PyWhatKit] Enviado a {numero}")
            return True
        except Exception as e:
            print(f"❌ [PyWhatKit] Error: {e}")
            return False

class SendWPPConnect:
    """Implementación mediante API Local (WPPConnect/Node.js)"""
    def __init__(self, url_api="http://localhost:3000"):
        self.url = url_api

    def enviar(self, numero, texto):
        try:
            payload = {
                "phone": numero,
                "message": texto
            }

            print("ENVIANDO PAYLOAD:", payload)

            response = requests.post(f"{self.url}/send-message", json=payload, timeout=10)

            if response.status_code == 200:
                print(f"✅ [WPPConnect] Enviado a {numero}")
                return True

            print(f"❌ [WPPConnect] Error HTTP: {response.status_code} - {response.text}")
            return False

        except Exception as e:
            print(f"❌ [WPPConnect] Error de conexión: {e}")
            return False

class SendWPP:
    def __init__(self, numero):
        self.numero = numero
        self.config = ConfigLoader()
        
        motor = self.config.data.get("configuracion_bot", {}).get("motor_envio", "pywhatkit")
        
        if motor == "wppconnect":
            self.engine = SendWPPConnect()
        else:
            self.engine = SendPyWhatKit()

    def enviar(self, texto):
        return self.engine.enviar(self.numero, texto)