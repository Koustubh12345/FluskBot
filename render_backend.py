import os
import requests
import uuid
from datetime import datetime
import logging
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# --- Configuration ---
TELEGRAM_TOKEN = "8379296931:AAEn1fQnSl4VWsj1ApAvzt7Jvx4vMlL6bgo"
# IMPORTANT: This URL is for your webhook. It must be your live Render URL.
WEBHOOK_URL = "https://fluskbot.onrender.com/webhook" 
PORT = int(os.environ.get('PORT', '5000'))
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # Safer max file size: 50MB

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Initialize Telegram bot
bot = Bot(token=TELEGRAM_TOKEN)
application = Application.builder().token(TELEGRAM_TOKEN).build()

# --- File Utilities ---
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message."""
    await update.message.reply_text('Hi! Send me any file, and I will give you a permanent download link.')

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_object, file_name: str, mime_type: str) -> None:
    """Generic handler for all file types."""
    
    processing_message = await update.message.reply_text('Processing your file...')
    
    file_id = file_object.file_id
    
    try:
        # Get file path from Telegram
        file_info = await context.bot.get_file(file_id)
        file_path = file_info.file_path
        
        # Download file from Telegram's servers
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        response = requests.get(file_url)
        
        if response.status_code == 200:
            # Generate a unique filename and secure it
            unique_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_filename = secure_filename(f"{timestamp}_{unique_id}_{file_name}")
            
            # Save the file directly to our local upload folder
            file_path_local = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            with open(file_path_local, 'wb') as f:
                f.write(response.content)
            
            # Generate the download URL from our Flask app
            download_url = f"{request.host_url}download/{unique_filename}"
            
            # Edit the processing message with the download link
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=processing_message.message_id,
                text=f"✅ File uploaded successfully!\n\n📁 **File**: {file_name}\n🔗 [Download Link]({download_url})",
                parse_mode='Markdown'
            )
            logger.info(f"File '{file_name}' saved and link generated: {download_url}")
        else:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=processing_message.message_id,
                text="❌ Error downloading file from Telegram"
            )
    except Exception as e:
        logger.error(f"Error handling file: {e}", exc_info=True)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=processing_message.message_id,
            text=f"❌ An error occurred: {str(e)}"
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    file = update.message.document
    await handle_file(update, context, file, file.file_name, file.mime_type)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]
    await handle_file(update, context, photo, "photo.jpg", 'image/jpeg')

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    video = update.message.video
    await handle_file(update, context, video, video.file_name or "video.mp4", video.mime_type)

# --- Flask Routes ---
@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Serve files from the upload directory."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check route."""
    return jsonify({"status": "healthy"})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates."""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        application.process_update(update)
    return 'ok'

# --- Main entry point ---
if __name__ == '__main__':
    # Add handlers to the application
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.AUDIO, handle_file))

    # Set the webhook URL
    # This must be done once when the app is started
    bot.setWebhook(WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=PORT)
