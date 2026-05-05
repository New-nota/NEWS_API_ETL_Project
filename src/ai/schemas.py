"""Pydantic schemas for AI summary data structures."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SentimentLabel = Literal["positive", "negative", "neutral"]


class SentimentDistribution(BaseModel):
    positive: float = Field(ge=0, le=100)
    negative: float = Field(ge=0, le=100)
    neutral: float = Field(ge=0, le=100)


class HighlightArticle(BaseModel):
    url: str
    title: str
    author: str | None = None
    description: str | None = None
    reason: str


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class SummaryResponse(BaseModel):
    articles_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    main_conclusions: list[str] = Field(min_length=3, max_length=3)
    sentiment_label: SentimentLabel
    sentiment_score: float = Field(ge=0, le=100)
    sentiment_distribution: SentimentDistribution
    main_topics: list[str] = Field(min_length=1, max_length=3)
    highlight: HighlightArticle
    data_quality_warnings: list[str] = Field(default_factory=list)

    model_provider: str = "mistral"
    model_name: str = "mistral-large-latest"
    prompt_version: str = "v1"
    usage: TokenUsage = Field(default_factory=TokenUsage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "articles_count": self.articles_count,
            "summary": self.summary,
            "main_conclusions": self.main_conclusions,
            "sentiment_label": self.sentiment_label,
            "sentiment_score": self.sentiment_score,
            "sentiment_distribution": self.sentiment_distribution.model_dump(),
            "main_topics": self.main_topics,
            "highlight": self.highlight.model_dump(),
            "data_quality_warnings": self.data_quality_warnings,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "usage": self.usage.model_dump(),
        }
