from __future__ import annotations

from contextlib import contextmanager
import locale
from typing import Iterator, Sequence

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from config.config import settings


def _decode_non_utf8_error(exc: UnicodeDecodeError) -> str:
    raw = exc.object
    if not isinstance(raw, (bytes, bytearray)):
        return str(exc)

    encodings_to_try = []
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings_to_try.append(preferred)
    encodings_to_try.extend(["cp1251", "cp866", "latin1"])

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
            "Run `python main.py --init-only` once or add `--bootstrap` to the run command."
        )

    if (
        "password authentication failed" in lower_message
        or "не прошёл проверку подлинности" in lower_message
    ):
        return (
            "Authentication failed. "
            "Check DB_HOST/DB_PORT/DB_USER/DB_PASSWORD and PostgreSQL `pg_hba.conf`."
        )

    if "pg_hba" in lower_message:
        return (
            "Connection rejected by pg_hba.conf. "
            "Allow the host/user/database combination or use a matching auth method."
        )

    return (
        "Connection failed with a non-UTF8 server message. "
        "Check DB settings and PostgreSQL server logs."
    )


@contextmanager
def get_connection(db_name: str, autocommit: bool = False) -> Iterator:
    connection_kwargs: dict[str, object] = {
        "dbname": db_name,
        "host": settings.db_host,
        "port": settings.db_port,
        "user": settings.db_user,
        "password": settings.db_password,
        "cursor_factory": RealDictCursor,
        "connect_timeout": settings.db_connect_timeout_seconds,
    }

    if settings.db_statement_timeout_ms > 0:
        connection_kwargs["options"] = f"-c statement_timeout={settings.db_statement_timeout_ms}"

    try:
        conn = psycopg2.connect(**connection_kwargs)
    except UnicodeDecodeError as exc:
        # On localized Windows installations libpq can return non-UTF8 auth errors
        # (for example invalid password / pg_hba issues), and psycopg2 may raise
        # UnicodeDecodeError instead of OperationalError.
        decoded_message = _decode_non_utf8_error(exc)
        system_encoding = locale.getpreferredencoding(False)
        hint = _build_connection_hint(decoded_message, db_name)
        raise RuntimeError(
            "PostgreSQL connection failed.\n"
            f"Target: host={settings.db_host} port={settings.db_port} "
            f"user={settings.db_user} db={db_name}\n"
            f"Hint: {hint}\n"
            f"System encoding: {system_encoding}\n"
            f"Raw server message: {decoded_message}"
        ) from exc
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(db_name: str, autocommit: bool = False) -> Iterator:
    with get_connection(db_name=db_name, autocommit=autocommit) as conn:
        with conn.cursor() as cur:
            try:
                yield conn, cur
            except Exception:
                if not autocommit:
                    conn.rollback()
                raise


def database_exists(db_name: str) -> bool:
    with get_cursor(settings.db_admin_db, autocommit=True) as (_, cur):
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        return cur.fetchone() is not None


