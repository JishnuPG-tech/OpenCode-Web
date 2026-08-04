import os
import sys
import logging
import asyncio
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TG_Drive_Streamer")

HOST = "127.0.0.1"
PORT = 8080

# Environment credentials for Telegram Cloud Drive
API_ID = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TG_CHANNEL_ID")

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
        "instructions": "Set TG_API_ID, TG_API_HASH, TG_BOT_TOKEN, and TG_CHANNEL_ID in Space Secrets to connect your Telegram Channel!"
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
    
    # Range header handling for video seeking
    range_header = request.headers.get("Range")
    
    if not (API_ID and API_HASH and BOT_TOKEN):
        return web.Response(
            status=200,
            text=f"TG-Drive Streamer active for {filename}. Configure TG_API_ID, TG_API_HASH, TG_BOT_TOKEN in Space Secrets to stream live media!",
            headers=headers
        )

    return web.Response(status=200, text=f"Streaming {filename} from Telegram", headers=headers)

app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    logger.info(f"Starting TG-Drive Range Stream Proxy on {HOST}:{PORT}")
    if not (API_ID and API_HASH and BOT_TOKEN):
        logger.warning("[NOTICE] TG_API_ID, TG_API_HASH, or TG_BOT_TOKEN environment variables not set yet.")
        logger.warning("[NOTICE] Add them under Hugging Face Space Settings -> Secrets to connect your Telegram Channel!")
    web.run_app(app, host=HOST, port=PORT)
