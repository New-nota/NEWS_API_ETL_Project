from __future__ import annotations

from src.transform import clean_article


def _base_payload() -> dict:
    return {
        "language": "ru",
        "key_word": "python",
        "fetched_at": "2026-01-01T10:00:00Z",
        "articles": [],
    }


def test_clean_article_handles_missing_articles_field() -> None:
    clean, stats = clean_article({"language": "ru", "key_word": "python"})

    assert clean == []
    assert stats["income_articles"] == 0
    assert stats["accepted_articles"] == 0
    assert stats["rejected_articles"] == 0


def test_clean_article_rejects_invalid_description_type() -> None:
    payload = _base_payload()
    payload["articles"] = [
        {
            "author": "author",
            "title": "title",
            "description": 100,
            "url": "https://example.com/news/1",
            "publishedAt": "2026-01-01T10:00:00Z",
        }
    ]

    clean, stats = clean_article(payload)

    assert clean == []
    assert stats["rejected_articles"] == 1
    assert stats["reasons_counts"]["invalid_description_type"] == 1


def test_clean_article_normalizes_timezone() -> None:
    payload = _base_payload()
    payload["articles"] = [
        {
            "author": "author",
            "title": "title",
            "description": "this description is definitely longer than twenty chars",
            "url": "https://example.com/news/2",
            "publishedAt": "2026-01-01T10:00:00Z",
            "source": {"name": "Example"},
        }
    ]

    clean, stats = clean_article(payload)

    assert stats["accepted_articles"] == 1
    assert clean[0]["published_at"].endswith("+00:00")
    assert clean[0]["source_name"] == "Example"
