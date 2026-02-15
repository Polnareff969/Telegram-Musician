import os, threading, uuid, re
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import yt_dlp
from mutagen.id3 import ID3, TIT2, TPE1, APIC

# --- WEB SERVER FOR UPTIMEROBOT ---
server = Flask(__name__)
@server.route('/')
def ping(): return "SoundCloud Bot is Alive", 200

def run_web_server():
    server.run(host='0.0.0.0', port=10000)

# --- CONFIGURATION ---
TOKEN = "8401688638:AAHS9eelsM63xF6lqWXkC4n5GbFLCGg8y58"

# --- HELPER: CLEAN TITLES ---
def clean_metadata(raw_title, uploader):
    # SoundCloud titles often already have Artist - Title
    clean = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', raw_title)
    clean = clean.replace('|', '').replace('  ', ' ').strip()
    
    if " - " in clean:
        artist, song = clean.split(" - ", 1)
    else:
        # If no dash, use the SoundCloud uploader name as Artist
        artist = uploader
        song = clean
        
    return artist.strip(), song.strip()

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☁️ SoundCloud Search: Send me a song name!")

async def search_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    status = await update.message.reply_text(f"🔍 Searching SoundCloud for: {query}...")

    # CHANGED TO SCSEARCH
    ydl_opts = {
        'format': 'bestaudio', 
        'noplaylist': True, 
        'quiet': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Prefix changed to scsearch
            info = ydl.extract_info(f"scsearch5:{query}", download=False)
            results = info['entries']
        except Exception as e:
            await status.edit_text(f"❌ SoundCloud search failed: {str(e)}")
            return

    if not results:
        await status.edit_text("❌ No results found.")
        return

    buttons = [[InlineKeyboardButton(r.get('title', 'Unknown')[:55], callback_data=r.get('url'))] for r in results]
    await status.edit_text("✅ Select from SoundCloud:", reply_markup=InlineKeyboardMarkup(buttons))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    sc_url = query.data # SoundCloud uses full URLs for callback safely
    unique_id = str(uuid.uuid4())
    file_path = f"{unique_id}.mp3"

    await query.edit_message_text("🚀 Downloading from SoundCloud...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': unique_id,
        'writethumbnail': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {
            'key': 'FFmpegThumbnailsConvertor',
            'format': 'jpg',
        }],
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(sc_url, download=True)
            artist, song = clean_metadata(info.get('title', 'Unknown'), info.get('uploader', 'Unknown'))

        # Inject Metadata
        audio = ID3(file_path)
        audio.add(TPE1(encoding=3, text=artist))
        audio.add(TIT2(encoding=3, text=song))
        
        # Add Thumbnail
        thumb_path = f"{unique_id}.jpg"
        if os.path.exists(thumb_path):
            with open(thumb_path, 'rb') as img:
                audio.add(APIC(3, 'image/jpeg', 3, 'Front Cover', img.read()))
        audio.save()

        await context.bot.send_audio(
            chat_id=query.message.chat_id, 
            audio=open(file_path, 'rb'),
            performer=artist,
            title=song,
            caption=f"☁️ **{artist} - {song}**",
            parse_mode="Markdown"
        )
        await query.message.delete()
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        for ext in ['.mp3', '.jpg', '.webp', '.png', '.original']:
            if os.path.exists(unique_id + ext): os.remove(unique_id + ext)

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_music))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling()
