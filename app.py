import ssl
ssl._create_default_https_context = ssl._create_unverified_context
from flask import Flask, request, jsonify
from src.menu_principal import MenuPrincipal


app = Flask(__name__)
sesiones = {}

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
    
    # Procesamos el comando y enviamos respuesta
    sesiones[numero].administro_menu(texto,sesiones,pushname)
    
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
