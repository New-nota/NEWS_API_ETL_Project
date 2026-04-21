from .db import get_cursor
from pathlib import Path
import json
from config.config import settings
from typing import Optional
BASE_DIR = (Path(__file__).resolve().parent.parent)/"data"/"clean"

    
def load_news(clean_news:str, max_rows: Optional[int] = None)-> int:
    LOAD_DIR = BASE_DIR/clean_news
    num_of_news = 0
    with open(LOAD_DIR, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not data:
        return 0
    
    query = """
            INSERT INTO bad_news_bears (
            language, 
            key_word, 
            author, 
            title, 
            description,
            url,
            published_at,
            fetched_at
            )
            VALUES (%s, %s, %s,%s, %s, %s, %s,%s)
            ON CONFLICT (url) DO NOTHING
            """
    
    with get_cursor(settings.db_news) as (conn, cur):
        for new in data:
            if max_rows is not None and num_of_news >= max_rows:
                break
            cur.execute(query, 
                        (new["language"],
                         new["key_word"],
                         new["author"],
                         new["title"],
                         new["description"],
                         new["url"],
                         new["published_at"],
                         new["fetched_at"]))
            if cur.rowcount == 1:
                num_of_news += 1
        conn.commit()
    return num_of_news

def upsert_article(cur, article: dict) -> int:
    query = """
            INSERT INTO articles (
            url,
            source_name,
            author,
            title,
            description,
            published_at
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (url) DO UPDATE
            SET
                source_name = EXCLUDED.source_name,
                author = EXCLUDED.author,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                published_at = EXCLUDED.published_at
            RETURNING id;
            """
    cur.execute(query,
                ( 
                    article["url"], 
                    article["source_name"], 
                    article["author"], 
                    article["title"],
                    article["description"],
                    article["published_at"],
                ),
                )
    row = cur.fetchone()
    return row["id"]

            
def load_user_news(cur, user_id: int, search_request_id: int, article_id: int, keyword: str, fetched_at: str)-> int:
    query = """
            INSERT INTO user_news (
            user_id,
            search_request_id,
            article_id,
            keyword,
            fetched_at
            )
            values(%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING;
            """
    cur.execute(query,(user_id, search_request_id, article_id, keyword, fetched_at))
    return cur.rowcount

def load_request_stats(search_request_id: int, stats: dict) -> None:
    query = """
            INSERT INTO request_stats (
            search_request_id,
            income_articles,
            accepted_articles,
            rejected_articles,
            reasons_counts,
            prime_reasons
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (search_request_id) DO UPDATE
            SET
                income_articles = EXCLUDED.income_articles,
                accepted_articles = EXCLUDED.accepted_articles,
                rejected_articles = EXCLUDED.rejected_articles,
                reasons_counts = EXCLUDED.reasons_counts,
                prime_reasons = EXCLUDED.prime_reasons
            """
    
    with get_cursor(settings.db_news) as (conn, cur):
        cur.execute(query, (
            search_request_id,
            stats["income_articles"],
            stats["accepted_articles"],
            stats["rejected_articles"],
            json.dumps(stats["reasons_counts"]),
            json.dumps(stats["prime_reason"])
        ))
        conn.commit()


def load_web_pipeline(user_id: int, search_request_id: int, clean_data: list[dict]) -> int:
    loaded_count = 0
    with get_cursor(settings.db_news) as (conn, cur):
        for article in clean_data:
            keyword = article["key_word"]
            fetched_at = article["fetched_at"]
            article_id = upsert_article(cur,article)
            inserted = load_user_news(cur, user_id, search_request_id, article_id, keyword, fetched_at)
            loaded_count += inserted   
        conn.commit()
    return loaded_count

