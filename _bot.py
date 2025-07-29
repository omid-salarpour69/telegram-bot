import os
import re
import io
import time
import instaloader
import requests
from dotenv import load_dotenv
# from flask import Flask, request
import telebot
from telebot import types
from pytube import YouTube
from PIL import Image



load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
# WEBHOOK_URL = os.getenv("RAILWAY_WEBHOOK_URL")

bot = telebot.TeleBot(TOKEN)
# app = Flask(__name__)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

loader = instaloader.Instaloader()
user_state = {}

# ───── Start ─────
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📥 دانلود پست اینستاگرام"),
        types.KeyboardButton("🎬 دانلود ویدیو از یوتیوب"),
        types.KeyboardButton("📄 تبدیل عکس به PDF"),
        types.KeyboardButton("ℹ️ راهنما")
    )
    bot.send_message(message.chat.id, "سلام! یکی از گزینه‌های زیر را انتخاب کن:", reply_markup=markup)

# ───── پیام‌ها ─────
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text

    if text == "📥 دانلود پست اینستاگرام":
        bot.send_message(chat_id, "لینک پست یا ریل اینستاگرام را بفرست.")
        user_state[chat_id] = "awaiting_instagram"
    elif text == "🎬 دانلود ویدیو از یوتیوب":
        bot.send_message(chat_id, "لینک ویدیوی یوتیوب را ارسال کن.")
        user_state[chat_id] = "awaiting_youtube"
    elif text == "📄 تبدیل عکس به PDF":
        bot.send_message(chat_id, "لطفاً عکس‌ها را ارسال کن. بعد از اتمام بنویس 'تبدیل'")
        user_state[chat_id] = "awaiting_images"
        user_state[f"{chat_id}_images"] = []
    elif text == "ℹ️ راهنما":
        bot.send_message(chat_id, "📌 راهنما:\n- از یوتیوب یا اینستاگرام ویدیو بگیر\n- عکس به PDF تبدیل کن.")
    elif user_state.get(chat_id) == "awaiting_instagram":
        download_instagram_post(message)
        user_state[chat_id] = None
    elif user_state.get(chat_id) == "awaiting_youtube":
        download_youtube_video(message)
        user_state[chat_id] = None
    elif user_state.get(chat_id) == "awaiting_images":
        if text.strip().lower() == "تبدیل":
            convert_images_to_pdf(chat_id, message)
            user_state[chat_id] = None
            user_state[f"{chat_id}_images"] = []
        else:
            bot.send_message(chat_id, "لطفاً فقط عکس بفرست یا بنویس 'تبدیل' برای ساخت PDF.")
    else:
        bot.send_message(chat_id, "گزینه نامعتبر است.")

# ───── عکس برای PDF ─────
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    chat_id = message.chat.id
    if user_state.get(chat_id) == "awaiting_images":
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        path = f"downloads/{chat_id}_{message.message_id}.jpg"
        with open(path, 'wb') as f:
            f.write(downloaded_file)
        user_state[f"{chat_id}_images"].append(path)
        bot.send_message(chat_id, "📸 عکس ذخیره شد.")

def convert_images_to_pdf(chat_id, message):
    image_paths = user_state.get(f"{chat_id}_images", [])
    if not image_paths:
        bot.send_message(chat_id, "❌ عکسی دریافت نشده.")
        return
    images = [Image.open(p).convert("RGB") for p in image_paths]
    output_path = f"downloads/{chat_id}_output.pdf"
    images[0].save(output_path, save_all=True, append_images=images[1:])
    with open(output_path, "rb") as f:
        bot.send_document(chat_id, f)

# ───── اینستاگرام ─────
def download_instagram_post(message):
    chat_id = message.chat.id
    url = message.text.strip()
    try:
        if "instagram.com/p/" not in url and "instagram.com/reel/" not in url:
            bot.reply_to(message, "❌ لینک معتبر نیست.")
            return
        shortcode = url.split("/p/")[-1].split("/")[0] if "/p/" in url else url.split("/reel/")[-1].split("/")[0]
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target="downloads")
        bot.reply_to(message, "✅ دانلود موفق.")
    except Exception as e:
        bot.reply_to(message, f"⚠️ خطا:\n{e}")

# ───── یوتیوب ─────


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")

def fix_youtube_url(url):
    if "youtube.com/shorts/" in url:
        return f"https://youtube.com/watch?v={url.split('shorts/')[-1].split('?')[0]}"
    return url

def download_youtube_video(message):
    chat_id = message.chat.id
    original_url = message.text.strip()
    url = fix_youtube_url(original_url)

    status_msg = bot.send_message(chat_id, "⏳ در حال دریافت و دانلود ویدیو از Apify...")

    api_url = f"https://api.apify.com/v2/acts/bytepulselabs~youtube-video-downloader/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    payload = {
        "urls": [{"url": url}],
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"]
        }
    }

    try:
        res = requests.post(api_url, json=payload)
        items = res.json()

        if not items or not isinstance(items, list):
            raise Exception("داده‌ای دریافت نشد.")

        item = items[0]
        title = item.get("title", "ویدیو")
        video_url = item.get("videoUrl")

        if not video_url:
            raise Exception("لینک نهایی پیدا نشد.")

        response = requests.get(video_url, stream=True)
        if response.status_code != 200:
            raise Exception("دانلود فایل با شکست مواجه شد.")

        file_size_bytes = response.headers.get('Content-Length')
        file_size_bytes = int(file_size_bytes) if file_size_bytes else None
        max_size_bytes = 50 * 1024 * 1024

        if file_size_bytes and file_size_bytes > max_size_bytes:
            bot.send_message(chat_id, f"⚠️ حجم فایل بیش از ۵۰MB هست ({round(file_size_bytes / 1024 / 1024, 2)}MB)\nارسال مستقیم ممکن نیست. لینک دانلود:\n{video_url}")
            return

        video_stream = io.BytesIO()
        downloaded = 0
        chunk_size = 1024 * 64
        last_update = 0

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                video_stream.write(chunk)
                downloaded += len(chunk)

                if file_size_bytes:
                    progress = int(downloaded * 100 / file_size_bytes)
                    if time.time() - last_update > 1.5:
                        bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id,
                                              text=f"📦 در حال دانلود: {progress}%")
                        last_update = time.time()

        bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id,
                              text="✅ دانلود کامل شد. در حال ارسال ویدیو...")

        video_stream.seek(0)
        video_stream.name = "video.mp4"

        try:
            bot.send_video(chat_id, video_stream, caption=f"🎬 <b>{title}</b>", parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, f"❌ ارسال فایل به تلگرام شکست خورد:\n`{e}`", parse_mode="Markdown")
        finally:
            video_stream.close()
            del video_stream

    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا:\n`{e}`", parse_mode="Markdown")

# # ───── Webhook Flask ─────
# @app.route("/", methods=["GET"])
# def home():
#     return "ربات آنلاین است", 200

# @app.route(f"/{TOKEN}", methods=["POST"])
# def receive_update():
#     json_data = request.get_data().decode("utf-8")
#     update = telebot.types.Update.de_json(json_data)
#     bot.process_new_updates([update])
#     return "OK", 200

# ───── اجرای Webhook ─────
if __name__ == "__main__":
    bot.delete_webhook()
    bot.infinity_polling()
    # bot.remove_webhook()
    # bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    # app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
