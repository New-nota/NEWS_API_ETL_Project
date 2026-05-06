from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src import pipeline
from src.ai import MistralClientError
from src.ai.schemas import (
    HighlightArticle,
    SentimentDistribution,
    SummaryResponse,
    TokenUsage,
)


def _patch_ai_settings(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
    base = pipeline.settings
    namespace = SimpleNamespace(
        ai_summary_enabled=overrides.get("ai_summary_enabled", base.ai_summary_enabled),
        ai_report_max_articles=overrides.get(
            "ai_report_max_articles", base.ai_report_max_articles
        ),
        ai_provider=overrides.get("ai_provider", base.ai_provider),
        ai_prompt_version=overrides.get("ai_prompt_version", base.ai_prompt_version),
    )
    monkeypatch.setattr(pipeline, "settings", namespace)


def _ok_summary(articles_count: int = 1) -> SummaryResponse:
    return SummaryResponse(
        articles_count=articles_count,
        summary="ok",
        main_conclusions=["c1", "c2", "c3"],
        sentiment_label="neutral",
        sentiment_score=100.0,
        sentiment_distribution=SentimentDistribution(positive=0, negative=0, neutral=100),
        main_topics=["t1"],
        highlight=HighlightArticle(
            url="https://example.com/x",
            title="x",
            reason="r",
        ),
        data_quality_warnings=[],
        usage=TokenUsage(),
    )


def _stub_articles(count: int) -> list[dict[str, Any]]:
    return [
        {
            "url": f"https://example.com/{idx}",
            "source_name": "S",
            "author": "A",
            "title": f"t{idx}",
            "description": "long enough description",
            "published_at": "2026-01-01T00:00:00+00:00",
        }
        for idx in range(count)
    ]


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

    def fake_extract(keyword: str, page: int, page_size: int, language: str, news_api_key: str | None = None):
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

    def fake_extract(keyword: str, page: int, page_size: int, language: str, news_api_key: str | None = None):
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


def test_ai_summary_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_settings(monkeypatch, ai_summary_enabled=False)

    def boom(*args, **kwargs):  # noqa: ANN001, ARG001
        raise AssertionError("AI path must not run when disabled")

    monkeypatch.setattr(pipeline, "fetch_articles_for_search_request", boom)
    monkeypatch.setattr(pipeline, "generate_news_summary", boom)
    monkeypatch.setattr(pipeline, "load_ai_report", boom)
    monkeypatch.setattr(pipeline, "load_failed_ai_report", boom)

    pipeline._generate_and_store_ai_summary(42, "python", {})


def test_ai_summary_truncates_articles_to_max(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_settings(monkeypatch, ai_summary_enabled=True, ai_report_max_articles=10)

    captured = {"articles": None}

    monkeypatch.setattr(
        pipeline, "fetch_articles_for_search_request", lambda _id: _stub_articles(100)
    )

    def fake_generate(articles, keyword, stats, use_ai=True):  # noqa: ARG001
        captured["articles"] = articles
        return _ok_summary(articles_count=len(articles))

    monkeypatch.setattr(pipeline, "generate_news_summary", fake_generate)
    monkeypatch.setattr(pipeline, "load_ai_report", lambda *a, **kw: None)

    pipeline._generate_and_store_ai_summary(42, "python", {})

    assert len(captured["articles"]) == 10


def test_ai_summary_persists_failed_report_on_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ai_settings(monkeypatch, ai_summary_enabled=True)

    monkeypatch.setattr(
        pipeline, "fetch_articles_for_search_request", lambda _id: _stub_articles(3)
    )

    def boom(*args, **kwargs):  # noqa: ANN001, ARG001
        raise MistralClientError("upstream broke")

    monkeypatch.setattr(pipeline, "generate_news_summary", boom)

    captured = {"calls": []}

    def fake_failed(search_request_id, error_text, **kwargs):
        captured["calls"].append(
            {
                "search_request_id": search_request_id,
                "error_text": error_text,
                **kwargs,
            }
        )

    monkeypatch.setattr(pipeline, "load_failed_ai_report", fake_failed)

    def must_not_call(*args, **kwargs):  # noqa: ANN001, ARG001
        raise AssertionError("success loader must not run on AI failure")

    monkeypatch.setattr(pipeline, "load_ai_report", must_not_call)

    pipeline._generate_and_store_ai_summary(42, "python", {})

    assert len(captured["calls"]) == 1
    call = captured["calls"][0]
    assert call["search_request_id"] == 42
    assert "upstream broke" in call["error_text"]
    assert call["news_count"] == 3


def test_ai_summary_persists_failed_report_when_no_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ai_settings(monkeypatch, ai_summary_enabled=True)

    monkeypatch.setattr(pipeline, "fetch_articles_for_search_request", lambda _id: [])

    captured = {"calls": []}

    def fake_failed(search_request_id, error_text, **kwargs):
        captured["calls"].append((search_request_id, error_text, kwargs.get("news_count")))

    monkeypatch.setattr(pipeline, "load_failed_ai_report", fake_failed)

    def must_not_call(*args, **kwargs):  # noqa: ANN001, ARG001
        raise AssertionError("AI client/load must not run when no articles")

    monkeypatch.setattr(pipeline, "generate_news_summary", must_not_call)
    monkeypatch.setattr(pipeline, "load_ai_report", must_not_call)

    pipeline._generate_and_store_ai_summary(42, "python", {})

    assert captured["calls"] == [(42, "No articles linked to search request", 0)]


def test_ai_summary_loads_report_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_settings(monkeypatch, ai_summary_enabled=True)

    monkeypatch.setattr(
        pipeline, "fetch_articles_for_search_request", lambda _id: _stub_articles(2)
    )
    monkeypatch.setattr(
        pipeline, "generate_news_summary", lambda *a, **kw: _ok_summary(2)
    )

    captured = {"loaded": []}

    def fake_load(search_request_id, summary):
        captured["loaded"].append((search_request_id, summary.articles_count))

    monkeypatch.setattr(pipeline, "load_ai_report", fake_load)

    def must_not_call(*args, **kwargs):  # noqa: ANN001, ARG001
        raise AssertionError("failed loader must not run on AI success")

    monkeypatch.setattr(pipeline, "load_failed_ai_report", must_not_call)

    pipeline._generate_and_store_ai_summary(42, "python", {})

    assert captured["loaded"] == [(42, 2)]
