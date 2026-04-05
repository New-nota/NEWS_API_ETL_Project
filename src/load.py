from db import get_cursor
from pathlib import Path
import json
from config.config import settings
BASE_DIR = (Path(__file__).resolve().parent.parent)/"data"/"clean"

def load_news(clean_news:str)-> None:
    LOAD_DIR = BASE_DIR/clean_news
    with open(LOAD_DIR, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not data:
        return
    
    query = """
            INSERT INTO bad_news_bears (
            country, 
            category, 
            key_word, 
            author, 
            title, 
            description,
            url,
            published_at,
            fetched_at
            )
            VALUES (%s, %s, %s, %s,%s, %s, %s, %s,%s)
            ON CONFLICT (url) DO NOTHING
            """
    
    with get_cursor(settings.db_news) as (conn, cur):
        for new in data:
            cur.execute(query, 
                        (new["country"],
                         new["category"],
                         new["key_word"],
                         new["author"],
                         new["title"],
                         new["description"],
                         new["url"],
                         new["published_at"],
                         new["fetched_at"]))
    conn.commit()
            