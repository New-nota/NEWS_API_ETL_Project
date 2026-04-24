from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    # Keep local runs deterministic: values from project `.env` must win over
    # stale shell/session variables left from older commands.
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    # Preserve explicit key presence from `.env` (including empty values),
    # because python-dotenv skips unset keys when loading.
    for key, value in dotenv_values(ENV_PATH).items():
        if value is None:
            continue
        os.environ[key] = value


def _get_env_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    raw_value = os.getenv(name, default)
    if raw_value is None:
        if required:
            raise ValueError(f"Environment variable {name} is required")
        return ""

    value = raw_value.strip()
    if required and not value:
        raise ValueError(f"Environment variable {name} is required")
    return value


def _get_env_int(
    name: str,
    default: int | None = None,
    *,
    required: bool = False,
    min_value: int | None = None,
) -> int:
    if default is None:
        raw_default: str | None = None
    else:
        raw_default = str(default)

    raw_value = os.getenv(name, raw_default)
    if raw_value is None:
        if required:
            raise ValueError(f"Environment variable {name} is required")
        raise ValueError(f"Environment variable {name} has no default value")

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc

    if min_value is not None and value < min_value:
        raise ValueError(f"Environment variable {name} must be >= {min_value}")
    return value


def _get_env_float(
    name: str,
    default: float | None = None,
    *,
    min_value: float | None = None,
) -> float:
    if default is None:
        raw_default: str | None = None
    else:
        raw_default = str(default)

    raw_value = os.getenv(name, raw_default)
    if raw_value is None:
        raise ValueError(f"Environment variable {name} has no default value")

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float") from exc

    if min_value is not None and value < min_value:
        raise ValueError(f"Environment variable {name} must be >= {min_value}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_admin_db: str
    db_news: str

    newsapi_key: str
    news_url: str
    default_language: str
    sort_by: str

    request_timeout_seconds: float
    request_max_retries: int
    request_backoff_factor: float
    request_max_backoff_seconds: float
    request_page_size_max: int
    max_pages_per_request: int
    newsapi_max_total_results: int

    db_connect_timeout_seconds: int
    db_statement_timeout_ms: int

    @property
    def KEY_API(self) -> str:  # backward compatibility
        return self.newsapi_key

    @property
    def NEWS_URL(self) -> str:  # backward compatibility
        return self.news_url

    @property
    def sortBy(self) -> str:  # backward compatibility
        return self.sort_by

    @property
    def langueage(self) -> str:  # backward compatibility (legacy typo)
        return self.default_language


_ALLOWED_SORT_BY = {"relevancy", "popularity", "publishedAt"}


def build_settings() -> Settings:
    sort_by = _get_env_str("NEWSAPI_SORT_BY", "publishedAt")
    if sort_by not in _ALLOWED_SORT_BY:
        allowed = ", ".join(sorted(_ALLOWED_SORT_BY))
        raise ValueError(f"NEWSAPI_SORT_BY must be one of: {allowed}")

    return Settings(
        db_host=_get_env_str("DB_HOST", "localhost"),
        db_port=_get_env_int("DB_PORT", 5432, min_value=1),
        db_user=_get_env_str("DB_USER", "postgres"),
        db_password=_get_env_str("DB_PASSWORD", "postgres"),
        db_admin_db=_get_env_str("DB_ADMIN_DB", "postgres"),
        db_news=_get_env_str("DB_NEWS", "news_db"),
        newsapi_key=_get_env_str("NEWSAPI_KEY", ""),
        news_url=_get_env_str("NEWSAPI_URL", "https://newsapi.org/v2/everything"),
        default_language=_get_env_str("NEWSAPI_DEFAULT_LANGUAGE", "ru"),
        sort_by=sort_by,
        request_timeout_seconds=_get_env_float("REQUEST_TIMEOUT_SECONDS", 15.0, min_value=1.0),
        request_max_retries=_get_env_int("REQUEST_MAX_RETRIES", 3, min_value=0),
        request_backoff_factor=_get_env_float("REQUEST_BACKOFF_FACTOR", 1.0, min_value=0.0),
        request_max_backoff_seconds=_get_env_float("REQUEST_MAX_BACKOFF_SECONDS", 30.0, min_value=0.0),
        request_page_size_max=_get_env_int("REQUEST_PAGE_SIZE_MAX", 100, min_value=1),
        max_pages_per_request=_get_env_int("MAX_PAGES_PER_REQUEST", 50, min_value=1),
        newsapi_max_total_results=_get_env_int("NEWSAPI_MAX_TOTAL_RESULTS", 1000, min_value=1),
        db_connect_timeout_seconds=_get_env_int("DB_CONNECT_TIMEOUT_SECONDS", 10, min_value=1),
        db_statement_timeout_ms=_get_env_int("DB_STATEMENT_TIMEOUT_MS", 45000, min_value=0),
    )


settings = build_settings()
