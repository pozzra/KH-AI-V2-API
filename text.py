import os
import logging
import io
import base64
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import speech_recognition as sr
import re
try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None
    logging.warning('pydub is not installed. Voice to text conversion will not work. Install it with: pip install pydub')
from datetime import datetime
try:
    from PIL import Image
except ImportError:
    Image = None
    logging.warning('Pillow (PIL) is not installed. Image generation will not work. Install it with: pip install pillow')
from io import BytesIO

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

# Directory to save voice files
VOICE_DIR = 'voices'
os.makedirs(VOICE_DIR, exist_ok=True)

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
        [ "Contact Admin"]  # New button row
    ]
    reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)

    # Safely get user name for welcome message
    user = update.effective_user
    if user is not None:
        first_name = user.first_name or ""
        last_name = user.last_name or ""
    else:
        first_name = ""
        last_name = ""
    welcome_message = (
        f'សួស្តី! {first_name} {last_name} ខ្ញុំជា KH AI V2 របស់អ្នក។ តើខ្ញុំអាចជួយអ្វីបាន?\n'
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
        '• /generate_image - បង្កើតរូបភាពផ្អែកលើការពិពណ៌នារបស់អ្នក។\n'
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

    # Check user state for image generation request
    if user_bot_state.get(user_id) == 'awaiting_image_description':
        user_bot_state[user_id] = None
        if Image is None:
            await update.message.reply_text('Pillow (PIL) មិនត្រូវបានដំឡើងទេ។ សូមដំឡើងវាជាមុនសិន៖ pip install pillow')
            return
        try:
            thinking_message = await update.message.reply_text("KH AI V2 កំពុងបង្កើតរូបភាព... សូមរង់ចាំបន្តិច។")
            image_bytes, caption = gemini_generate_image(user_message)
            if image_bytes:
                image = BytesIO(image_bytes)
                image.seek(0)
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image)
                if caption:
                    await update.message.reply_text(f"Caption: {caption}")
                await thinking_message.delete()
            else:
                await thinking_message.edit_text("សុំទោស មិនអាចបង្កើតរូបភាពបានទេ។")
        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            await update.message.reply_text("កំហុសក្នុងការបង្កើតរូបភាព។ សូមព្យាយាមម្តងទៀត។")
        return

    # បង្ហាញសារកំពុងគិតសម្រាប់សារជជែកធម្មតា។
    # Show thinking message for regular chat messages
    thinking_message = await update.message.reply_text(" KH AI V2 កំពុងគិត...! \n សូមរង់ចាំបន្តិច។") # Bot is thinking... Please wait a moment.

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

        # បន្ថែមសារ KH AI V2 ទៅក្នុងប្រវត្តិ
        # Add bot message to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

        # ផ្ញើការឆ្លើយតបទៅអ្នកប្រើប្រាស់
        # Send the response back to the user
        await thinking_message.edit_text(ai_response) # Edit the thinking message with the actual response
    except Exception as e:
        logger.error(f"Error generating content from Gemini for text: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការសារអត្ថបទរបស់អ្នក។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your text message.
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
    thinking_message = await update.message.reply_text(" KH AI V2 កំពុងដំណើរការរូបភាពរបស់អ្នក...! \nសូមរង់ចាំបន្តិច។") # Bot is processing your image... Please wait a moment.

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

        # បន្ថែមសារ KH AI V2 ទៅក្នុងប្រវត្តិ
        # Add bot message to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

        await thinking_message.edit_text(ai_response) # Edit the thinking message with the actual response

    except Exception as e:
        logger.error(f"Error handling photo with Gemini: {e}", exc_info=True) # Log full exception info
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការរូបភាពរបស់អ្នក។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )
        # Sorry, an error occurred while processing your image.
        # Please try again later.

