import logging
import time

from src.db import get_cursor
from config.config import settings
from src import run_pipeline_for_web_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s |%(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

def get_nearest_queue() -> dict | None:
    query = """ SELECT
      id, user_id, keyword, language, limit_count, page_size
       FROM search_requests
        WHERE status = 'queued'
        ORDER BY created_at
         LIMIT 1 """
    with get_cursor(settings.db_news) as (_, cur):
        cur.execute(query)
        return cur.fetchone()

def mark_as_running(search_request_id: int) -> None:
    query = """ UPDATE search_requests
                SET
                status = 'running',
                started_at = NOW(),
                error_text = NULL
                WHERE id = %s
            """
    with get_cursor(settings.db_news) as (conn, cur):
        cur.execute(query, (search_request_id,))
        conn.commit()

def mark_as_success(search_request_id: int) -> None:
    query = """UPDATE search_requests
                SET 
                status = 'success',
                finished_at = NOW()
                WHERE id = %s """
    with get_cursor(settings.db_news) as (conn, cur):
        cur.execute(query, (search_request_id,))
        conn.commit()
def mark_as_error(search_request_id: int, error_text: str) -> None:
    query = """UPDATE search_requests
                SET
                status = 'failed',
                finished_at = NOW(),
                error_text = %s
                WHERE id = %s"""
    with get_cursor(settings.db_news) as (conn,cur):
        cur.execute(query, (error_text, search_request_id))
        conn.commit()

def one_request() -> bool:
    request_row = get_nearest_queue()
    if not request_row:
        return False
    search_request_id = request_row["id"]
    user_id = request_row["user_id"]
    keyword = request_row["keyword"]
    limit_count = request_row["limit_count"]
    page_size = request_row["page_size"]
    logger.info(f"Pipeline starts for {user_id} on {search_request_id} by keyword {keyword}")
    mark_as_running(search_request_id)

    try:
        amount_of_articles = run_pipeline_for_web_user(user_id, search_request_id, keyword, limit_count, page_size)

        mark_as_success(search_request_id)
        logger.info(f"Pipeline finished successfully for {user_id} on {search_request_id} by {keyword}")
        logger.info(f"pushed {amount_of_articles} articles")
    except Exception as e:
        logger.exception(f"Pipeline for {user_id} on {search_request_id} by {keyword} failed: {e}")
        mark_as_error(search_request_id, str(e))
    return True

def run_worker_loop(pull_interval: int = 3) -> None:
    logger.info("Worker started")
    while True:
        processed = one_request()
        if not processed:
            time.sleep(pull_interval)

if __name__ == "__main__":
    run_worker_loop()