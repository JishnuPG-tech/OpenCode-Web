import os
import urllib.request
import logging
import re
from typing import Optional, Dict, Any
import yt_dlp
from backend.app.core.config import settings
from backend.app.services.metadata_service import MetadataService
from backend.app.services.ffmpeg_service import FFmpegService
from backend.app.services.validation_service import ValidationService
from backend.app.utils.media import normalize_instagram_url
from backend.app.models.response import ErrorCode

logger = logging.getLogger("DownloadService")

class DownloadService:
    @classmethod
    def download_item(
        cls,
        url: str,
        task_dir: str,
        item_index: Optional[int] = None,
        item_entry: Optional[Dict[str, Any]] = None,
        requested_format: Optional[str] = None,
        audio_only: bool = False,
        mux_audio: bool = False
    ) -> str:
        norm_url = normalize_instagram_url(url)
        is_photo_music = mux_audio or (requested_format and ("photo_music" in requested_format.lower() or "video_photo" in requested_format.lower()))

        # Strategy 1: Direct Photo CDN Download (Only if audio muxing is NOT requested)
        if item_entry and not audio_only and not is_photo_music:
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

        # Strategy 2: Single-Frame Photo + Music MP4 Muxing
        if is_photo_music:
            logger.info("Executing Single-Frame Photo + Music MP4 creation")
            # 1. Download Photo
            img_url = (item_entry or {}).get("thumbnail") or (item_entry or {}).get("url")
            if not img_url and (item_entry or {}).get("thumbnails"):
                img_url = item_entry["thumbnails"][-1].get("url")
            
            photo_path = os.path.join(task_dir, "source_photo.jpg")
            if img_url:
                req = urllib.request.Request(img_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://www.instagram.com/"
                })
                with urllib.request.urlopen(req) as resp, open(photo_path, "wb") as f:
                    f.write(resp.read())
            
            # 2. Download Audio Track via yt-dlp
            audio_tmpl = os.path.join(task_dir, "source_audio.%(ext)s")
            ydl_audio_opts: Dict[str, Any] = {
                "outtmpl": audio_tmpl,
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }]
            }
            if os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0:
                ydl_audio_opts["cookiefile"] = settings.COOKIES_FILE
            
            ffmpeg_bin = FFmpegService.get_ffmpeg_binary()
            if ffmpeg_bin:
                ydl_audio_opts["ffmpeg_location"] = ffmpeg_bin
                
            with yt_dlp.YoutubeDL(ydl_audio_opts) as ydl:
                ydl.download([norm_url])

            audio_path = os.path.join(task_dir, "source_audio.m4a")
            output_mp4 = os.path.join(task_dir, f"InstaFlow_PhotoMusic_{(item_entry or {}).get('id', 'media')}.mp4")
            
            if os.path.exists(photo_path) and os.path.exists(audio_path):
                FFmpegService.combine_photo_and_audio(photo_path, audio_path, output_mp4)
                ValidationService.validate_file(output_mp4, is_video=True)
                return output_mp4

        # Strategy 2: In-Memory Native yt-dlp Video / Audio Download
        out_tmpl = os.path.join(task_dir, "InstaFlow_%(title).100s.%(ext)s")
        
        ffmpeg_bin = FFmpegService.get_ffmpeg_binary()
        is_audio = audio_only or (requested_format and ("audio" in requested_format.lower() or "m4a" in requested_format.lower()))

        fmt_str = "b[ext=mp4]/best[ext=mp4]/bestvideo[vcodec^=avc1]+bestaudio/b/best"
        if requested_format:
            req_lower = requested_format.lower().strip()
            if "2160" in req_lower or "4k" in req_lower:
                fmt_str = "bestvideo[height<=3840][width<=2160]+bestaudio/bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/b[ext=mp4]/b/best"
            elif "1440" in req_lower or "2k" in req_lower:
                fmt_str = "bestvideo[height<=2560][width<=1440]+bestaudio/bestvideo[height<=1440]+bestaudio/bestvideo+bestaudio/b[ext=mp4]/b/best"
            elif "1080" in req_lower:
                fmt_str = "bestvideo[height<=1920][width<=1080]+bestaudio/bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio/b[ext=mp4]/b/best"
            elif "720" in req_lower:
                fmt_str = "bestvideo[height<=1280][width<=720]+bestaudio/bestvideo[height<=720]+bestaudio/bestvideo+bestaudio/b[ext=mp4]/b/best"
            elif "480" in req_lower:
                fmt_str = "bestvideo[height<=854][width<=480]+bestaudio/bestvideo[height<=480]+bestaudio/bestvideo+bestaudio/b[ext=mp4]/b/best"
            elif "360" in req_lower:
                fmt_str = "bestvideo[height<=640][width<=360]+bestaudio/bestvideo[height<=360]+bestaudio/bestvideo+bestaudio/b[ext=mp4]/b/best"
            elif req_lower in ["lowest", "worst"]:
                fmt_str = "worstvideo+worstaudio/worst"
            elif req_lower in ["best", "optimal", "auto", "bestvideo+bestaudio/best"]:
                fmt_str = "b[ext=mp4]/best[ext=mp4]/bestvideo+bestaudio/b/best"
            else:
                fmt_str = f"b[ext=mp4]/best[ext=mp4]/{requested_format}/best"

        # Step 1: Anonymous Mode FIRST (No cookies sent - prevents bot warnings & account flags)
        ydl_opts: Dict[str, Any] = {
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "cachedir": False,
            "force_ipv4": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.instagram.com/",
                "X-IG-App-ID": "936619743392459",
            }
        }
        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        if is_audio:
            logger.info("Executing Audio-Only Extraction via native yt-dlp (Anonymous Mode)")
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }]
            })
        else:
            logger.info(f"Executing Full Video Download via native yt-dlp (Anonymous Mode, format: {fmt_str})")
            ydl_opts.update({
                "format": fmt_str,
                "merge_output_format": "mp4"
            })

        if item_index and item_index > 0:
            ydl_opts["playlist_items"] = str(item_index)
        else:
            ydl_opts["noplaylist"] = True

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([norm_url])
        except Exception as err:
            err_str = str(err)
            logger.warning(f"Primary anonymous yt-dlp download failed: {err_str[:200]}. Trying Cookie Mode fallback...")
            
            if os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0:
                fb_opts = dict(ydl_opts)
                fb_opts["cookiefile"] = settings.COOKIES_FILE
                try:
                    with yt_dlp.YoutubeDL(fb_opts) as ydl_fb:
                        ydl_fb.download([norm_url])
                except Exception as fb_err:
                    logger.error(f"yt-dlp cookie fallback download failed: {fb_err}")
                    raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: {err_str[:200]}")
            else:
                raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: {err_str[:200]}")

        # Scan task_dir for valid completed output files
        all_entries = [f for f in os.listdir(task_dir) if not f.startswith(".")]
        
        clean_files = []
        for f in all_entries:
            lname = f.lower()
            if lname.endswith((".part", ".ytdl", ".tmp", ".temp", ".nomedia", ".json")):
                continue
            if "fdash" in lname or re.search(r'\.f\d+\.', lname):
                continue
            clean_files.append(os.path.join(task_dir, f))

        if is_audio:
            # For audio requests, select .m4a / .mp3 / .aac audio file
            audio_files = [f for f in clean_files if f.lower().endswith((".m4a", ".mp3", ".aac", ".flac", ".ogg"))]
            if audio_files:
                audio_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                target_file = audio_files[0]
            elif clean_files:
                clean_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                target_file = clean_files[0]
            else:
                raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: No downloaded audio file produced.")
        else:
            # For video requests, strictly select .mp4 video file with audio
            video_files = [f for f in clean_files if f.lower().endswith((".mp4", ".mkv", ".webm"))]
            if video_files:
                video_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                target_file = video_files[0]
            elif clean_files:
                clean_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                target_file = clean_files[0]
            else:
                raw_files = [os.path.join(task_dir, f) for f in all_entries if not f.endswith((".part", ".ytdl", ".tmp"))]
                raw_mp4s = [f for f in raw_files if f.lower().endswith((".mp4", ".mkv", ".webm"))]
                if raw_mp4s:
                    raw_mp4s.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    target_file = raw_mp4s[0]
                elif raw_files:
                    raw_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    target_file = raw_files[0]
                else:
                    raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: No downloaded media file produced.")

        is_video_res = target_file.lower().endswith((".mp4", ".mkv", ".webm"))
        ValidationService.validate_file(target_file, is_video=is_video_res)
        return target_file
