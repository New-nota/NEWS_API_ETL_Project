from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Sequence

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from config.config import settings

@contextmanager
def get_connection(db_name: str, autocommit: bool = False) -> Iterator:
    conn = psycopg2.connect(
        dbname = db_name,
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        cursor_factory=RealDictCursor
        )
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_cursor(db_name: str, autocommit: bool = False) -> Iterator:
    with get_connection(db_name=db_name, autocommit=autocommit) as conn:
        with conn.cursor() as cur:
            yield conn, cur


def database_exists(db_name: str,) -> bool:
    with get_cursor(settings.db_admin_db, autocommit=True) as (_, cur):
        cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (db_name,))
        return cur.fetchone() is not None
    
def ensure_databases_exists(db_names:Sequence[str]) -> None:
    missing = [db_name for db_name in db_names if not database_exists(db_name, )]
    if missing:
        joined = ', '.join(missing)
        raise RuntimeError(f'There is no data base: {joined}')

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
    
def ensure_tables_exist(db_name: str, table_names:Sequence[str]) -> None:
    missing = [table_name for table_name in table_names if not table_exists(db_name, table_name)]
    if missing:
        joined = ', '.join(missing)
        raise RuntimeError(f'In data base {db_name} tables {joined} does not exists')

def create_database_if_not_exists(db_name: str) -> None:
    if database_exists(db_name):
        return
    with get_cursor(settings.db_admin_db, autocommit=True) as (_, cur):
        cur.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' ").format(sql.Identifier(db_name)))

def init_database() -> None:
    create_database_if_not_exists(settings.db_news)

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
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                started_at TIMESTAMP,
                finished_at TIMESTAMP
            );
        """
    index_list = ["""
                CREATE INDEX IF NOT EXISTS idx_search_requests_user_id
                    ON search_requests(user_id)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_search_requests_status
                    ON search_requests(status)
                """]
    with get_cursor(settings.db_news) as (conn, cur):
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
                published_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """
    index = """
            CREATE INDEX IF NOT EXISTS idx_articles_published_at
                ON articles(published_at DESC)
            """
    with get_cursor(settings.db_news) as (conn, cur):
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
                fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, article_id, search_request_id)
            );
        """
    index_list = ["""
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
                """]
    with get_cursor(settings.db_news) as (conn, cur):
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
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """
    with get_cursor(settings.db_news) as (conn, cur):
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
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        last_login_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    with get_cursor(settings.db_news) as (conn, cur):
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
            url TEXT UNIQUE  NOT NULL,
            published_at TIMESTAMP NOT NULL, 
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
    with get_cursor(settings.db_news) as (conn, cur):
        cur.execute(query)
        conn.commit()

