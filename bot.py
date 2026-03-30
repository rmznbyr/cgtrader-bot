import os
import re
import io
import json
import zipfile
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "8360418340:AAHKn6zyjvzJc3Fulr6xTdidKK98Yd3rAYw")
HISTORY_FILE = "download_history.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": "https://www.cgtrader.com/",
}


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def is_downloaded(url):
    history = load_history()
    return history.get(url)

def mark_downloaded(url, slug, designer):
    history = load_history()
    history[url] = {
        "slug": slug,
        "designer": designer,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_history(history)


def extract_images(page_url):
    r = requests.get(page_url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    html = r.text

    id_match = re.search(r'img-new\.cgtrader\.com/items/(\d+)/[a-f0-9]+/thumb/', html)
    if not id_match:
        return None, None, None

    item_id = id_match.group(1)
    pattern = rf'https://img-new\.cgtrader\.com/items/{item_id}/[a-f0-9]+/thumb/[^\s"\'<>]+'
    thumbs = list(dict.fromkeys(re.findall(pattern, html)))
    urls = [u.replace('/thumb/', '/') for u in thumbs]

    d_match = re.search(r'/designers/([a-zA-Z0-9_\-]+)', html)
    designer = "unknown"
    if d_match and d_match.group(1) not in ("browse", "top", "new", "popular"):
        designer = d_match.group(1)

    slug = page_url.rstrip("/").split("/")[-1][:50]
    return urls, designer, slug


async def do_download(update, context, url, msg=None):
    try:
        if msg:
            await msg.edit_text("🔍 Sayfa taranıyor...")
        else:
            msg = await update.message.reply_text("🔍 Sayfa taranıyor...")

        urls, designer, slug = extract_images(url)

        if not urls:
            await msg.edit_text("❌ Bu sayfada ürün resmi bulunamadı.")
            return

        await msg.edit_text(f"📦 {len(urls)} resim bulundu, indiriliyor...")

        zip_buffer = io.BytesIO()
        done = 0

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, img_url in enumerate(urls, 1):
                ext = img_url.split('.')[-1].split('?')[0] or 'jpg'
                filename = f"{i}.{ext}"
                try:
                    r = requests.get(img_url, headers=HEADERS, timeout=20)
                    if r.status_code == 200 and len(r.content) > 500:
                        zf.writestr(filename, r.content)
                        done += 1
                except Exception:
                    pass

                if i % 5 == 0:
                    await msg.edit_text(f"⏳ {i}/{len(urls)} indiriliyor...")

        zip_buffer.seek(0)
        zip_name = f"{designer} - {slug}.zip"

        await msg.edit_text(f"✅ {done} resim hazır, gönderiliyor...")
        await update.effective_message.reply_document(
            document=zip_buffer,
            filename=zip_name,
            caption=f"✅ {done} resim\n📁 {zip_name}"
        )
        await msg.delete()
        mark_downloaded(url, slug, designer)

    except Exception as e:
        if msg:
            await msg.edit_text(f"❌ Hata oluştu: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Merhaba! CGTrader Resim İndirici Bot'a hoş geldin.\n\n"
        "📎 Bana bir CGTrader ürün linki gönder, resimleri ZIP olarak sana göndereyim!\n\n"
        "📋 /gecmis — daha önce indirdiklerini gör"
    )

async def gecmis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history = load_history()
    if not history:
        await update.message.reply_text("📋 Henüz hiç indirme yapmadın.")
        return

    lines = ["📋 *İndirme Geçmişi*\n"]
    for i, (url, info) in enumerate(list(history.items())[-20:], 1):
        lines.append(f"{i}. `{info['designer']} - {info['slug'][:30]}`\n   🕐 {info['date']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "cgtrader.com" not in url:
        await update.message.reply_text("❌ Lütfen geçerli bir CGTrader ürün linki gönder.")
        return

    prev = is_downloaded(url)
    if prev:
        keyboard = [
            [
                InlineKeyboardButton("⬇️ Yine de indir", callback_data=f"dl|{url}"),
                InlineKeyboardButton("❌ İptal", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ *Bu ürünü daha önce indirdin!*\n\n"
            f"📁 {prev['designer']} - {prev['slug'][:40]}\n"
            f"🕐 {prev['date']}\n\n"
            f"Yine de indirmek ister misin?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    await do_download(update, context, url)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ İptal edildi.")
        return

    if query.data.startswith("dl|"):
        url = query.data[3:]
        await query.edit_message_text("⏳ İndiriliyor...")
        await do_download(update, context, url, msg=query.message)


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gecmis", gecmis))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("Bot başlatıldı...")
    app.run_polling()


if __name__ == "__main__":
    main()
