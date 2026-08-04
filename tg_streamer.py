import os
import sys
import re
import json
import logging
import asyncio
import aiohttp
from aiohttp import web

# Pyrogram imports for MTProto direct chunk streaming
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TG_Drive_Streamer")

HOST = "127.0.0.1"
PORT = 8080

API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TG_CHANNEL_ID")

MEDIA_DIR = "/data/jellyfin/media/Movies"
os.makedirs(MEDIA_DIR, exist_ok=True)

# Initialize Pyrogram Bot Client
tg_app = None
if API_ID and API_HASH and BOT_TOKEN:
    try:
        tg_app = Client(
            "tg_jellyfin_streamer",
            api_id=int(API_ID),
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            in_memory=True
        )
        logger.info("[PYROGRAM] Pyrogram client instantiated successfully.")
    except Exception as e:
        logger.error(f"[PYROGRAM] Error instantiating Pyrogram: {e}")

routes = web.RouteTableDef()

@routes.get("/")
@routes.get("/health")
async def health(request):
    is_ready = bool(tg_app and tg_app.is_connected)
    return web.json_response({
        "status": "ok",
        "service": "TG-Drive MTProto Streamer & Auto-Sync Engine",
        "pyrogram_connected": is_ready,
        "channel_id": CHANNEL_ID or "Not set",
        "media_dir": MEDIA_DIR,
        "mode": "Pyrogram MTProto High-Speed Direct Streamer"
    })

def clean_movie_title(text):
    """Clean filename/caption to a nice movie title"""
    if not text:
        return None
    text = re.sub(r'\.(mp4|mkv|avi|mov|wmv|flv)$', '', text, flags=re.IGNORECASE)
    text = text.replace('.', ' ').replace('_', ' ')
    return text.strip()

def process_telegram_message(message: Message):
    """Generates .strm file in Jellyfin media directory for a Telegram Message"""
    if not message or not message.media:
        return None
        
    msg_id = message.id
    media = getattr(message, message.media.value, None)
    if not media:
        return None

    file_name = getattr(media, "file_name", None) or message.caption or f"Telegram_Movie_{msg_id}"
    clean_title = clean_movie_title(file_name) or f"Movie_{msg_id}"
    
    strm_filename = f"{clean_title}.strm"
    strm_path = os.path.join(MEDIA_DIR, strm_filename)
    
    stream_url = f"http://127.0.0.1:8080/stream/{msg_id}/{clean_title}.mp4"

    with open(strm_path, "w") as f:
        f.write(stream_url)
    
    logger.info(f"[AUTO-SYNC] 🎉 Indexed movie: {strm_filename} -> {strm_path}")
    return strm_filename

async def trigger_jellyfin_scan():
    """Trigger Jellyfin Library Scan automatically"""
    try:
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post("http://127.0.0.1:8096/Library/Refresh") as resp:
                logger.info(f"Jellyfin library refresh triggered: {resp.status}")
    except Exception as e:
        logger.warning(f"Could not trigger Jellyfin library refresh: {e}")

@routes.get("/stream_file")
@routes.get("/stream/{message_id}")
@routes.get("/stream/{message_id}/{filename}")
async def stream_file(request):
    """
    MTProto High-Speed Chunk Streamer via Pyrogram.
    Pipes binary chunks directly from Telegram servers to Jellyfin with Range seeking support.
    """
    msg_id_str = request.match_info.get("message_id") or request.query.get("message_id")
    filename = request.match_info.get("filename", "video.mp4")

    if not msg_id_str:
        return web.Response(status=400, text="Missing message_id")

    try:
        message_id = int(msg_id_str)
    except ValueError:
        return web.Response(status=400, text="Invalid message_id")

    if not tg_app or not tg_app.is_connected:
        logger.error("[STREAM] Pyrogram Client is not connected!")
        return web.Response(status=503, text="Telegram Client not connected")

    chat_id = int(CHANNEL_ID) if CHANNEL_ID else None
    if not chat_id:
        return web.Response(status=400, text="TG_CHANNEL_ID not set")

    try:
        # Fetch Telegram Message via MTProto
        message = await tg_app.get_messages(chat_id, message_id)
        if not message or not message.media:
            logger.error(f"[STREAM] Message {message_id} media not found in channel {chat_id}")
            return web.Response(status=404, text=f"Media not found for message {message_id}")

        media = getattr(message, message.media.value, None)
        file_size = getattr(media, "file_size", 0)

        # Parse HTTP Range header
        range_header = request.headers.get("Range")
        offset = 0
        limit = file_size

        if range_header:
            match = re.match(r"^bytes=(\d+)-(\d+)?$", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else file_size - 1
                offset = start
                limit = end - start + 1

        # Calculate chunk parameters for Pyrogram (1MB chunks)
        chunk_size = 1024 * 1024
        chunk_offset = offset // chunk_size
        chunk_limit = ((limit + chunk_size - 1) // chunk_size) + 1 if limit > 0 else 0

        status = 206 if range_header else 200
        headers = {
            "Content-Type": "video/mp4",
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(limit if range_header else file_size)
        }
        if range_header:
            headers["Content-Range"] = f"bytes {offset}-{offset + limit - 1}/{file_size}"

        logger.info(f"[STREAM] Proxying Msg #{message_id} ({filename}) - Size: {file_size} bytes, Offset: {offset}, Limit: {limit}")

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        async for chunk in tg_app.stream_media(message, offset=chunk_offset, limit=chunk_limit):
            await response.write(chunk)

        return response
    except RPCError as e:
        logger.error(f"[STREAM] Pyrogram RPCError streaming message {message_id}: {e}")
        return web.Response(status=500, text=f"Telegram API Error: {e}")
    except Exception as e:
        logger.error(f"[STREAM] Error streaming message {message_id}: {e}")
        return web.Response(status=500, text=str(e))

async def start_pyrogram():
    """Starts Pyrogram Client & auto-scans channel history on boot"""
    if not tg_app:
        logger.warning("[PYROGRAM] Pyrogram client not configured (Missing TG_API_ID/TG_API_HASH/TG_BOT_TOKEN).")
        return

    logger.info("[PYROGRAM] Starting Pyrogram MTProto Client...")
    await tg_app.start()
    logger.info("[PYROGRAM] Pyrogram Client started successfully!")

    # Register live channel listener
    if CHANNEL_ID:
        try:
            target_chat = int(CHANNEL_ID)
            @tg_app.on_message(filters.chat(target_chat))
            async def handle_new_post(client, message: Message):
                if message.media:
                    process_telegram_message(message)
                    await trigger_jellyfin_scan()

            # Initial channel history scan (recent 50 messages)
            logger.info(f"[AUTO-SYNC] Scanning recent channel history for chat {target_chat}...")
            async for message in tg_app.get_chat_history(target_chat, limit=50):
                if message.media:
                    process_telegram_message(message)
            await trigger_jellyfin_scan()
        except Exception as e:
            logger.warning(f"[AUTO-SYNC] Channel listener/history setup warning: {e}")

async def stop_pyrogram():
    if tg_app and tg_app.is_connected:
        await tg_app.stop()

async def start_background_tasks(app):
    app['pyrogram_task'] = asyncio.create_task(start_pyrogram())

async def cleanup_background_tasks(app):
    await stop_pyrogram()

app = web.Application()
app.add_routes(routes)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == "__main__":
    import socket
    logger.info(f"Starting TG-Drive MTProto Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
