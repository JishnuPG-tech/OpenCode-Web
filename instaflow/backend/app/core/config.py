import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "InstaFlow Remote Processing Engine"
    APP_VERSION: str = "2.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", os.getenv("7860", "8000")))
    
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/instaflow_downloads" if os.name != "nt" else os.path.join(BASE_DIR, "app", "utils", "temp"))
    COOKIES_FILE: str = os.getenv("COOKIES_FILE", os.path.join(BASE_DIR, "..", "cookies.txt"))
    
    CHUNK_SIZE: int = 128 * 1024  # 128 KB
    MAX_CONCURRENT_DOWNLOADS: int = 10

    class Config:
        case_sensitive = True

settings = Settings()
os.makedirs(settings.TEMP_DIR, exist_ok=True)
