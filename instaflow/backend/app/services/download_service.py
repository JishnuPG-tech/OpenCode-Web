import os
import sys
import subprocess
import urllib.request
import logging
from typing import Optional, Dict, Any
from backend.app.services.metadata_service import MetadataService
from backend.app.services.ffmpeg_service import FFmpegService
from backend.app.services.validation_service import ValidationService
from backend.app.utils.media import normalize_instagram_url
from backend.app.utils.filename import sanitize_filename
from backend.app.models.response import ErrorCode

logger = logging.getLogger("DownloadService")

class DownloadService:
    @classmethod
    def download_item(
        cls,
        url: str,
        task_dir: str,
        item_index: Optional[int] = None,
        item_entry: Optional[Dict[str, Any]] = None
    ) -> str:
        norm_url = normalize_instagram_url(url)
        
        # Check Strategy 1: Direct Photo CDN Download
        if item_entry:
            img_url = item_entry.get("thumbnail") or item_entry.get("url")
            if not img_url and item_entry.get("thumbnails"):
                img_url = item_entry["thumbnails"][-1].get("url")
                
            vcodec = item_entry.get("vcodec")
            acodec = item_entry.get("acodec")
            duration = float(item_entry.get("duration") or 0.0)
            
            if img_url and (not vcodec or vcodec == "none") and (not acodec or acodec == "none") and duration == 0.0:
                logger.info("Executing Photo CDN download")
                ext = "jpg"
                if ".webp" in img_url.lower(): ext = "webp"
                elif ".png" in img_url.lower(): ext = "png"
                
                fname = f"InstaFlow_{item_entry.get('id', 'photo')}.{ext}"
                target_path = os.path.join(task_dir, fname)
                
                req = urllib.request.Request(img_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://www.instagram.com/"
                })
                with urllib.request.urlopen(req) as resp, open(target_path, "wb") as f:
                    f.write(resp.read())
                    
                ValidationService.validate_file(target_path, is_video=False)
                return target_path

        # Strategy 2: Video Download via yt-dlp + FFmpeg Audio Muxing
        out_tmpl = os.path.join(task_dir, "InstaFlow_%(title).100s.%(ext)s")
        cmd = [sys.executable, "-m", "yt_dlp", "-4", "-o", out_tmpl]
        
        ffmpeg_bin = FFmpegService.get_ffmpeg_binary()
        if ffmpeg_bin:
            cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_bin)])
            
        cmd.extend(["--merge-output-format", "mp4"])
        cmd.extend(["-f", "bestvideo+bestaudio/best"])
        
        if item_index and item_index > 0:
            cmd.extend(["--playlist-items", str(item_index)])
        else:
            cmd.append("--no-playlist")
            
        cmd.extend(MetadataService.get_ig_headers())
        cmd.append(norm_url)
        
        logger.info(f"Executing yt-dlp command: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        if res.returncode != 0:
            logger.warning(f"Explicit format failed: {res.stderr[:200]}. Retrying fallback...")
            cmd_fallback = [sys.executable, "-m", "yt_dlp", "-4", "-o", out_tmpl]
            if ffmpeg_bin:
                cmd_fallback.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_bin)])
            if item_index and item_index > 0:
                cmd_fallback.extend(["--playlist-items", str(item_index)])
            else:
                cmd_fallback.append("--no-playlist")
            cmd_fallback.extend(MetadataService.get_ig_headers())
            cmd_fallback.append(norm_url)
            res = subprocess.run(cmd_fallback, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: {res.stderr[:200]}")

        files = [
            os.path.join(task_dir, f) for f in os.listdir(task_dir)
            if not f.endswith(".part") and not f.endswith(".ytdl") and not f.endswith(".tmp")
        ]
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        if not files:
            raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: No downloaded media file produced.")
            
        target_file = files[0]
        is_video = target_file.lower().endswith((".mp4", ".mkv", ".webm"))
        ValidationService.validate_file(target_file, is_video=is_video)
        return target_file
