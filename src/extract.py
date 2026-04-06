import requests as r
from config.config import settings
from datetime import datetime
from pathlib import Path
import json
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent

def import_to_raw_json(data:dict[str, Any], category: str, hot_pot: str, page: int) -> str:
    NEDD_DIR = BASE_DIR / "data" / "raw"
    NEDD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    create_data = f"{timestamp}_{category}_{hot_pot}_page_{page}.json"
    file_path = NEDD_DIR / create_data
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return create_data



def make_extract(category: str, hot_pot: str, page: int = 1, page_size: int = 100) -> str:
    if category not in settings.CATEGORIES:
        raise ValueError(f"Unknown category:{category}. Allowed:{settings.CATEGORIES}")
    params = {
    "apiKey": settings.KEY_API,
    "country":settings.COUNTRY,
    "category":category,
    "q": hot_pot,
    "pageSize" : page_size,
    "page" : page
    }
    try:
        data = r.get(settings.NEWS_URL, params=params, timeout=15)
        data.raise_for_status()
        payload = data.json()
        payload["fetched_at"] = datetime.now().isoformat()
        payload["country"] = settings.COUNTRY
        payload["category"] = category
        payload["key_word"] = hot_pot
        if payload.get("totalResults", 0) == 0:
            print("There nothing we can do here")

        new_file_name = import_to_raw_json(payload, category, hot_pot, page)
        return new_file_name
    
    except r.exceptions.Timeout:
        print("Error: NewsAPI reauest time out")
        raise
    except r.exceptions.ConnectionError:
        print("Error: no internet connection or API is not available")
        raise
    except r.exceptions.HTTPError as e:
        print(f"Error HTTP: {e}")
        raise
    except ValueError:
        print("Error: sorry we can't parse JSON")
        raise




