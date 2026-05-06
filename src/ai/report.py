"""AI summary generation for a pocket of news articles."""

from __future__ import annotations

import logging
from typing import Any

from config.config import settings

from .client import MistralClientError, generate_summary
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .schemas import (
    HighlightArticle,
    SentimentDistribution,
    SummaryResponse,
    TokenUsage,
)

logger = logging.getLogger(__name__)

_VALID_SENTIMENT_LABELS = {"positive", "negative", "neutral"}


def _format_published_at(value: Any) -> str:
    if value is None:
        return "Unknown"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_articles_text(articles: list[dict[str, Any]], max_length: int = 15000) -> str:
    parts = []
    for idx, article in enumerate(articles, 1):
        title = article.get("title") or "No title"
        author = article.get("author") or "Unknown"
        source = article.get("source_name") or "Unknown"
        published_at = _format_published_at(article.get("published_at"))
        description = article.get("description") or "No description"
        url = article.get("url") or "No URL"
        snippet = description[:500] + ("..." if len(description) > 500 else "")
        parts.append(
            f"  Article {idx}:\n"
            f"    Title: {title}\n"
            f"    Source: {source}\n"
            f"    Author: {author}\n"
            f"    Published: {published_at}\n"
            f"    URL: {url}\n"
            f"    Description: {snippet}\n"
        )

    text = "\n".join(parts)
    if len(text) > max_length:
        text = text[:max_length] + "\n... (truncated)"
    return text


def _detect_data_quality_warnings(
    articles: list[dict[str, Any]],
    stats: dict[str, Any] | None,
) -> list[str]:
    warnings: list[str] = []

    missing_author = sum(1 for a in articles if not a.get("author"))
    missing_description = sum(1 for a in articles if not a.get("description"))
    missing_source = sum(1 for a in articles if not a.get("source_name"))

    if missing_author:
        warnings.append(f"{missing_author} articles missing author")
    if missing_description:
        warnings.append(f"{missing_description} articles missing description")
    if missing_source:
        warnings.append(f"{missing_source} articles missing source")

    urls = [a.get("url", "") for a in articles]
    duplicate_count = len(urls) - len(set(urls))
    if duplicate_count > 0:
        warnings.append(f"Found {duplicate_count} duplicate URLs")

    if stats:
        rejected = int(stats.get("rejected_articles", 0))
        if rejected > 0:
            reasons = stats.get("reasons_counts") or {}
            top = max(reasons.items(), key=lambda kv: kv[1], default=(None, 0))
            if top[0]:
                warnings.append(
                    f"{rejected} articles rejected during transform; top reason: {top[0]}"
                )

    return warnings


def _normalize_sentiment(
    raw: dict[str, Any],
) -> tuple[SentimentDistribution, str, float]:
    # Operate on plain floats first — the schema enforces le=100, but the
    # whole point of this function is to rescue out-of-range model output
    # by renormalizing.
    pos = max(float(raw.get("positive", 0) or 0), 0.0)
    neg = max(float(raw.get("negative", 0) or 0), 0.0)
    neu = max(float(raw.get("neutral", 0) or 0), 0.0)

    total = pos + neg + neu
    if total <= 0:
        pos, neg, neu = 0.0, 0.0, 100.0
        total = 100.0

    if not (99 <= total <= 101):
        pos = pos / total * 100
        neg = neg / total * 100
        neu = neu / total * 100

    pos = min(round(pos, 2), 100.0)
    neg = min(round(neg, 2), 100.0)
    neu = min(round(neu, 2), 100.0)

    distribution = SentimentDistribution(positive=pos, negative=neg, neutral=neu)
    pairs = {"positive": pos, "negative": neg, "neutral": neu}
    label = max(pairs, key=lambda key: pairs[key])
    score = round(pairs[label], 2)
    return distribution, label, score


