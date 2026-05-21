from __future__ import annotations

import logging
import time

from sqlalchemy import func, update

from .db import claim_next_search_request, get_session, claim_pending_key_validation, mark_key_validation_result
from .models import SearchRequest
from .pipeline import run_pipeline_for_web_user
from .user_news_api_key import get_decrypted_news_api_key_for_user, validate_news_api_key, EncryptedNewsApiKey, decrypt_news_api_key
from config.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def mark_as_success(search_request_id: int) -> None:
    stmt = (
        update(SearchRequest)
        .where(SearchRequest.id == search_request_id)
        .values(status="success", finished_at=func.now(), error_text=None)
    )

    with get_session() as session:
        result = session.execute(stmt)
        if result.rowcount != 1:
            logger.warning("Search request %s was not marked as success", search_request_id)


def mark_as_error(search_request_id: int, error_text: str) -> None:
    stmt = (
        update(SearchRequest)
        .where(SearchRequest.id == search_request_id)
        .values(status="failed", finished_at=func.now(), error_text=error_text[:2000])
    )

    with get_session() as session:
        result = session.execute(stmt)
        if result.rowcount != 1:
            logger.warning("Search request %s was not marked as failed", search_request_id)

def one_key_validation() -> bool:
    job = claim_pending_key_validation()
    if not job:
        return False
    pipi_ip = job["id"]
    try:
        api_key = decrypt_news_api_key(
            EncryptedNewsApiKey(
                encrypted_key=job["encrypted_key"],
                iv=job["iv"],
                auth_tag=job["auth_tag"]
            )
        )
        result = validate_news_api_key(api_key)
        mark_key_validation_result(pipi_ip, result.status, result.error)
        logger.info("Ключ %s проверен со статусом -> %s", pipi_ip, result.status)
    except Exception as exc:
        logger.warning("Ключ %s проверка прервана: %s", pipi_ip, exc)# галя, ты ща упадешь ( проблема с сетью или крипто ошибка( откат на retry + не помечаем invalid))
        mark_key_validation_result(pipi_ip, "pending_validation", None)


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
    is_trial = request_row["is_trial"]


    logger.info(
        "Pipeline starts user_id=%s search_request_id=%s keyword=%s",
        user_id,
        search_request_id,
        keyword,
    )

    try:
        if is_trial:
            news_api_key = settings.newsapi_key
            if not news_api_key:
                raise RuntimeError("NewsApiKey не указан в конфиге(требуется для пробных запросов)")
            logger.info("Search %s: using owner key (trial mode)", search_request_id)
        else:
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
        if one_key_validation():
            continue
        if one_request():
            continue
        
        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    run_worker_loop()
