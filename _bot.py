import os
import re
import instaloader
import requests
from dotenv import load_dotenv
from flask import Flask, request
import telebot
from telebot import types
from pytube import YouTube
from PIL import Image

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RAILWAY_WEBHOOK_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

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
def fix_youtube_url(url):
    if "youtube.com/shorts/" in url:
        return f"https://youtube.com/watch?v={url.split('shorts/')[-1].split('?')[0]}"
    return url

def download_youtube_video(message):
    chat_id = message.chat.id
    url = fix_youtube_url(message.text.strip())

    try:
        bot.send_message(chat_id, "⏳ در حال دریافت لینک از ytmate...")
        session = requests.Session()
        res = session.post("https://ytmate.ltd/api/ajaxSearch/index", data={"q": url, "vt": "home"})
        res_json = res.json()
        html = res_json.get("result", "")
        k_id = re.search(r'k__id\s*=\s*\"(.+?)\"', html).group(1)
        title_match = re.search(r"<b>Title:</b> (.+?)<br/>", html)
        title = title_match.group(1) if title_match else "ویدیو"

        res2 = session.post("https://ytmate.ltd/api/ajaxConvert/convert", data={
            "type": "youtube",
            "_id": k_id,
            "v_id": url.split("v=")[-1],
            "ftype": "mp4",
            "fquality": "360"
        })
        final_html = res2.json().get("result", "")
        match = re.search(r'href="(https://[^"]+)"', final_html)
        if not match:
            raise Exception("لینک نهایی پیدا نشد.")
        final_link = match.group(1)
        bot.send_message(chat_id, f"🎬 <b>{title}</b>\n🔗 <a href='{final_link}'>دانلود</a>",
                        parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا:\n`{e}`", parse_mode="Markdown")

# ───── Webhook Flask ─────
@app.route("/", methods=["GET"])
def home():
    return "ربات آنلاین است", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def receive_update():
    json_data = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

# ───── اجرای Webhook ─────
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
