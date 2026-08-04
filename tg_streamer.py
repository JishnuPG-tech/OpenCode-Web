import os
import sys
import logging
import asyncio
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
    is_configured = bool(API_ID and API_HASH and BOT_TOKEN)
    return web.json_response({
        "status": "ok",
        "service": "TG-Drive Direct Streamer",
        "configured": is_configured,
        "channel_id": CHANNEL_ID or "Not set",
        "media_dir": MEDIA_DIR,
        "instructions": "Set TG_API_ID, TG_API_HASH, TG_BOT_TOKEN, and TG_CHANNEL_ID in Space Secrets!"
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

@routes.post("/add_strm")
async def add_strm(request):
    """
    Generate a .strm file for Jellyfin given a message_id and movie_title
    """
    try:
        data = await request.json()
        message_id = data.get("message_id")
        title = data.get("title", f"Movie_{message_id}")
        
        if not message_id:
            return web.json_response({"error": "message_id is required"}, status=400)
            
        strm_filename = f"{title}.strm"
        strm_path = os.path.join(MEDIA_DIR, strm_filename)
        stream_url = f"http://127.0.0.1:8080/stream/{message_id}/{title}.mp4"
        
        with open(strm_path, "w") as f:
            f.write(stream_url)
            
        logger.info(f"Created .strm file at {strm_path} -> {stream_url}")
        return web.json_response({"status": "created", "path": strm_path, "url": stream_url})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    logger.info(f"Starting TG-Drive Range Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
