import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "servicio": "agente-facturas-bridge"})

@app.route("/registrar", methods=["POST"])
def registrar():
    try:
        datos = request.get_json()
        if not datos:
            return jsonify({"error": "No se recibieron datos JSON"}), 400

        respuesta = requests.post(
            APPS_SCRIPT_URL,
            json=datos,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )

        return jsonify({
            "ok": True,
            "apps_script_status": respuesta.status_code,
            "apps_script_respuesta": respuesta.text[:500]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
