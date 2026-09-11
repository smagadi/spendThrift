from __future__ import annotations

import duckdb

from backend.database import fetch_dicts
from backend.expense_rules import expense_filter_bare, expense_filter_sql


def _where(
    year: int | None,
    cardholder: str | None,
    card_id: str | None,
) -> tuple[str, list]:
    clauses = [expense_filter_sql("t")]
    params: list = []
    if year is not None:
        clauses.append("year(t.date) = ?")
        params.append(year)
    if cardholder:
        clauses.append("c.cardholder = ?")
        params.append(cardholder)
    if card_id:
        clauses.append("t.card_id = ?")
        params.append(card_id)
    return " AND ".join(clauses), params


def _join_sql(extra: str, year, cardholder, card_id) -> tuple[str, list]:
    where, params = _where(year, cardholder, card_id)
    sql = f"""
        FROM credit_card_transactions t
        JOIN credit_cards c ON c.card_id = t.card_id
        WHERE {where}
        {extra}
    """
    return sql, params


def ytd_total(conn, year: int, cardholder=None, card_id=None) -> float:
    sql, params = _join_sql("", year, cardholder, card_id)
    row = conn.execute(f"SELECT COALESCE(SUM(t.amount), 0) {sql}", params).fetchone()
    return float(row[0])


def yearly_by_card(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY t.card_id, c.card_name, c.cardholder ORDER BY total DESC",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"""
        SELECT t.card_id, c.card_name, c.cardholder, SUM(t.amount) AS total
        {sql}
        """,
        params,
    )


def yearly_by_user(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY c.cardholder ORDER BY total DESC",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT c.cardholder, SUM(t.amount) AS total {sql}",
        params,
    )


def top_spending_card(conn, year: int, cardholder=None, card_id=None) -> dict | None:
    rows = yearly_by_card(conn, year, cardholder, card_id)
    return rows[0] if rows else None


def category_breakdown(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY t.category ORDER BY total DESC",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT t.category, SUM(t.amount) AS total {sql}",
        params,
    )


def top_spending_category(conn, year: int, cardholder=None, card_id=None) -> dict | None:
    rows = category_breakdown(conn, year, cardholder, card_id)
    return rows[0] if rows else None


def mom_aggregate(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY month(t.date) ORDER BY month",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT month(t.date) AS month, SUM(t.amount) AS total {sql}",
        params,
    )


def mom_by_card(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY t.card_id, c.card_name, c.cardholder, month(t.date) ORDER BY month, t.card_id",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"""
        SELECT t.card_id, c.card_name, c.cardholder, month(t.date) AS month, SUM(t.amount) AS total
        {sql}
        """,
        params,
    )


def mom_by_user(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY c.cardholder, month(t.date) ORDER BY month, c.cardholder",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT c.cardholder, month(t.date) AS month, SUM(t.amount) AS total {sql}",
        params,
    )


def quarterly_totals(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY quarter(t.date) ORDER BY quarter",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT quarter(t.date) AS quarter, SUM(t.amount) AS total {sql}",
        params,
    )


def top_transactions(conn, year: int, cardholder=None, card_id=None, limit: int = 10) -> list[dict]:
    where, params = _where(year, cardholder, card_id)
    params = [*params, limit]
    return fetch_dicts(
        conn,
        f"""
        SELECT t.date, t.description, t.amount, t.category, c.card_name, c.cardholder, t.card_id
        FROM credit_card_transactions t
        JOIN credit_cards c ON c.card_id = t.card_id
        WHERE {where}
        ORDER BY t.amount DESC, t.date DESC
        LIMIT ?
        """,
        params,
    )


def top_merchants(conn, year: int, cardholder=None, card_id=None, limit: int = 5) -> list[dict]:
    sql, params = _join_sql(
        """
        GROUP BY normalize_merchant(t.description)
        ORDER BY total DESC
        LIMIT ?
        """,
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"""
        SELECT normalize_merchant(t.description) AS merchant,
               SUM(t.amount) AS total,
               COUNT(*) AS txn_count
        {sql}
        """,
        [*params, limit],
    )


def category_by_card(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY t.card_id, c.card_name, t.category ORDER BY c.card_name, total DESC",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT t.card_id, c.card_name, t.category, SUM(t.amount) AS total {sql}",
        params,
    )


def category_by_user(conn, year: int, cardholder=None, card_id=None) -> list[dict]:
    sql, params = _join_sql(
        "GROUP BY c.cardholder, t.category ORDER BY c.cardholder, total DESC",
        year,
        cardholder,
        card_id,
    )
    return fetch_dicts(
        conn,
        f"SELECT c.cardholder, t.category, SUM(t.amount) AS total {sql}",
        params,
    )


def recurring_merchants(conn, year: int | None = None, cardholder=None, card_id=None) -> list[dict]:
    where, params = _where(year, cardholder, card_id)
    return fetch_dicts(
        conn,
        f"""
        SELECT
            normalize_merchant(t.description) AS merchant,
            SUM(t.amount) AS total_spent,
            COUNT(*) AS txn_count,
            COUNT(DISTINCT month(t.date)) AS month_count,
            MIN(t.amount) AS min_amount,
            MAX(t.amount) AS max_amount,
            MAX(t.date) AS last_charged,
            any_value(t.category) AS category
        FROM credit_card_transactions t
        JOIN credit_cards c ON c.card_id = t.card_id
        WHERE {where}
        GROUP BY normalize_merchant(t.description)
        HAVING COUNT(*) >= 2 AND COUNT(DISTINCT month(t.date)) >= 2
        ORDER BY total_spent DESC, merchant
        """,
        params,
    )


def available_years(conn: duckdb.DuckDBPyConnection) -> list[int]:
    rows = fetch_dicts(
        conn,
        f"""
        SELECT DISTINCT year(date) AS year FROM credit_card_transactions
        WHERE {expense_filter_bare()}
        ORDER BY year DESC
        """,
    )
    return [int(r["year"]) for r in rows]
