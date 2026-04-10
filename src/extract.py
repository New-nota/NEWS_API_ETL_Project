import requests as r
from config.config import settings
from datetime import datetime
from pathlib import Path
import json
from typing import Any
import logging

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

def import_to_raw_json(data:dict[str, Any], key_word: str, page: int) -> str:
    raw_dir = BASE_DIR / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    create_data = f"{timestamp}_{key_word}_page_{page}.json"
    file_path = raw_dir / create_data

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return create_data



def make_extract( key_word: str, page: int = 1, page_size: int = 100) -> tuple[str,int]:
    params = {
    "apiKey": settings.KEY_API,
    "language":settings.langueage,
    "q": key_word,
    "pageSize" : page_size,
    "page" : page,
    "sortBy": settings.sortBy
    }
    try:
        data = r.get(settings.NEWS_URL, params=params, timeout=15)
        data.raise_for_status()
        payload = data.json()
        logger.info(f"raise of status: {data.status_code}")
        payload["fetched_at"] = datetime.now().isoformat()
        payload["language"] = settings.langueage
        payload["key_word"] = key_word
        articles_count = len(payload.get("articles", []))
        if articles_count == 0:
            logger.info("There are no more articles")

        new_file_name = import_to_raw_json(payload, key_word, page)
        return new_file_name, articles_count
    
    except r.exceptions.Timeout:
        logger.error("Error: NewsAPI reauest time out")
        raise
    except r.exceptions.ConnectionError:
        logger.error("Error: no internet connection or API is not available")
        raise
    except r.exceptions.HTTPError as e:
        logger.error(f"Error HTTP: {e}")
        raise
    except ValueError:
        logger.error("Error: sorry we can't parse JSON")
        raise




