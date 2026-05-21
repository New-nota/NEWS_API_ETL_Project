from __future__ import annotations

import locale
import re
from contextlib import contextmanager

from typing import Iterator, Sequence

from datetime import datetime, timedelta, timezone
from sqlalchemy import URL, Engine, and_, or_, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from config.config import settings

from .models import (
    AppUser,
    Article,
    BadNewsBears,
    Base,
    RequestAiReport,
    RequestStats,
    SearchRequest,
    UserNews,
    UsersKeys,
)

_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _decode_non_utf8_error(exc: UnicodeDecodeError) -> str:
    raw = exc.object
    if not isinstance(raw, (bytes, bytearray)):
        return str(exc)

    encodings_to_try = []
    preferred = locale.getpreferredencoding(False) # система
    if preferred:
        encodings_to_try.append(preferred)
    encodings_to_try.extend(["cp1251", "cp866", "latin1"]) # иные кодировки

    seen: set[str] = set()
    for encoding in encodings_to_try:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return bytes(raw).decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue

    return bytes(raw).decode("latin1", errors="replace")


def _build_connection_hint(decoded_message: str, db_name: str) -> str:
    lower_message = decoded_message.lower()
    if (
        ("database" in lower_message and "does not exist" in lower_message)
        or ("база данных" in lower_message and "не существует" in lower_message)
    ):
        return (
            f"Database '{db_name}' does not exist. "
            "Запусти `python main.py --init-only` один раз или используй `--bootstrap` чтобы запустить команду."
        )

    if (
        "password authentication failed" in lower_message
        or "не прошёл проверку подлинности" in lower_message
    ):
        return (
            "Authentication failed. "
            "Проверь DB_HOST/DB_PORT/DB_USER/DB_PASSWORD и PostgreSQL `pg_hba.conf`."
        )

    if "pg_hba" in lower_message:
        return (
            "Подключение отклонено pg_hba.conf. "
            "Проверь host/user/database комбинацию или используй соответсвующий метод аутентификации"
        )

    return (
        "Подключение не удалось, сообщение сервера было не в UTF-8."
        "Проверь настройки базы и логи PostgreSQL"
    )


def _wrap_connect_error(exc: UnicodeDecodeError, db_name: str) -> RuntimeError:
    decoded_message = _decode_non_utf8_error(exc)
    system_encoding = locale.getpreferredencoding(False)
    hint = _build_connection_hint(decoded_message, db_name)
    return RuntimeError(
        "PostgreSQL connection failed.\n"
        f"Target: host={settings.db_host} port={settings.db_port} "
        f"user={settings.db_user} db={db_name}\n"
        f"Hint: {hint}\n"
        f"System encoding: {system_encoding}\n"
        f"Raw server message: {decoded_message}"
    )


def _make_url(db_name: str) -> URL:
    return URL.create(
        drivername="postgresql+psycopg2",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=db_name,
    )


def _build_engine(db_name: str) -> Engine:
    connect_args: dict[str, object] = {
        "connect_timeout": settings.db_connect_timeout_seconds,
    }
    if settings.db_statement_timeout_ms > 0:
        connect_args["options"] = (
            f"-c statement_timeout={settings.db_statement_timeout_ms}"
        )
    return create_engine(
        _make_url(db_name),
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


_engines: dict[str, Engine] = {}


def engine_for(db_name: str) -> Engine:
    engine = _engines.get(db_name)
    if engine is None:
        engine = _build_engine(db_name)
        _engines[db_name] = engine
    return engine


def _news_engine() -> Engine:
    return engine_for(settings.news_db)


@contextmanager
def _connect(engine: Engine, db_name: str, *, autocommit: bool = False) -> Iterator:
    try:
        conn = engine.connect()
    except UnicodeDecodeError as exc:
        # On localized Windows installations libpq can return non-UTF8 auth errors
        # (for example invalid password / pg_hba issues), and psycopg2 may raise
        # UnicodeDecodeError instead of OperationalError. SQLAlchemy passes it
        # through unwrapped.
        raise _wrap_connect_error(exc, db_name) from exc

    try:
        if autocommit:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
        if not autocommit and conn.in_transaction():
            conn.commit()
    except Exception:
        if not autocommit and conn.in_transaction():
            conn.rollback()
        raise
    finally:
        conn.close()


_SessionLocal: sessionmaker[Session] | None = None


def _session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_news_engine(), expire_on_commit=False, future=True
        )
    return _SessionLocal


@contextmanager
def get_session() -> Iterator[Session]:
    factory = _session_factory()
    try:
        session = factory()
    except UnicodeDecodeError as exc:
        raise _wrap_connect_error(exc, settings.news_db) from exc

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_exists(db_name: str) -> bool:
    with _connect(engine_for(settings.db_admin_db), settings.db_admin_db, autocommit=True) as conn:
        row = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": db_name},
        ).first()
        return row is not None


