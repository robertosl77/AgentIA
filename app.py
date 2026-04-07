import ssl
ssl._create_default_https_context = ssl._create_unverified_context
from flask import Flask, request, jsonify
from src.menu_principal import MenuPrincipal
from src.log.error_logger import ErrorLogger

app = Flask(__name__)
sesiones = {}
error_logger = ErrorLogger()  # ← instancia global para persistir entre requests

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    numero = data.get('from') # Ej: "541168387770@c.us"
    texto = data.get('body')
    texto = texto.strip().lower() if texto else ""
    pushname = data.get('pushname', '')

    if numero not in sesiones:
        # IMPORTANTE: MenuPrincipal NO debe tener inputs en su __init__
        sesiones[numero] = MenuPrincipal(numero)

    try:
        # Procesamos el comando y enviamos respuesta
        sesiones[numero].administro_menu(sesiones, texto, pushname)

    except Exception as e:
        # Registramos el error técnico en error_log.json
        error_logger.registrar(numero, texto, e)

        # Avisamos al cliente sin exponer detalles técnicos
        try:
            sesiones[numero].sw.enviar(
                "⚠️ Ocurrió un problema técnico. Ya fue registrado y será revisado.\n"
                "Por favor intentá nuevamente en unos momentos."
            )
        except Exception:
            # Si tampoco podemos mandarle el mensaje, al menos quedó en el log
            pass

        # Reseteamos la sesión en memoria para que pueda reintentar limpio
        del sesiones[numero]

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # app.run(port=5000)
    print("🚀 Flask corriendo en http://localhost:5000")
    app.run(port=5000, debug=True, use_reloader=False)
    print("Flask ha terminado.")




# from src.menu_principal import MenuPrincipal

# tu_numero = "+541168387770"

# if __name__ == "__main__":
#     mp = MenuPrincipal(tu_numero)
#     mp.iniciar()


# PARA PRUEBAS SIN CELULAR
# bash:
# curl -X POST http://localhost:5000/webhook \
#   -H "Content-Type: application/json" \
#   -d "{\"from\": \"5491168387770@c.us\", \"body\": \"1\"}"

# powershell:
# Invoke-WebRequest -Uri "http://localhost:5000/webhook" `
#   -Method POST `
#   -ContentType "application/json" `
#   -Body '{"from": "5491168387770@c.us", "body": "1"}'



# Borrado de todos los pycaches:
# Get-ChildItem -Path . -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force

# Para generar un txt con la estructura de carpetas y archivos:
# tree /f > "doc\estructura.txt"       