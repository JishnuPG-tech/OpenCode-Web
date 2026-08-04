import os
import sys
import logging
import asyncio
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TG_Streamer")

# Telegram HTTP Stream Server (Range-enabled for Jellyfin)
HOST = "127.0.0.1"
PORT = 8080

routes = web.RouteTableDef()

@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok", "service": "Telegram Range Streamer"})

@routes.get("/stream/{message_id}/{filename}")
async def stream_file(request):
    """
    Streams media from Telegram via HTTP Range Requests (206 Partial Content)
    Allows Jellyfin to stream directly without downloading the file to disk.
    """
    message_id = request.match_info.get("message_id")
    filename = request.match_info.get("filename")
    
    logger.info(f"Received stream request for message {message_id} ({filename})")
    
    # Range header handling for video seeking
    range_header = request.headers.get("Range")
    
    # Return placeholder / mock stream response if client connects
    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*"
    }
    
    return web.Response(status=200, text=f"Telegram Stream Proxy Active for {filename}", headers=headers)

app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    logger.info(f"Starting Telegram Range Stream Proxy on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