def ensure_databases_exists(db_names: Sequence[str]) -> None:
    missing = [db_name for db_name in db_names if not database_exists(db_name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing database(s): {joined}")


def table_exists(db_name: str, table_name: str) -> bool:
    with _connect(engine_for(db_name), db_name, autocommit=True) as conn:
        row = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": table_name},
        ).first()
        return row is not None


def ensure_tables_exist(db_name: str, table_names: Sequence[str]) -> None:
    missing = [table_name for table_name in table_names if not table_exists(db_name, table_name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing table(s) in database {db_name}: {joined}")


def create_database_if_not_exists(db_name: str) -> None:
    if database_exists(db_name):
        return

    if not _DB_NAME_RE.match(db_name):
        # `CREATE DATABASE` cannot be parameterized; reject anything that
        # would otherwise require manual quoting/escaping.
        raise ValueError(
            f"Отказано в создании базы данных изза неподобающего имени: {db_name!r}. "
            "Разрещенные символы: латиница, цифры, нижнее подчеркивание."
        )

    with _connect(engine_for(settings.db_admin_db), settings.db_admin_db, autocommit=True) as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}" ENCODING \'UTF8\''))


def init_database() -> None:
    create_database_if_not_exists(settings.news_db)


def _create_table(table_attr: str) -> None:
    Base.metadata.tables[table_attr].create(_news_engine(), checkfirst=True)


def create_search_requests_table() -> None:
    _create_table("search_requests")
    with _connect(_news_engine(), settings.news_db) as conn:
        conn.execute(text(
            "ALTER TABLE search_requests ADD COLUMN IF NOT EXISTS is_trial BOOLEAN NOT NULL DEFAULT FALSE"
        ))


def create_articles_table() -> None:
    _create_table("articles")


def create_user_news_table() -> None:
    _create_table("user_news")
    

def create_request_stats_table() -> None:
    _create_table("request_stats")

    trigger_function = """
        CREATE OR REPLACE FUNCTION set_request_stats_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """

    trigger = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_request_stats_updated_at'
            ) THEN
                CREATE TRIGGER trg_request_stats_updated_at
                BEFORE UPDATE ON request_stats
                FOR EACH ROW
                EXECUTE FUNCTION set_request_stats_updated_at();
            END IF;
        END $$;
    """

    with _connect(_news_engine(), settings.news_db) as conn:
        conn.execute(text(trigger_function))
        conn.execute(text(trigger))


def create_request_ai_report_table() -> None:
    _create_table("request_ai_report")

    # Idempotently bring older deployments to the current shape: add
    # status/error_text and relax NOT NULL on AI fields so failed rows can
    # be stored alongside successful ones.
    migrations = [
        "ALTER TABLE request_ai_report ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'success'",
        "ALTER TABLE request_ai_report ADD COLUMN IF NOT EXISTS error_text TEXT",
        "ALTER TABLE request_ai_report ALTER COLUMN summary DROP NOT NULL",
        "ALTER TABLE request_ai_report ALTER COLUMN sentiment_label DROP NOT NULL",
        "ALTER TABLE request_ai_report ALTER COLUMN model_provider DROP NOT NULL",
        "ALTER TABLE request_ai_report ALTER COLUMN model_name DROP NOT NULL",
    ]

    add_status_check = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'request_ai_report_status_check'
            ) THEN
                ALTER TABLE request_ai_report
                ADD CONSTRAINT request_ai_report_status_check
                CHECK (status IN ('success', 'failed'));
            END IF;
        END $$;
    """

    with _connect(_news_engine(), settings.news_db) as conn:
        for migration in migrations:
            conn.execute(text(migration))
        conn.execute(text(add_status_check))


def create_app_users_table() -> None:
    _create_table("app_users")
    with _connect(_news_engine(), settings.news_db) as conn:
        conn.execute(text(
            "ALTER TABLE app_users ADD COLUMN IF NOT EXISTS trial_uses Integer not null Default 0"
        ))


def create_news_tables() -> None:
    _create_table("bad_news_bears")


def create_users_keys_table() -> None:
    _create_table("users_keys")
    migrations = [
        "ALTER TABLE users_keys ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending_validation'",
        "ALTER TABLE users_keys ADD COLUMN IF NOT EXISTS validation_error TEXT",
        "ALTER TABLE users_keys ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ",
    ]
    add_status_check = """
    ALTER TABLE users_keys DROP CONSTRAINT IF EXISTS users_keys_status_check;
    ALTER TABLE users_keys ADD CONSTRAINT users_keys_status_check
        CHECK (status IN ('pending_validation', 'validating', 'valid', 'invalid', 'exhausted'));
    """
    trigger_function = """
        CREATE OR REPLACE FUNCTION set_users_keys_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    trigger = """
        DO $$
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_users_keys_updated_at'
            ) THEN
                CREATE TRIGGER trg_users_keys_updated_at
                BEFORE UPDATE ON users_keys
                FOR EACH ROW
                EXECUTE FUNCTION set_users_keys_updated_at();
            END IF;
        END $$;
        """
    with _connect(_news_engine(), settings.news_db) as conn:
        for m in migrations:
            conn.execute(text(m))
        conn.execute(text(add_status_check))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS users_keys_status_idx ON users_keys (status)"
        ))
        conn.execute(text(trigger_function))
        conn.execute(text(trigger))


def claim_next_search_request() -> dict | None:
    # CTE-based atomic claim: SELECT ... FOR UPDATE SKIP LOCKED + UPDATE in
    # one statement so multiple workers can run safely against the queue.
    with get_session() as session:
        request = session.execute(
            select(SearchRequest).where(SearchRequest.status == "queued").order_by(SearchRequest.created_at).limit(1).with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if request is None:
            return None
        request.status = "running"
        request.started_at = datetime.now(timezone.utc)
        request.error_text = None
        session.flush()

        return {
            "id" : request.id,
            "user_id": request.user_id,
            "keyword" : request.keyword,
            "language": request.language,
            "limit_count": request.limit_count,
            "page_size": request.page_size,
            "is_trial": request.is_trial
        }


def claim_pending_key_validation() -> dict | None:
    # подхватывает и pending и зависшие
    # в случае падения воркера триггер updated_at покажет что просшло > 10 мин 
    stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10) 
    with get_session() as session:
        key = session.execute(select(UsersKeys).where(or_(UsersKeys.status == "pending_validation", and_(UsersKeys.status == "validating", UsersKeys.updated_at < stale_threshold,)))
                              .order_by(UsersKeys.id).limit(1).with_for_update(skip_locked=True)).scalar_one_or_none()
        if key is None:
            return None
        key.status = "validating"
        session.flush()

        return {
            "id": key.id,
            "user_id": key.user_id,
            "encrypted_key": key.encrypted_key,
            "iv": key.iv, 
            "auth_tag": key.auth_tag,
        }
def mark_key_validation_result(key_id: int, status: str, error: str | None) -> None:
    with get_session() as session:
        key = session.get(UsersKeys, key_id)
        if key is None:
            return
        key.status = status
        key.validation_error = error
        if status != "pending_validation":
            key.validated_at = datetime.now(timezone.utc)

def search_request_exists(search_request_id: int) -> bool:
    with get_session() as session:
        return session.scalar(
            select(SearchRequest.id).where(SearchRequest.id == search_request_id)
        ) is not None


def app_user_exists(user_id: int) -> bool:
    with get_session() as session:
        return session.scalar(
            select(AppUser.id).where(AppUser.id == user_id)
        ) is not None


def search_request_belongs_to_user(search_request_id: int, user_id: int) -> bool:
    with get_session() as session:
        return session.scalar(
            select(SearchRequest.id).where(
                SearchRequest.id == search_request_id,
                SearchRequest.user_id == user_id,
            )
        ) is not None


def fetch_articles_for_search_request(search_request_id: int) -> list[dict]:
    stmt = (
        select(
            Article.url,
            Article.source_name,
            Article.author,
            Article.title,
            Article.description,
            Article.published_at,
        )
        .join(UserNews, UserNews.article_id == Article.id)
        .where(UserNews.search_request_id == search_request_id)
        .order_by(Article.published_at.desc().nulls_last(), Article.id)
    )

    with get_session() as session:
        rows = session.execute(stmt).mappings().all()
        return [dict(row) for row in rows]


__all__ = [
    "AppUser",
    "Article",
    "BadNewsBears",
    "RequestAiReport",
    "RequestStats",
    "SearchRequest",
    "UserNews",
    "UsersKeys",
    "app_user_exists",
    "claim_next_search_request",
    "create_app_users_table",
    "create_articles_table",
    "create_database_if_not_exists",
    "create_news_tables",
    "create_request_ai_report_table",
    "create_request_stats_table",
    "create_search_requests_table",
    "create_user_news_table",
    "create_users_keys_table",
    "database_exists",
    "engine_for",
    "ensure_databases_exists",
    "ensure_tables_exist",
    "fetch_articles_for_search_request",
    "get_session",
    "init_database",
    "search_request_belongs_to_user",
    "search_request_exists",
    "table_exists",
    "claim_panding_key_validation",
    "mark_key_validation_result"
]

