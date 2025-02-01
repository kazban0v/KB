import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import API_ID, API_HASH, BOT_TOKEN
from yt_dlp import YoutubeDL
import eyed3
from database import init_db, add_user, add_download_to_history

# Initialize database
init_db()

# Initialize bot
bot = Client("youtube_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User state dictionary
user_states = {}

# Available video quality options
VIDEO_QUALITIES = {
    "360p": "360",
    "480p": "480",
    "720p": "720",
    "1080p": "1080"
}

def set_mp3_tags(file_path, title, artist):
    try:
        audiofile = eyed3.load(file_path)
        if audiofile and audiofile.tag:
            audiofile.tag.title = title
            audiofile.tag.artist = artist
            audiofile.tag.save()
        else:
            audiofile = eyed3.load(file_path)
            if audiofile.tag is None:
                audiofile.initTag()
            audiofile.tag.title = title
            audiofile.tag.artist = artist
            audiofile.tag.save()
        return True
    except Exception as e:
        print(f"Tag error: {e}")
        return False

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")],
        [InlineKeyboardButton("📥 Как использовать", callback_data="how_to_use")],
    ])

def get_format_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 MP3", callback_data="choose_mp3")],
        [InlineKeyboardButton("🎬 Видео", callback_data="choose_video")],
    ])

def get_video_quality_keyboard():
    buttons = []
    for quality in VIDEO_QUALITIES.keys():
        buttons.append([InlineKeyboardButton(f"📺 {quality}", callback_data=f"quality_{quality}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_format")])
    return InlineKeyboardMarkup(buttons)

async def download_video(url, quality, message, user_id):
    progress_msg = await message.edit_text(f"🎬 Загружаю видео в {quality}...")
    
    try:
        ydl_opts = {
            'format': f'bestvideo[height<={VIDEO_QUALITIES[quality]}]+bestaudio/best[height<={VIDEO_QUALITIES[quality]}]',
            'merge_output_format': 'mp4',
            'outtmpl': f'downloads/{user_id}_%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            
            if not file_path.endswith('.mp4'):
                file_path = file_path.rsplit('.', 1)[0] + '.mp4'

            duration = info.get('duration')
            title = info.get('title')
            
            await progress_msg.edit_text("📤 Отправляю видео...")
            
            await message.reply_video(
                video=file_path,
                duration=duration,
                caption=f"🎬 **{title}**\n"
                        f"📺 Качество: {quality}\n\n"
                        "Скачано с помощью @SoundsBot_KB",
                supports_streaming=True
            )
            
            if os.path.exists(file_path):
                os.remove(file_path)
            
            add_download_to_history(user_id, title, url, "video")
            return True
            
    except Exception as e:
        await progress_msg.edit_text(f"❌ Ошибка при загрузке: {str(e)}")
        return False

async def download_mp3(url, message, user_id, state):
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "outtmpl": f"downloads/{user_id}_%(title)s.%(ext)s",
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_name = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Да", callback_data="yes_metadata"),
            InlineKeyboardButton("Нет", callback_data="no_metadata")
        ]])

        state["file_name"] = file_name
        state["stage"] = "waiting_for_metadata"

        await message.edit_text(
            "✅ MP3 загружен!\n\nХотите изменить метаданные (название/автор)?",
            reply_markup=keyboard
        )
        
        add_download_to_history(user_id, info.get('title'), url, "mp3")
        return True

    except Exception as e:
        await message.edit_text(f"❌ Ошибка при загрузке MP3: {str(e)}")
        return False

@bot.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    add_user(user_id, username, first_name)

    await message.reply(
        f"👋 Привет, {first_name}!\n\n"
        "Я помогу скачать медиа с YouTube в нужном формате или изменить метаданные MP3 файлов.\n"
        "Отправь мне ссылку на YouTube видео или MP3 файл!\n\n"
        "Нажми на кнопки ниже, чтобы узнать больше.",
        reply_markup=get_main_keyboard()
    )

@bot.on_message(filters.regex(r"https?://(www\.)?(youtube\.com|youtu\.be)/.+"))
async def url_handler(client, message: Message):
    url = message.text
    user_id = message.from_user.id
    
    try:
        status_message = await message.reply("🔍 Получаю информацию о видео...")
        
        with YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            title = info.get("title", "Unknown video")
            uploader = info.get("uploader", "Unknown uploader")

        if duration > 1200:  # 20 minutes
            await status_message.edit_text(
                f"❌ Видео **{title}** слишком длинное ({duration // 60} минут). "
                "Максимальная длина — 20 минут."
            )
            return

        user_states[user_id] = {
            "url": url,
            "title": title,
            "uploader": uploader,
            "duration": duration,
            "status_message": status_message
        }

        await status_message.edit_text(
            f"🎥 **{title}**\n"
            f"👤 {uploader}\n"
            f"⏱ Длительность: {duration // 60}:{duration % 60:02d}\n\n"
            "Выберите формат загрузки:",
            reply_markup=get_format_keyboard()
        )

    except Exception as e:
        await message.reply(f"❌ Ошибка при получении информации: {e}")

