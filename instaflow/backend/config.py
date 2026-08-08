import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_FILE = os.path.join(PROJECT_ROOT, "cookies.txt")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

HOST = "0.0.0.0"
PORT = 8000
