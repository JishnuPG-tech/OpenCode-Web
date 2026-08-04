import os
import sys
import re
import json
import glob
import socket
import logging
import asyncio
import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TG_Drive_Streamer")

HOST = "127.0.0.1"
PORT = 8080

API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TG_CHANNEL_ID")

MEDIA_DIR = "/data/jellyfin/media/Movies"
CACHE_FILE = "/data/jellyfin/file_ids.json"
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

def cleanup_orphan_strm_files():
    """Removes old .strm files that reference message IDs without valid file_id mappings"""
    try:
        strm_files = glob.glob(os.path.join(MEDIA_DIR, "*.strm"))
        removed_count = 0
        for strm_path in strm_files:
            try:
                with open(strm_path, "r") as f:
                    content = f.read().strip()
                if "file_id=" not in content:
                    # Legacy URL format: /stream/{message_id}/{filename}
                    match = re.search(r'/stream/(\d+)', content)
                    if match:
                        msg_id = match.group(1)
                        if msg_id not in FILE_ID_CACHE:
                            os.remove(strm_path)
                            removed_count += 1
                            logger.info(f"[CLEANUP] Removed orphan .strm file without file_id: {strm_path}")
            except Exception as e:
                logger.warning(f"[CLEANUP] Error checking {strm_path}: {e}")
        if removed_count > 0:
            logger.info(f"[CLEANUP] Removed {removed_count} orphan .strm file(s).")
    except Exception as e:
        logger.warning(f"[CLEANUP] General cleanup error: {e}")

load_file_id_cache()
cleanup_orphan_strm_files()

routes = web.RouteTableDef()

@routes.get("/")
@routes.get("/health")
async def health(request):
    is_configured = bool(BOT_TOKEN)
    return web.json_response({
        "status": "ok",
        "service": "TG-Drive Real Direct Streamer & Auto-Sync Engine",
        "configured": is_configured,
        "channel_id": CHANNEL_ID or "Not set",
        "media_dir": MEDIA_DIR,
        "cached_files": len(FILE_ID_CACHE),
        "mode": "Persistent Telegram Binary Streamer"
    })

@routes.get("/stream_file")
@routes.get("/stream/{message_id}")
@routes.get("/stream/{message_id}/{filename}")
async def stream_file(request):
    """
    Real HTTP 206 Partial Content Range Proxy for Telegram Files
    Pipes actual binary chunks from Telegram to Jellyfin on-the-fly.
    """
    file_id = request.query.get("file_id")
    message_id = request.match_info.get("message_id")
    filename = request.match_info.get("filename", "video.mp4")

    if not file_id and message_id:
        file_id = FILE_ID_CACHE.get(str(message_id))

    if not file_id or not BOT_TOKEN:
        logger.error(f"[STREAM] Missing file_id or BOT_TOKEN for message_id: {message_id}")
        return web.Response(status=404, text=f"File ID not found for message {message_id}. Please re-forward the file to your Telegram channel.")

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    headers_req = {"User-Agent": "Mozilla/5.0"}
    
    async with aiohttp.ClientSession(connector=connector, headers=headers_req) as session:
        # Step 1: Get File Path from Telegram API
        get_file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        async with session.get(get_file_url) as resp:
            if resp.status != 200:
                logger.error(f"[STREAM] Telegram getFile failed with status {resp.status}")
                return web.Response(status=resp.status, text="Failed to resolve file path from Telegram")
            
            data = await resp.json()
            file_path = data.get("result", {}).get("file_path")
            file_size = data.get("result", {}).get("file_size", 0)

        if not file_path:
            logger.error("[STREAM] File path empty in Telegram response")
            return web.Response(status=404, text="Telegram file path not found")

        # Step 2: Proxy Binary Media Stream with Range Header Support
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        pass_headers = {}
        if "Range" in request.headers:
            pass_headers["Range"] = request.headers["Range"]

        logger.info(f"[STREAM] Proxying {filename} (Size: {file_size} bytes, Range: {pass_headers.get('Range', 'Full')})")

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

            response = web.StreamResponse(
                status=stream_resp.status,
                headers=resp_headers
            )
            await response.prepare(request)
            
            async for chunk in stream_resp.content.iter_chunked(64 * 1024):
                await response.write(chunk)
            
            return response

def clean_movie_title(text):
    """Clean filename/caption to a nice movie title"""
    if not text:
        return None
    text = re.sub(r'\.(mp4|mkv|avi|mov|wmv|flv)$', '', text, flags=re.IGNORECASE)
    text = text.replace('.', ' ').replace('_', ' ')
    return text.strip()

async def trigger_jellyfin_scan():
    """Trigger Jellyfin Library Scan automatically"""
    try:
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post("http://127.0.0.1:8096/Library/Refresh") as resp:
                logger.info(f"Jellyfin library refresh triggered: {resp.status}")
    except Exception as e:
        logger.warning(f"Could not trigger Jellyfin library refresh: {e}")

def process_telegram_post(post):
    """Processes a Telegram channel post or message and creates a .strm file with file_id"""
    if not post:
        return None
        
    message_id = post.get("message_id")
    video = post.get("video") or post.get("document")
    
    if video and message_id:
        file_id = video.get("file_id")
        file_name = video.get("file_name") or post.get("caption") or f"Telegram_Movie_{message_id}"
        clean_title = clean_movie_title(file_name) or f"Movie_{message_id}"
        
        if file_id:
            FILE_ID_CACHE[str(message_id)] = file_id
            save_file_id_cache()
        
        strm_filename = f"{clean_title}.strm"
        strm_path = os.path.join(MEDIA_DIR, strm_filename)
        
        # Write .strm file with file_id directly embedded
        if file_id:
            stream_url = f"http://127.0.0.1:8080/stream_file?file_id={file_id}&filename={clean_title}.mp4"
        else:
            stream_url = f"http://127.0.0.1:8080/stream/{message_id}/{clean_title}.mp4"

        with open(strm_path, "w") as f:
            f.write(stream_url)
        
        logger.info(f"[AUTO-SYNC] 🎉 Automatically indexed: {strm_filename} -> {strm_path}")
        return strm_filename
    return None

@routes.post("/telegram-webhook")
async def telegram_webhook(request):
    """Instant Telegram Webhook Endpoint"""
    try:
        update = await request.json()
        post = update.get("channel_post") or update.get("message")
        strm = process_telegram_post(post)
        if strm:
            await trigger_jellyfin_scan()
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"[WEBHOOK] Error processing Telegram update: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=400)

def register_webhook_sync():
    """Sets up Telegram Webhook automatically on startup using urllib"""
    if not BOT_TOKEN:
        return
    webhook_url = "https://jishnupg-opencode-cli.hf.space/tg-stream/telegram-webhook"
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    try:
        import urllib.request
        import json
        import ssl
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            data = json.loads(response.read().decode())
            logger.info(f"[WEBHOOK] Telegram Webhook registration response: {data}")
    except Exception as e:
        logger.warning(f"[WEBHOOK] Webhook registration warning: {e}")

async def setup_telegram_webhook():
    await asyncio.to_thread(register_webhook_sync)

async def start_background_tasks(app):
    await setup_telegram_webhook()

app = web.Application()
app.add_routes(routes)
app.on_startup.append(start_background_tasks)

if __name__ == "__main__":
    logger.info(f"Starting TG-Drive Range Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
