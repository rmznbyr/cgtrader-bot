import os
import re
import io
import zipfile
import hashlib
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "8360418340:AAHKn6zyjvzJc3Fulr6xTdidKK98Yd3rAYw")
HISTORY_CHANNEL = -1003947852695

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": "https://www.cgtrader.com/",
}

HISTORY = {}
URL_MAP = {}


def url_to_key(url):
    return hashlib.md5(url.encode()).hexdigest()[:16]


def parse_and_save(text):
    """Kanal mesajından URL ve bilgileri çıkar."""
    lines = text.strip().split('\n')
    url = None
    designer = "unknown"
    slug = "unknown"

    for line in lines:
        if "🔗 " in line:
            url = line.split("🔗 ", 1)[1].strip()
        elif line.startswith("✅ "):
            parts = line[2:].strip().split(" - ", 1)
            if len(parts) == 2:
                designer = parts[0].strip()
                slug = parts[1].strip()

    if url and "cgtrader.com" in url:
        HISTORY[url] = {
            "designer": designer,
            "slug": slug,
            "date": "Geçmiş"
        }
        return True
    return False


async def post_init(app):
    """Bot başlarken kanalı tara ve geçmişi yükle."""
    print("Kanal geçmişi yükleniyor...")
    loaded = 0

    try:
        # Kanal mesajlarını ID'ye göre tara (1'den başla)
        msg_id = 1
        empty_count = 0

        while empty_count < 20:
            try:
                msg = await app.bot.forward_message(
                    chat_id=HISTORY_CHANNEL,
                    from_chat_id=HISTORY_CHANNEL,
                    message_id=msg_id
                )
                # Forward edilen mesajı sil
                await app.bot.delete_message(
                    chat_id=HISTORY_CHANNEL,
                    message_id=msg.message_id
                )
                if msg.text and "🔗" in msg.text and "cgtrader.com" in msg.text:
                    if parse_and_save(msg.text):
                        loaded += 1
                empty_count = 0
            except Exception:
                empty_count += 1

            msg_id += 1
            if msg_id > 50000:
                break

        print(f"✅ {loaded} geçmiş kayıt yüklendi")
    except Exception as e:
        print(f"Geçmiş yükleme hatası: {e}")


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
            msg = await update.effective_message.reply_text("🔍 Sayfa taranıyor...")

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

        HISTORY[url] = {
            "designer": designer,
            "slug": slug,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }

        try:
            await context.bot.send_message(
                chat_id=HISTORY_CHANNEL,
                text=f"✅ {designer} - {slug}\n🔗 {url}",
                disable_web_page_preview=True
            )
        except Exception as e:
            print(f"Kanal hatası: {e}")

    except Exception as e:
        if msg:
            await msg.edit_text(f"❌ Hata oluştu: {str(e)}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "👋 Merhaba! CGTrader Resim İndirici Bot'a hoş geldin.\n\n"
        "📎 Bana bir CGTrader ürün linki gönder, resimleri ZIP olarak sana göndereyim!\n\n"
        "📋 /gecmis — daha önce indirdiklerini gör"
    )


async def gecmis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return
    if not HISTORY:
        await update.effective_message.reply_text(
            "📋 Henüz hiç indirme yapmadın.\n\n"
            f"Kanal: https://t.me/cgtrader_gecmis"
        )
        return

    lines = ["📋 *Son İndirmeler*\n"]
    for i, (url, info) in enumerate(list(HISTORY.items())[-20:], 1):
        lines.append(f"{i}. `{info['designer']} - {info['slug'][:30]}`\n   🕐 {info['date']}")

    lines.append(f"\n📺 Tüm geçmiş: https://t.me/cgtrader_gecmis")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text:
        return

    url = update.effective_message.text.strip()

    if "cgtrader.com" not in url:
        await update.effective_message.reply_text("❌ Lütfen geçerli bir CGTrader ürün linki gönder.")
        return

    if url in HISTORY:
        info = HISTORY[url]
        key = url_to_key(url)
        URL_MAP[key] = url
        keyboard = [[
            InlineKeyboardButton("⬇️ Yine de indir", callback_data=f"dl|{key}"),
            InlineKeyboardButton("❌ İptal", callback_data="cancel")
        ]]
        await update.effective_message.reply_text(
            f"⚠️ *Bu ürünü daha önce indirdin!*\n\n"
            f"📁 {info['designer']} - {info['slug'][:40]}\n"
            f"🕐 {info['date']}\n\n"
            f"Yine de indirmek ister misin?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
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
        key = query.data[3:]
        url = URL_MAP.get(key)
        if not url:
            await query.edit_message_text("❌ Link bulunamadı, tekrar gönder.")
            return
        await query.edit_message_text("⏳ İndiriliyor...")
        await do_download(update, context, url, msg=query.message)


def main():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(False)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gecmis", gecmis))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("Bot başlatıldı...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
