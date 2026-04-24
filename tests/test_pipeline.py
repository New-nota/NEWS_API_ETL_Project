from __future__ import annotations

import pytest

from src import pipeline


def _page_stats() -> dict:
    return {
        "income_articles": 100,
        "accepted_articles": 80,
        "rejected_articles": 20,
        "reasons_counts": {
            "invalid_article_type": 0,
            "no_author": 1,
            "no_title": 0,
            "no_description": 1,
            "invalid_description_type": 0,
            "short_description": 0,
            "no_url": 0,
            "invalid_url_type": 0,
            "invalid_url": 0,
            "no_published_at": 0,
            "invalid_published_at": 0,
        },
        "prime_reasons": {
            "invalid_article_type": 0,
            "no_author": 1,
            "no_title": 0,
            "no_description": 1,
            "invalid_description_type": 0,
            "short_description": 0,
            "no_url": 0,
            "invalid_url_type": 0,
            "invalid_url": 0,
            "no_published_at": 0,
            "invalid_published_at": 0,
        },
    }


def test_pipeline_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"pages": 0, "max_rows": []}

    def fake_extract(keyword: str, page: int, page_size: int, language: str):
        calls["pages"] += 1
        return (
            {
                "articles": [{}] * 100,
                "totalResults": 100,
                "language": language,
                "key_word": keyword,
                "fetched_at": "2026-01-01T00:00:00+00:00",
            },
            100,
        )

    def fake_transform(payload: dict):
        clean_data = [
            {
                "key_word": "k",
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "url": f"https://example.com/{idx}",
                "author": "author",
                "title": "title",
                "description": "long enough description for validation",
                "published_at": "2026-01-01T00:00:00+00:00",
                "source_name": None,
            }
            for idx in range(80)
        ]
        return clean_data, _page_stats()

    def fake_load(user_id: int, search_request_id: int, clean_data: list[dict], max_rows: int | None = None):
        calls["max_rows"].append(max_rows)
        if max_rows is None:
            return len(clean_data)
        return min(len(clean_data), max_rows)

    def fake_stats(search_request_id: int, stats: dict):
        return None

    monkeypatch.setattr(pipeline, "make_extract_web", fake_extract)
    monkeypatch.setattr(pipeline, "transform_article_web", fake_transform)
    monkeypatch.setattr(pipeline, "load_web_pipeline", fake_load)
    monkeypatch.setattr(pipeline, "load_request_stats", fake_stats)

    loaded = pipeline.run_pipeline_for_web_user(
        user_id=1,
        search_request_id=10,
        key_word="python",
        limit=10,
        page_size=100,
        language="en",
    )

    assert loaded == 10
    assert calls["pages"] == 1
    assert calls["max_rows"] == [10]


def test_pipeline_writes_stats_even_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stats_calls = {"count": 0}

    def fake_extract(keyword: str, page: int, page_size: int, language: str):
        raise RuntimeError("boom")

    def fake_stats(search_request_id: int, stats: dict):
        stats_calls["count"] += 1

    monkeypatch.setattr(pipeline, "make_extract_web", fake_extract)
    monkeypatch.setattr(pipeline, "load_request_stats", fake_stats)

    with pytest.raises(RuntimeError):
        pipeline.run_pipeline_for_web_user(
            user_id=1,
            search_request_id=10,
            key_word="python",
            limit=10,
            page_size=100,
            language="en",
        )

    assert stats_calls["count"] == 1
