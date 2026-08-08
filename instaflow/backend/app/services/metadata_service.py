import os
import logging
from typing import Dict, Any, List
import yt_dlp
from backend.app.core.config import settings
from backend.app.utils.media import normalize_instagram_url
from backend.app.models.response import ErrorCode

logger = logging.getLogger("MetadataService")

class MetadataService:
    @staticmethod
    def get_ig_headers() -> List[str]:
        args = [
            "--add-header", "X-IG-App-ID:936619743392459",
            "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "--add-header", "Referer:https://www.instagram.com/"
        ]
        if os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0:
            args.extend(["--cookies", settings.COOKIES_FILE])
        return args

    @staticmethod
    def get_ydl_opts(extract_flat: bool = False) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": extract_flat,
            "cachedir": False,
            "force_ipv4": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.instagram.com/",
                "X-IG-App-ID": "936619743392459",
            }
        }
        if os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0:
            opts["cookiefile"] = settings.COOKIES_FILE
        return opts

    @classmethod
    def fetch_metadata(cls, url: str) -> Dict[str, Any]:
        norm_url = normalize_instagram_url(url)
        logger.info(f"Fetching in-memory yt-dlp metadata for {norm_url}")
        
        # Step 1: Anonymous Mode FIRST (No cookies - prevents bot warnings & account flags)
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
                info_anon = ydl_anon.extract_info(norm_url, download=False)
                if info_anon:
                    logger.info("Anonymous Mode metadata extraction succeeded!")
                    return ydl_anon.sanitize_info(info_anon)
        except Exception as anon_err:
            logger.warning(f"Anonymous Mode metadata extraction failed: {str(anon_err)[:150]}. Checking Cookie Mode fallback...")

        # Step 2: Cookie Mode fallback (Only if anonymous mode failed and cookies file exists)
        if os.path.exists(settings.COOKIES_FILE) and os.path.getsize(settings.COOKIES_FILE) > 0:
            cookie_opts = cls.get_ydl_opts()
            try:
                with yt_dlp.YoutubeDL(cookie_opts) as ydl_cookie:
                    info_cookie = ydl_cookie.extract_info(norm_url, download=False)
                    if info_cookie:
                        logger.info("Cookie Mode metadata extraction succeeded!")
                        return ydl_cookie.sanitize_info(info_cookie)
            except Exception as cookie_err:
                logger.error(f"Cookie Mode metadata extraction failed: {str(cookie_err)[:150]}")

        # Fallback error categorization
        err_str = str(anon_err) if 'anon_err' in locals() else "Metadata extraction failed"
        if "Login required" in err_str:
            raise ValueError(ErrorCode.LOGIN_REQUIRED.value)
        elif "Private account" in err_str or "private" in err_str.lower():
            raise ValueError(ErrorCode.PRIVATE_POST.value)
        elif "429" in err_str or "Too Many Requests" in err_str:
            raise ValueError(ErrorCode.RATE_LIMITED.value)
        elif "404" in err_str or "Not Found" in err_str:
            raise ValueError(ErrorCode.NOT_FOUND.value)
        else:
            raise RuntimeError(f"{ErrorCode.DOWNLOAD_FAILED.value}: {err_str[:200]}")
