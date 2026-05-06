from __future__ import annotations

import pytest

from src.ai import MistralClientError, generate_news_summary
from src.ai import report as ai_report
from src.ai.client import MistralCompletion


def _articles() -> list[dict]:
    return [
        {
            "url": "https://example.com/a",
            "source_name": "Source A",
            "author": "Alice",
            "title": "Title A",
            "description": "Description A is long enough for validation",
            "published_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "url": "https://example.com/b",
            "source_name": "Source B",
            "author": "Bob",
            "title": "Title B",
            "description": "Description B is also long enough",
            "published_at": "2026-01-02T00:00:00+00:00",
        },
    ]


def _completion(content: dict) -> MistralCompletion:
    return MistralCompletion(
        content=content,
        model_name="mistral-test",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
    )


def _good_payload() -> dict:
    return {
        "summary": "two articles",
        "main_conclusions": ["c1", "c2", "c3"],
        "sentiment_label": "neutral",
        "sentiment_score": 60,
        "sentiment_distribution": {"positive": 20, "negative": 20, "neutral": 60},
        "main_topics": ["t1", "t2"],
        "highlight": {
            "url": "https://example.com/a",
            "title": "Title A",
            "author": "Alice",
            "description": "Description A is long enough for validation",
            "reason": "most relevant",
        },
        "data_quality_warnings": [],
    }


def test_ai_disabled_returns_fallback_without_calling_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args, **kwargs):  # noqa: ANN001, ARG001
        raise AssertionError("AI client must not be called when use_ai=False")

    monkeypatch.setattr(ai_report, "generate_summary", boom)

    summary = generate_news_summary(_articles(), "python", None, use_ai=False)

    assert summary.articles_count == 2
    assert summary.sentiment_label == "neutral"
    assert summary.sentiment_distribution.neutral == 100
    assert summary.highlight.url == "https://example.com/a"


def test_label_forced_to_dominant_distribution_key(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _good_payload()
    payload["sentiment_label"] = "positive"  # disagrees with distribution
    payload["sentiment_score"] = 80
    payload["sentiment_distribution"] = {"positive": 10, "negative": 30, "neutral": 60}

    monkeypatch.setattr(ai_report, "generate_summary", lambda *a, **kw: _completion(payload))

    summary = generate_news_summary(_articles(), "python", None, use_ai=True)

    assert summary.sentiment_label == "neutral"


def test_renormalizes_distribution_to_100(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _good_payload()
    payload["sentiment_distribution"] = {"positive": 200, "negative": 100, "neutral": 200}

    monkeypatch.setattr(ai_report, "generate_summary", lambda *a, **kw: _completion(payload))

    summary = generate_news_summary(_articles(), "python", None, use_ai=True)
    total = (
        summary.sentiment_distribution.positive
        + summary.sentiment_distribution.negative
        + summary.sentiment_distribution.neutral
    )
    assert total == pytest.approx(100.0, abs=0.05)


def test_highlight_falls_back_to_real_url_when_invented(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _good_payload()
    payload["highlight"]["url"] = "https://invented.example/notreal"
    payload["highlight"]["title"] = "Hallucinated"

    monkeypatch.setattr(ai_report, "generate_summary", lambda *a, **kw: _completion(payload))

    summary = generate_news_summary(_articles(), "python", None, use_ai=True)

    real_urls = {a["url"] for a in _articles()}
    assert summary.highlight.url in real_urls
    assert summary.highlight.url == "https://example.com/a"


def test_invalid_response_raises_mistral_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _good_payload()
    payload["main_conclusions"] = ["only one"]  # violates the 3-item rule

    monkeypatch.setattr(ai_report, "generate_summary", lambda *a, **kw: _completion(payload))

    with pytest.raises(MistralClientError):
        generate_news_summary(_articles(), "python", None, use_ai=True)


def test_data_quality_warnings_flag_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    articles = _articles()
    articles[0]["author"] = None
    articles[1]["description"] = None
    articles[1]["source_name"] = None

    payload = _good_payload()
    monkeypatch.setattr(ai_report, "generate_summary", lambda *a, **kw: _completion(payload))

    summary = generate_news_summary(articles, "python", None, use_ai=True)
    joined = " | ".join(summary.data_quality_warnings)

    assert "missing author" in joined
    assert "missing description" in joined
    assert "missing source" in joined


def test_articles_text_includes_source_and_published_at() -> None:
    text = ai_report._build_articles_text(_articles())

    assert "Source A" in text
    assert "Source B" in text
    assert "2026-01-01T00:00:00+00:00" in text
    assert "2026-01-02T00:00:00+00:00" in text


def test_use_ai_with_empty_list_raises() -> None:
    with pytest.raises(ValueError):
        generate_news_summary([], "python", None, use_ai=True)
