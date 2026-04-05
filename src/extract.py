import requests as r
from config.config import settings
import make_raw_data as mrd
from datetime import datetime

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

        new_file_name = mrd.import_to_raw_json(payload, category, hot_pot, page)
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




