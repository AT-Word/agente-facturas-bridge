import os
import json
import base64
import requests
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

PROMPT_EXTRACCION = """Sos un asistente contable especializado en Argentina.
Analizá este comprobante y extraé TODOS los datos en formato JSON.

Devolvé ÚNICAMENTE el JSON, sin texto adicional, con esta estructura exacta:

{
  "tipo_operacion": "compra o venta",
  "tipo_comprobante": "A, B, C, M o E",
  "numero_comprobante": "0001-00012345",
  "fecha": "DD/MM/AAAA",
  "razon_social_emisor": "",
  "cuit_emisor": "XX-XXXXXXXX-X",
  "razon_social_receptor": "",
  "cuit_receptor": "XX-XXXXXXXX-X",
  "condicion_iva_emisor": "",
  "neto_gravado_21": 0.00,
  "neto_gravado_105": 0.00,
  "iva_21": 0.00,
  "iva_105": 0.00,
  "no_gravado": 0.00,
  "percepcion_iva": 0.00,
  "percepcion_iibb": 0.00,
  "retencion_ganancias": 0.00,
  "total": 0.00,
  "cae": "",
  "vencimiento_cae": "DD/MM/AAAA",
  "concepto": "",
  "observaciones": ""
}

Si algún campo no figura en el comprobante, usá null para texto y 0.00 para números."""

async def procesar_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ No autorizado.")
        return

    await update.message.reply_text("📄 Recibí el comprobante, procesando...")

    try:
        # Obtener archivo
        if update.message.photo:
            archivo = await update.message.photo[-1].get_file()
            media_type = "image/jpeg"
            tipo = "image"
        elif update.message.document:
            archivo = await update.message.document.get_file()
            nombre = update.message.document.file_name.lower()
            if nombre.endswith(".pdf"):
                media_type = "application/pdf"
                tipo = "document"
            elif nombre.endswith(".png"):
                media_type = "image/png"
                tipo = "image"
            else:
                media_type = "image/jpeg"
                tipo = "image"
        else:
            await update.message.reply_text("❌ Mandame una foto o PDF de la factura.")
            return

        # Descargar y convertir a base64
        contenido_bytes = await archivo.download_as_bytearray()
        datos_b64 = base64.standard_b64encode(contenido_bytes).decode("utf-8")

        # Llamar a Claude
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        if tipo == "document":
            contenido_mensaje = [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": datos_b64
                    }
                },
                {"type": "text", "text": PROMPT_EXTRACCION}
            ]
        else:
            contenido_mensaje = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": datos_b64
                    }
                },
                {"type": "text", "text": PROMPT_EXTRACCION}
            ]

        await update.message.reply_text("🤖 Claude está analizando el comprobante...")

        mensaje = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": contenido_mensaje}]
        )

        respuesta_texto = mensaje.content[0].text.strip()

        # Parsear JSON
        if "```json" in respuesta_texto:
            respuesta_texto = respuesta_texto.split("```json")[1].split("```")[0].strip()
        elif "```" in respuesta_texto:
            respuesta_texto = respuesta_texto.split("```")[1].split("```")[0].strip()

        datos = json.loads(respuesta_texto)

        # Enviar a Google Sheets
        await update.message.reply_text("📊 Registrando en Google Sheets...")

        respuesta_sheets = requests.post(
            APPS_SCRIPT_URL,
            json=datos,
            timeout=30
        )

        if respuesta_sheets.status_code == 200:
            confirmacion = (
                f"✅ *Factura registrada exitosamente*\n\n"
                f"📋 *Comprobante:* {datos.get('tipo_comprobante')} {datos.get('numero_comprobante')}\n"
                f"🏢 *Emisor:* {datos.get('razon_social_emisor')}\n"
                f"📅 *Fecha:* {datos.get('fecha')}\n"
                f"💰 *Total:* ${datos.get('total')}\n"
                f"🔑 *CAE:* {datos.get('cae')}"
            )
            await update.message.reply_text(confirmacion, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ Error al registrar en Sheets: {respuesta_sheets.text[:200]}")

    except json.JSONDecodeError:
        await update.message.reply_text("❌ Claude no pudo extraer los datos. Intentá con una foto más clara.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ No autorizado.")
        return
    await update.message.reply_text(
        "👋 ¡Hola Fernando! Soy tu agente contable.\n\n"
        "Mandame una foto o PDF de cualquier factura y la registro automáticamente en Google Sheets.\n\n"
        "📸 Foto JPG/PNG → ✅\n"
        "📄 PDF → ✅"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.COMMAND & filters.Regex("start"), start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, procesar_documento))
    print("Bot iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
