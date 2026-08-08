import shutil
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("FFmpegService")

class FFmpegService:
    @staticmethod
    def get_ffmpeg_binary() -> Optional[str]:
        return shutil.which("ffmpeg")

    @classmethod
    def verify_media_file(cls, filepath: str) -> bool:
        ffmpeg_bin = cls.get_ffmpeg_binary()
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return True # Fallback to file size check if ffprobe not available
            
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0

    @classmethod
    def combine_photo_and_audio(cls, photo_path: str, audio_path: str, output_mp4: str) -> str:
        ffmpeg_bin = cls.get_ffmpeg_binary() or "ffmpeg"
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", photo_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            output_mp4
        ]
        logger.info(f"Merging photo and audio into single-frame MP4: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg combine failed: {res.stderr}")
            raise RuntimeError(f"Failed to merge photo and audio: {res.stderr[:200]}")
        return output_mp4
