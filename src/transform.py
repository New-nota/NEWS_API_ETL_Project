from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .extract import sanitize_filename_component

logger = logging.getLogger(__name__)
BASE_DIR = (Path(__file__).resolve().parent.parent) / "data"

REASON_KEYS = (
    "invalid_article_type",
    "no_author",
    "no_title",
    "no_description",
    "invalid_description_type",
    "short_description",
    "no_url",
    "invalid_url_type",
    "invalid_url",
    "no_published_at",
    "invalid_published_at",
)


def make_empty_stats() -> dict[str, Any]:
    return {
        "income_articles": 0,
        "accepted_articles": 0,
        "rejected_articles": 0,
        "reasons_counts": {reason: 0 for reason in REASON_KEYS},
        "prime_reasons": {reason: 0 for reason in REASON_KEYS},
    }


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_timestamp(value: Any) -> str:
    if isinstance(value, str):
        raw_value = value.strip()
        if raw_value:
            parsed = _parse_iso8601(raw_value)
            if parsed is not None:
                return parsed
    return datetime.now(timezone.utc).isoformat()


def _parse_iso8601(raw_value: str) -> str | None:
    candidate = raw_value.strip()
    if not candidate:
        return None

    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).isoformat()


def _normalize_article(
    element: Mapping[str, Any],
    language: str,
    key_word: str,
    fetched_at: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []

    author = _normalize_text(element.get("author"))
    if author is None:
        reasons.append("no_author")

    title = _normalize_text(element.get("title"))
    if title is None:
        reasons.append("no_title")

    description_value = element.get("description")
    description: str | None = None
    if description_value is None or description_value == "":
        reasons.append("no_description")
    elif not isinstance(description_value, str):
        reasons.append("invalid_description_type")
    else:
        description = description_value.strip()
        if len(description) < 20:
            reasons.append("short_description")

    url_value = element.get("url")
    url: str | None = None
    if url_value is None or url_value == "":
        reasons.append("no_url")
    elif not isinstance(url_value, str):
        reasons.append("invalid_url_type")
    else:
        url = url_value.strip()
        if not url.startswith(("http://", "https://")):
            reasons.append("invalid_url")

    published_raw = element.get("publishedAt")
    if published_raw is None or published_raw == "":
        reasons.append("no_published_at")
        published_at = None
    elif not isinstance(published_raw, str):
        reasons.append("invalid_published_at")
        published_at = None
    else:
        published_at = _parse_iso8601(published_raw)
        if published_at is None:
            reasons.append("invalid_published_at")

    if reasons:
        return None, reasons

    return {
        "language": language,
        "key_word": key_word,
        "author": author,
        "title": title,
        "description": description,
        "url": url,
        "published_at": published_at,
        "fetched_at": fetched_at,
        "source_name": _normalize_text(element.get("source", {}).get("name"))
        if isinstance(element.get("source"), Mapping)
        else None,
    }, []


def clean_article(data: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    clean_data: list[dict[str, Any]] = []
    stats = make_empty_stats()

    articles = data.get("articles")
    if not isinstance(articles, list):
        logger.warning("Payload contains invalid articles field: %s", type(articles).__name__)
        articles = []

    stats["income_articles"] = len(articles)

    language = _normalize_text(data.get("language")) or "ru"
    key_word = _normalize_text(data.get("key_word")) or "unknown"
    fetched_at = _normalize_timestamp(data.get("fetched_at"))

    for element in articles:
        if not isinstance(element, Mapping):
            stats["rejected_articles"] += 1
            stats["reasons_counts"]["invalid_article_type"] += 1
            stats["prime_reasons"]["invalid_article_type"] += 1
            continue

        normalized, reasons = _normalize_article(element, language, key_word, fetched_at)
        if reasons:
            stats["rejected_articles"] += 1
            for reason in reasons:
                stats["reasons_counts"][reason] += 1
            stats["prime_reasons"][reasons[0]] += 1
            continue

        stats["accepted_articles"] += 1
        clean_data.append(normalized)

    return clean_data, stats


def transform_article_debug(new_file_name: str, key_word: str, page: int) -> str:
    extract_path = BASE_DIR / "raw" / new_file_name
    if not extract_path.exists():
        raise FileNotFoundError(f"Raw payload file does not exist: {extract_path}")

    try:
        with extract_path.open("r", encoding="utf-8") as file_handler:
            data = json.load(file_handler)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Raw payload file is not valid JSON: {extract_path}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Raw payload root must be a JSON object")

    logger.info("income=%s articles", len(data.get("articles", [])) if isinstance(data.get("articles"), list) else 0)
    clean_data, stats = clean_article(data)

    load_dir = BASE_DIR / "clean"
    load_dir.mkdir(parents=True, exist_ok=True)

    stats_dir = load_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y_%m_%d-%H-%M-%S")
    safe_keyword = sanitize_filename_component(key_word)

    stats_file_name = f"stats_{safe_keyword}_page_{page}_{timestamp}.json"
    cleaned_file_name = f"cleaned_{safe_keyword}_page_{page}_{timestamp}.json"

    cleaned_path = load_dir / cleaned_file_name
    stats_path = stats_dir / stats_file_name

    with cleaned_path.open("w", encoding="utf-8") as file_handler:
        json.dump(clean_data, file_handler, ensure_ascii=False, indent=2)

    with stats_path.open("w", encoding="utf-8") as file_handler:
        json.dump(stats, file_handler, ensure_ascii=False, indent=2)

    logger.info("outcome=%s articles", len(clean_data))
    logger.info("income_articles=%s", stats["income_articles"])
    logger.info("accepted_articles=%s", stats["accepted_articles"])
    logger.info("rejected_articles=%s", stats["rejected_articles"])
    logger.info("reasons_counts=%s", stats["reasons_counts"])
    logger.info("prime_reasons=%s", stats["prime_reasons"])

    return cleaned_file_name


def transform_article_web(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    incoming_articles = payload.get("articles")
    incoming_count = len(incoming_articles) if isinstance(incoming_articles, list) else 0
    logger.info("income=%s articles", incoming_count)

    clean_data, stats = clean_article(payload)

    logger.info("outcome=%s articles", len(clean_data))
    logger.info("income_articles=%s", stats["income_articles"])
    logger.info("accepted_articles=%s", stats["accepted_articles"])
    logger.info("rejected_articles=%s", stats["rejected_articles"])
    logger.info("reasons_counts=%s", stats["reasons_counts"])
    logger.info("prime_reasons=%s", stats["prime_reasons"])

    return clean_data, stats
