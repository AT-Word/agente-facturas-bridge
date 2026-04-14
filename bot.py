import os
import sys
import json
import base64
import logging
import requests
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

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

async def procesar_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ No autorizado.")
        return

    await update.message.reply_text("📄 Recibí el comprobante, procesando...")

    try:
        if update.message.photo:
            archivo = await update.message.photo[-1].get_file()
            media_type = "image/jpeg"
            tipo = "image"
            nombre_archivo = f"factura_{archivo.file_id}.jpg"
        elif update.message.document:
            archivo = await update.message.document.get_file()
            nombre_archivo = update.message.document.file_name
            nombre_lower = nombre_archivo.lower()
            if nombre_lower.endswith(".pdf"):
                media_type = "application/pdf"
                tipo = "document"
            elif nombre_lower.endswith(".png"):
                media_type = "image/png"
                tipo = "image"
            else:
                media_type = "image/jpeg"
                tipo = "image"
        else:
            await update.message.reply_text("❌ Mandame una foto o PDF de la factura.")
            return

        contenido_bytes = bytes(await archivo.download_as_bytearray())
        datos_b64 = base64.standard_b64encode(contenido_bytes).decode("utf-8")

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        if tipo == "document":
            contenido_mensaje = [
                {"type": "document", "source": {"type": "base64", "media_type": media_type, "data": datos_b64}},
                {"type": "text", "text": PROMPT_EXTRACCION}
            ]
        else:
            contenido_mensaje = [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": datos_b64}},
                {"type": "text", "text": PROMPT_EXTRACCION}
            ]

        await update.message.reply_text("🤖 Claude está analizando el comprobante...")

        mensaje = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": contenido_me
