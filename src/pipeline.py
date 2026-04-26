from __future__ import annotations

import logging
import math
from typing import Any

from config.config import settings

from .extract import make_extract_debug, make_extract_web
from .load import load_news, load_request_stats, load_web_pipeline
from .transform import make_empty_stats, transform_article_debug, transform_article_web

logger = logging.getLogger(__name__)


def merge_stats(stats: dict[str, Any], page_stats: dict[str, Any]) -> None:
    stats["income_articles"] += int(page_stats.get("income_articles", 0))
    stats["accepted_articles"] += int(page_stats.get("accepted_articles", 0))
    stats["rejected_articles"] += int(page_stats.get("rejected_articles", 0))

    for reason, value in page_stats.get("reasons_counts", {}).items():
        stats["reasons_counts"].setdefault(reason, 0)
        stats["reasons_counts"][reason] += int(value)

    for reason, value in page_stats.get("prime_reasons", {}).items():
        stats["prime_reasons"].setdefault(reason, 0)
        stats["prime_reasons"][reason] += int(value)


def _resolve_max_pages(payload: dict[str, Any], page_size: int) -> int:
    raw_total = payload.get("totalResults")
    if not isinstance(raw_total, int) or raw_total <= 0:
        return settings.max_pages_per_request

    bounded_total = min(raw_total, settings.newsapi_max_total_results)
    pages_by_total = max(1, math.ceil(bounded_total / page_size))
    return min(settings.max_pages_per_request, pages_by_total)


def run_pipeline_for_web_user(
    user_id: int,
    search_request_id: int,
    key_word: str,
    limit: int,
    page_size: int,
    language: str | None = None,
    news_api_key: str | None = None,
) -> int:
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    language_to_use = language or settings.default_language
    effective_page_size = min(page_size, settings.request_page_size_max)

    statistics = make_empty_stats()
    loaded_total = 0
    page = 1
    max_pages = settings.max_pages_per_request

    try:
        while loaded_total < limit and page <= max_pages:
            payload, raw_articles_count = make_extract_web(key_word, page, effective_page_size, language_to_use, news_api_key=news_api_key)

            if page == 1:
                max_pages = _resolve_max_pages(payload, effective_page_size)

            if raw_articles_count == 0:
                logger.warning("No more articles for keyword=%s on page=%s", key_word, page)
                break

            clean_data, page_stats = transform_article_web(payload)
            merge_stats(statistics, page_stats)

            remaining = limit - loaded_total
            loaded_page = load_web_pipeline(
                user_id=user_id,
                search_request_id=search_request_id,
                clean_data=clean_data,
                max_rows=remaining,
            )
            loaded_total += loaded_page

            logger.info(
                "Pipeline page summary keyword=%s page=%s raw=%s clean=%s loaded=%s loaded_total=%s limit=%s",
                key_word,
                page,
                raw_articles_count,
                len(clean_data),
                loaded_page,
                loaded_total,
                limit,
            )
            page += 1

        if page > max_pages and loaded_total < limit:
            logger.warning(
                "Reached max pages for keyword=%s (max_pages=%s). Loaded %s of %s requested",
                key_word,
                max_pages,
                loaded_total,
                limit,
            )
    finally:
        load_request_stats(search_request_id, statistics)

    logger.info("Loaded %s news for keyword=%s", loaded_total, key_word)
    return loaded_total


def run_debug_pipeline(
    keyword: str,
    limit: int,
    page_size: int,
    language: str | None = None,
) -> int:
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    language_to_use = language or settings.default_language
    effective_page_size = min(page_size, settings.request_page_size_max)

    loaded_total = 0
    page = 1

    while loaded_total < limit and page <= settings.max_pages_per_request:
        remaining = limit - loaded_total
        new_file_name, raw_articles_count = make_extract_debug(keyword, page, effective_page_size, language_to_use)
        if raw_articles_count == 0:
            logger.warning("No more articles for keyword=%s on page=%s", keyword, page)
            break

        clean_data_file = transform_article_debug(new_file_name, keyword, page)
        loaded_page = load_news(clean_data_file, max_rows=remaining)
        loaded_total += loaded_page

        logger.info(
            "Debug page summary keyword=%s page=%s raw=%s loaded=%s loaded_total=%s limit=%s",
            keyword,
            page,
            raw_articles_count,
            loaded_page,
            loaded_total,
            limit,
        )
        page += 1

    logger.info("Loaded %s debug news for keyword=%s", loaded_total, keyword)
    return loaded_total
