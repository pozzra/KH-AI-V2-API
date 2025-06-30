import os
import logging
import io
import base64
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# កំណត់រចនាសម្ព័ន្ធការកាប់ឈើ
# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# កំណត់រចនាសម្ព័ន្ធគន្លឹះ API របស់ Telegram និង Gemini
# Configure Telegram and Gemini API keys
TELEGRAM_BOT_TOKEN = "7432484173:AAFY_Xq9B-SVZZ1ro9ergLucG3h4CWe76WI"  # Your actual bot token
GEMINI_API_KEY = "AIzaSyBeDsq-53N0TWKr9XzPQmStEjpsWpnoRPQ" # Gemini API key

# កំណត់រចនាសម្ព័ន្ធម៉ូដែល Gemini
# Configure the Gemini model
genai.configure(api_key=GEMINI_API_KEY)
# Using a specific model for code generation might be beneficial, but gemini-2.0-flash is also capable.
# For better code generation, consider models like 'gemini-pro' if available for your use case and API key.
model = genai.GenerativeModel('gemini-2.0-flash')

# Initialize Google Cloud Speech client
# IMPORTANT: For this to work, you must set the GOOGLE_APPLICATION_CREDENTIALS environment variable
# to the path of your Google Cloud service account key JSON file BEFORE running this script.
# Example for Windows: set GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your\service-account-key.json"
# Example for Linux/macOS: export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
speech_client = None
try:
    # Attempt to initialize SpeechClient only if GOOGLE_APPLICATION_CREDENTIALS is set
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        from google.cloud import speech # Moved import here to avoid NameError if not installed
        speech_client = speech.SpeechClient()
        logger.info("Google Cloud SpeechClient initialized successfully.")
    else:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set. Voice transcription will not work.")
except Exception as e:
    logger.error(f"Failed to initialize Google Cloud SpeechClient. Voice transcription will not work: {e}")
    logger.error("Please ensure you have installed 'google-cloud-speech' and set up Google Cloud credentials as an environment variable.")

# Import PyPDF2 for PDF text extraction
import PyPDF2 # Changed: Import the main PyPDF2 module

# ទិន្នន័យប្រវត្តិជជែកសម្រាប់អ្នកប្រើប្រាស់ម្នាក់ៗ
# Chat history data for each user
user_chat_history = {}

# តាមដានស្ថានភាពអ្នកប្រើប្រាស់ (ឧ. កំពុងរង់ចាំការពិពណ៌នាកូដ)
# Track user state (e.g., awaiting code description, awaiting edited question)
user_bot_state = {} # Stores states like {'user_id': 'awaiting_code_description'}

