import os
import sys
import re
import json
import shutil
import subprocess
import urllib.request
import logging
from typing import Dict, Any, Optional, List, Tuple
from backend.config import DOWNLOADS_DIR, COOKIES_FILE

logger = logging.getLogger("InstaFlowExtractor")
logging.basicConfig(level=logging.INFO)

# ----------------------------------------------------
# 1. URL NORMALIZER & VALIDATOR
# ----------------------------------------------------
class InstagramUrlNormalizer:
    @staticmethod
    def normalize(raw_url: str) -> str:
        if not raw_url or not raw_url.strip():
            return ""
        trimmed = raw_url.strip()
        if "?" not in trimmed:
            return trimmed
        base, q = trimmed.split("?", 1)
        clean_params = [
            p for p in q.split("&")
            if not p.lower().startswith(("utm_", "igsh", "igshid", "fbclid", "share_id"))
        ]
        return f"{base}?{'&'.join(clean_params)}" if clean_params else base

class InstagramUrlValidator:
    REEL_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|tv)/([A-Za-z0-9_-]+)", re.I)
    POST_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/p/([A-Za-z0-9_-]+)", re.I)
    STORY_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/stories/([A-Za-z0-9._-]+)/(\d+)", re.I)

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        trimmed = InstagramUrlNormalizer.normalize(url)
        if not trimmed:
            return {"is_valid": False, "type": "UNKNOWN", "raw": url}
        
        m_reel = cls.REEL_PATTERN.search(trimmed)
        if m_reel:
            return {"is_valid": True, "type": "REEL", "shortcode": m_reel.group(1), "raw": trimmed}
        
        m_post = cls.POST_PATTERN.search(trimmed)
        if m_post:
            return {"is_valid": True, "type": "POST", "shortcode": m_post.group(1), "raw": trimmed}
        
        m_story = cls.STORY_PATTERN.search(trimmed)
        if m_story:
            return {"is_valid": True, "type": "STORY", "username": m_story.group(1), "shortcode": m_story.group(2), "raw": trimmed}
        
        return {"is_valid": False, "type": "UNKNOWN", "raw": trimmed}

# ----------------------------------------------------
# 2. SMART COOKIE PARSER & INJECTOR
# ----------------------------------------------------
def parse_and_inject_cookies(raw_text: str) -> Tuple[str, int]:
    text = raw_text.strip()
    if not text:
        return "", 0
        
    lines = ["# Netscape HTTP Cookie File", "# http://curl.haxx.se/rfc/cookie_spec.html\n"]
    
    # JSON array check
    if text.startswith("[") and text.endswith("]"):
        try:
            arr = json.loads(text)
            count = 0
            for item in arr:
                name = item.get("name")
                value = item.get("value")
                domain = item.get("domain", ".instagram.com")
                if name and value:
                    lines.append(f"{domain}\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}")
                    count += 1
            content = "\n".join(lines)
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            return content, count
        except Exception as e:
            logger.warning(f"Failed to parse JSON cookies: {e}")

    # Header style check
    if text.lower().startswith("cookie:"):
        text = text[7:].strip()
        
    pairs = text.split(";")
    count = 0
    for p in pairs:
        if "=" in p:
            parts = p.strip().split("=", 1)
            k, v = parts[0].strip(), parts[1].strip()
            if k and v:
                lines.append(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\t{k}\t{v}")
                count += 1
                
    if count == 0 and len(text) > 10:
        lines.append(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{text}")
        count = 1
        
    content = "\n".join(lines)
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    return content, count

# ----------------------------------------------------
# 3. EXTRACTION & DOWNLOAD ENGINE
# ----------------------------------------------------
def find_ffmpeg_path() -> Optional[str]:
    ffmpeg_bin = shutil.which("ffmpeg")
    return ffmpeg_bin if ffmpeg_bin else None

def fetch_metadata(url: str) -> Dict[str, Any]:
    norm_url = InstagramUrlNormalizer.normalize(url)
    logger.info(f"[Extractor] Extracting metadata for: {norm_url}")
    
    # Step 1: Anonymous Mode FIRST (No cookies sent)
    anon_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "cachedir": False,
        "force_ipv4": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.instagram.com/",
            "X-IG-App-ID": "936619743392459",
        }
    }
    try:
        with yt_dlp.YoutubeDL(anon_opts) as ydl_anon:
            info = ydl_anon.extract_info(norm_url, download=False)
            if info:
                return ydl_anon.sanitize_info(info)
    except Exception as anon_err:
        logger.warning(f"[Extractor] Anonymous Mode failed: {str(anon_err)[:150]}. Trying cookie fallback...")

    # Step 2: Cookie Mode Fallback
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        cookie_opts = dict(anon_opts)
        cookie_opts["cookiefile"] = COOKIES_FILE
        try:
            with yt_dlp.YoutubeDL(cookie_opts) as ydl_cookie:
                info = ydl_cookie.extract_info(norm_url, download=False)
                if info:
                    return ydl_cookie.sanitize_info(info)
        except Exception as cookie_err:
            logger.error(f"[Extractor] Cookie Mode failed: {cookie_err}")

    raise Exception("LOGIN_REQUIRED_OR_PRIVATE")

