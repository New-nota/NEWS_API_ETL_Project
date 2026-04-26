from __future__ import annotations

import logging
import time

from config.config import settings

from .db import claim_next_search_request, get_cursor
from .pipeline import run_pipeline_for_web_user
from .user_news_api_key import get_decrypted_news_api_key_for_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def mark_as_success(search_request_id: int) -> None:
    query = """
        UPDATE search_requests
        SET
            status = 'success',
            finished_at = NOW(),
            error_text = NULL
        WHERE id = %s
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query, (search_request_id,))
        if cur.rowcount != 1:
            logger.warning("Search request %s was not marked as success", search_request_id)
        conn.commit()


def mark_as_error(search_request_id: int, error_text: str) -> None:
    query = """
        UPDATE search_requests
        SET
            status = 'failed',
            finished_at = NOW(),
            error_text = %s
        WHERE id = %s
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query, (error_text[:2000], search_request_id))
        if cur.rowcount != 1:
            logger.warning("Search request %s was not marked as failed", search_request_id)
        conn.commit()


def one_request() -> bool:
    request_row = claim_next_search_request()
    if not request_row:
        return False

    search_request_id = request_row["id"]
    user_id = request_row["user_id"]
    keyword = request_row["keyword"]
    limit_count = request_row["limit_count"]
    page_size = request_row["page_size"]
    language = request_row["language"]

    logger.info(
        "Pipeline starts user_id=%s search_request_id=%s keyword=%s",
        user_id,
        search_request_id,
        keyword,
    )

    try:
        news_api_key = get_decrypted_news_api_key_for_user(user_id)
        if not news_api_key:
            raise RuntimeError("User has no NEWSAPI key yet.")
        
        amount_of_articles = run_pipeline_for_web_user(
            user_id=user_id,
            search_request_id=search_request_id,
            key_word=keyword,
            limit=limit_count,
            page_size=page_size,
            language=language,
            news_api_key=news_api_key,
        )

        mark_as_success(search_request_id)
        logger.info(
            "Pipeline finished successfully user_id=%s search_request_id=%s keyword=%s loaded=%s",
            user_id,
            search_request_id,
            keyword,
            amount_of_articles,
        )
    except Exception as exc:
        logger.exception(
            "Pipeline failed user_id=%s search_request_id=%s keyword=%s error=%s",
            user_id,
            search_request_id,
            keyword,
            exc,
        )
        mark_as_error(search_request_id, str(exc))

    return True


def run_worker_loop(poll_interval_seconds: int = 3) -> None:
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be > 0")

    logger.info("Worker started")
    while True:
        processed = one_request()
        if not processed:
            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    run_worker_loop()
