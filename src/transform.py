from pathlib import Path
import json
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
BASE_DIR = (Path(__file__).resolve().parent.parent)/"data"

def clean_article(data) -> list[dict[str,str]]:
    clean_data = []
    for element in data["articles"]:
        if element["author"] and element["author"] != '' and element["title"] and element["title"] != '' and element.get("description") and len(element["description"]) >= 20 and element["url"] is not None:
            clean_data.append(
                {
                    "country": data["country"],
                    "category": data["category"],
                    "key_word": data["key_word"],
                    "author": element["author"],
                    "title": element["title"],
                    "description": element["description"],
                    "url": element["url"],
                    "published_at": element["publishedAt"],
                    "fetched_at": data["fetched_at"],
                }
            )
    return clean_data

def transform_article(new_file_name:str,category: str, hot_pot: str, page: int) -> str:
    extract_dir = BASE_DIR / "raw" / new_file_name
    with open(extract_dir, 'r', encoding='utf-8') as f:
        data = json.load(f)
    logger.info(f"income: {len(data)} articals")
    clean = clean_article(data)
    load_dir = BASE_DIR / "clean"
    load_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H-%M-%S")
    create_clean_data = f"cleaned_{category}_{hot_pot}_page_{page}_{timestamp}.json"
    cleaned_file_path = load_dir / create_clean_data
    logger.info(f"outcome: {len(clean)} articals")
    with open(cleaned_file_path, "w", encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    return create_clean_data