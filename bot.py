import os, threading, uuid, re
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import yt_dlp
from mutagen.id3 import ID3, TIT2, TPE1, APIC

# --- WEB SERVER FOR UPTIMEROBOT ---
server = Flask(__name__)
@server.route('/')
def ping(): return "Music Bot Active", 200

def run_web_server():
    server.run(host='0.0.0.0', port=10000)

# --- CONFIGURATION ---
TOKEN = "8401688638:AAHS9eelsM63xF6lqWXkC4n5GbFLCGg8y58"
url_map = {}

# --- HELPER: CLEAN TITLES ---
def clean_metadata(raw_title, uploader):
    # Scrub [Lyrics], (Official), etc.
    clean = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', raw_title)
    clean = clean.replace('|', '').replace('  ', ' ').strip()
    
    if " - " in clean:
        artist, song = clean.split(" - ", 1)
    else:
        artist = uploader
        song = clean
        
    return artist.strip(), song.strip()

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☁️ SoundCloud Search: Send me a song name!")

async def search_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    status = await update.message.reply_text(f"🔍 Searching: {query}...")

    ydl_opts = {'format': 'bestaudio', 'noplaylist': True, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Using SoundCloud search
            info = ydl.extract_info(f"scsearch5:{query}", download=False)
            results = info['entries']
        except Exception as e:
            await status.edit_text(f"❌ Search failed: {str(e)}")
            return

    if not results:
        await status.edit_text("❌ No results found.")
        return

    buttons = []
    for r in results:
        short_id = str(uuid.uuid4())[:8]
        url_map[short_id] = r.get('url')
        buttons.append([InlineKeyboardButton(r.get('title', 'Track')[:55], callback_data=short_id)])

    await status.edit_text("✅ Select a version:", reply_markup=InlineKeyboardMarkup(buttons))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    short_id = query.data
    sc_url = url_map.get(short_id)
    
    if not sc_url:
        await query.edit_message_text("❌ Session expired. Please search again.")
        return

    unique_id = str(uuid.uuid4())
    file_path = f"{unique_id}.mp3"

    await query.edit_message_text("🚀 Processing clean metadata...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': unique_id,
        'writethumbnail': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(sc_url, download=True)
            artist, song = clean_metadata(info.get('title', 'Unknown'), info.get('uploader', 'Unknown'))

        # --- TAG OVERRIDE ---
        audio = ID3(file_path)
        audio.delete() # Wipes out "Playlist/Frozen" junk tags
        audio.add(TPE1(encoding=3, text=artist)) # Force Artist
        audio.add(TIT2(encoding=3, text=song))   # Force Title
        
        # Add Thumbnail
        thumb_path = f"{unique_id}.jpg"
        if os.path.exists(thumb_path):
            with open(thumb_path, 'rb') as img:
                audio.add(APIC(3, 'image/jpeg', 3, 'Front Cover', img.read()))
        audio.save()

        # Send to Telegram
        await context.bot.send_audio(
            chat_id=query.message.chat_id, 
            audio=open(file_path, 'rb'),
            performer=artist,
            title=song,
            caption=f"✅ **{artist} - {song}**",
            parse_mode="Markdown"
        )
        await query.message.delete()
        if short_id in url_map: del url_map[short_id]
        
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Final cleanup of temp files
        for ext in ['.mp3', '.jpg', '.webp', '.png', '.original']:
            p = unique_id + ext
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_music))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling()
