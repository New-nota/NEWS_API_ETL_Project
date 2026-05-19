from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .ai.schemas import SummaryResponse
from .db import get_session
from .models import Article, BadNewsBears, RequestAiReport, RequestStats, UserNews

BASE_DIR = (Path(__file__).resolve().parent.parent) / "data" / "clean"


def load_news(clean_news: str, max_rows: int | None = None) -> int:
    load_path = BASE_DIR / clean_news
    if not load_path.exists():
        raise FileNotFoundError(f"Clean payload file does not exist: {load_path}")

    with load_path.open("r", encoding="utf-8") as file_handler:
        data = json.load(file_handler)

    if not isinstance(data, list) or not data:
        return 0

    rows = data if max_rows is None else data[:max_rows]

    loaded_count = 0
    with get_session() as session:
        for news in rows:
            stmt = (
                pg_insert(BadNewsBears)
                .values(
                    language=news["language"],
                    key_word=news["key_word"],
                    author=news["author"],
                    title=news["title"],
                    description=news["description"],
                    url=news["url"],
                    published_at=news["published_at"],
                    fetched_at=news["fetched_at"],
                )
                .on_conflict_do_nothing(index_elements=[BadNewsBears.url])
            )
            result = session.execute(stmt)
            if result.rowcount == 1:
                loaded_count += 1

    return loaded_count


def upsert_article(session: Session, article: dict[str, Any]) -> int:
    stmt = pg_insert(Article).values(
        url=article["url"],
        source_name=article.get("source_name"),
        author=article["author"],
        title=article["title"],
        description=article["description"],
        published_at=article["published_at"],
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Article.url],
        set_={
            "source_name": stmt.excluded.source_name,
            "author": stmt.excluded.author,
            "title": stmt.excluded.title,
            "description": stmt.excluded.description,
            "published_at": stmt.excluded.published_at,
        },
    ).returning(Article.id)

    return session.execute(stmt).scalar_one()


def load_user_news(
    session: Session,
    user_id: int,
    search_request_id: int,
    article_id: int,
    keyword: str,
    fetched_at: str,
) -> int:
    stmt = (
        pg_insert(UserNews)
        .values(
            user_id=user_id,
            search_request_id=search_request_id,
            article_id=article_id,
            keyword=keyword,
            fetched_at=fetched_at,
        )
        .on_conflict_do_nothing()
    )
    result = session.execute(stmt)
    return result.rowcount or 0


def _extract_prime_reasons(stats: dict[str, Any]) -> dict[str, Any]:
    if "prime_reasons" in stats:
        return stats["prime_reasons"]
    return stats.get("prime_reason", {})


def load_request_stats(search_request_id: int, stats: dict[str, Any]) -> None:
    stmt = pg_insert(RequestStats).values(
        search_request_id=search_request_id,
        income_articles=int(stats.get("income_articles", 0)),
        accepted_articles=int(stats.get("accepted_articles", 0)),
        rejected_articles=int(stats.get("rejected_articles", 0)),
        reasons_counts=stats.get("reasons_counts", {}),
        prime_reasons=_extract_prime_reasons(stats),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[RequestStats.search_request_id],
        set_={
            "income_articles": stmt.excluded.income_articles,
            "accepted_articles": stmt.excluded.accepted_articles,
            "rejected_articles": stmt.excluded.rejected_articles,
            "reasons_counts": stmt.excluded.reasons_counts,
            "prime_reasons": stmt.excluded.prime_reasons,
        },
    )

    with get_session() as session:
        session.execute(stmt)


def load_ai_report(search_request_id: int, summary: SummaryResponse) -> None:
    stmt = pg_insert(RequestAiReport).values(
        search_request_id=search_request_id,
        status="success",
        error_text=None,
        model_provider=summary.model_provider,
        model_name=summary.model_name,
        news_count=summary.articles_count,
        summary=summary.summary,
        main_conclusions=summary.main_conclusions,
        sentiment_label=summary.sentiment_label,
        sentiment_score=summary.sentiment_score,
        sentiment_distribution=summary.sentiment_distribution.model_dump(),
        main_topics=summary.main_topics,
        highlight=summary.highlight.model_dump(),
        data_quality_warnings=summary.data_quality_warnings,
        # DB column is misspelled ("promt_version"); Python attr is "prompt_version".
        promt_version=summary.prompt_version,
        input_tokens=summary.usage.input_tokens,
        output_tokens=summary.usage.output_tokens,
        total_tokens=summary.usage.total_tokens,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[RequestAiReport.search_request_id],
        set_={
            "status": "success",
            "error_text": None,
            "model_provider": stmt.excluded.model_provider,
            "model_name": stmt.excluded.model_name,
            "news_count": stmt.excluded.news_count,
            "summary": stmt.excluded.summary,
            "main_conclusions": stmt.excluded.main_conclusions,
            "sentiment_label": stmt.excluded.sentiment_label,
            "sentiment_score": stmt.excluded.sentiment_score,
            "sentiment_distribution": stmt.excluded.sentiment_distribution,
            "main_topics": stmt.excluded.main_topics,
            "highlight": stmt.excluded.highlight,
            "data_quality_warnings": stmt.excluded.data_quality_warnings,
            # Schema column "promt_version" (sic) — Python attr is "prompt_version".
            "promt_version": stmt.excluded.promt_version,
            "input_tokens": stmt.excluded.input_tokens,
            "output_tokens": stmt.excluded.output_tokens,
            "total_tokens": stmt.excluded.total_tokens,
        },
    )

    with get_session() as session:
        session.execute(stmt)


def load_failed_ai_report(
    search_request_id: int,
    error_text: str,
    *,
    news_count: int = 0,
    model_provider: str | None = None,
    prompt_version: str | None = None,
) -> None:
    truncated_error = (error_text or "")[:2000]

    stmt = pg_insert(RequestAiReport).values(
        search_request_id=search_request_id,
        status="failed",
        error_text=truncated_error,
        model_provider=model_provider,
        news_count=news_count,
        # DB column is "promt_version" (sic); Python attr is "prompt_version".
        promt_version=prompt_version if prompt_version is not None else "v1",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[RequestAiReport.search_request_id],
        set_={
            "status": "failed",
            "error_text": stmt.excluded.error_text,
            "model_provider": stmt.excluded.model_provider,
            "news_count": stmt.excluded.news_count,
            "promt_version": func.coalesce(
                stmt.excluded.promt_version,
                RequestAiReport.prompt_version,
            ),
        },
    )

    with get_session() as session:
        session.execute(stmt)


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
    with get_session() as session:
        for article in rows:
            keyword = article["key_word"]
            fetched_at = article["fetched_at"]

            article_id = upsert_article(session, article)
            inserted = load_user_news(
                session, user_id, search_request_id, article_id, keyword, fetched_at
            )
            loaded_count += inserted

    return loaded_count
