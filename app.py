import ssl
ssl._create_default_https_context = ssl._create_unverified_context
from flask import Flask, request, jsonify
from src.menu_principal import MenuPrincipal
from src.log.error_logger import ErrorLogger

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB para archivos base64
sesiones = {}
error_logger = ErrorLogger()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    numero = data.get('from')
    texto = data.get('body')
    pushname = data.get('pushname', '')
    media_base64 = data.get('media_base64')  # None si es texto puro
    mimetype = data.get('mimetype', '')
    filename = data.get('filename', '')

    # Si hay archivo adjunto, el body puede contener basura (base64 como texto)
    # En ese caso ignoramos el body como comando
    if media_base64:
        texto = ""
    else:
        texto = texto.strip().lower() if texto else ""

    if numero not in sesiones:
        sesiones[numero] = MenuPrincipal(numero)

    try:
        sesiones[numero].administro_menu(
            sesiones, texto, pushname,
            media_base64=media_base64,
            mimetype=mimetype,
            filename=filename
        )

    except Exception as e:
        error_logger.registrar(numero, texto, e)

        try:
            sesiones[numero].sw.enviar(
                "⚠️ Ocurrió un problema técnico. Ya fue registrado y será revisado.\n"
                "Por favor intentá nuevamente en unos momentos."
            )
        except Exception:
            pass

        del sesiones[numero]

    return jsonify({"status": "ok"})

if __name__ == "__main__":
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