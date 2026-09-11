from __future__ import annotations

from datetime import date

import duckdb

from backend.database import fetch_dicts


def search_transactions(
    conn: duckdb.DuckDBPyConnection,
    *,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    cardholder: str | None = None,
    card_id: str | None = None,
    year: int | None = None,
) -> list[dict]:
    clauses = ["1=1"]
    params: list = []
    if keyword:
        clauses.append("t.description ILIKE ?")
        params.append(f"%{keyword}%")
    if date_from:
        clauses.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("t.date <= ?")
        params.append(date_to)
    if amount_min is not None:
        clauses.append("t.amount >= ?")
        params.append(amount_min)
    if amount_max is not None:
        clauses.append("t.amount <= ?")
        params.append(amount_max)
    if cardholder:
        clauses.append("c.cardholder = ?")
        params.append(cardholder)
    if card_id:
        clauses.append("t.card_id = ?")
        params.append(card_id)
    if year is not None:
        clauses.append("year(t.date) = ?")
        params.append(year)
    where = " AND ".join(clauses)
    return fetch_dicts(
        conn,
        f"""
        SELECT t.id, t.date, t.description, t.amount, t.category, t.spend_type,
               t.source_filename, c.card_name, c.cardholder, t.card_id
        FROM credit_card_transactions t
        JOIN credit_cards c ON c.card_id = t.card_id
        WHERE {where}
        ORDER BY t.date DESC, t.amount DESC
        """,
        params,
    )
