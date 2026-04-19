import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
TN_ACCESS_TOKEN = os.environ.get("TN_ACCESS_TOKEN")
TN_STORE_ID = os.environ.get("TN_STORE_ID")

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

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "no code"}), 400
    resp = requests.post(
        "https://www.tiendanube.com/apps/authorize/token",
        json={
            "client_id": "30058",
            "client_secret": "47f77cbf9f6a601edde73cbf1fe57ea9fef7891519647c28",
            "grant_type": "authorization_code",
            "code": code
        }
    )
    return jsonify(resp.json())

@app.route("/test-tiendanube", methods=["GET"])
def test_tiendanube():
    try:
        token = os.environ.get("TN_ACCESS_TOKEN")
        store_id = os.environ.get("TN_STORE_ID")
        resp = requests.get(
            f"https://api.tiendanube.com/v1/{store_id}/products?limit=5",
            headers={
                "Authentication": f"bearer {token}",
                "User-Agent": "AT Word Agente (atwordecommerce@gmail.com)"
            }
        )
        return jsonify({"raw": resp.json(), "token_usado": token[:10] + "..."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