@bot.on_message(filters.audio | filters.document)
async def audio_handler(client, message: Message):
    user_id = message.from_user.id
    
    # Check if the file is an MP3
    is_audio = bool(message.audio)
    is_mp3_document = bool(message.document and message.document.mime_type == "audio/mpeg")
    
    if not (is_audio or is_mp3_document):
        await message.reply("❌ Пожалуйста, отправьте MP3 файл.")
        return
    
    # Get the file
    file_obj = message.audio if is_audio else message.document
    
    # Create downloads directory if it doesn't exist
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    file_path = f"downloads/{user_id}_{file_obj.file_name}"
    
    # Download the file
    await message.reply("⏳ Загружаю файл...")
    await message.download(file_path)
    
    # Store file info in user state
    user_states[user_id] = {
        "file_path": file_path,
        "original_name": file_obj.file_name,
        "stage": "start_editing"
    }
    
    # Create keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить метаданные", callback_data="edit_metadata")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ])
    
    await message.reply(
        "🎵 Файл загружен!\n"
        "Хотите изменить метаданные (название/исполнитель)?",
        reply_markup=keyboard
    )

@bot.on_callback_query(filters.regex("about"))
async def about_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "ℹ️ **О боте**\n\n"
        "Этот бот позволяет:\n"
        "1. Скачивать видео и аудио с YouTube\n"
        "2. Изменять метаданные MP3 файлов\n"
        "3. Поддерживает различные качества видео\n\n"
        "Создано @SoundsBot_KB",
        reply_markup=get_main_keyboard()
    )

@bot.on_callback_query(filters.regex("how_to_use"))
async def how_to_use_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📥 **Как использовать бота**\n\n"
        "Для YouTube:\n"
        "1. Отправьте ссылку на видео\n"
        "2. Выберите формат (MP3 или Видео)\n"
        "3. Для видео выберите качество\n"
        "4. Для MP3 можно изменить метаданные\n\n"
        "Для MP3 файлов:\n"
        "1. Отправьте MP3 файл\n"
        "2. Выберите 'Изменить метаданные'\n"
        "3. Введите новое название и исполнителя\n\n"
        "Создано @SoundsBot_KB",
        reply_markup=get_main_keyboard()
    )

@bot.on_callback_query(filters.regex("choose_mp3"))
async def mp3_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state = user_states.get(user_id)
    
    if not state:
        await callback_query.answer("❌ Сессия истекла. Отправьте ссылку заново.")
        return

    await callback_query.message.edit_text("🎵 Начинаю загрузку MP3...")
    await download_mp3(state["url"], callback_query.message, user_id, state)

@bot.on_callback_query(filters.regex("choose_video"))
async def video_quality_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "📺 Выберите качество видео:",
        reply_markup=get_video_quality_keyboard()
    )

@bot.on_callback_query(filters.regex("^quality_"))
async def download_video_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state = user_states.get(user_id)
    quality = callback_query.data.split("_")[1]

    if not state:
        await callback_query.answer("❌ Сессия истекла. Отправьте ссылку заново.")
        return

    success = await download_video(
        state["url"], 
        quality, 
        callback_query.message,
        user_id
    )

    if success:
        del user_states[user_id]

@bot.on_callback_query(filters.regex("edit_metadata"))
async def edit_metadata_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id not in user_states:
        await callback_query.answer("❌ Сессия истекла. Отправьте файл заново.")
        return
    
    user_states[user_id]["stage"] = "waiting_for_title"
    await callback_query.message.edit_text("📝 Введите новое название трека:")

@bot.on_callback_query(filters.regex("yes_metadata"))
async def yes_metadata_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_states[user_id]["stage"] = "waiting_for_new_title"
    
    await callback_query.message.edit_text(
        "📝 Введите новое название песни:"
    )

@bot.on_callback_query(filters.regex("no_metadata"))
async def no_metadata_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state = user_states[user_id]
    
    set_mp3_tags(state["file_name"], state["title"], state["uploader"])
    await callback_query.message.edit_text("✅ Отправляю файл...")

    await callback_query.message.reply_audio(
        audio=state["file_name"],
        title=state["title"],
        performer=state["uploader"],
        caption="Скачано с помощью @SoundsBot_KB"
    )

    if os.path.exists(state["file_name"]):
        os.remove(state["file_name"])
    del user_states[user_id]

@bot.on_callback_query(filters.regex("back_to_format"))
async def back_to_format_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit_text(
        "Выберите формат загрузки:",
        reply_markup=get_format_keyboard()
    )

@bot.on_message(filters.text & ~filters.command("start"))
async def metadata_handler(client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_states:
        return

    state = user_states[user_id]

    if state["stage"] == "waiting_for_new_title":
        state["new_title"] = message.text
        await message.reply("👤 Теперь введите имя исполнителя:")
        state["stage"] = "waiting_for_new_artist"

    elif state["stage"] == "waiting_for_new_artist":
        state["new_artist"] = message.text
        set_mp3_tags(state["file_name"], state["new_title"], state["new_artist"])

        await message.reply_audio(
            audio=state["file_name"],
            title=state["new_title"],
            performer=state["new_artist"],
            caption="Скачано с помощью @SoundsBot_KB"
        )

        if os.path.exists(state["file_name"]):
            os.remove(state["file_name"])
        del user_states[user_id]

# Запуск бота
bot.run()