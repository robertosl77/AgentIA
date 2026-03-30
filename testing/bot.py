# import pywhatkit
from send_wpp import SendWPP

# Cambiá al número de tu teléfono personal (desarrollador)
# pywhatkit.sendwhatmsg_instantly("+541168387770", "Hola desde el bot! Prueba ok?")
# pywhatkit.sendwhatmsg_instantly("+541151069392", "Hola desde el bot! Prueba ok?")

wpp = SendWPP("+541168387770")
wpp.enviar("Hola, este es un mensaje de prueba")
