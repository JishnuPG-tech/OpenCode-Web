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

# Persistent mapping: message_id -> {file_id, chat_id, file_size, title}
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
        "service": "TG-Drive Direct FileId MTProto Streamer",
        "pyrogram_connected": is_ready,
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

def create_strm_file(msg_id, file_id, clean_title):
    """Writes .strm file into Jellyfin Movies directory"""
    strm_filename = f"{clean_title}.strm"
    strm_path = os.path.join(MEDIA_DIR, strm_filename)
    
    stream_url = f"http://127.0.0.1:8080/stream_file?file_id={file_id}&message_id={msg_id}&filename={clean_title}.mp4"

    with open(strm_path, "w") as f:
        f.write(stream_url)
    
    logger.info(f"[AUTO-SYNC] 🎉 Created movie .strm file: {strm_filename} -> {strm_path}")
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

@routes.post("/")
@routes.post("/telegram-webhook")
@routes.post("/webhook")
async def telegram_webhook(request):
    """
    Telegram Webhook Handler:
    Parses live incoming channel posts / forwarded messages sent to the bot/channel,
    extracts file_id + movie title, creates .strm file, and triggers Jellyfin rescan!
    """
    try:
        data = await request.json()
        logger.info(f"[WEBHOOK] Received update from Telegram: update_id={data.get('update_id')}")

        post = data.get("channel_post") or data.get("message")
        if not post:
            return web.json_response({"ok": True})

        msg_id = post.get("message_id")
        chat = post.get("chat", {})
        chat_id = chat.get("id")

        # Extract video / document / audio / animation media
        media_obj = post.get("video") or post.get("document") or post.get("audio") or post.get("animation")
        if not media_obj:
            return web.json_response({"ok": True})

        file_id = media_obj.get("file_id")
        file_name = media_obj.get("file_name") or post.get("caption") or f"Telegram_Movie_{msg_id}"
        file_size = media_obj.get("file_size", 0)
        clean_title = clean_movie_title(file_name) or f"Movie_{msg_id}"

        if file_id and msg_id:
            FILE_ID_CACHE[str(msg_id)] = {
                "file_id": file_id,
                "chat_id": chat_id,
                "file_size": file_size,
                "title": clean_title
            }
            save_cache()

            strm_name = create_strm_file(msg_id, file_id, clean_title)
            logger.info(f"[WEBHOOK] 🎉 Successfully indexed movie from Webhook: {strm_name}")
            await trigger_jellyfin_scan()

        return web.json_response({"ok": True})
    except Exception as e:
        logger.error(f"[WEBHOOK] Error processing webhook payload: {e}")
        return web.json_response({"ok": True})

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
    Direct FileId MTProto Streamer:
    Streams movie bytes directly via Pyrogram MTProto using the raw file_id.
    Zero peer resolution required! Zero channel requirements! Unlimited file size!
    """
    file_id = request.query.get("file_id")
    msg_id_str = request.match_info.get("message_id") or request.query.get("message_id")
    filename = request.match_info.get("filename", "video.mp4")

    cached_entry = FILE_ID_CACHE.get(str(msg_id_str))
    file_size = 0
    if isinstance(cached_entry, dict):
        if not file_id:
            file_id = cached_entry.get("file_id")
        file_size = cached_entry.get("file_size", 0)

    if not file_id:
        return web.Response(status=404, text=f"Media not available for message {msg_id_str}.")

    # Primary Direct Pyrogram MTProto Stream via file_id
    if tg_app and tg_app.is_connected:
        try:
            range_header = request.headers.get("Range")
            offset = 0
            limit = file_size

            if range_header and file_size > 0:
                match = re.match(r"^bytes=(\d+)-(\d+)?$", range_header)
                if match:
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else file_size - 1
                    offset = start
                    limit = end - start + 1

            chunk_size = 1024 * 1024
            chunk_offset = offset // chunk_size
            chunk_limit = ((limit + chunk_size - 1) // chunk_size) + 1 if limit > 0 else 0

            status = 206 if range_header and file_size > 0 else 200
            headers = {
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Content-Disposition": f'inline; filename="{filename}"'
            }
            if file_size > 0:
                headers["Content-Length"] = str(limit if range_header else file_size)
                if range_header:
                    headers["Content-Range"] = f"bytes {offset}-{offset + limit - 1}/{file_size}"

            logger.info(f"[MTPROTO-FILEID] Direct streaming ({filename}) via Pyrogram MTProto FileId")

            response = web.StreamResponse(status=status, headers=headers)
            await response.prepare(request)

            async for chunk in tg_app.stream_media(file_id, offset=chunk_offset, limit=chunk_limit):
                await response.write(chunk)

            return response
        except Exception as e:
            logger.warning(f"[STREAM] Direct MTProto stream via file_id failed ({e}), attempting Bot API fallback...")

    # Secondary Fallback: Bot API HTTP Proxy
    return await stream_via_bot_api(request, file_id, filename)

async def restore_cached_strm_files():
    """Restores all cached movie .strm files from FILE_ID_CACHE on boot"""
    count = 0
    for msg_id, data in FILE_ID_CACHE.items():
        if isinstance(data, dict):
            file_id = data.get("file_id")
            title = data.get("title") or f"Movie_{msg_id}"
            if file_id and title:
                create_strm_file(msg_id, file_id, title)
                count += 1
    if count > 0:
        logger.info(f"[RESTORE] Restored {count} movie .strm file(s) from persistent disk cache.")
        await trigger_jellyfin_scan()

async def start_pyrogram():
    """Starts Pyrogram Client and restores cached movies"""
    await restore_cached_strm_files()

    if not tg_app:
        logger.warning("[PYROGRAM] Pyrogram client not configured.")
        return

    logger.info("[PYROGRAM] Starting Pyrogram MTProto Client...")
    await tg_app.start()
    logger.info("[PYROGRAM] Pyrogram Client started successfully!")

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
    logger.info(f"Starting TG-Drive Direct FileId Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
