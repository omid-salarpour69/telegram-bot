import telebot
import instaloader
import os
from dotenv import load_dotenv
from telebot import types
from pytube import YouTube
from PIL import Image
import yt_dlp
import requests
import re

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

loader = instaloader.Instaloader()

# وضعیت موقت برای هر کاربر
user_state = {}

# ───── Start Command ─────
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

# ───── Message Handler ─────
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
        bot.send_message(chat_id, "لطفاً یک یا چند عکس بفرست. وقتی تمام شدند بنویس: `تبدیل`", parse_mode="Markdown")
        user_state[chat_id] = "awaiting_images"
        user_state[f"{chat_id}_images"] = []
    elif text == "ℹ️ راهنما":
        bot.send_message(chat_id, "📌 با این ربات می‌تونی:\n- از اینستاگرام ویدیو دانلود کنی\n- از یوتیوب ویدیو بگیری\n- عکس‌هات رو به PDF تبدیل کنی")
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
        bot.send_message(chat_id, "گزینه نامعتبر است. لطفاً یکی از دکمه‌ها را بزن.")

# ───── دانلود از اینستاگرام ─────
def download_instagram_post(message):
    chat_id = message.chat.id
    url = message.text.strip()
    try:
        if "instagram.com/p/" not in url and "instagram.com/reel/" not in url:
            bot.reply_to(message, "❌ لینک اینستاگرام معتبر نیست.")
            return
        shortcode = url.split("/p/")[-1].split("/")[0] if "/p/" in url else url.split("/reel/")[-1].split("/")[0]
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target="downloads")
        bot.reply_to(message, "✅ پست با موفقیت دانلود شد و در پوشه downloads ذخیره شد.")
    except Exception as e:
        bot.reply_to(message, f"⚠️ خطا در دانلود: {e}")

# ───── دانلود از یوتیوب ─────

def fix_youtube_url(url: str) -> str:
    if "youtube.com/shorts/" in url:
        video_id = url.split("shorts/")[-1].split("?")[0]
        return f"https://youtube.com/watch?v={video_id}"
    return url

def download_youtube_video(message):
    chat_id = message.chat.id
    url = fix_youtube_url(message.text.strip())

    try:
        bot.send_message(chat_id, "⏳ در حال دریافت لینک از ytmate...")

        session = requests.Session()

        # مرحله ۱: گرفتن اطلاعات ویدیو
        res = session.post("https://ytmate.ltd/api/ajaxSearch/index", data={
            "q": url,
            "vt": "home"
        })

        res_json = res.json()
        html_content = res_json.get("result", "")
        k_id = re.search(r"k__id\s*=\s*\"(.+?)\"", html_content).group(1)
        title_match = re.search(r"<b>Title:</b> (.+?)<br/>", html_content)
        title = title_match.group(1) if title_match else "ویدیو"

        # مرحله ۲: گرفتن لینک نهایی mp4
        res2 = session.post("https://ytmate.ltd/api/ajaxConvert/convert", data={
            "type": "youtube",
            "_id": k_id,
            "v_id": url.split("v=")[-1],
            "ftype": "mp4",
            "fquality": "360"
        })

        download_url = res2.json().get("result", "")
        link_match = re.search(r'href="(https://[^"]+)"', download_url)
        if not link_match:
            raise Exception("لینک قابل استخراج نبود.")

        final_link = link_match.group(1)

        text = f"🎬 <b>{title}</b>\n\n🔗 لینک دانلود MP4:\n<a href='{final_link}'>دانلود مستقیم</a>"
        bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در دریافت لینک:\n`{e}`", parse_mode="Markdown")

# ───── تبدیل عکس به PDF ─────
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    chat_id = message.chat.id
    if user_state.get(chat_id) == "awaiting_images":
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image_path = f"downloads/{chat_id}_{message.message_id}.jpg"
        with open(image_path, 'wb') as f:
            f.write(downloaded_file)
        user_state[f"{chat_id}_images"].append(image_path)
        bot.send_message(chat_id, "📸 عکس ذخیره شد.")

def convert_images_to_pdf(chat_id, message):
    image_paths = user_state.get(f"{chat_id}_images", [])
    if not image_paths:
        bot.send_message(chat_id, "❌ عکسی دریافت نشده.")
        return
    images = [Image.open(img).convert('RGB') for img in image_paths]
    pdf_path = f"downloads/{chat_id}_output.pdf"
    images[0].save(pdf_path, save_all=True, append_images=images[1:])
    with open(pdf_path, 'rb') as f:
        bot.send_document(chat_id, f)
    bot.send_message(chat_id, "✅ فایل PDF ارسال شد.")

# ───── اجرای ربات ─────
try:
    bot.polling(none_stop=True)
except Exception as e:
    print(f"❌ Bot polling error: {e}")
