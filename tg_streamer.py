import os
import sys
import re
import json
import logging
import asyncio
import socket
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

DATA_DIR = "/data/jellyfin"
MEDIA_DIR = os.path.join(DATA_DIR, "media/Movies")
CACHE_FILE = os.path.join(DATA_DIR, "file_ids.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

# Persistent mapping from message_id -> file_id
FILE_ID_CACHE = {}

def load_file_id_cache():
    global FILE_ID_CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                FILE_ID_CACHE = json.load(f)
                logger.info(f"[CACHE] Loaded {len(FILE_ID_CACHE)} file_ids from disk cache.")
        except Exception as e:
            logger.warning(f"[CACHE] Error loading file_ids.json: {e}")

def save_file_id_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(FILE_ID_CACHE, f, indent=2)
    except Exception as e:
        logger.warning(f"[CACHE] Error saving file_ids.json: {e}")

load_file_id_cache()

def parse_chat_id(val):
    """Safely parses TG_CHANNEL_ID into integer or username string"""
    if not val:
        return None
    val = str(val).strip()
    if val.startswith("@"):
        return val
    try:
        return int(val)
    except ValueError:
        return val

# Persistent Pyrogram Bot Client (in_memory=False to save peer access hashes to /data/jellyfin)
tg_app = None
if API_ID and API_HASH and BOT_TOKEN:
    try:
        tg_app = Client(
            "tg_jellyfin_session",
            api_id=int(API_ID),
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workdir=DATA_DIR,
            in_memory=False
        )
        logger.info("[PYROGRAM] Pyrogram persistent client instantiated successfully.")
    except Exception as e:
        logger.error(f"[PYROGRAM] Error instantiating Pyrogram: {e}")

routes = web.RouteTableDef()

@routes.get("/")
@routes.get("/health")
async def health(request):
    is_ready = bool(tg_app and tg_app.is_connected)
    return web.json_response({
        "status": "ok",
        "service": "TG-Drive Dual Engine Streamer (MTProto + Bot API)",
        "pyrogram_connected": is_ready,
        "channel_id": CHANNEL_ID or "Not set",
        "cached_files": len(FILE_ID_CACHE),
        "media_dir": MEDIA_DIR
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

    file_id = getattr(media, "file_id", None)
    if file_id:
        FILE_ID_CACHE[str(msg_id)] = file_id
        save_file_id_cache()

    file_name = getattr(media, "file_name", None) or message.caption or f"Telegram_Movie_{msg_id}"
    clean_title = clean_movie_title(file_name) or f"Movie_{msg_id}"
    
    strm_filename = f"{clean_title}.strm"
    strm_path = os.path.join(MEDIA_DIR, strm_filename)
    
    if file_id:
        stream_url = f"http://127.0.0.1:8080/stream_file?file_id={file_id}&message_id={msg_id}&filename={clean_title}.mp4"
    else:
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

async def stream_via_bot_api(request, file_id, filename):
    """Fallback Streamer using Telegram Bot API getFile + HTTP Range Proxy"""
    if not BOT_TOKEN or not file_id:
        return web.Response(status=404, text="Missing file_id or BOT_TOKEN")

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    headers_req = {"User-Agent": "Mozilla/5.0"}
    
    async with aiohttp.ClientSession(connector=connector, headers=headers_req) as session:
        get_file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        async with session.get(get_file_url) as resp:
            if resp.status != 200:
                logger.error(f"[BOT-API] getFile failed with status {resp.status}")
                return web.Response(status=resp.status, text="Failed to resolve file path from Telegram Bot API")
            
            data = await resp.json()
            file_path = data.get("result", {}).get("file_path")
            file_size = data.get("result", {}).get("file_size", 0)

        if not file_path:
            return web.Response(status=404, text="Telegram file path not found")

        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        pass_headers = {}
        if "Range" in request.headers:
            pass_headers["Range"] = request.headers["Range"]

        logger.info(f"[BOT-API] Streaming {filename} via Bot API Proxy (Size: {file_size} bytes)")

        async with session.get(download_url, headers=pass_headers) as stream_resp:
            resp_headers = {
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Content-Disposition": f'inline; filename="{filename}"'
            }
            if "Content-Length" in stream_resp.headers:
                resp_headers["Content-Length"] = stream_resp.headers["Content-Length"]
            if "Content-Range" in stream_resp.headers:
                resp_headers["Content-Range"] = stream_resp.headers["Content-Range"]

            response = web.StreamResponse(status=stream_resp.status, headers=resp_headers)
            await response.prepare(request)
            
            async for chunk in stream_resp.content.iter_chunked(64 * 1024):
                await response.write(chunk)
            
            return response

@routes.get("/stream_file")
@routes.get("/stream/{message_id}")
@routes.get("/stream/{message_id}/{filename}")
async def stream_file(request):
    """
    Dual Streamer:
    Primary: Pyrogram MTProto Direct Stream (Fast, Unlimited File Size)
    Fallback: Telegram Bot API getFile HTTP 206 Proxy
    """
    file_id = request.query.get("file_id")
    msg_id_str = request.match_info.get("message_id") or request.query.get("message_id")
    filename = request.match_info.get("filename", "video.mp4")

    if not file_id and msg_id_str:
        file_id = FILE_ID_CACHE.get(str(msg_id_str))

    # Try Pyrogram MTProto Stream first
    if tg_app and tg_app.is_connected and msg_id_str and CHANNEL_ID:
        try:
            message_id = int(msg_id_str)
            chat_id = parse_chat_id(CHANNEL_ID)
            
            message = None
            try:
                message = await tg_app.get_messages(chat_id, message_id)
            except RPCError as pe:
                if "PEER_ID_INVALID" in str(pe) or "Peer id invalid" in str(pe):
                    logger.info(f"[PYROGRAM] Refreshing peer cache for chat {chat_id}...")
                    chat_obj = await tg_app.get_chat(chat_id)
                    message = await tg_app.get_messages(chat_obj.id, message_id)

            if message and message.media:
                media = getattr(message, message.media.value, None)
                file_size = getattr(media, "file_size", 0)

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

                logger.info(f"[PYROGRAM] Streaming Msg #{message_id} ({filename}) via MTProto")

                response = web.StreamResponse(status=status, headers=headers)
                await response.prepare(request)

                async for chunk in tg_app.stream_media(message, offset=chunk_offset, limit=chunk_limit):
                    await response.write(chunk)

                return response
        except Exception as e:
            logger.warning(f"[STREAM] Pyrogram MTProto stream failed ({e}), attempting Bot API fallback...")

    # Fallback to Bot API HTTP Proxy if file_id is available
    if file_id:
        return await stream_via_bot_api(request, file_id, filename)

    logger.error(f"[STREAM] Could not stream message {msg_id_str} - No valid MTProto peer or file_id.")
    return web.Response(status=404, text=f"Media not available for message {msg_id_str}")

async def start_pyrogram():
    """Starts Pyrogram Client with persistent session and auto-scans channel history on boot"""
    if not tg_app:
        logger.warning("[PYROGRAM] Pyrogram client not configured.")
        return

    logger.info("[PYROGRAM] Starting Pyrogram MTProto Client with persistent session...")
    await tg_app.start()
    logger.info("[PYROGRAM] Pyrogram Client started successfully!")

    target_chat = parse_chat_id(CHANNEL_ID)
    if target_chat:
        try:
            logger.info(f"[PEER] Resolving and caching chat {target_chat}...")
            chat_obj = await tg_app.get_chat(target_chat)
            logger.info(f"[PEER] Chat resolved: '{chat_obj.title}' (ID: {chat_obj.id})")
            target_chat = chat_obj.id

            @tg_app.on_message(filters.chat(target_chat))
            async def handle_new_post(client, message: Message):
                if message.media:
                    process_telegram_message(message)
                    await trigger_jellyfin_scan()

            logger.info(f"[AUTO-SYNC] Scanning recent channel history for chat {target_chat}...")
            async for message in tg_app.get_chat_history(target_chat, limit=50):
                if message.media:
                    process_telegram_message(message)
            await trigger_jellyfin_scan()
        except Exception as e:
            logger.warning(f"[AUTO-SYNC] Channel listener/history scan warning: {e}")

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
    logger.info(f"Starting TG-Drive Dual Engine Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
