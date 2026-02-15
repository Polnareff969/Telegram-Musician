import os, threading, uuid, re
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import yt_dlp
from mutagen.id3 import ID3, TIT2, TPE1, APIC

# --- WEB SERVER FOR UPTIMEROBOT ---
server = Flask(__name__)
@server.route('/')
def ping(): return "Music Bot is Alive", 200

def run_web_server():
    # Render uses port 10000 by default
    server.run(host='0.0.0.0', port=10000)

# --- CONFIGURATION ---
TOKEN = "8401688638:AAHS9eelsM63xF6lqWXkC4n5GbFLCGg8y58"

# --- HELPER: CLEAN TITLES ---
def clean_metadata(raw_title, uploader):
    # Remove junk like [Official Video], (Lyrics), etc.
    clean = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', raw_title)
    # Remove extra spaces and special chars
    clean = clean.replace('|', '').replace('  ', ' ').strip()
    
    if " - " in clean:
        artist, song = clean.split(" - ", 1)
    else:
        artist = uploader
        song = clean
        
    return artist.strip(), song.strip()

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎵 Send me a song name to search!")

async def search_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    status = await update.message.reply_text(f"🔍 Searching for: {query}...")

    ydl_opts = {'format': 'bestaudio', 'noplaylist': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            results = info['entries']
        except Exception:
            await status.edit_text("❌ Search failed.")
            return

    buttons = [[InlineKeyboardButton(r['title'][:55], callback_data=r['id'])] for r in results]
    await status.edit_text("✅ Select the version:", reply_markup=InlineKeyboardMarkup(buttons))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    video_id = query.data
    url = f"https://www.youtube.com/watch?v={video_id}"
    unique_id = str(uuid.uuid4())
    file_path = f"{unique_id}.mp3"

    await query.edit_message_text("🚀 Downloading & Tagging...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': unique_id,
        'writethumbnail': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {
            # Force conversion of thumbnails to jpg so Mutagen can read them
            'key': 'FFmpegThumbnailsConvertor',
            'format': 'jpg',
        }],
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            artist, song = clean_metadata(info['title'], info['uploader'])

        # Injecting Cleaned Metadata
        audio = ID3(file_path)
        audio.add(TPE1(encoding=3, text=artist))
        audio.add(TIT2(encoding=3, text=song))
        
        # Add Thumbnail
        thumb_path = f"{unique_id}.jpg"
        if os.path.exists(thumb_path):
            with open(thumb_path, 'rb') as img:
                audio.add(APIC(3, 'image/jpeg', 3, 'Front Cover', img.read()))
        audio.save()

        # Send to User
        await context.bot.send_audio(
            chat_id=query.message.chat_id, 
            audio=open(file_path, 'rb'),
            performer=artist,
            title=song,
            caption=f"✅ **{artist} - {song}**",
            parse_mode="Markdown"
        )
        await query.message.delete()
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Cleanup
        for ext in ['.mp3', '.jpg', '.webp', '.png']:
            if os.path.exists(unique_id + ext): os.remove(unique_id + ext)

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_music))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling()
