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

MAX_SIZE_MB = 50
CHUNK_SIZE = 1024 * 64  # 64KB

def download_youtube_video(message):
    chat_id = message.chat.id
    original_url = message.text.strip()
    api_base = "https://your-api.up.railway.app"
    
    try:
        # ارسال درخواست به API برای گرفتن لینک دانلود
        info_url = f"{api_base}/download?url={original_url}"
        res = requests.get(info_url)

        if res.status_code != 200 or "download_url" not in res.json():
            raise Exception(res.json().get("error", "خطا در API"))

        data = res.json()
        direct_url = data["download_url"]
        title = data["title"]
        size_mb = data.get("filesize_mb", 0)

        if size_mb > MAX_SIZE_MB:
            bot.send_message(chat_id,
                f"⚠️ حجم فایل بیشتر از {MAX_SIZE_MB}MB هست ({size_mb}MB)\nلینک دانلود:\n{direct_url}")
            return

        status_msg = bot.send_message(chat_id, "📦 در حال دانلود و ارسال ویدیو...")

        # دانلود فایل و ارسال در تلگرام
        video_stream = io.BytesIO()
        video_stream.name = "video.mp4"
        res_file = requests.get(direct_url, stream=True)

        for chunk in res_file.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                video_stream.write(chunk)

        video_stream.seek(0)
        bot.send_video(chat_id, video_stream, caption=f"🎬 <b>{title}</b>", parse_mode="HTML")
        video_stream.close()
        del video_stream

    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در دریافت لینک یا دانلود:\n`{e}`", parse_mode="Markdown")

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
