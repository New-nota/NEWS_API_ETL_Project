from __future__ import annotations

import os 
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "Localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "postgres")
    db_admin_db: str = os.getenv("DB_ADMIN_DB", "postgres")

    db_news: str = os.getenv("DB_NEWS","news_db")

    KEY_API: str = os.getenv("NEWSAPI_KEY", "NO")
    NEWS_URL = "https://newsapi.org/v2/top-headlines"

    COUNTRY = "US"

settings = Settings()
    



