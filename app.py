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
TN_ACCESS_TOKEN = os.environ.get("TN_ACCESS_TOKEN")
TN_STORE_ID = os.environ.get("TN_STORE_ID")

@app.route("/test-tiendanube", methods=["GET"])
def test_tiendanube():
    try:
        resp = requests.get(
            f"https://api.tiendanube.com/v1/{TN_STORE_ID}/products?limit=5",
            headers={
                "Authentication": f"bearer {TN_ACCESS_TOKEN}",
                "User-Agent": "AT Word Agente (atword@gmail.com)"
            }
        )
        return jsonify({"raw": resp.json()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
