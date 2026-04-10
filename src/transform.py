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
    elif len(element.get("description"))<20:
        reasons.append("short_description")
    
    if not element.get("url"):
        reasons.append("no_url")
    return reasons


def clean_article(data) -> tuple[list[dict[str,str]], dict]:
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
        },
        "prime_reason":{
            "no_author":0,
            "no_title":0,
            "no_description":0,
            "short_description":0,
            "no_url":0
        }
    }
    articles = data.get("articles", [])
    statistic['income_articles'] = len(articles)
    for element in data["articles"]:
        reasons = valid_article(element)
        if reasons:
            statistic['rejected_articles'] += 1
            for reason in reasons:
                statistic["reasons_counts"][reason] += 1
            statistic['prime_reason'][reasons[0]] += 1
            continue
        statistic["accepted_articles"] += 1
        clean_data.append(
            {
                "language": data["language"],
                "key_word": data["key_word"],
                "author": element["author"],
                "title": element["title"],
                "description": element["description"],
                "url": element["url"],
                "published_at": element["publishedAt"],
                "fetched_at": data["fetched_at"],
            }
        )
    return clean_data, statistic

def transform_article(new_file_name:str, key_word: str, page: int) -> str:
    extract_dir = BASE_DIR / "raw" / new_file_name
    with open(extract_dir, 'r', encoding='utf-8') as f:
        data = json.load(f)
    logger.info(f"income: {len(data.get('articles', []))} articals")
    clean, stats = clean_article(data)
    load_dir = BASE_DIR / "clean"
    load_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d-%H-%M-%S")
    stats_clean_data = f"stats_{key_word}_page_{page}_{timestamp}.json"
    create_clean_data = f"cleaned_{key_word}_page_{page}_{timestamp}.json"
    cleaned_file_path = load_dir / create_clean_data
    stats_dir = load_dir/ "stats" 
    stats_dir.mkdir(parents=True, exist_ok=True)
    stats_file_path = stats_dir / stats_clean_data
    logger.info(f"outcome: {len(clean)} articals")
    logger.info("stats collected")
    with open(cleaned_file_path, "w", encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    with open(stats_file_path, 'w', encoding='utf-8') as f:
        json.dump(stats,f, ensure_ascii=False, indent=2)
    logger.info("income_articles=%s", stats['income_articles'])
    logger.info("accepted_articles=%s", stats['accepted_articles'])
    logger.info("rejected_articles=%s", stats['rejected_articles'])
    logger.info("reasons_counts=%s", stats['reasons_counts'])
    logger.info("prime_reason=%s", stats['prime_reason'])
    return create_clean_data