import os
import time
import shutil
import asyncio
import logging
from backend.app.core.config import settings
from backend.app.utils.temp import cleanup_task_temp_dir

logger = logging.getLogger("CleanupService")

class CleanupService:
    @staticmethod
    def cleanup_task(task_dir: str):
        logger.info(f"Triggering automatic cleanup for task dir: {task_dir}")
        cleanup_task_temp_dir(task_dir)

    @classmethod
    async def periodic_cleanup_loop(cls, interval_seconds: int = 900, max_age_seconds: int = 900):
        """
        Background daemon running every 15 minutes to purge any abandoned temp directories.
        """
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                temp_dir = settings.TEMP_DIR
                if not os.path.exists(temp_dir):
                    continue

                now = time.time()
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path):
                        mtime = os.path.getmtime(item_path)
                        if (now - mtime) > max_age_seconds:
                            logger.info(f"Sweeping abandoned temp directory: {item_path}")
                            shutil.rmtree(item_path, ignore_errors=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in periodic cleanup loop: {e}")
