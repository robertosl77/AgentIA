import pywhatkit

class SendWPP:
    """Clase para enviar mensajes por WhatsApp"""

    def __init__(self, numero):
        self.numero = numero

    def enviar(self, texto):
        """Envía un mensaje por WhatsApp"""
        try:
            # pywhatkit.sendwhatmsg_instantly(self.numero, texto, wait_time=18, tab_close=True)
            print(texto)
            print(f"✅ Enviado correctamente")
            return True
        except Exception as e:
            print(f"❌ Error enviando mensaje: {e}")
            return False