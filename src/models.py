from __future__ import annotations

from datetime import datetime
from typing import Any

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    google_sub: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    trial_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class SearchRequest(Base):
    __tablename__ = "search_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="ru"
    )
    limit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    is_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    __table_args__ = (
        CheckConstraint("limit_count > 0", name="search_requests_limit_count_check"),
        CheckConstraint("page_size > 0", name="search_requests_page_size_check"),
        CheckConstraint(
            "status IN ('queued', 'running', 'success', 'failed')",
            name="search_requests_status_check",
        ),
        Index("idx_search_requests_user_id", "user_id"),
        Index("idx_search_requests_status_created_at", "status", "created_at"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_name: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_articles_published_at", text("published_at DESC")),
    )


class UserNews(Base):
    __tablename__ = "user_news"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    search_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "article_id",
            "search_request_id",
            name="user_news_user_id_article_id_search_request_id_key",
        ),
        Index("idx_user_news_user_id", "user_id"),
        Index("idx_user_news_search_request_id", "search_request_id"),
        Index("idx_user_news_article_id", "article_id"),
    )


class RequestStats(Base):
    __tablename__ = "request_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    income_articles: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    accepted_articles: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rejected_articles: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    reasons_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    prime_reasons: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class RequestAiReport(Base):
    __tablename__ = "request_ai_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="success"
    )
    error_text: Mapped[str | None] = mapped_column(Text)

    model_provider: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)

    news_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    summary: Mapped[str | None] = mapped_column(Text)
    main_conclusions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    sentiment_label: Mapped[str | None] = mapped_column(Text)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    sentiment_distribution: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    main_topics: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    highlight: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    data_quality_warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    # Schema column is misspelled ("promt_version", missing 'p') — see CLAUDE.md.
    # Map it to a properly-spelled Python attribute.
    prompt_version: Mapped[str] = mapped_column(
        "promt_version", Text, nullable=False, server_default="v1"
    )

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'failed')",
            name="request_ai_report_status_check",
        ),
    )


class UsersKeys(Base):
    __tablename__ = "users_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False
    )
    service: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    iv: Mapped[str] = mapped_column(Text, nullable=False)
    auth_tag: Mapped[str] = mapped_column(Text, nullable=False)
    key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="pending_validation")
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "service", name="users_keys_user_id_service_key"),
        CheckConstraint(
            "status IN ('pending_validation', 'validating', 'valid', 'invalid', 'exhausted')", name="users_key_status_check",
        ),
    )


class BadNewsBears(Base):
    __tablename__ = "bad_news_bears"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    language: Mapped[str] = mapped_column(String, nullable=False)
    key_word: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    published_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
