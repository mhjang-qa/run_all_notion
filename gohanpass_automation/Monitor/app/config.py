import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
env_path = BASE_DIR / ".env"
env_example_path = BASE_DIR / ".env.example"

load_dotenv(env_path)
if not env_path.exists():
    load_dotenv(env_example_path)
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
NOTION_DB_ID = os.getenv("NOTION_DB_ID", "").strip()
NOTION_VERSION = os.getenv("NOTION_VERSION", "2022-06-28")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))