# មុខងារសម្រាប់បំប្លែងសំឡេងទៅជាអត្ថបទដោយប្រើ Google Cloud Speech-to-Text
# Function to transcribe audio using Google Cloud Speech-to-Text
async def transcribe_audio(audio_bytes: bytes) -> str:
    """Use Google Cloud Speech-to-Text to transcribe audio bytes to text."""
    if not speech_client:
        raise Exception("Google Cloud SpeechClient is not initialized. Cannot transcribe audio.")

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
        sample_rate_hertz=16000,
        language_code="km-KH",
    )

    try:
        # Use the synchronous recognize method (not async)
        response = speech_client.recognize(config=config, audio=audio)
        if response.results:
            return response.results[0].alternatives[0].transcript
        return ""
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}", exc_info=True)
        raise

# មុខងារសម្រាប់គ្រប់គ្រងសារជាសំឡេង
# Function for handling voice messages
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not update.message.voice:
        await update.message.reply_text('សូមផ្ញើសារជាសំឡេងរបស់អ្នកមកខ្ញុំដោយផ្ទាល់។')
        return

    voice_file_id = update.message.voice.file_id
    logger.info(f"Received voice message with file_id: {voice_file_id}")

    # Show processing message immediately
    processing_message = await update.message.reply_text(" KH AI V2 កំពុងដំណើរការសំឡេងរបស់អ្នក........! \nសូមរង់ចាំបន្តិច។")

    # Save the voice file
    file = await context.bot.get_file(voice_file_id)
    voice_bytes = io.BytesIO()
    await file.download_to_memory(voice_bytes)
    voice_bytes.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    voice_filename = f"{user_id}_{timestamp}.ogg"
    voice_path = os.path.join(VOICE_DIR, voice_filename)
    with open(voice_path, 'wb') as f:
        f.write(voice_bytes.getvalue())

    # Convert ogg to wav for speech_recognition
    wav_path = voice_path.replace('.ogg', '.wav')
    try:
        if AudioSegment is None:
            await processing_message.edit_text('pydub មិនត្រូវបានដំឡើងទេ។ សូមដំឡើងវាជាមុនសិន៖ pip install pydub')
            return
        audio = AudioSegment.from_ogg(voice_path)
        audio.export(wav_path, format='wav')
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            transcribed_text = recognizer.recognize_google(audio_data, language='km-KH')
    except Exception as e:
        logger.error(f"Error converting voice to text: {e}", exc_info=True)
        await processing_message.edit_text('កំហុសក្នុងការបម្លែងសំឡេងទៅអត្ថបទ។ សូមព្យាយាមម្តងទៀត។')
        if os.path.exists(wav_path):
            os.remove(wav_path)
        return
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

    # Add transcribed text to chat history
    if user_id not in user_chat_history:
        user_chat_history[user_id] = []
    user_chat_history[user_id].append({"role": "user", "parts": [{"text": transcribed_text}]})

    # Send the transcribed text to Gemini AI
    try:
        chat_session = model.start_chat(history=user_chat_history[user_id])
        response = chat_session.send_message(transcribed_text)
        ai_response = response.text
        # Add bot response to history
        user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})
        await processing_message.edit_text(f"អត្ថបទដែលបានបម្លែង៖ {transcribed_text}\n\nAI៖ {ai_response}")
    except Exception as e:
        logger.error(f"Error getting AI response: {e}", exc_info=True)
        await processing_message.edit_text('កំហុសក្នុងការទទួលបានចម្លើយពី AI។ សូមព្យាយាមម្តងទៀត។')

