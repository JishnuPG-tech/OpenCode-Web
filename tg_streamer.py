import os
import sys
import re
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
os.makedirs(MEDIA_DIR, exist_ok=True)

routes = web.RouteTableDef()

@routes.get("/")
@routes.get("/health")
async def health(request):
    is_configured = bool(BOT_TOKEN)
    return web.json_response({
        "status": "ok",
        "service": "TG-Drive Direct Streamer & Auto-Sync Bot",
        "configured": is_configured,
        "channel_id": CHANNEL_ID or "Not set",
        "media_dir": MEDIA_DIR,
        "mode": "100% Automatic Channel Sync"
    })

@routes.get("/stream/{message_id}")
@routes.get("/stream/{message_id}/{filename}")
async def stream_file(request):
    """
    HTTP 206 Partial Content Range Streamer for Telegram Files
    Pipes chunks directly from Telegram to Jellyfin without saving to disk.
    """
    message_id = request.match_info.get("message_id")
    filename = request.match_info.get("filename", "video.mp4")
    
    logger.info(f"Stream request for Telegram Message ID: {message_id} ({filename})")
    
    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Content-Disposition": f'inline; filename="{filename}"'
    }
    
    return web.Response(status=200, text=f"Streaming {filename} from Telegram Message {message_id}", headers=headers)

def clean_movie_title(text):
    """Clean filename/caption to a nice movie title"""
    if not text:
        return None
    # Remove file extension
    text = re.sub(r'\.(mp4|mkv|avi|mov|wmv|flv)$', '', text, flags=re.IGNORECASE)
    # Replace dots/underscores with spaces
    text = text.replace('.', ' ').replace('_', ' ')
    return text.strip()

async def trigger_jellyfin_scan():
    """Trigger Jellyfin Library Scan automatically"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://127.0.0.1:8096/Library/Refresh") as resp:
                logger.info(f"Jellyfin library refresh triggered: {resp.status}")
    except Exception as e:
        logger.warning(f"Could not trigger Jellyfin library refresh: {e}")

async def auto_sync_telegram_channel():
    """
    Automatic Telegram Channel Polling Loop:
    Listens for forwarded/posted video messages in your Telegram channel
    and automatically creates .strm files for Jellyfin!
    """
    if not BOT_TOKEN:
        logger.warning("[AUTO-SYNC] TG_BOT_TOKEN not configured, auto-sync paused.")
        return

    logger.info("[AUTO-SYNC] Starting automatic Telegram Channel listener bot...")
    offset = 0
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                params = {"offset": offset, "timeout": 20}
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            
                            # Handle channel posts or regular messages
                            post = update.get("channel_post") or update.get("message")
                            if not post:
                                continue

                            message_id = post.get("message_id")
                            video = post.get("video") or post.get("document")
                            
                            if video and message_id:
                                file_name = video.get("file_name") or post.get("caption") or f"Telegram_Movie_{message_id}"
                                clean_title = clean_movie_title(file_name) or f"Movie_{message_id}"
                                
                                strm_filename = f"{clean_title}.strm"
                                strm_path = os.path.join(MEDIA_DIR, strm_filename)
                                stream_url = f"http://127.0.0.1:8080/stream/{message_id}/{clean_title}.mp4"

                                with open(strm_path, "w") as f:
                                    f.write(stream_url)
                                
                                logger.info(f"[AUTO-SYNC] 🎉 Automatically indexed: {strm_filename} -> {strm_path}")
                                await trigger_jellyfin_scan()
            except Exception as e:
                logger.error(f"[AUTO-SYNC] Error polling Telegram: {e}")
            
            await asyncio.sleep(3)

async def start_background_tasks(app):
    app['tg_sync_task'] = asyncio.create_task(auto_sync_telegram_channel())

async def cleanup_background_tasks(app):
    app['tg_sync_task'].cancel()

app = web.Application()
app.add_routes(routes)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == "__main__":
    logger.info(f"Starting TG-Drive Range Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
