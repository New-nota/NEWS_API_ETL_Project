from pathlib import Path
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
BASE_DIR = (Path(__file__).resolve().parent.parent)/"data"

def valid_article(element: dict) -> list[str]:
    reasons = []
    if not element.get("author"):
        reasons.append("no_author")

    if not element.get("title"):
        reasons.append("no_title")

    if not element.get("description"):
        reasons.append("no_description")
    elif len(element.get("description")):
        reasons.append("short_description")
    
    if not element.get("url"):
        reasons.append("no_url")
    return reasons


def clean_article(data) -> list[dict[str,str]]:
    clean_data = []
    statistic = {
        "income_articles" : 0,
        "accepted_articles" : 0,
        "rejected_articles" : 0,
        "reasons_counts" :{
            "no_author":0,
            "no_title":0,
            "no_description":0,
            "short_description":0,
            "no_url":0
        }
    }
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
    logger.info(f"income: {len(data.get("articles", []))} articals")
    clean = clean_article(data)
    load_dir = BASE_DIR / "clean"
    load_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H-%M-%S")
    create_clean_data = f"cleaned_{category}_{hot_pot}_page_{page}_{timestamp}.json"
    cleaned_file_path = load_dir / create_clean_data
    logger.info(f"outcome: {len(clean.get("articles", []))} articals")
    with open(cleaned_file_path, "w", encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    return create_clean_data