def _coerce_main_conclusions(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("main_conclusions must be a list of 3 strings")
    items = [str(item).strip() for item in raw if str(item).strip()]
    if len(items) < 3:
        raise ValueError(f"main_conclusions must contain 3 items, got {len(items)}")
    return items[:3]


def _coerce_main_topics(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    items = [str(item).strip() for item in raw if str(item).strip()]
    return items[:3]


def _build_highlight(raw: Any, articles: list[dict[str, Any]]) -> HighlightArticle:
    fallback = articles[0]
    if not isinstance(raw, dict):
        return HighlightArticle(
            url=fallback["url"],
            title=fallback["title"],
            author=fallback.get("author"),
            description=fallback.get("description"),
            reason="Selected by fallback (model returned no highlight)",
        )

    raw_url = str(raw.get("url") or "").strip()
    matched = next((a for a in articles if a.get("url") == raw_url), None)

    if matched is None:
        # Model invented a URL not present in the input. Fall back to the first
        # real article so downstream consumers always see a valid URL.
        url = fallback["url"]
        matched = fallback
    else:
        url = raw_url

    return HighlightArticle(
        url=url,
        title=str(raw.get("title") or matched.get("title") or fallback["title"]),
        author=raw.get("author") or matched.get("author"),
        description=raw.get("description") or matched.get("description"),
        reason=str(raw.get("reason") or "Selected by AI"),
    )


def _fallback_summary(
    articles: list[dict[str, Any]],
    keyword: str,
    warnings: list[str],
) -> SummaryResponse:
    fallback_topic = keyword or "news"
    return SummaryResponse(
        articles_count=len(articles),
        summary=f"Found {len(articles)} articles about {keyword}. AI analysis is disabled.",
        main_conclusions=[
            f"Found {len(articles)} articles about {keyword}",
            "AI analysis is disabled or unavailable",
            "Manual review is recommended",
        ],
        sentiment_label="neutral",
        sentiment_score=100.0,
        sentiment_distribution=SentimentDistribution(positive=0, negative=0, neutral=100),
        main_topics=[fallback_topic],
        highlight=HighlightArticle(
            url=articles[0]["url"],
            title=articles[0]["title"],
            author=articles[0].get("author"),
            description=articles[0].get("description"),
            reason="First article (AI disabled)",
        ),
        data_quality_warnings=warnings,
        model_provider=settings.ai_provider,
        prompt_version=settings.ai_prompt_version,
    )


def generate_news_summary(
    articles: list[dict[str, Any]],
    keyword: str,
    stats: dict[str, Any] | None = None,
    use_ai: bool = True,
) -> SummaryResponse:
    if not articles:
        raise ValueError("Cannot generate summary for empty article list")

    warnings = _detect_data_quality_warnings(articles, stats)

    if not use_ai or not settings.ai_summary_enabled:
        logger.info("AI summary disabled — returning fallback")
        return _fallback_summary(articles, keyword, warnings)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        keyword=keyword,
        count=len(articles),
        articles=_build_articles_text(articles),
    )

    completion = generate_summary(SYSTEM_PROMPT, user_prompt)
    payload = completion.content

    try:
        main_conclusions = _coerce_main_conclusions(payload.get("main_conclusions"))
        main_topics = _coerce_main_topics(payload.get("main_topics")) or [keyword or "news"]

        distribution, computed_label, computed_score = _normalize_sentiment(
            payload.get("sentiment_distribution") or {}
        )

        # The model can disagree with its own distribution (e.g. claim "positive"
        # but emit a distribution dominated by "neutral"). Trust the distribution,
        # not the label.
        sentiment_label = computed_label

        raw_score = payload.get("sentiment_score")
        try:
            sentiment_score = round(float(raw_score), 2) if raw_score is not None else computed_score
        except (TypeError, ValueError):
            sentiment_score = computed_score

        highlight = _build_highlight(payload.get("highlight"), articles)

        ai_warnings = payload.get("data_quality_warnings") or []
        if isinstance(ai_warnings, list):
            warnings.extend(str(w) for w in ai_warnings if str(w).strip())

        summary_text = str(payload.get("summary") or "").strip()
        if not summary_text:
            summary_text = " ".join(main_conclusions)

        return SummaryResponse(
            articles_count=len(articles),
            summary=summary_text,
            main_conclusions=main_conclusions,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            sentiment_distribution=distribution,
            main_topics=main_topics,
            highlight=highlight,
            data_quality_warnings=warnings,
            model_provider=settings.ai_provider,
            model_name=completion.model_name,
            prompt_version=settings.ai_prompt_version,
            usage=TokenUsage(
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                total_tokens=completion.total_tokens,
            ),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise MistralClientError(f"Failed to parse AI response: {exc}") from exc