def ensure_databases_exists(db_names: Sequence[str]) -> None:
    missing = [db_name for db_name in db_names if not database_exists(db_name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing database(s): {joined}")


def table_exists(db_name: str, table_name: str) -> bool:
    with get_cursor(db_name, autocommit=True) as (_, cur):
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


def ensure_tables_exist(db_name: str, table_names: Sequence[str]) -> None:
    missing = [table_name for table_name in table_names if not table_exists(db_name, table_name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing table(s) in database {db_name}: {joined}")


def create_database_if_not_exists(db_name: str) -> None:
    if database_exists(db_name):
        return

    with get_cursor(settings.db_admin_db, autocommit=True) as (_, cur):
        cur.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(db_name)))


def init_database() -> None:
    create_database_if_not_exists(settings.news_db)


def create_search_requests_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS search_requests (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            language VARCHAR(10) NOT NULL DEFAULT 'ru',
            limit_count INTEGER NOT NULL CHECK (limit_count > 0),
            page_size INTEGER NOT NULL CHECK (page_size > 0),
            status VARCHAR(20) NOT NULL CHECK (status IN ('queued', 'running', 'success', 'failed')),
            error_text TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
    """

    index_list = [
        """
        CREATE INDEX IF NOT EXISTS idx_search_requests_user_id
            ON search_requests(user_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_search_requests_status_created_at
            ON search_requests(status, created_at)
        """,
    ]

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        for index_query in index_list:
            cur.execute(index_query)
        conn.commit()


def create_articles_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS articles (
            id BIGSERIAL PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            source_name TEXT,
            author TEXT,
            title TEXT NOT NULL,
            description TEXT,
            published_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """

    index = """
        CREATE INDEX IF NOT EXISTS idx_articles_published_at
            ON articles(published_at DESC)
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        cur.execute(index)
        conn.commit()


def create_user_news_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS user_news (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            search_request_id BIGINT NOT NULL REFERENCES search_requests(id) ON DELETE CASCADE,
            article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, article_id, search_request_id)
        )
    """

    index_list = [
        """
        CREATE INDEX IF NOT EXISTS idx_user_news_user_id
            ON user_news(user_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_user_news_search_request_id
            ON user_news(search_request_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_user_news_article_id
            ON user_news(article_id)
        """,
    ]

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        for index_query in index_list:
            cur.execute(index_query)
        conn.commit()


def create_request_stats_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS request_stats (
            id BIGSERIAL PRIMARY KEY,
            search_request_id BIGINT NOT NULL UNIQUE REFERENCES search_requests(id) ON DELETE CASCADE,
            income_articles INTEGER NOT NULL DEFAULT 0,
            accepted_articles INTEGER NOT NULL DEFAULT 0,
            rejected_articles INTEGER NOT NULL DEFAULT 0,
            reasons_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
            prime_reasons JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """

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

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        cur.execute(trigger_function)
        cur.execute(trigger)
        conn.commit()


def create_request_ai_report_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS request_ai_report (
            id BIGSERIAL PRIMARY KEY,
            search_request_id BIGINT NOT NULL UNIQUE REFERENCES search_requests(id) ON DELETE CASCADE,

            model_provider TEXT NOT NULL,
            model_name TEXT NOT NULL,

            news_count INTEGER NOT NULL DEFAULT 0,
            
            summary TEXT NOT NULL,
            main_conclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
            sentiment_label TEXT NOT NULL,
            sentiment_score NUMERIC(5, 2),
            sentiment_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
            main_topics JSONB NOT NULL DEFAULT '[]'::jsonb,
            highlight JSONB NOT NULL DEFAULT '{}'::jsonb,
            data_quality_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,

            promt_version TEXT NOT NULL DEFAULT 'v1',

            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        conn.commit()


def create_app_users_table() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS app_users (
            id BIGSERIAL PRIMARY KEY,
            google_sub TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            name TEXT,
            image_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        conn.commit()


def create_news_tables() -> None:
    query = """
        CREATE TABLE IF NOT EXISTS bad_news_bears (
            id BIGSERIAL PRIMARY KEY,
            language VARCHAR NOT NULL,
            key_word VARCHAR NOT NULL,
            author VARCHAR,
            title TEXT NOT NULL,
            description TEXT,
            url TEXT UNIQUE NOT NULL,
            published_at TIMESTAMPTZ NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        conn.commit()

def create_users_keys_table() -> None:
    query = """
            CREATE TABLE IF NOT EXISTS users_keys(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            service VARCHAR(50) NOT NULL,
            encrypted_key TEXT NOT NULL,
            iv TEXT NOT NULL,
            auth_tag TEXT NOT NULL,
            key_last4 VARCHAR(4) NOT NULL,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, service)
            );
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
    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        cur.execute(trigger_function)
        cur.execute(trigger)
        conn.commit()


def claim_next_search_request() -> dict | None:
    query = """
        WITH next_request AS (
            SELECT id
            FROM search_requests
            WHERE status = 'queued'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE search_requests AS sr
        SET
            status = 'running',
            started_at = NOW(),
            error_text = NULL
        FROM next_request
        WHERE sr.id = next_request.id
        RETURNING sr.id, sr.user_id, sr.keyword, sr.language, sr.limit_count, sr.page_size
    """

    with get_cursor(settings.news_db) as (conn, cur):
        cur.execute(query)
        row = cur.fetchone()
        conn.commit()
        return row


def search_request_exists(search_request_id: int) -> bool:
    query = "SELECT 1 FROM search_requests WHERE id = %s"
    with get_cursor(settings.news_db, autocommit=True) as (_, cur):
        cur.execute(query, (search_request_id,))
        return cur.fetchone() is not None


def app_user_exists(user_id: int) -> bool:
    query = "SELECT 1 FROM app_users WHERE id = %s"
    with get_cursor(settings.news_db, autocommit=True) as (_, cur):
        cur.execute(query, (user_id,))
        return cur.fetchone() is not None


def search_request_belongs_to_user(search_request_id: int, user_id: int) -> bool:
    query = "SELECT 1 FROM search_requests WHERE id = %s AND user_id = %s"
    with get_cursor(settings.news_db, autocommit=True) as (_, cur):
        cur.execute(query, (search_request_id, user_id))
        return cur.fetchone() is not None


def fetch_articles_for_search_request(search_request_id: int) -> list[dict]:
    query = """
        SELECT
            a.url,
            a.source_name,
            a.author,
            a.title,
            a.description,
            a.published_at
        FROM articles a
        JOIN user_news un ON un.article_id = a.id
        WHERE un.search_request_id = %s
        ORDER BY a.published_at DESC NULLS LAST, a.id
    """
    with get_cursor(settings.news_db, autocommit=True) as (_, cur):
        cur.execute(query, (search_request_id,))
        return [dict(row) for row in cur.fetchall()]
