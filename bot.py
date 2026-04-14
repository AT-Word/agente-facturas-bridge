import os
import sys
import json
import base64
import logging
import requests
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

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
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
CREDENTIALS_PATH = "/etc/secrets/google_credentials.json"

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

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def subir_a_drive(contenido_bytes, nombre_archivo, media_type):
    try:
        service = get_drive_service()
        file_metadata = {
            "name": nombre_archivo,
            "parents": [DRIVE_FOLDER_ID] if DRIVE_FOLDER_ID else []
        }
        media = MediaIoBaseUpload(
            io.BytesIO(contenido_bytes),
            mimetype=media_type,
            resumable=True
        )
        archivo = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink"
        ).execute()

        # Hacer el archivo público
        service.permissions().create(
            fileId=archivo["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()

        return archivo.get("webViewLink")
    except Exception as e:
        logger.error(f"Error subiendo a Drive: {e}")
        return None

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

        # Subir a Google Drive
        await update.message.reply_text("☁️ Guardando comprobante en Drive...")
        link_drive = subir_a_drive(contenido_bytes, nombre_archivo, media_type)

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
            messages=[{"role": "user", "content": contenido_mensaje}]
        )

        respuesta_texto = mensaje.content[0].text.strip()

        if "```json" in respuesta_texto:
            respuesta_texto = respuesta_texto.split("```json")[1].split("```")[0].strip()
        elif "```" in respuesta_texto:
            respuesta_texto = respuesta_texto.split("```")[1].split("```")[0].strip()

        datos = json.loads(respuesta_texto)

        # Agregar link de Drive al JSON
        if link_drive:
            datos["link_comprobante"] = link_drive

        await update.message.reply_text("📊 Registrando en Google Sheets...")

        respuesta_sheets = requests.post(APPS_SCRIPT_URL, json=datos, timeout=30)

        if respuesta_sheets.status_code == 200:
            confirmacion = (
                f"✅ *Factura registrada exitosamente*\n\n"
                f"📋 *Comprobante:* {datos.get('tipo_comprobante')} {datos.get('numero_comprobante')}\n"
                f"🏢 *Emisor:* {datos.get('razon_social_emisor')}\n"
                f"📅 *Fecha:* {datos.get('fecha')}\n"
                f"💰 *Total:* ${datos.get('total')}\n"
                f"🔑 *CAE:* {datos.get('cae')}\n"
            )
            if link_drive:
                confirmacion += f"📎 [Ver comprobante]({link_drive})"

            await update.message.reply_text(confirmacion, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ Error al registrar en Sheets: {respuesta_sheets.text[:200]}")

    except json.JSONDecodeError:
        await update.message.reply_text("❌ Claude no pudo extraer los datos. Intentá con una foto más clara.")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

def main():
    import asyncio
    logger.info("Iniciando bot de Telegram...")
    logger.info(f"TELEGRAM_TOKEN configurado: {'Sí' if TELEGRAM_TOKEN else 'NO'}")
    logger.info(f"ANTHROPIC_API_KEY configurado: {'Sí' if ANTHROPIC_API_KEY else 'NO'}")
    logger.info(f"APPS_SCRIPT_URL configurado: {'Sí' if APPS_SCRIPT_URL else 'NO'}")
    logger.info(f"DRIVE_FOLDER_ID configurado: {'Sí' if DRIVE_FOLDER_ID else 'NO'}")
    logger.info(f"ALLOWED_USER_ID: {ALLOWED_USER_ID}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, procesar_documento))

    logger.info("Bot iniciado y escuchando...")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
