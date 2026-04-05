from pathlib import Path
import json
from datetime import datetime
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
    EXTRACT_DIR = BASE_DIR / "raw" / new_file_name
    with open(EXTRACT_DIR, 'r', encoding='utf-8') as f:
        data = json.load(f)
    clean = clean_article(data)
    LOAD_DIR = BASE_DIR / "clean"
    LOAD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H-%M-%S")
    create_clean_data = f"cleaned_{category}_{hot_pot}_page_{page}_{timestamp}.json"
    cleaned_file_path = LOAD_DIR / create_clean_data
    with open(cleaned_file_path, "w", encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    return create_clean_data