from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import duckdb

from backend.database import fetch_dicts
from backend.expense_rules import REFUND_CATEGORY, category_to_spend_type, is_refund_category
from backend.errors import CategoryError

IST = ZoneInfo("Asia/Kolkata")

MASTER_CATEGORIES = [
    "Groceries & Supermarket",
    "Dining Out & Food Delivery",
    "Utilities & Bills",
    "Fuel & Transportation",
    "Shopping & E-Commerce",
    "Healthcare & Pharmacy",
    "Rent & Housing",
    "Investments & Insurance",
    "Entertainment & Subscriptions",
    "Travel & Hotels",
    "Miscellaneous",
    "Unknown",
    REFUND_CATEGORY,
]

UNIDENTIFIED = "Unidentified"


def clean_description(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def all_dropdown_categories(conn: duckdb.DuckDBPyConnection) -> list[str]:
    custom = [
        r["category_name"]
        for r in fetch_dicts(
            conn, "SELECT category_name FROM custom_categories ORDER BY lower(category_name)"
        )
    ]
    seen = {c.lower() for c in MASTER_CATEGORIES}
    out = list(MASTER_CATEGORIES)
    for name in custom:
        if name.lower() not in seen:
            out.append(name)
            seen.add(name.lower())
    return out


def lookup_category(conn: duckdb.DuckDBPyConnection, cleaned_description: str) -> str:
    rows = fetch_dicts(
        conn,
        "SELECT assigned_category FROM category_cache WHERE merchant_pattern = ?",
        [cleaned_description],
    )
    return rows[0]["assigned_category"] if rows else UNIDENTIFIED


def add_custom_category(conn: duckdb.DuckDBPyConnection, name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    if not cleaned:
        raise CategoryError("Category name is required")
    if cleaned.lower() == UNIDENTIFIED.lower():
        raise CategoryError("Unidentified is reserved for pending review")
    existing = all_dropdown_categories(conn)
    if any(cleaned.lower() == e.lower() for e in existing):
        raise CategoryError(f"Category already exists: {cleaned}")
    conn.execute(
        "INSERT INTO custom_categories (category_name, created_at) VALUES (?, ?)",
        [cleaned, datetime.now(IST).replace(tzinfo=None)],
    )
    return cleaned


def _assert_assignable(conn: duckdb.DuckDBPyConnection, category: str) -> None:
    if category == UNIDENTIFIED:
        raise CategoryError("Cannot assign Unidentified; it is pending-review only")
    allowed = all_dropdown_categories(conn)
    if not any(category.lower() == a.lower() for a in allowed):
        raise CategoryError(f"Unknown category: {category}")


def save_mappings(conn: duckdb.DuckDBPyConnection, mappings: list[dict]) -> int:
    """Batch save. Each item: transaction_id + category (writes cache from row description)."""
    count = 0
    for item in mappings:
        txn_id = item["transaction_id"]
        category = item["category"]
        _assert_assignable(conn, category)
        rows = fetch_dicts(
            conn,
            "SELECT id, description FROM credit_card_transactions WHERE id = ?",
            [txn_id],
        )
        if not rows:
            continue
        desc = rows[0]["description"]
        spend_type = category_to_spend_type(category)
        conn.execute(
            "UPDATE credit_card_transactions SET category = ?, spend_type = ? WHERE id = ?",
            [category, spend_type, txn_id],
        )
        conn.execute(
            """
            INSERT INTO category_cache (merchant_pattern, assigned_category)
            VALUES (?, ?)
            ON CONFLICT (merchant_pattern) DO UPDATE SET assigned_category = excluded.assigned_category
            """,
            [desc, category],
        )
        count += 1
    return count


def recategorize(
    conn: duckdb.DuckDBPyConnection,
    merchant_pattern: str,
    category: str,
    *,
    apply_existing: bool = True,
) -> int:
    _assert_assignable(conn, category)
    pattern = clean_description(merchant_pattern)
    conn.execute(
        """
        INSERT INTO category_cache (merchant_pattern, assigned_category)
        VALUES (?, ?)
        ON CONFLICT (merchant_pattern) DO UPDATE SET assigned_category = excluded.assigned_category
        """,
        [pattern, category],
    )
    if not apply_existing:
        return 0
    spend_type = category_to_spend_type(category)
    conn.execute(
        "UPDATE credit_card_transactions SET category = ?, spend_type = ? WHERE description = ?",
        [category, spend_type, pattern],
    )
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM credit_card_transactions WHERE description = ? AND category = ?",
            [pattern, category],
        ).fetchone()[0]
    )


def unidentified_transactions(
    conn: duckdb.DuckDBPyConnection, card_id: str | None = None
) -> list[dict]:
    sql = """
        SELECT t.* FROM credit_card_transactions t
        WHERE t.category = ?
    """
    params: list = [UNIDENTIFIED]
    if card_id:
        sql += " AND t.card_id = ?"
        params.append(card_id)
    sql += " ORDER BY t.date DESC, t.id"
    return fetch_dicts(conn, sql, params)


def unidentified_count(conn: duckdb.DuckDBPyConnection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM credit_card_transactions WHERE category = ?",
        [UNIDENTIFIED],
    ).fetchone()[0]


def list_category_cache(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    return fetch_dicts(
        conn,
        """
        SELECT merchant_pattern, assigned_category
        FROM category_cache
        ORDER BY merchant_pattern
        """,
    )