# មុខងារសម្រាប់ពាក្យបញ្ជា /start
# Function for the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ផ្ញើសារនៅពេលពាក្យបញ្ជា /start ត្រូវបានចេញ។
    បង្ហាញប៊ូតុងម៉ឺនុយនៅខាងក្រោមប្រអប់បញ្ចូលអត្ថបទ (ReplyKeyboardMarkup)
    """
    # Button menu options
    menu_keyboard = [
        ["/voice_to_text", "/pdf_or_img"],
        ["/generate_code", "/edit_last"],
        ["/show_history", "/clear_history"],
        [ "Contact Admin"]  # New button row
    ]
    reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)

    welcome_message = (
        'សួស្តី! ខ្ញុំជារ៉ូបូត AI របស់អ្នក។ តើខ្ញុំអាចជួយអ្វីបាន?\n'
        'អ្នកអាច៖\n'
        '• ផ្ញើសារអត្ថបទមកខ្ញុំដើម្បីជជែក។\n'
        '• ផ្ញើរូបភាពមកខ្ញុំដើម្បីវិភាគ (ឧ. ផ្ញើរូបថត).\n'
        '• ផ្ញើសារជាសំឡេងមកខ្ញុំដើម្បីបំប្លែងទៅជាអត្ថបទ (មុខងារ Speech-to-Text ត្រូវមាន).\n'
        '• ផ្ញើឯកសារ PDF មកខ្ញុំ (ត្រូវការសេវាកម្មទាញយកអត្ថបទ).\n'
        '• ប្រើពាក្យបញ្ជាដើម្បីបង្កើតកូដ។\n\n'
        'ពាក្យបញ្ជាដែលមាន៖\n'
        '• /start - ចាប់ផ្តើមជជែក ឬទទួលបានព័ត៌មាននេះម្តងទៀត។\n'
        '• /voice_to_text - ព័ត៌មានអំពីរបៀបផ្ញើសារជាសំឡេង។\n'
        '• /pdf_or_img - ព័ត៌មានអំពីរបៀបផ្ញើឯកសារ ឬរូបភាព។\n'
        '• /generate_code - បង្កើតកូដផ្អែកលើការពិពណ៌នារបស់អ្នក។\n'
        '• /edit_last - កែសម្រួលសំណួរចុងក្រោយរបស់អ្នក។\n'
        '• /show_history - មើលប្រវត្តិជជែករបស់អ្នក។\n'
        '• /clear_history - លុបប្រវត្តិជជែករបស់អ្នក។'
    )
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

# មុខងារសម្រាប់គ្រប់គ្រងសារអត្ថបទ
# Function for handling text messages
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ឆ្លើយតបទៅនឹងសារអត្ថបទរបស់អ្នកប្រើប្រាស់ដោយប្រើម៉ូដែល Gemini ឬដំណើរការសំណើកូដ/កែសម្រួល។"""
    # Respond to user text messages using the Gemini model or process code/edit requests.
    user_id = update.effective_user.id
    user_message = update.message.text
    logger.info(f"Received text message from {user_id}: {user_message}")

    # Handle Contact Admin button
    if user_message.strip() == "Contact Admin":
        await update.message.reply_text("ទំនាក់ទំនងអេដមិន៖ @kun_amra")
        return

    # ពិនិត្យមើលស្ថានភាពអ្នកប្រើប្រាស់សម្រាប់សំណើកូដ
    # Check user state for code generation request
    if user_bot_state.get(user_id) == 'awaiting_code_description':
        await generate_code_response(update, context, user_message)
        user_bot_state[user_id] = None # Reset state after handling
        return
    
    # ពិនិត្យមើលស្ថានភាពអ្នកប្រើប្រាស់សម្រាប់សំណើកែសម្រួលសំណួរ
    # Check user state for edit question request
    if user_bot_state.get(user_id) == 'awaiting_edited_question':
        await process_edited_question(update, context, user_message)
        user_bot_state[user_id] = None # Reset state after handling
        return

    # បង្ហាញសារកំពុងគិតសម្រាប់សារជជែកធម្មតា។
    # Show thinking message for regular chat messages
    thinking_message = await update.message.reply_text("រ៉ូបូតកំពុងគិត... សូមរង់ចាំបន្តិច។") # Bot is thinking... Please wait a moment.

    try:
        # បន្ថែមសារអ្នកប្រើប្រាស់ទៅក្នុងប្រវត្តិ
        # Add user message to history
        if user_id not in user_chat_history:
            user_chat_history[user_id] = []
        user_chat_history[user_id].append({"role": "user", "parts": [{"text": user_message}]})

        # ផ្ញើសារទៅម៉ូដែល Gemini ជាមួយនឹងប្រវត្តិ
        # Send message to Gemini model with history
        chat_session = model.start_chat(history=user_chat_history[user_id])
        response = chat_session.send_message(user_message)
        ai_response = response.text
        logger.info(f"Gemini response: {ai_response}")

        # បន្ថែមសាររ៉ូបូតទៅក្នុងប្រវត្តិ
        # Add bot message to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

        # ផ្ញើការឆ្លើយតបទៅអ្នកប្រើប្រាស់
        # Send the response back to the user
        await thinking_message.edit_text(ai_response) # Edit the thinking message with the actual response
    except Exception as e:
        logger.error(f"Error generating content from Gemini for text: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការសារអត្ថបទរបស់អ្នក។ '
            'សូមពិនិត្យមើល Gemini API Key របស់អ្នក និងការតភ្ជាប់អ៊ីនធឺណិត។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your text message.
        # Please check your Gemini API Key and internet connection.
        # Please try again later.

# មុខងារសម្រាប់គ្រប់គ្រងការផ្ទុករូបភាព
# Function for handling image uploads
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ដំណើរការរូបថតដែលបានផ្ទុកឡើងដោយប្រើម៉ូដែល Gemini."""
    # Process uploaded photos using the Gemini model.
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("សុំទោស ខ្ញុំមិនអាចរកឃើញរូបថតបានទេ។")
        return

    # Check image file size (limit: 5MB)
    max_image_size = 5 * 1024 * 1024  # 5MB
    file_id = update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    if file.file_size > max_image_size:
        await update.message.reply_text("សុំទោស រូបភាពធំពេក (លើស 5MB)។ សូមផ្ញើរូបភាពដែលមានទំហំតិចជាង 5MB។")
        return

    # ទទួលបានរូបថតដែលមានគុណភាពខ្ពស់បំផុត
    # Get the highest quality photo
    logger.info(f"Received photo with file_id: {file_id}")

    # បង្ហាញសារកំពុងគិត
    # Show thinking message
    thinking_message = await update.message.reply_text("រ៉ូបូតកំពុងដំណើរការរូបភាពរបស់អ្នក... សូមរង់ចាំបន្តិច។") # Bot is processing your image... Please wait a moment.

    try:
        # ទាញយករូបថត
        # Download the photo
        file = await context.bot.get_file(file_id)
        photo_bytes = io.BytesIO()
        await file.download_to_memory(photo_bytes)
        photo_bytes.seek(0) # កំណត់ទីតាំងទស្សន៍ទ្រនិចទៅដើមឯកសារ
        
        # Base64 encode the image
        base64_image = base64.b64encode(photo_bytes.getvalue()).decode('utf-8')

        # បង្កើតមាតិកាសម្រាប់ម៉ូដែល Gemini (អត្ថបទនិងទិន្នន័យក្នុងបន្ទាត់)
        # Create content for the Gemini model (text and inline data)
        image_parts = {
            "inline_data": {
                "mime_type": "image/jpeg", # Assuming JPEG, can be dynamic if needed
                "data": base64_image
            }
        }
        user_content_parts = [{"text": "តើរូបភាពនេះបង្ហាញអ្វី?"}, image_parts] # Default prompt for image

        # បន្ថែមសារអ្នកប្រើប្រាស់ (រូបភាព) ទៅក្នុងប្រវត្តិ
        # Add user message (image) to history
        if user_id not in user_chat_history:
            user_chat_history[user_id] = []
        user_chat_history[user_id].append({"role": "user", "parts": user_content_parts})

        # ផ្ញើការសាកសួរទៅម៉ូដែល Gemini ជាមួយនឹងប្រវត្តិ
        # Send query to Gemini model with history
        chat_session = model.start_chat(history=user_chat_history[user_id])
        response = chat_session.send_message(user_content_parts)
        ai_response = response.text
        logger.info(f"Gemini response for photo: {ai_response}")

        # បន្ថែមសាររ៉ូបូតទៅក្នុងប្រវត្តិ
        # Add bot message to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

        await thinking_message.edit_text(ai_response) # Edit the thinking message with the actual response

    except Exception as e:
        logger.error(f"Error handling photo with Gemini: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការរូបភាពរបស់អ្នក។ '
            'សូមពិនិត្យមើល Gemini API Key របស់អ្នក និងការតភ្ជាប់អ៊ីនធឺណិត។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your image.
        # Please check your Gemini API Key and internet connection.
        # Please try again later.

# មុខងារសម្រាប់បំប្លែងសំឡេងទៅជាអត្ថបទដោយប្រើ Google Cloud Speech-to-Text
# Function to transcribe audio using Google Cloud Speech-to-Text
async def transcribe_audio(audio_bytes: bytes) -> str:
    """ប្រើ Google Cloud Speech-to-Text ដើម្បីបំប្លែងបៃអូឌីយ៉ូទៅជាអត្ថបទ។"""
    # Use Google Cloud Speech-to-Text to transcribe audio bytes to text.
    if not speech_client:
        raise Exception("Google Cloud SpeechClient is not initialized. Cannot transcribe audio.")

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS, # Telegram voice messages are typically OGG_OPUS
        sample_rate_hertz=16000, # Common sample rate for voice
        language_code="km-KH", # Cambodian Khmer. Adjust as needed for other languages
    )

    try:
        # Note: speech_client.recognize_async is genuinely async and needs await
        response = await speech_client.recognize_async(config=config, audio=audio)
        if response.results:
            # Get the most likely transcription
            return response.results[0].alternatives[0].transcript
        return ""
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}", exc_info=True) # Log full exception info
        raise

# មុខងារសម្រាប់គ្រប់គ្រងសារជាសំឡេង
# Function for handling voice messages
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """បំប្លែងសារជាសំឡេងទៅជាអត្ថបទ និងឆ្លើយតបដោយប្រើម៉ូដែល Gemini។"""
    # Transcribe voice messages to text and respond using the Gemini model.
    user_id = update.effective_user.id
    if not update.message.voice:
        # If this function is called via /voice_to_text command, it won't have a voice message directly.
        await update.message.reply_text(
            'សូមផ្ញើសារជាសំឡេងរបស់អ្នកមកខ្ញុំដោយផ្ទាល់។\n'
            'ដើម្បីឱ្យខ្ញុំអាចឆ្លើយតបបាន ខ្ញុំត្រូវការសេវាកម្មបំប្លែងសំឡេងទៅជាអត្ថបទ (Speech-to-Text) ដើម្បីបំប្លែងវាទៅជាអត្ថបទជាមុនសិន។'
        )
        return
    
    voice_file_id = update.message.voice.file_id
    logger.info(f"Received voice message with file_id: {voice_file_id}")
    
    if not speech_client:
        await update.message.reply_text('សុំទោស សេវាកម្មបំប្លែងសំឡេងទៅជាអត្ថបទមិនទាន់ត្រូវបានកំណត់រចនាសម្ព័ន្ធត្រឹមត្រូវទេ។')
        # Sorry, the Speech-to-Text service is not properly configured.
        return

    # បង្ហាញសារកំពុងគិត
    # Show thinking message
    thinking_message = await update.message.reply_text("រ៉ូបូតកំពុងបំប្លែងសំឡេងរបស់អ្នកទៅជាអត្ថបទ... សូមរង់ចាំបន្តិច។") # Bot is transcribing your voice... Please wait a moment.

    try:
        file = await context.bot.get_file(voice_file_id)  # FIXED: use voice_file_id
        voice_bytes = io.BytesIO()
        await file.download_to_memory(voice_bytes)
        voice_bytes.seek(0)

        # Echo the user's voice message back
        voice_bytes.seek(0)
        await update.message.reply_voice(voice=voice_bytes)

        transcribed_text = await transcribe_audio(voice_bytes.getvalue())
        
        if transcribed_text:
            await thinking_message.edit_text(f"អត្ថបទដែលបានបំប្លែង: {transcribed_text}\n\nរ៉ូបូតកំពុងឆ្លើយតប...") # Edit with transcribed text and thinking message
            logger.info(f"Transcribed text: {transcribed_text}")

            # បន្ថែមអត្ថបទដែលបានបំប្លែងទៅក្នុងប្រវត្តិ
            # Add transcribed text to history
            if user_id not in user_chat_history:
                user_chat_history[user_id] = []
            user_chat_history[user_id].append({"role": "user", "parts": [{"text": transcribed_text}]})

            # ផ្ញើអត្ថបទដែលបានបំប្លែងទៅម៉ូដែល Gemini ជាមួយនឹងប្រវត្តិ
            # Send the transcribed text to the Gemini model with history
            chat_session = model.start_chat(history=user_chat_history[user_id])
            response = chat_session.send_message(transcribed_text)
            ai_response = response.text
            logger.info(f"Gemini response for voice: {ai_response}")

            # បន្ថែមសាររ៉ូបូតទៅក្នុងប្រវត្តិ
            # Add bot message to history
            user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

            await thinking_message.edit_text(f"អត្ថបទដែលបានបំប្លែង: {transcribed_text}\n\n{ai_response}") # Edit with transcribed text and AI response
        else:
            await thinking_message.edit_text("ខ្ញុំមិនអាចបំប្លែងសំឡេងទៅជាអត្ថបទបានទេ។ សូមព្យាយាមម្តងទៀត។")
            # I could not transcribe the voice to text. Please try again.

    except Exception as e:
        logger.error(f"Error handling voice message: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការសារជាសំឡេងរបស់អ្នក។ '
            'សូមពិនិត្យមើលការកំណត់រចនាសម្ព័ន្ធ Speech-to-Text API របស់អ្នក។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your voice message.
        # Please check your Speech-to-Text API configuration.
        # Please try again later.

# មុខងារសម្រាប់គ្រប់គ្រងឯកសារ PDF
# Function for handling PDF documents
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ទាញយកអត្ថបទពីឯកសារ PDF និងឆ្លើយតបដោយប្រើម៉ូដែល Gemini."""
    # Extract text from PDF document and respond using the Gemini model.
    user_id = update.effective_user.id
    if not update.message.document or not update.message.document.mime_type == 'application/pdf':
        await update.message.reply_text("សុំទោស ខ្ញុំមិនអាចរកឃើញឯកសារ PDF បានទេ។")
        return

    # Check PDF file size (limit: 10MB)
    max_pdf_size = 10 * 1024 * 1024  # 10MB
    if update.message.document.file_size > max_pdf_size:
        await update.message.reply_text("សុំទោស ឯកសារ PDF ធំពេក (លើស 10MB)។ សូមផ្ញើឯកសារដែលមានទំហំតិចជាង 10MB។")
        return

    file_id = update.message.document.file_id
    file_name = update.message.document.file_name
    logger.info(f"Received PDF document: {file_name} with file_id: {file_id}")

    # បង្ហាញសារកំពុងគិត
    # Show thinking message
    thinking_message = await update.message.reply_text(f"រ៉ូបូតកំពុងដំណើរការឯកសារ PDF ({file_name})... សូមរង់ចាំបន្តិច។") # Bot is processing your PDF... Please wait a moment.

    try:
        file = await context.bot.get_file(file_id)
        pdf_bytes = io.BytesIO()
        await file.download_to_memory(pdf_bytes)
        pdf_bytes.seek(0)

        # Using PdfReader from PyPDF2
        pdf_reader = PyPDF2.PdfReader(pdf_bytes) # Corrected: Use PyPDF2.PdfReader directly
        pdf_text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            pdf_text += page.extract_text() + "\n"
        
        if pdf_text:
            # Limit text length to avoid exceeding Gemini's token limits for now
            # For very large PDFs, consider summarizing or processing in chunks
            max_text_length = 5000 # Adjust as needed
            processed_text = pdf_text[:max_text_length]
            if len(pdf_text) > max_text_length:
                processed_text += "\n[អត្ថបទត្រូវបានកាត់បន្ថយដោយសារទំហំធំ]" # Text truncated due to size

            # Telegram message length limit is 4096 characters
            def safe_edit_text(message_obj, text, **kwargs):
                max_len = 4096
                if len(text) > max_len:
                    text = text[:max_len-50] + '\n\n[សារ​ត្រូវ​បាន​កាត់បន្ថយ​ដោយសារទំហំ​ធំ]' # Message truncated due to size
                return message_obj.edit_text(text, **kwargs)

            await safe_edit_text(thinking_message, f"បានទាញយកអត្ថបទពី PDF:\n\n{processed_text}\n\nរ៉ូបូតកំពុងឆ្លើយតប...") # Edit with extracted text and thinking message
            logger.info(f"Extracted text from PDF (first {len(processed_text)} chars): {processed_text[:200]}...") # Log only first 200 chars

            # បន្ថែមអត្ថបទដែលបានទាញយកទៅក្នុងប្រវត្តិ
            # Add extracted text to history
            if user_id not in user_chat_history:
                user_chat_history[user_id] = []
            user_chat_history[user_id].append({"role": "user", "parts": [{"text": f"Please analyze this PDF content:\n\n{processed_text}"}]})

            # ផ្ញើអត្ថបទដែលបានទាញយកទៅម៉ូដែល Gemini ជាមួយនឹងប្រវត្តិ
            # Send the extracted text to the Gemini model with history
            chat_session = model.start_chat(history=user_chat_history[user_id])
            response = chat_session.send_message(f"Please analyze this PDF content:\n\n{processed_text}") # Prompt Gemini to analyze
            ai_response = response.text
            logger.info(f"Gemini response for PDF: {ai_response}")
            
            # បន្ថែមសាររ៉ូបូតទៅក្នុងប្រវត្តិ
            # Add bot message to history
            user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

            await safe_edit_text(thinking_message, f"ការវិភាគ PDF របស់ខ្ញុំ៖\n\n{ai_response}") # My PDF analysis:
        else:
            await thinking_message.edit_text("ខ្ញុំមិនអាចទាញយកអត្ថបទពីឯកសារ PDF នេះបានទេ។")
            # I could not extract text from this PDF document.

    except PyPDF2.errors.PdfReadError: # Corrected: Access PdfReadError via PyPDF2.errors
        logger.error(f"Invalid PDF file: {file_name}", exc_info=True) # Log full exception info
        await thinking_message.edit_text("សុំទោស នេះមិនមែនជាឯកសារ PDF ត្រឹមត្រូវទេ។")
        # Sorry, this is not a valid PDF document.
    except Exception as e:
        logger.error(f"Error handling PDF with Gemini: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text('សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការឯកសារ PDF របស់អ្នក។ សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។')
        # Sorry, an error occurred while processing your PDF document. Please try again later.

# មុខងារសម្រាប់ពាក្យបញ្ជា /pdf_or_img
# Function for the /pdf_or_img command
async def handle_document_and_photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ផ្តល់ការណែនាំអំពីរបៀបផ្ញើរូបភាព ឬឯកសារ PDF។"""
    # Provide instructions on how to send images or PDF documents.
    await update.message.reply_text(
        'សូមផ្ញើរូបភាព ឬឯកសារ PDF របស់អ្នកមកខ្ញុំដោយផ្ទាល់។\n'
        'រូបភាពនឹងត្រូវបានវិភាគដោយ AI។ ឯកសារ PDF នឹងត្រូវបានដំណើរការដើម្បីទាញយកអត្ថបទ។'
    )

# មុខងារសម្រាប់ពាក្យបញ្ជា /generate_code
# Function for the /generate_code command
async def generate_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ប្រាប់អ្នកប្រើប្រាស់ឱ្យផ្តល់ការពិពណ៌នាកូដ និងកំណត់ស្ថានភាព។"""
    # Prompt the user to provide code description and set the state.
    user_id = update.effective_user.id
    user_bot_state[user_id] = 'awaiting_code_description'
    await update.message.reply_text(
        'តើអ្នកចង់ឱ្យខ្ញុំបង្កើតកូដអ្វី? សូមផ្តល់ការពិពណ៌នាលំអិត។' # What code do you want me to generate? Please provide a detailed description.
    )

# មុខងារសម្រាប់បង្កើតកូដដោយផ្អែកលើការពិពណ៌នា
# Function to generate code based on description
async def generate_code_response(update: Update, context: ContextTypes.DEFAULT_TYPE, code_description: str) -> None:
    """ប្រើ Gemini ដើម្បីបង្កើតកូដផ្អែកលើការពិពណ៌នារបស់អ្នកប្រើប្រាស់។"""
    # Use Gemini to generate code based on user's description.
    user_id = update.effective_user.id
    logger.info(f"Generating code for {user_id} with description: {code_description}")

    thinking_message = await update.message.reply_text("រ៉ូបូតកំពុងបង្កើតកូដ... សូមរង់ចាំបន្តិច។") # Bot is generating code... Please wait a moment.

    try:
        # បន្ថែមការពិពណ៌នាកូដទៅក្នុងប្រវត្តិ
        # Add code description to history
        if user_id not in user_chat_history:
            user_chat_history[user_id] = []
        user_chat_history[user_id].append({"role": "user", "parts": [{"text": f"Generate code for the following:\n\n{code_description}\n\nPlease provide the code in a Markdown code block with language specified."}]})

        chat_session = model.start_chat(history=user_chat_history[user_id])
        
        # សំណូមពរជាក់លាក់សម្រាប់ម៉ូដែលដើម្បីបង្កើតកូដ
        # Specific prompt for the model to generate code
        response = chat_session.send_message(f"Generate code for the following:\n\n{code_description}\n\nPlease provide the code in a Markdown code block with language specified.")
        
        generated_code = response.text
        logger.info(f"Gemini generated code: {generated_code[:200]}...") # Log first 200 chars

        # បន្ថែមកូដដែលបានបង្កើតទៅក្នុងប្រវត្តិ
        # Add generated code to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": generated_code}]})

        await thinking_message.edit_text(f"នេះជាកូដដែលបានបង្កើតរបស់អ្នក:\n\n{generated_code}") # Here is your generated code.

    except Exception as e:
        logger.error(f"Error generating code with Gemini: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលបង្កើតកូដរបស់អ្នក។ '
            'សូមពិនិត្យមើល Gemini API Key របស់អ្នក និងការតភ្ជាប់អ៊ីនធឺណិត។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while generating your code.
        # Please check your Gemini API Key and internet connection.
        # Please try again later.

# មុខងារសម្រាប់ពាក្យបញ្ជា /edit_last
# Function for the /edit_last command
async def edit_last_question_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ប្រាប់អ្នកប្រើប្រាស់ឱ្យផ្តល់សំណួរដែលបានកែសម្រួល។"""
    # Prompt the user to provide the edited question.
    user_id = update.effective_user.id
    if user_id not in user_chat_history or not user_chat_history[user_id]:
        await update.message.reply_text('អ្នកមិនមានសំណួរចុងក្រោយដើម្បីកែសម្រួលទេ។') # You don't have a last question to edit.
        return

    # កំណត់ស្ថានភាពរង់ចាំសម្រាប់សំណួរដែលបានកែសម្រួល
    # Set the state to await the edited question
    user_bot_state[user_id] = 'awaiting_edited_question'
    await update.message.reply_text(
        'សូមផ្ញើសំណួរដែលបានកែសម្រួលរបស់អ្នក។ ខ្ញុំនឹងប្រើវាជំនួសសំណួរចុងក្រោយរបស់អ្នក។' # Please send your corrected question. I will use it to replace your last question.
    )

# មុខងារសម្រាប់ដំណើរការសំណួរដែលបានកែសម្រួល
# Function to process the edited question
async def process_edited_question(update: Update, context: ContextTypes.DEFAULT_TYPE, edited_question: str) -> None:
    """ជំនួសសំណួរចុងក្រោយក្នុងប្រវត្តិ និងដំណើរការម្តងទៀត។"""
    # Replace the last question in history and re-process.
    user_id = update.effective_user.id
    logger.info(f"Processing edited question for {user_id}: {edited_question}")

    thinking_message = await update.message.reply_text("រ៉ូបូតកំពុងដំណើរការសំណួរដែលបានកែសម្រួលរបស់អ្នក... សូមរង់ចាំបន្តិច។") # Bot is processing your edited question... Please wait a moment.

    try:
        if user_id in user_chat_history and user_chat_history[user_id]:
            # រកមើលសារអ្នកប្រើប្រាស់ចុងក្រោយក្នុងប្រវត្តិ
            # Find the last user message in history
            last_user_message_index = -1
            for i in range(len(user_chat_history[user_id]) - 1, -1, -1):
                if user_chat_history[user_id][i]["role"] == "user":
                    last_user_message_index = i
                    break
            
            if last_user_message_index != -1:
                # ជំនួសសារអ្នកប្រើប្រាស់ចុងក្រោយ
                # Replace the last user message
                user_chat_history[user_id][last_user_message_index] = {"role": "user", "parts": [{"text": edited_question}]}
                # លុបសាររ៉ូបូតបន្ទាប់ពីសារអ្នកប្រើប្រាស់ដែលបានកែសម្រួល (ប្រសិនបើមាន)
                # Remove bot's response after the edited user message (if any)
                if last_user_message_index + 1 < len(user_chat_history[user_id]) and user_chat_history[user_id][last_user_message_index + 1]["role"] == "model":
                    del user_chat_history[user_id][last_user_message_index + 1]

                # ផ្ញើសំណួរដែលបានកែសម្រួលទៅម៉ូដែល Gemini ជាមួយនឹងប្រវត្តិដែលបានធ្វើបច្ចុប្បន្នភាព
                # Send the edited question to Gemini with updated history
                chat_session = model.start_chat(history=user_chat_history[user_id])
                response = chat_session.send_message(edited_question)
                ai_response = response.text
                logger.info(f"Gemini response for edited question: {ai_response}")

                # បន្ថែមការឆ្លើយតបថ្មីរបស់រ៉ូបូតទៅក្នុងប្រវត្តិ
                # Add new bot response to history
                user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

                await thinking_message.edit_text(f"សំណួររបស់អ្នកត្រូវបានកែសម្រួល និងដំណើរការឡើងវិញ។\n\nការឆ្លើយតបថ្មី៖ {ai_response}") # Your question has been edited and reprocessed. New response:
            else:
                await thinking_message.edit_text("មិនអាចរកឃើញសំណួរចុងក្រោយរបស់អ្នកក្នុងប្រវត្តិដើម្បីកែសម្រួលទេ។") # Could not find your last question in history to edit.
        else:
            await thinking_message.edit_text("អ្នកមិនមានប្រវត្តិជជែកទេ។") # You don't have chat history.

    except Exception as e:
        logger.error(f"Error processing edited question: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការសំណួរដែលបានកែសម្រួលរបស់អ្នក។ '
            'សូមពិនិត្យមើល Gemini API Key របស់អ្នក និងការតភ្ជាប់អ៊ីនធឺណិត។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your edited question.
        # Please check your Gemini API Key and internet connection.
        # Please try again later.

# មុខងារសម្រាប់បង្ហាញប្រវត្តិជជែក
# Function for displaying chat history
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """បង្ហាញប្រវត្តិជជែកសម្រាប់អ្នកប្រើប្រាស់បច្ចុប្បន្ន។"""
    # Display chat history for the current user.
    user_id = update.effective_user.id
    if user_id in user_chat_history and user_chat_history[user_id]:
        history_text = "ប្រវត្តិជជែករបស់អ្នក:\n\n" # Your chat history:
        for entry in user_chat_history[user_id]:
            role = "អ្នក" if entry["role"] == "user" else "រ៉ូបូត" # You or Bot
            # Assuming 'parts' contains a list of dicts, each with a 'text' key
            # Join all text parts if there are multiple (e.g., for multi-modal input)
            content = " ".join([part["text"] for part in entry["parts"] if "text" in part])
            history_text += f"**{role}**: {content}\n\n"
        
        # Telegram message length limit is 4096 characters
        if len(history_text) > 4000:
            history_text = history_text[:3900] + "\n\n[ប្រវត្តិត្រូវបានកាត់បន្ថយដោយសារទំហំធំ]" # History truncated due to size

        await update.message.reply_text(history_text, parse_mode='Markdown')
    else:
        await update.message.reply_text('អ្នកមិនទាន់មានប្រវត្តិជជែកនៅឡើយទេ។') # You don't have any chat history yet.

# មុខងារសម្រាប់ពាក្យបញ្ជា /clear_history
# Function for the /clear_history command
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """លុបប្រវត្តិជជែកសម្រាប់អ្នកប្រើប្រាស់បច្ចុប្បន្ន។"""
    # Clear chat history for the current user.
    user_id = update.effective_user.id
    if user_id in user_chat_history:
        del user_chat_history[user_id]
        user_bot_state[user_id] = None # Clear any pending state
        await update.message.reply_text('ប្រវត្តិជជែករបស់អ្នកត្រូវបានលុប។ យើងអាចចាប់ផ្តើមការសន្ទនាថ្មី។')
        # Your chat history has been cleared. We can start a new conversation.
    else:
        await update.message.reply_text('អ្នកមិនមានប្រវត្តិជជែកដើម្បីលុបទេ។')
        # You don't have any chat history to clear.

async def set_telegram_commands(application: Application):
    """កំណត់ពាក្យបញ្ជាសម្រាប់រ៉ូបូត Telegram ។"""
    # Set the commands for the Telegram bot.
    commands = [
        BotCommand("start", "ចាប់ផ្តើមជជែក / ទទួលបានព័ត៌មាន"), # Start chat / Get info
        BotCommand("voice_to_text", "បំប្លែងសំឡេងទៅជាអត្ថបទ"), # Convert voice to text
        BotCommand("pdf_or_img", "ព័ត៌មានរូបភាព/ឯកសារ PDF"), # Image/PDF info
        BotCommand("generate_code", "បង្កើតកូដ"), # Generate code
        BotCommand("edit_last_q", "កែសម្រួលសំណួរចុងក្រោយ"), # Edit last question
        BotCommand("show_history", "មើលប្រវត្តិជជែក"), # View chat history
        BotCommand("clear_history", "លុបប្រវត្តិជជែក") # Clear chat history
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Telegram commands set successfully.")

def main() -> None:
    """ដំណើរការរ៉ូបូត។"""
    # Run the bot.
    # បង្កើតកម្មវិធីនិងបញ្ជូនសញ្ញាសម្គាល់រ៉ូបូតរបស់អ្នក
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # បញ្ជូនអ្នកគ្រប់គ្រងផ្សេងគ្នា
    # On different commands, answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("voice_to_text", handle_voice))
    application.add_handler(CommandHandler("pdf_or_img", handle_document_and_photo_command))
    application.add_handler(CommandHandler("generate_code", generate_code_command)) # New handler for code generation
    application.add_handler(CommandHandler("edit_last_q", edit_last_question_command)) # New handler for editing last question
    application.add_handler(CommandHandler("show_history", show_history)) # New handler for showing history
    application.add_handler(CommandHandler("clear_history", clear_history)) # Handler for clearing history

    # អ្នកគ្រប់គ្រងសម្រាប់សារអត្ថបទដែលបានកែសម្រួល
    # Handler for edited text messages
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & ~filters.COMMAND, handle_edited_text_message))

    # នៅលើសារអត្ថបទដែលមិនមែនជាពាក្យបញ្ជា ឆ្លើយតបដោយប្រើ handle_text_message
    # On non-command text messages, respond with handle_text_message
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # អ្នកគ្រប់គ្រងសម្រាប់រូបថត
    # Handler for photos (will trigger for direct photo uploads)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # អ្នកគ្រប់គ្រងសម្រាប់សារជាសំឡេង
    # Handler for voice messages (will trigger for direct voice uploads)
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # អ្នកគ្រប់គ្រងសម្រាប់ឯកសារ PDF
    # Handler for PDF documents (will trigger for direct PDF uploads)
    application.add_handler(MessageHandler(filters.Document.MimeType("application/pdf"), handle_pdf))
    
    # កំណត់ពាក្យបញ្ជារ៉ូបូត Telegram នៅពេលចាប់ផ្តើម
    # Set Telegram bot commands on startup
    application.add_handler(CommandHandler("setcommands", set_telegram_commands_handler)) # A temporary handler to call set_telegram_commands

    # ចាប់ផ្តើមរ៉ូបូត
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# មុខងារអ្នកគ្រប់គ្រងសម្រាប់ set_telegram_commands
# Handler function for set_telegram_commands
async def set_telegram_commands_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ហៅមុខងារដើម្បីកំណត់ពាក្យបញ្ជារ៉ូបូត Telegram ។"""
    # Call the function to set Telegram bot commands.
    await set_telegram_commands(context.application)
    await update.message.reply_text("ពាក្យបញ្ជារ៉ូបូត Telegram ត្រូវបានកំណត់។")
    # Telegram bot commands have been set.

# មុខងារសម្រាប់គ្រប់គ្រងសារអត្ថបទដែលបានកែសម្រួល
# Function for handling edited text messages
async def handle_edited_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ដំណើរការសារអត្ថបទដែលបានកែសម្រួលដោយលុបការសន្ទនាចុងក្រោយ និងដំណើរការសារដែលបានកែសម្រួលជាថ្មី។"""
    # Process edited text messages by removing the last turn and reprocessing the edited message.
    user_id = update.effective_user.id
    edited_message_text = update.edited_message.text
    logger.info(f"Received edited text message from {user_id}: {edited_message_text}")

    # បង្ហាញសារកំពុងគិត
    # Show thinking message
    thinking_message = await update.edited_message.reply_text("រ៉ូបូតកំពុងដំណើរការសារដែលបានកែសម្រួលរបស់អ្នក... សូមរង់ចាំបន្តិច។") # Bot is processing your edited message... Please wait a moment.

    try:
        # លុបការសន្ទនាចុងក្រោយ (សារអ្នកប្រើប្រាស់ + ការឆ្លើយតបរបស់រ៉ូបូត) ប្រសិនបើមាន
        # Remove the last turn (user message + bot response) if it exists
        if user_id in user_chat_history and len(user_chat_history[user_id]) >= 2:
            if user_chat_history[user_id][-1]["role"] == "model" and user_chat_history[user_id][-2]["role"] == "user":
                user_chat_history[user_id].pop() # លុបការឆ្លើយតបរបស់រ៉ូបូត
                user_chat_history[user_id].pop() # លុបសារអ្នកប្រើប្រាស់ដើម
                logger.info(f"Removed last user-bot turn for {user_id} due to message edit for re-processing.")
            else:
                logger.warning(f"Could not easily determine last user-bot turn for {user_id} to remove after edit. History may be inconsistent.")
        elif user_id in user_chat_history and len(user_chat_history[user_id]) == 1 and user_chat_history[user_id][-1]["role"] == "user":
            # In case only the user's message is in history and they edit it before bot responds
            user_chat_history[user_id].pop()
            logger.info(f"Removed last user message for {user_id} as it was the only entry and was edited.")

        # បន្ថែមសារដែលបានកែសម្រួលទៅក្នុងប្រវត្តិជាសារអ្នកប្រើប្រាស់ថ្មី។
        # Add the edited message to history as a new user message.
        if user_id not in user_chat_history:
            user_chat_history[user_id] = []
        user_chat_history[user_id].append({"role": "user", "parts": [{"text": edited_message_text}]})

        # ផ្ញើសារដែលបានកែសម្រួលទៅម៉ូដែល Gemini ជាមួយនឹងប្រវត្តិដែលបានធ្វើបច្ចុប្បន្នភាព
        # Send the edited message to Gemini with updated history
        chat_session = model.start_chat(history=user_chat_history[user_id])
        response = chat_session.send_message(edited_message_text)
        ai_response = response.text
        logger.info(f"Gemini response for edited message: {ai_response}")

        # បន្ថែមការឆ្លើយតបរបស់រ៉ូបូតទៅក្នុងប្រវត្តិ
        # Add bot response to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

        await thinking_message.edit_text(f"សាររបស់អ្នកត្រូវបានកែសម្រួល និងដំណើរការឡើងវិញ។\n\nការឆ្លើយតបថ្មី៖ {ai_response}") # Your message has been edited and reprocessed. New response:

    except Exception as e:
        logger.error(f"Error handling edited text message with Gemini: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការសារដែលបានកែសម្រួលរបស់អ្នក។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your edited message.
        # Please try again later.

if __name__ == "__main__":
    main()