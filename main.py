import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import API_ID, API_HASH, BOT_TOKEN
from yt_dlp import YoutubeDL
import eyed3
from database import init_db, add_user, add_download_to_history

# Инициализация базы данных
init_db()

# Инициализация бота
bot = Client("youtube_mp3_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Словарь для хранения состояния пользователя
user_states = {}

# Функция для корректной установки MP3 тегов
def set_mp3_tags(file_path, title, artist):
    try:
        audiofile = eyed3.load(file_path)
        if audiofile:
            audiofile.tag.clear()
            audiofile.tag.artist = artist
            audiofile.tag.title = title
            audiofile.tag.save(version=eyed3.id3.ID3_V2_3)
    except Exception as e:
        print(f"Ошибка тегов: {e}")

# Приветственное сообщение
@bot.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    add_user(user_id, username, first_name)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ℹ️ О боте", callback_data="about")],
            [InlineKeyboardButton("📥 Как использовать", callback_data="how_to_use")],
        ]
    )

    await message.reply(
        f"👋 Привет, {first_name}!\n\n"
        "Я помогу скачать музыку с YouTube и менять метаданные. Просто отправь мне ссылку на видео!\n\n"
        "Нажми на кнопки ниже, чтобы узнать больше.",
        reply_markup=keyboard
    )

# Обработка кнопок меню
@bot.on_callback_query(filters.regex("about"))
async def about_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit(
        "ℹ️ **О боте**\n\n"
        "Этот бот позволяет скачивать аудио из видео на YouTube в формате MP3. "
        "Можно менять метаданные в этом боте."
        "Сделано ботом [SoundsBot_KB](https://t.me/SoundsBot_KB)."
    )

@bot.on_callback_query(filters.regex("how_to_use"))
async def how_to_use_handler(client, callback_query: CallbackQuery):
    await callback_query.message.edit(
        "📥 **Как использовать бота**\n\n"
        "1. Найди видео на YouTube.\n"
        "2. Скопируй ссылку на это видео.\n"
        "3. Отправь её мне в чат.\n"
        "4. Я конвертирую видео в MP3 и отправлю тебе файл!\n\n"
        "Сделано ботом [SoundsBot_KB](https://t.me/SoundsBot_KB)."
    )

# Обработка ссылок YouTube
@bot.on_message(filters.regex(r"https?://(www\.)?(youtube\.com|youtu\.be)/.+"))
async def youtube_handler(client, message: Message):
    url = message.text
    user_id = message.from_user.id
    
    try:
        with YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            title = info.get("title", "Неизвестное видео")
            uploader = info.get("uploader", "Неизвестный автор")

        # Ограничение по длительности
        max_duration = 7200  # Максимум 2 часа
        if duration > max_duration:
            await message.reply(
                f"❌ Видео **{title}** слишком длинное ({duration // 60} минут). "
                f"Максимальная длина — {max_duration // 60} минут."
            )
            return

        await message.reply("🔄 Скачиваю видео...")

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
            ydl.download([url])
            file_name = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".mp4", ".mp3")

        # Сохраняем историю скачивания
        add_download_to_history(user_id, title, url, file_name)

        # Сохраняем состояние для пользователя и предлагаем изменить теги
        user_states[user_id] = {
            "file_name": file_name,
            "title": title,
            "artist": uploader,
            "stage": "waiting_for_metadata"
        }

        # Кнопки "Да/Нет"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Да", callback_data="yes_metadata"),
            InlineKeyboardButton("Нет", callback_data="no_metadata")
        ]])

        await message.reply(
            f"🎵 **{title}**\n👤 {uploader}\n\nХочешь изменить название или автора?",
            reply_markup=keyboard
        )

    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# Обработка кнопок "Да/Нет" для изменения метаданных
@bot.on_callback_query(filters.regex("yes_metadata"))
async def yes_metadata_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_states[user_id]["stage"] = "waiting_for_new_title"
    
    await callback_query.message.edit(
        "📝 Введи новое название песни:"
    )

@bot.on_callback_query(filters.regex("no_metadata"))
async def no_metadata_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state = user_states[user_id]
    
    set_mp3_tags(state["file_name"], state["title"], state["artist"])
    await callback_query.message.edit("✅ Метаданные не были изменены. Отправляю файл...")

    await callback_query.message.reply_document(
        document=state["file_name"],
        caption=f"🎵 **{state['title']}**\n👤 {state['artist']}\n\nСоздано ботом [SoundsBot_KB](https://t.me/SoundsBot_KB)"
    )

    # Удаляем файл после отправки
    os.remove(state["file_name"])

    # Очищаем состояние пользователя
    del user_states[user_id]

# Обработка текстовых сообщений для изменения метаданных
@bot.on_message(filters.text)
async def metadata_handler(client, message: Message):
    user_id = message.from_user.id

    # Проверяем, есть ли активное состояние для пользователя
    if user_id not in user_states:
        return

    state = user_states[user_id]

    # Если в стадии ожидания нового названия
    if state["stage"] == "waiting_for_new_title":
        state["title"] = message.text
        await message.reply("👤 Теперь введи нового автора:")
        state["stage"] = "waiting_for_new_artist"

    # Если в стадии ожидания нового автора
    elif state["stage"] == "waiting_for_new_artist":
        state["artist"] = message.text
        set_mp3_tags(state["file_name"], state["title"], state["artist"])

        await message.reply_document(
            document=state["file_name"],
            caption=f"🎵 **{state['title']}**\n👤 {state['artist']}\n\nСоздано ботом [SoundsBot_KB](https://t.me/SoundsBot_KB)"
        )

        # Удаляем файл после отправки
        os.remove(state["file_name"])

        # Очищаем состояние пользователя
        del user_states[user_id]

# Запуск бота
bot.run()