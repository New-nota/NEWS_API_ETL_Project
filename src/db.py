from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from config.config import settings

@contextmanager
def get_connection(db_name: str, autocommit: bool = False) -> Iterator:
    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        passowrd=settings.db_password,
        cursor_factory=RealDictCursor
        )
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()