def download_media_item(
    url: str,
    playlist_index: Optional[int] = None,
    item_entry: Optional[Dict[str, Any]] = None,
    quality: Optional[int] = None,
    audio_only: bool = False,
    merge_photo_audio: bool = False
) -> str:
    norm_url = InstagramUrlNormalizer.normalize(url)
    ffmpeg_path = find_ffmpeg_path()

    # Strategy 1: Photo / Direct CDN Image Download
    if item_entry and not audio_only and not merge_photo_audio:
        img_url = item_entry.get("thumbnail") or item_entry.get("url")
        if not img_url and item_entry.get("thumbnails"):
            img_url = item_entry["thumbnails"][-1].get("url")
            
        vcodec = item_entry.get("vcodec")
        acodec = item_entry.get("acodec")
        duration = item_entry.get("duration") or 0.0
        
        # Pure Photo Post check
        if img_url and (not vcodec or vcodec == "none") and (not acodec or acodec == "none") and duration == 0.0:
            logger.info(f"[Extractor] Photo item detected. Executing direct high-res CDN download.")
            ext = "jpg"
            if ".webp" in img_url.lower(): ext = "webp"
            elif ".png" in img_url.lower(): ext = "png"
            
            filename = f"InstaFlow_{item_entry.get('id', 'photo')}.{ext}"
            filepath = os.path.join(DOWNLOADS_DIR, filename)
            
            req = urllib.request.Request(img_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.instagram.com/"
            })
            with urllib.request.urlopen(req) as resp, open(filepath, "wb") as f:
                f.write(resp.read())
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return filepath

    # Strategy 1.5: Photo + Music Merge (Single-Frame MP4)
    if merge_photo_audio and item_entry and ffmpeg_path:
        img_url = item_entry.get("thumbnail") or item_entry.get("url")
        if not img_url and item_entry.get("thumbnails"):
            img_url = item_entry["thumbnails"][-1].get("url")

        if img_url:
            logger.info(f"[Extractor] Merging photo and music into MP4...")
            photo_path = os.path.join(DOWNLOADS_DIR, f"temp_photo_{item_entry.get('id')}.jpg")
            audio_path = os.path.join(DOWNLOADS_DIR, f"temp_audio_{item_entry.get('id')}.m4a")
            output_path = os.path.join(DOWNLOADS_DIR, f"InstaFlow_{item_entry.get('id')}_music.mp4")

            try:
                # 1. Download Photo
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"})
                with urllib.request.urlopen(req) as resp, open(photo_path, "wb") as f:
                    f.write(resp.read())

                # 2. Download Audio via yt-dlp
                audio_cmd = [sys.executable, "-m", "yt_dlp", "-4", "-f", "bestaudio", "-o", audio_path]
                if playlist_index: audio_cmd.extend(["--playlist-items", str(playlist_index)])
                audio_cmd.extend(get_ig_headers())
                audio_cmd.append(norm_url)
                subprocess.run(audio_cmd, capture_output=True)

                # 3. Merge via FFmpeg
                # cmd: ffmpeg -loop 1 -i photo.jpg -i music.m4a -c:v libx264 -tune stillimage -c:a aac -b:a 192k -pix_fmt yuv420p -shortest output.mp4
                merge_cmd = [
                    ffmpeg_path, "-y", "-loop", "1", "-i", photo_path, "-i", audio_path,
                    "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p", "-shortest", output_path
                ]
                subprocess.run(merge_cmd, capture_output=True)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path
            finally:
                if os.path.exists(photo_path): os.remove(photo_path)
                if os.path.exists(audio_path): os.remove(audio_path)

    # Strategy 2: Video Reel Download via native yt-dlp Python API (Anonymous Mode Primary)
    out_tmpl = os.path.join(DOWNLOADS_DIR, "InstaFlow_%(title).100s.%(ext)s")
    
    fmt_str = "b[ext=mp4]/best[ext=mp4]/bestvideo+bestaudio/b/best"
    if audio_only:
        fmt_str = "bestaudio/best"
    elif quality:
        res_map = {1: 2160, 2: 1440, 3: 1080, 4: 720, 5: 480, 6: 360}
        limit = res_map.get(quality)
        if limit:
            fmt_str = f"bestvideo[height<={limit}]+bestaudio/best[height<={limit}]/best"
        elif quality == 7:
            fmt_str = "worstvideo+worstaudio/worst"

    ydl_opts: Dict[str, Any] = {
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "force_ipv4": True,
        "format": fmt_str,
        "merge_output_format": "mp4",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.instagram.com/",
            "X-IG-App-ID": "936619743392459",
        }
    }
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_path)
    if playlist_index and playlist_index > 0:
        ydl_opts["playlist_items"] = str(playlist_index)
    else:
        ydl_opts["noplaylist"] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([norm_url])
    except Exception as anon_err:
        logger.warning(f"[Extractor] Primary anonymous download failed: {anon_err}. Retrying with cookies if available...")
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
            cookie_opts = dict(ydl_opts)
            cookie_opts["cookiefile"] = COOKIES_FILE
            try:
                with yt_dlp.YoutubeDL(cookie_opts) as ydl_fb:
                    ydl_fb.download([norm_url])
            except Exception as fb_err:
                raise Exception(f"Download failed: {fb_err}")
        else:
            raise Exception(f"Download failed: {anon_err}")
    
    # Locate output file
    files = [
        os.path.join(DOWNLOADS_DIR, f)
        for f in os.listdir(DOWNLOADS_DIR)
        if not f.endswith(".part") and not f.endswith(".ytdl") and not f.endswith(".tmp")
    ]
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if not files or os.path.getsize(files[0]) == 0:
        raise Exception("Download succeeded but no output file was produced.")
    
    return files[0]