# មុខងារសម្រាប់គ្រប់គ្រងឯកសារ PDF
# Function for handling PDF documents
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ទាញយកអត្ថបទពីឯកសារ PDF និងឆ្លើយតបដោយប្រើម៉ូដែល Gemini."""
    user_id = update.effective_user.id
    if not update.message.document or not update.message.document.mime_type == 'application/pdf':
        await update.message.reply_text("សុំទោស ខ្ញុំមិនអាចរកឃើញឯកសារ PDF បានទេ។")
        return

    max_pdf_size = 10 * 1024 * 1024  # 10MB
    if update.message.document.file_size > max_pdf_size:
        await update.message.reply_text("សុំទោស ឯកសារ PDF ធំពេក (លើស 10MB)។ សូមផ្ញើឯកសារដែលមានទំហំតិចជាង 10MB។")
        return

    file_id = update.message.document.file_id
    file_name = update.message.document.file_name
    logger.info(f"Received PDF document: {file_name} with file_id: {file_id}")

    thinking_message = await update.message.reply_text(f" KH AI V2 កំពុងដំណើរការឯកសារ PDF ({file_name})... សូមរង់ចាំបន្តិច។")

    try:
        file = await context.bot.get_file(file_id)
        pdf_bytes = io.BytesIO()
        await file.download_to_memory(pdf_bytes)
        pdf_bytes.seek(0)

        pdf_reader = PyPDF2.PdfReader(pdf_bytes)
        pdf_text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            pdf_text += page.extract_text() + "\n"
        
        if pdf_text:
            # No artificial limit, but split for Telegram
            extracted_text = f"បានទាញយកអត្ថបទពី PDF:\n\n{pdf_text}\n\n KH AI V2 កំពុងឆ្លើយតប..."
            await send_long_message(thinking_message, extracted_text)
            logger.info(f"Extracted text from PDF (first 200 chars): {pdf_text[:200]}...")

            # Add extracted text to history
            if user_id not in user_chat_history:
                user_chat_history[user_id] = []
            user_chat_history[user_id].append({"role": "user", "parts": [{"text": f"Please analyze this PDF content:\n\n{pdf_text}"}]})

            # Send the extracted text to the Gemini model with history
            chat_session = model.start_chat(history=user_chat_history[user_id])
            response = chat_session.send_message(f"Please analyze this PDF content:\n\n{pdf_text}")
            ai_response = response.text
            logger.info(f"Gemini response for PDF: {ai_response}")

            # Add bot message to history
            user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})

            await send_long_message(thinking_message, f"ការវិភាគ PDF របស់ខ្ញុំ៖\n\n{ai_response}")
        else:
            await thinking_message.edit_text("ខ្ញុំមិនអាចទាញយកអត្ថបទពីឯកសារ PDF នេះបានទេ។")
    except PyPDF2.errors.PdfReadError:
        logger.error(f"Invalid PDF file: {file_name}", exc_info=True)
        await thinking_message.edit_text("សុំទោស នេះមិនមែនជាឯកសារ PDF ត្រឹមត្រូវទេ។")
    except Exception as e:
        logger.error(f"Error handling PDF with Gemini: {e}", exc_info=True)
        await thinking_message.edit_text('សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការឯកសារ PDF របស់អ្នក។ សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។')

# មុខងារសម្រាប់ពាក្យបញ្ជា /pdf_or_img
# Function for the /pdf_or_img command
async def handle_document_and_photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ផ្តល់ការណែនាំអំពីរបៀបផ្ញើរូបភាព ឬឯកសារ PDF។"""
    # Provide instructions on how to send images or PDF documents.
    await update.message.reply_text(
        'សូមផ្ញើរូបភាព ឬឯកសារ PDF របស់អ្នកមកខ្ញុំដោយផ្ទាល់។\n'
        'រូបភាពនឹងត្រូវបានវិភាគដោយ KH AI V2 ។ ឯកសារ PDF នឹងត្រូវបានដំណើរការដើម្បីទាញយកអត្ថបទ។'
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

    thinking_message = await update.message.reply_text(" KH AI V2 កំពុងបង្កើតកូដ... សូមរង់ចាំបន្តិច។") # Bot is generating code... Please wait a moment.

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
    user_id = update.effective_user.id
    logger.info(f"Processing edited question for {user_id}: {edited_question}")

    thinking_message = await update.message.reply_text(" KH AI V2 កំពុងដំណើរការសំណួរដែលបានកែសម្រួលរបស់អ្នក... សូមរង់ចាំបន្តិច។")

    try:
        if user_id in user_chat_history and user_chat_history[user_id]:
            # រកមើលសារអ្នកប្រើប្រាស់ចុងក្រោយក្នុងប្រវត្តិ
            last_user_message_index = -1
            for i in range(len(user_chat_history[user_id]) - 1, -1, -1):
                if user_chat_history[user_id][i]["role"] == "user":
                    last_user_message_index = i
                    break
            if last_user_message_index != -1:
                user_chat_history[user_id][last_user_message_index] = {"role": "user", "parts": [{"text": edited_question}]}
                if last_user_message_index + 1 < len(user_chat_history[user_id]) and user_chat_history[user_id][last_user_message_index + 1]["role"] == "model":
                    del user_chat_history[user_id][last_user_message_index + 1]
                chat_session = model.start_chat(history=user_chat_history[user_id])
                response = chat_session.send_message(edited_question)
                ai_response = response.text
                logger.info(f"Gemini response for edited question: {ai_response}")
                user_chat_history[user_id].append({"role": "model", "parts": [{"text": ai_response}]})
                # Split long response for Telegram
                full_text = f"សំណួររបស់អ្នកត្រូវបានកែសម្រួល និងដំណើរការឡើងវិញ។\n\nការឆ្លើយតបថ្មី៖ {ai_response}"
                max_len = 4096
                if len(full_text) <= max_len:
                    await thinking_message.edit_text(full_text)
                else:
                    await thinking_message.edit_text(full_text[:max_len])
                    # Send the rest as new messages
                    for i in range(max_len, len(full_text), max_len):
                        await update.message.reply_text(full_text[i:i+max_len])
            else:
                await thinking_message.edit_text("មិនអាចរកឃើញសំណួរចុងក្រោយរបស់អ្នកក្នុងប្រវត្តិដើម្បីកែសម្រួលទេ។")
        else:
            await thinking_message.edit_text("អ្នកមិនមានប្រវត្តិជជែកទេ។")
    except Exception as e:
        logger.error(f"Error processing edited question: {e}", exc_info=True)
        await thinking_message.edit_text(
            'សុំទោស មានកំហុសឆ្គងកើតឡើងនៅពេលដំណើរការសំណួរដែលបានកែសម្រួលរបស់អ្នក។ '
            'សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។'
        )

# Helper function to escape Markdown special characters
def escape_markdown(text: str) -> str:
    # Telegram MarkdownV2 escaping
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

# មុខងារសម្រាប់បង្ហាញប្រវត្តិជជែក
# Function for displaying chat history
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id in user_chat_history and user_chat_history[user_id]:
        history_text = "ប្រវត្តិជជែករបស់អ្នក:\n\n"
        for entry in user_chat_history[user_id]:
            role = "អ្នក" if entry["role"] == "user" else " KH AI V2 "
            content = " ".join([part["text"] for part in entry["parts"] if "text" in part])
            history_text += f"**{role}**: {content}\n\n"
        # Escape Markdown special characters
        history_text = escape_markdown(history_text)
        await send_long_message(update.message, history_text, parse_mode='Markdown')
    else:
        await update.message.reply_text('អ្នកមិនទាន់មានប្រវត្តិជជែកនៅឡើយទេ។')

# មុខងារសម្រាប់ពាក្យបញ្ជា /clear_history
# Function for the /clear_history command
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """លុបប្រវត្តិជជែកសម្រាប់អ្នកប្រើប្រាស់បច្ចុប្បន្ន និងលុបឯកសារសំឡេងរបស់អ្នកប្រើប្រាស់។"""
    user_id = update.effective_user.id
    # Delete chat history
    had_history = user_id in user_chat_history
    if had_history:
        del user_chat_history[user_id]
        user_bot_state[user_id] = None # Clear any pending state
    # Delete all voice files for this user
    deleted_files = 0
    for f in os.listdir(VOICE_DIR):
        if f.startswith(str(user_id)):
            try:
                os.remove(os.path.join(VOICE_DIR, f))
                deleted_files += 1
            except Exception as e:
                logger.warning(f"Could not delete file {f}: {e}")
    if had_history or deleted_files > 0:
        await update.message.reply_text('ប្រវត្តិជជែក និងឯកសារសំឡេងរបស់អ្នកត្រូវបានលុប។ យើងអាចចាប់ផ្តើមការសន្ទនាថ្មី។')
    else:
        await update.message.reply_text('អ្នកមិនមានប្រវត្តិជជែក ឬឯកសារសំឡេងដើម្បីលុបទេ។')

async def set_telegram_commands(application: Application):
    """កំណត់ពាក្យបញ្ជាសម្រាប់ KH AI V2  Telegram ។"""
    # Set the commands for the Telegram bot.
    commands = [
        BotCommand("start", "ចាប់ផ្តើមជជែក / ទទួលបានព័ត៌មាន"), # Start chat / Get info
        BotCommand("voice_to_text", "បំប្លែងសំឡេងទៅជាអត្ថបទ"), # Convert voice to text
        BotCommand("pdf_or_img", "ព័ត៌មានរូបភាព/ឯកសារ PDF"), # Image/PDF info
        BotCommand("generate_code", "បង្កើតកូដ"), # Generate code
        BotCommand("generate_image", "បង្កើតរូបភាព"),  # New image generation command
        BotCommand("edit_last", "កែសម្រួលសំណួរចុងក្រោយ"), # Edit last question
        BotCommand("show_history", "មើលប្រវត្តិជជែក"), # View chat history
        BotCommand("clear_history", "លុបប្រវត្តិជជែក") # Clear chat history
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Telegram commands set successfully.")

def main() -> None:
    """ដំណើរការ KH AI V2 ។"""
    # Run the bot.
    # បង្កើតកម្មវិធីនិងបញ្ជូនសញ្ញាសម្គាល់ KH AI V2 របស់អ្នក
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # បញ្ជូនអ្នកគ្រប់គ្រងផ្សេងគ្នា
    # On different commands, answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("voice_to_text", handle_voice))
    application.add_handler(CommandHandler("pdf_or_img", handle_document_and_photo_command))
    application.add_handler(CommandHandler("generate_code", generate_code_command)) # New handler for code generation
    application.add_handler(CommandHandler("edit_last", edit_last_question_command)) # Fixed: handler for editing last question
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
    
    # កំណត់ពាក្យបញ្ជា KH AI V2  Telegram នៅពេលចាប់ផ្តើម
    # Set Telegram bot commands on startup
    application.add_handler(CommandHandler("setcommands", set_telegram_commands_handler)) # A temporary handler to call set_telegram_commands

    # ចាប់ផ្តើម KH AI V2 
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# មុខងារអ្នកគ្រប់គ្រងសម្រាប់ set_telegram_commands
# Handler function for set_telegram_commands
async def set_telegram_commands_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ហៅមុខងារដើម្បីកំណត់ពាក្យបញ្ជា KH AI V2  Telegram ។"""
    # Call the function to set Telegram bot commands.
    await set_telegram_commands(context.application)
    await update.message.reply_text("ពាក្យបញ្ជា KH AI V2  Telegram ត្រូវបានកំណត់។")
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
    thinking_message = await update.edited_message.reply_text(" KH AI V2 កំពុងដំណើរការសារដែលបានកែសម្រួលរបស់អ្នក... សូមរង់ចាំបន្តិច។") # Bot is processing your edited message... Please wait a moment.

    try:
        # លុបការសន្ទនាចុងក្រោយ (សារអ្នកប្រើប្រាស់ + ការឆ្លើយតបរបស់ KH AI V2 ) ប្រសិនបើមាន
        # Remove the last turn (user message + bot response) if it exists
        if user_id in user_chat_history and len(user_chat_history[user_id]) >= 2:
            if user_chat_history[user_id][-1]["role"] == "model" and user_chat_history[user_id][-2]["role"] == "user":
                user_chat_history[user_id].pop() # លុបការឆ្លើយតបរបស់ KH AI V2 
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

        # បន្ថែមការឆ្លើយតបរបស់ KH AI V2 ទៅក្នុងប្រវត្តិ
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

# Command to convert the latest voice file to text
async def voice_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if AudioSegment is None:
        await update.message.reply_text('pydub មិនត្រូវបានដំឡើងទេ។ សូមដំឡើងវាជាមុនសិន៖ pip install pydub')
        return
    # Find the latest voice file for this user
    user_files = [f for f in os.listdir(VOICE_DIR) if f.startswith(str(user_id)) and f.endswith('.ogg')]
    if not user_files:
        await update.message.reply_text('មិនមានសំឡេងដែលបានរក្សាទុកសម្រាប់អ្នកទេ។')
        return
    latest_file = sorted(user_files)[-1]
    voice_path = os.path.join(VOICE_DIR, latest_file)
    # Convert ogg to wav for speech_recognition
    wav_path = voice_path.replace('.ogg', '.wav')
    try:
        audio = AudioSegment.from_ogg(voice_path)
        audio.export(wav_path, format='wav')
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='km-KH')
        await update.message.reply_text(f"អត្ថបទដែលបានបម្លែង៖ {text}")
    except Exception as e:
        logger.error(f"Error converting voice to text: {e}", exc_info=True)
        await update.message.reply_text('កំហុសក្នុងការបម្លែងសំឡេងទៅអត្ថបទ។ សូមព្យាយាមម្តងទៀត។')
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

# Utility function to send long messages in chunks
async def send_long_message(message_obj, text, **kwargs):
    max_len = 4096
    for i in range(0, len(text), max_len):
        await message_obj.reply_text(text[i:i+max_len], **kwargs)

# Add user state for image generation
# In user_bot_state: 'awaiting_image_description'

# /generate_image command handler
async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_bot_state[user_id] = 'awaiting_image_description'
    await update.message.reply_text('សូមពិពណ៌នារូបភាពដែលអ្នកចង់បង្កើត។')

# Handle image description reply
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text
    logger.info(f"Received text message from {user_id}: {user_message}")

    # ... existing code ...
    # Add this block before other state checks
    if user_bot_state.get(user_id) == 'awaiting_image_description':
        user_bot_state[user_id] = None
        try:
            thinking_message = await update.message.reply_text("KH AI V2 កំពុងបង្កើតរូបភាព... សូមរង់ចាំបន្តិច។")
            image_bytes, caption = gemini_generate_image(user_message)
            if image_bytes:
                image = BytesIO(image_bytes)
                image.seek(0)
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image)
                if caption:
                    await update.message.reply_text(f"Caption: {caption}")
                await thinking_message.delete()
            else:
                await thinking_message.edit_text("សុំទោស មិនអាចបង្កើតរូបភាពបានទេ។")
        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            await update.message.reply_text("កំហុសក្នុងការបង្កើតរូបភាព។ សូមព្យាយាមម្តងទៀត។")
        return
    # ... rest of handle_text_message ...

def gemini_generate_image(prompt: str):
    """Generate an image and caption from a prompt using Gemini."""
    try:
        # Use the Gemini 1.5 Pro or Flash model for image generation
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        image_bytes = None
        caption = None
        # Try to extract image and caption from the response
        if hasattr(response, 'candidates') and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    caption = part.text.strip().replace('**Caption:** ', '')
                elif hasattr(part, 'inline_data') and part.inline_data:
                    image_bytes = part.inline_data.data
        return image_bytes, caption
    except Exception as e:
        logger.error(f"Error in gemini_generate_image: {e}", exc_info=True)
        return None, None

if __name__ == "__main__":
    main()
    