import requests as r
from typing import Any
from config import settings
import make_raw_data as mrd

def make_request(category: str, hot_pot: str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
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

        mrd.import_to_raw_json(payload, category, hot_pot, page)
        return payload
    
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




