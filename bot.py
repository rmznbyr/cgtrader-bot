import os
import re
import io
import zipfile
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "8360418340:AAHKn6zyjvzJc3Fulr6xTdidKK98Yd3rAYw")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": "https://www.cgtrader.com/",
}


def extract_images(page_url):
    r = requests.get(page_url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    html = r.text

    # Item ID
    id_match = re.search(r'img-new\.cgtrader\.com/items/(\d+)/[a-f0-9]+/thumb/', html)
    if not id_match:
        return None, None, None

    item_id = id_match.group(1)

    # Sadece bu ürüne ait thumb URL'leri
    pattern = rf'https://img-new\.cgtrader\.com/items/{item_id}/[a-f0-9]+/thumb/[^\s"\'<>]+'
    thumbs = list(dict.fromkeys(re.findall(pattern, html)))
    urls = [u.replace('/thumb/', '/') for u in thumbs]

    # Tasarımcı
    d_match = re.search(r'/designers/([a-zA-Z0-9_\-]+)', html)
    designer = "unknown"
    if d_match and d_match.group(1) not in ("browse", "top", "new", "popular"):
        designer = d_match.group(1)

    # Slug
    slug = page_url.rstrip("/").split("/")[-1][:50]

    return urls, designer, slug


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Merhaba! CGTrader Resim İndirici Bot'a hoş geldin.\n\n"
        "📎 Bana bir CGTrader ürün linki gönder, resimleri ZIP olarak sana göndereyim!"
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "cgtrader.com" not in url:
        await update.message.reply_text("❌ Lütfen geçerli bir CGTrader ürün linki gönder.")
        return

    msg = await update.message.reply_text("🔍 Sayfa taranıyor...")

    try:
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
        await update.message.reply_document(
            document=zip_buffer,
            filename=zip_name,
            caption=f"✅ {done} resim\n📁 {zip_name}"
        )
        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Hata oluştu: {str(e)}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("Bot başlatıldı...")
    app.run_polling()


if __name__ == "__main__":
    main()
