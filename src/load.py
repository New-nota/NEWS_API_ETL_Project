from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from psycopg2.extras import Json

from config.config import settings

from .ai.schemas import SummaryResponse
from .db import get_cursor

BASE_DIR = (Path(__file__).resolve().parent.parent) / "data" / "clean"


def load_news(clean_news: str, max_rows: int | None = None) -> int:
    load_path = BASE_DIR / clean_news
    if not load_path.exists():
        raise FileNotFoundError(f"Clean payload file does not exist: {load_path}")

    with load_path.open("r", encoding="utf-8") as file_handler:
        data = json.load(file_handler)

    if not isinstance(data, list) or not data:
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO NOTHING
    """

    rows = data if max_rows is None else data[:max_rows]

    loaded_count = 0
    with get_cursor(settings.news_db) as (conn, cur):
        for news in rows:
            cur.execute(
                query,
                (
                    news["language"],
                    news["key_word"],
                    news["author"],
                    news["title"],
                    news["description"],
                    news["url"],
                    news["published_at"],
                    news["fetched_at"],
                ),
            )
            if cur.rowcount == 1:
                loaded_count += 1
        conn.commit()

    return loaded_count


def upsert_article(cur, article: dict[str, Any]) -> int:
    query = """
        INSERT INTO articles (
            url,
            source_name,
            author,
            title,
            description,
            published_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO UPDATE
        SET
            source_name = EXCLUDED.source_name,
            author = EXCLUDED.author,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            published_at = EXCLUDED.published_at
        RETURNING id
    """

    cur.execute(
        query,
        (
            article["url"],
            article.get("source_name"),
            article["author"],
            article["title"],
            article["description"],
            article["published_at"],
        ),
    )
    row = cur.fetchone()
    return row["id"]


def load_user_news(
    cur,
    user_id: int,
    search_request_id: int,
    article_id: int,
    keyword: str,
    fetched_at: str,
) -> int:
    query = """
        INSERT INTO user_news (
            user_id,
            search_request_id,
            article_id,
            keyword,
            fetched_at
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    cur.execute(query, (user_id, search_request_id, article_id, keyword, fetched_at))
    return cur.rowcount


def _extract_prime_reasons(stats: dict[str, Any]) -> dict[str, Any]:
    if "prime_reasons" in stats:
        return stats["prime_reasons"]
    return stats.get("prime_reason", {})


def load_request_stats(search_request_id: int, stats: dict[str, Any]) -> None:
    query = """
        INSERT INTO request_stats (
            search_request_id,
            income_articles,
            accepted_articles,
            rejected_articles,
            reasons_counts,
            prime_reasons
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (search_request_id) DO UPDATE
        SET
            income_articles = EXCLUDED.income_articles,
            accepted_articles = EXCLUDED.accepted_articles,
            rejected_articles = EXCLUDED.rejected_articles,
            reasons_counts = EXCLUDED.reasons_counts,
            prime_reasons = EXCLUDED.prime_reasons
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(
            query,
            (
                search_request_id,
                int(stats.get("income_articles", 0)),
                int(stats.get("accepted_articles", 0)),
                int(stats.get("rejected_articles", 0)),
                Json(stats.get("reasons_counts", {})),
                Json(_extract_prime_reasons(stats)),
            ),
        )
        conn.commit()


def load_ai_report(search_request_id: int, summary: SummaryResponse) -> None:
    query = """
        INSERT INTO request_ai_report (
            search_request_id,
            status,
            error_text,
            model_provider,
            model_name,
            news_count,
            summary,
            main_conclusions,
            sentiment_label,
            sentiment_score,
            sentiment_distribution,
            main_topics,
            highlight,
            data_quality_warnings,
            promt_version,
            input_tokens,
            output_tokens,
            total_tokens
        )
        VALUES (%s, 'success', NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (search_request_id) DO UPDATE
        SET
            status = 'success',
            error_text = NULL,
            model_provider = EXCLUDED.model_provider,
            model_name = EXCLUDED.model_name,
            news_count = EXCLUDED.news_count,
            summary = EXCLUDED.summary,
            main_conclusions = EXCLUDED.main_conclusions,
            sentiment_label = EXCLUDED.sentiment_label,
            sentiment_score = EXCLUDED.sentiment_score,
            sentiment_distribution = EXCLUDED.sentiment_distribution,
            main_topics = EXCLUDED.main_topics,
            highlight = EXCLUDED.highlight,
            data_quality_warnings = EXCLUDED.data_quality_warnings,
            promt_version = EXCLUDED.promt_version,
            input_tokens = EXCLUDED.input_tokens,
            output_tokens = EXCLUDED.output_tokens,
            total_tokens = EXCLUDED.total_tokens
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(
            query,
            (
                search_request_id,
                summary.model_provider,
                summary.model_name,
                summary.articles_count,
                summary.summary,
                Json(summary.main_conclusions),
                summary.sentiment_label,
                summary.sentiment_score,
                Json(summary.sentiment_distribution.model_dump()),
                Json(summary.main_topics),
                Json(summary.highlight.model_dump()),
                Json(summary.data_quality_warnings),
                summary.prompt_version,
                summary.usage.input_tokens,
                summary.usage.output_tokens,
                summary.usage.total_tokens,
            ),
        )
        conn.commit()


def load_failed_ai_report(
    search_request_id: int,
    error_text: str,
    *,
    news_count: int = 0,
    model_provider: str | None = None,
    prompt_version: str | None = None,
) -> None:
    query = """
        INSERT INTO request_ai_report (
            search_request_id,
            status,
            error_text,
            model_provider,
            news_count,
            promt_version
        )
        VALUES (%s, 'failed', %s, %s, %s, COALESCE(%s, 'v1'))
        ON CONFLICT (search_request_id) DO UPDATE
        SET
            status = 'failed',
            error_text = EXCLUDED.error_text,
            model_provider = EXCLUDED.model_provider,
            news_count = EXCLUDED.news_count,
            promt_version = COALESCE(EXCLUDED.promt_version, request_ai_report.promt_version)
    """

    truncated_error = (error_text or "")[:2000]

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(
            query,
            (
                search_request_id,
                truncated_error,
                model_provider,
                news_count,
                prompt_version,
            ),
        )
        conn.commit()


def load_web_pipeline(
    user_id: int,
    search_request_id: int,
    clean_data: list[dict[str, Any]],
    max_rows: int | None = None,
) -> int:
    if not clean_data:
        return 0

    if max_rows is not None:
        if max_rows <= 0:
            return 0
        rows = clean_data[:max_rows]
    else:
        rows = clean_data

    loaded_count = 0
    with get_cursor(settings.news_db) as (conn, cur):
        for article in rows:
            keyword = article["key_word"]
            fetched_at = article["fetched_at"]

            article_id = upsert_article(cur, article)
            inserted = load_user_news(cur, user_id, search_request_id, article_id, keyword, fetched_at)
            loaded_count += inserted

        conn.commit()

    return loaded_count
