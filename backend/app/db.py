"""
Database connection pool for Supabase PostgreSQL.
"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager

from app.config import settings


def _get_dsn() -> str:
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


@contextmanager
def get_db():
    """Context manager that yields a psycopg2 connection with RealDictCursor."""
    conn = psycopg2.connect(_get_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()
