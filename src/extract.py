from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.config import settings

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_filename_component(raw_value: str) -> str:
    sanitized = _SAFE_FILENAME_RE.sub("_", raw_value.strip())
    sanitized = sanitized.strip("._")
    if not sanitized:
        return "keyword"
    return sanitized[:120]


def _require_newsapi_key() -> str:
    key = settings.newsapi_key.strip()
    if not key:
        raise RuntimeError("NEWSAPI_KEY is not configured")

    placeholders = {
        "NO",
        "YOUR_REAL_NEWSAPI_KEY",
        "YOUR_NEWSAPI_KEY",
        "CHANGE_ME",
    }
    if key.upper() in placeholders:
        raise RuntimeError("NEWSAPI_KEY contains a placeholder value")

    return key


def _build_session() -> requests.Session:
    retry = Retry(
        total=settings.request_max_retries,
        connect=settings.request_max_retries,
        read=settings.request_max_retries,
        status=settings.request_max_retries,
        backoff_factor=settings.request_backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def import_to_raw_json(data: dict[str, Any], key_word: str, page: int) -> str:
    raw_dir = BASE_DIR / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    safe_keyword = sanitize_filename_component(key_word)
    file_name = f"{timestamp}_{safe_keyword}_page_{page}.json"
    file_path = raw_dir / file_name

    with file_path.open("w", encoding="utf-8") as file_handler:
        json.dump(data, file_handler, ensure_ascii=False, indent=2)

    return file_name


def _fetch_payload(
    key_word: str,
    page: int,
    page_size: int,
    language: str,
) -> tuple[dict[str, Any], int]:
    if page <= 0:
        raise ValueError("page must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    normalized_page_size = min(page_size, settings.request_page_size_max)

    params = {
        "apiKey": _require_newsapi_key(),
        "language": language,
        "q": key_word,
        "pageSize": normalized_page_size,
        "page": page,
        "sortBy": settings.sort_by,
    }

    session = _build_session()
    try:
        response = session.get(
            settings.news_url,
            params=params,
            timeout=settings.request_timeout_seconds,
        )
    except requests.exceptions.Timeout as exc:
        logger.error("NewsAPI request timeout (page=%s, keyword=%s)", page, key_word)
        raise RuntimeError("NewsAPI request timed out") from exc
    except requests.exceptions.ConnectionError as exc:
        logger.error("NewsAPI connection failed (page=%s, keyword=%s)", page, key_word)
        raise RuntimeError("NewsAPI connection failed") from exc
    finally:
        session.close()

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        logger.error("NewsAPI rate limit reached (Retry-After=%s)", retry_after)
        raise RuntimeError("NewsAPI rate limit reached")

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        logger.error(
            "NewsAPI HTTP error status=%s, body=%s",
            response.status_code,
            response.text[:400],
        )
        raise RuntimeError(f"NewsAPI HTTP error: {response.status_code}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("NewsAPI returned invalid JSON")
        raise RuntimeError("NewsAPI returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("NewsAPI payload has invalid root type")

    if payload.get("status") == "error":
        code = payload.get("code", "unknown")
        message = payload.get("message", "unknown error")
        raise RuntimeError(f"NewsAPI returned error payload: {code} - {message}")

    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    payload["language"] = language
    payload["key_word"] = key_word

    raw_articles = payload.get("articles")
    if not isinstance(raw_articles, list):
        logger.warning("NewsAPI payload contains non-list articles field")
        payload["articles"] = []
        articles_count = 0
    else:
        articles_count = len(raw_articles)

    logger.info(
        "NewsAPI fetch completed (status=%s, keyword=%s, page=%s, page_size=%s, raw_articles=%s)",
        response.status_code,
        key_word,
        page,
        normalized_page_size,
        articles_count,
    )

    return payload, articles_count


def make_extract_debug(
    key_word: str,
    page: int = 1,
    page_size: int = 20,
    language: str = "ru",
) -> tuple[str, int]:
    payload, articles_count = _fetch_payload(key_word, page, page_size, language)
    if articles_count == 0:
        logger.info("There are no more articles for keyword=%s", key_word)

    new_file_name = import_to_raw_json(payload, key_word, page)
    return new_file_name, articles_count


def make_extract_web(
    key_word: str,
    page: int = 1,
    page_size: int = 20,
    language: str = "ru",
) -> tuple[dict[str, Any], int]:
    payload, articles_count = _fetch_payload(key_word, page, page_size, language)
    if articles_count == 0:
        logger.info("There are no more articles for keyword=%s", key_word)
    return payload, articles_count
