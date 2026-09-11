"""DuckDB connection and idempotent schema (Phase 1).

One schema for all environments. Production uses a file on disk.
Tests (Phase 2+) must call ``connect(\":memory:\")`` or a temp path so they
never touch the production file.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROD_PATH = PROJECT_ROOT / "data" / "spends.duckdb"
ENV_DB_PATH = "SPENDS_DB_PATH"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS credit_cards (
    card_id VARCHAR PRIMARY KEY,
    bank_name VARCHAR NOT NULL,
    card_name VARCHAR NOT NULL,
    last_4_digits VARCHAR NOT NULL,
    cardholder VARCHAR NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (bank_name, last_4_digits, cardholder)
);

CREATE TABLE IF NOT EXISTS statement_uploads (
    upload_id VARCHAR PRIMARY KEY,
    card_id VARCHAR NOT NULL,
    original_filename VARCHAR NOT NULL,
    file_fingerprint VARCHAR NOT NULL,
    uploaded_at TIMESTAMP NOT NULL,
    row_count INTEGER NOT NULL,
    status VARCHAR NOT NULL,
    statement_period VARCHAR,
    FOREIGN KEY (card_id) REFERENCES credit_cards (card_id)
);

CREATE TABLE IF NOT EXISTS credit_card_transactions (
    id VARCHAR PRIMARY KEY,
    card_id VARCHAR NOT NULL,
    upload_id VARCHAR NOT NULL,
    source_filename VARCHAR NOT NULL,
    date DATE NOT NULL,
    description VARCHAR NOT NULL,
    amount DOUBLE NOT NULL,
    category VARCHAR NOT NULL DEFAULT 'Unidentified',
    spend_type VARCHAR NOT NULL DEFAULT 'One-Time',
    FOREIGN KEY (card_id) REFERENCES credit_cards (card_id),
    FOREIGN KEY (upload_id) REFERENCES statement_uploads (upload_id)
);

CREATE TABLE IF NOT EXISTS category_cache (
    merchant_pattern VARCHAR PRIMARY KEY,
    assigned_category VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_categories (
    category_name VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_categories_name_ci
    ON custom_categories (lower(category_name));
"""


def resolve_db_path(db_path: str | Path | None = None) -> str:
    """Prod file by default; ``:memory:`` or any path for tests."""
    if db_path is not None:
        return str(db_path)
    env = os.environ.get(ENV_DB_PATH)
    if env:
        return env
    return str(DEFAULT_PROD_PATH)


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for statement in SCHEMA_SQL.split(";"):
        sql = statement.strip()
        if sql:
            conn.execute(sql)


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open DuckDB, create parent dir for file DBs, apply schema if missing."""
    resolved = resolve_db_path(db_path)
    if resolved != ":memory:":
        Path(resolved).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(resolved)
    apply_schema(conn)
    from backend.merchants import register_merchant_functions

    register_merchant_functions(conn)
    return conn


def fetch_dicts(conn: duckdb.DuckDBPyConnection, sql: str, params: list | tuple | None = None) -> list[dict]:
    rel = conn.execute(sql, params or [])
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def initialize_database(db_path: str | Path | None = None) -> str:
    """Create/migrate the database file (or memory DB) and close. Returns path."""
    resolved = resolve_db_path(db_path)
    conn = connect(resolved)
    conn.close()
    return resolved
