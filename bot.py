import os
import sys
import json
import base64
import logging
import requests
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

PROMPT = """Sos un asistente contable especializado en Argentina. Analizá este comprobante y extraé TODOS los datos en formato JSON. Devolvé ÚNICAMENTE el JSON sin texto adicional:
{"tipo_operacion":"compra o venta","tipo_comprobante":"A B C M o E","numero_comprobante":"0001-00012345","fecha":"DD/MM/AAAA","razon_social_emisor":"","cuit_emisor":"XX-XXXXXXXX-X","razon_social_receptor":"","cuit_receptor":"XX-XXXXXXXX-X","condicion_iva_emisor":"","neto_gravado_21":0.00,"neto_gravado_105":0.00,"iva_21":0.00,"iva_105":0.00,"no_gravado":0.00,"percepcion_iva":0.00,"percepcion_iibb":0.00,"retencion_ganancias":0.00,"total":0.00,"cae":"","vencimiento_cae":"DD/MM/AAAA","concepto":"","observaciones":""}
Si un campo no figura usá null para texto y 0.00 para números."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("No autorizado.")
        return
    await update.message.reply_text("Hola Fernando! Manda una foto o PDF de factura y la registro en Google Sheets.")

async def procesar_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("No autorizado.")
        return

    await update.message.reply_text("Recivi el comprobante, procesando...")

    try:
        if update.message.photo:
            archivo = await update.message.photo[-1].get_file()
            media_type = "image/jpeg"
            tipo = "image"
            nombre = f"factura_{archivo.file_id}.jpg"
        elif update.message.document:
            archivo = await update.message.document.get_file()
            nombre = update.message.document.file_name
            if nombre.lower().endswith(".pdf"):
                media_type = "application/pdf"
                tipo = "document"
            elif nombre.lower().endswith(".png"):
                media_type = "image/png"
                tipo = "image"
            else:
                media_type = "image/jpeg"
                tipo = "image"
        else:
            await update.message.reply_text("Manda una foto o PDF.")
            return

        contenido_bytes = bytes(await archivo.download_as_bytearray())
        b64 = base64.standard_b64encode(contenido_bytes).decode("utf-8")

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        if tipo == "document":
            contenido = [{"type": "document", "source": {"type": "base64", "media_type": media_type, "data": b64}}, {"type": "text", "text": PROMPT}]
        else:
            contenido = [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}, {"type": "text", "text": PROMPT}]

        await update.message.reply_text("Claude analizando...")

        msg = client.messages.create(model="claude-opus-4-5", max_tokens=1500, messages=[{"role": "user", "content": contenido}])
        texto = msg.content[0].text.strip()

        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0].strip()
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0].strip()

        datos = json.loads(texto)
        datos["imagen_base64"] = b64
        datos["imagen_media_type"] = media_type
        datos["imagen_nombre"] = nombre

        await update.message.reply_text("Registrando en Google Sheets...")

        resp = requests.post(APPS_SCRIPT_URL, json=datos, timeout=60)

        if resp.status_code == 200:
            confirmacion = (
    f"✅ *Factura registrada exitosamente*\n\n"
    f"📋 *Comprobante:* {datos.get('tipo_comprobante')} {datos.get('numero_comprobante')}\n"
    f"🏢 *Emisor:* {datos.get('razon_social_emisor')}\n"
    f"📅 *Fecha:* {datos.get('fecha')}\n"
    f"💰 *Total:* ${datos.get('total')}\n"
    f"🔑 *CAE:* {datos.get('cae')}"
)
await update.message.reply_text(confirmacion, parse_mode="Markdown")
            await update.message.reply_text(confirmacion)
        else:
            await update.message.reply_text(f"Error en Sheets: {resp.text[:200]}")

    except json.JSONDecodeError:
        await update.message.reply_text("Claude no pudo leer la factura. Intentá con foto mas clara.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"Error: {str(e)}")

def main():
    import asyncio
    logger.info("Iniciando bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, procesar_documento))
    logger.info("Bot escuchando...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
