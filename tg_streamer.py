import os
import sys
import re
import json
import glob
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
RAW_CHANNEL_ID = os.environ.get("TG_CHANNEL_ID", "")

DATA_DIR = "/data/jellyfin"
MEDIA_DIR = os.path.join(DATA_DIR, "media/Movies")
CACHE_FILE = os.path.join(DATA_DIR, "file_ids.json")
CONFIG_FILE = os.path.join(DATA_DIR, "channel_config.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

# Persistent mapping: message_id -> file_id and learned channel_id
FILE_ID_CACHE = {}
DETECTED_CHANNEL_ID = None

def load_cache():
    global FILE_ID_CACHE, DETECTED_CHANNEL_ID
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                FILE_ID_CACHE = json.load(f)
                logger.info(f"[CACHE] Loaded {len(FILE_ID_CACHE)} file_ids from disk cache.")
        except Exception as e:
            logger.warning(f"[CACHE] Error loading file_ids.json: {e}")
            
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                DETECTED_CHANNEL_ID = cfg.get("channel_id")
                logger.info(f"[CONFIG] Loaded detected channel_id: {DETECTED_CHANNEL_ID}")
        except Exception as e:
            pass

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(FILE_ID_CACHE, f, indent=2)
    except Exception as e:
        logger.warning(f"[CACHE] Error saving file_ids.json: {e}")

def save_channel_config(cid):
    global DETECTED_CHANNEL_ID
    DETECTED_CHANNEL_ID = cid
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"channel_id": cid}, f, indent=2)
    except Exception as e:
        pass

load_cache()

def get_candidate_chat_ids():
    """Generates candidate chat IDs to handle different Telegram channel ID formats"""
    candidates = []
    if DETECTED_CHANNEL_ID:
        candidates.append(DETECTED_CHANNEL_ID)
    
    val = str(RAW_CHANNEL_ID).strip()
    if val:
        if val.startswith("@"):
            candidates.append(val)
        else:
            try:
                num = int(val)
                candidates.append(num)
                # Try adding or stripping -100 prefix
                if str(num).startswith("-100"):
                    raw_num = int(str(num)[4:])
                    candidates.append(raw_num)
                    candidates.append(-raw_num)
                else:
                    candidates.append(int(f"-100{abs(num)}"))
            except ValueError:
                candidates.append(val)
                
    # Deduplicate candidate list
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result

# Persistent Pyrogram Bot Client
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
        logger.info("[PYROGRAM] Pyrogram persistent client initialized.")
    except Exception as e:
        logger.error(f"[PYROGRAM] Error initializing Pyrogram: {e}")

routes = web.RouteTableDef()

