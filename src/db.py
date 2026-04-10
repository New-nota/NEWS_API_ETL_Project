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