@routes.get("/")
@routes.get("/health")
async def health(request):
    is_ready = bool(tg_app and tg_app.is_connected)
    return web.json_response({
        "status": "ok",
        "service": "TG-Drive Ultimate Dual Engine Streamer",
        "pyrogram_connected": is_ready,
        "raw_channel_id": RAW_CHANNEL_ID or "Not set",
        "detected_channel_id": DETECTED_CHANNEL_ID or "Not set",
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
    chat_id = message.chat.id if message.chat else None
    if chat_id and chat_id != DETECTED_CHANNEL_ID:
        save_channel_config(chat_id)

    media = getattr(message, message.media.value, None)
    if not media:
        return None

    file_id = getattr(media, "file_id", None)
    if file_id:
        FILE_ID_CACHE[str(msg_id)] = {
            "file_id": file_id,
            "chat_id": chat_id,
            "file_size": getattr(media, "file_size", 0)
        }
        save_cache()

    file_name = getattr(media, "file_name", None) or message.caption or f"Telegram_Movie_{msg_id}"
    clean_title = clean_movie_title(file_name) or f"Movie_{msg_id}"
    
    strm_filename = f"{clean_title}.strm"
    strm_path = os.path.join(MEDIA_DIR, strm_filename)
    
    # Always include file_id in stream URL for 100% instant fallback streaming!
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

def cleanup_orphan_strm_files():
    """Removes old .strm files that reference missing media to prevent 404/FileNotFound errors in Jellyfin"""
    try:
        strm_files = glob.glob(os.path.join(MEDIA_DIR, "*.strm"))
        removed = 0
        for strm_path in strm_files:
            try:
                with open(strm_path, "r") as f:
                    content = f.read().strip()
                if "file_id=" not in content:
                    match = re.search(r'/stream/(\d+)', content)
                    if match:
                        msg_id = match.group(1)
                        if msg_id not in FILE_ID_CACHE:
                            os.remove(strm_path)
                            removed += 1
            except Exception:
                pass
        if removed > 0:
            logger.info(f"[CLEANUP] Cleaned {removed} orphan .strm file(s).")
    except Exception as e:
        logger.warning(f"[CLEANUP] Warning during cleanup: {e}")

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
    1. Pyrogram MTProto Direct Stream (Fast, Unlimited File Size)
    2. Telegram Bot API getFile HTTP 206 Proxy (Failsafe Fallback)
    """
    file_id = request.query.get("file_id")
    msg_id_str = request.match_info.get("message_id") or request.query.get("message_id")
    filename = request.match_info.get("filename", "video.mp4")

    cached_entry = FILE_ID_CACHE.get(str(msg_id_str))
    if not file_id and cached_entry:
        if isinstance(cached_entry, dict):
            file_id = cached_entry.get("file_id")
        else:
            file_id = cached_entry

    # Attempt 1: Try Pyrogram MTProto Direct Streaming
    if tg_app and tg_app.is_connected and msg_id_str:
        try:
            message_id = int(msg_id_str)
            candidates = get_candidate_chat_ids()
            
            message = None
            for chat_candidate in candidates:
                try:
                    message = await tg_app.get_messages(chat_candidate, message_id)
                    if message and message.media:
                        save_channel_config(chat_candidate)
                        break
                except RPCError as pe:
                    if "PEER_ID_INVALID" in str(pe) or "Peer id invalid" in str(pe):
                        try:
                            chat_obj = await tg_app.get_chat(chat_candidate)
                            message = await tg_app.get_messages(chat_obj.id, message_id)
                            if message and message.media:
                                save_channel_config(chat_obj.id)
                                break
                        except Exception:
                            pass

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
            logger.warning(f"[STREAM] Pyrogram MTProto stream failed ({e}), switching to Bot API fallback...")

    # Attempt 2: Fallback to Telegram Bot API Range Streamer
    if file_id:
        return await stream_via_bot_api(request, file_id, filename)

    logger.error(f"[STREAM] Could not stream message {msg_id_str} - No valid MTProto peer or file_id.")
    return web.Response(status=404, text=f"Media not available for message {msg_id_str}. Please forward the video file to your Telegram Channel.")

async def start_pyrogram():
    """Starts Pyrogram Client, resolves candidate chats, and registers live message listener"""
    if not tg_app:
        logger.warning("[PYROGRAM] Pyrogram client not configured.")
        return

    logger.info("[PYROGRAM] Starting Pyrogram MTProto Client...")
    await tg_app.start()
    logger.info("[PYROGRAM] Pyrogram Client started successfully!")

    cleanup_orphan_strm_files()

    # Register global message listener for any channel/chat the bot is in
    @tg_app.on_message(filters.channel | filters.group)
    async def handle_new_post(client, message: Message):
        if message.media:
            process_telegram_message(message)
            await trigger_jellyfin_scan()

    candidates = get_candidate_chat_ids()
    for chat_candidate in candidates:
        try:
            logger.info(f"[PEER] Resolving chat candidate {chat_candidate}...")
            chat_obj = await tg_app.get_chat(chat_candidate)
            save_channel_config(chat_obj.id)
            logger.info(f"[PEER] Successfully resolved chat: '{chat_obj.title}' (ID: {chat_obj.id})")

            # Scan channel history (recent 50 messages)
            logger.info(f"[AUTO-SYNC] Scanning recent channel history for chat {chat_obj.id}...")
            async for message in tg_app.get_chat_history(chat_obj.id, limit=50):
                if message.media:
                    process_telegram_message(message)
            await trigger_jellyfin_scan()
            break
        except Exception as e:
            logger.warning(f"[PEER] Could not resolve candidate {chat_candidate}: {e}")

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
    logger.info(f"Starting TG-Drive Ultimate Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
