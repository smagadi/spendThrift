from __future__ import annotations

import re

import duckdb

from backend.database import fetch_dicts
from backend.errors import CardExistsError, CardNotFoundError

ALLOWED_BANKS = ("HDFC", "ICICI", "AXIS")


def make_card_id(bank_name: str, last_4_digits: str, cardholder: str) -> str:
    bank = bank_name.strip().upper()
    digits = re.sub(r"\D", "", last_4_digits)
    if len(digits) < 4:
        raise ValueError("last_4_digits must contain at least 4 digits")
    last4 = digits[-4:]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", cardholder.strip().upper()).strip("_")
    if not slug:
        raise ValueError("cardholder is required")
    return f"{bank}_{last4}_{slug}"


def create_card(
    conn: duckdb.DuckDBPyConnection,
    *,
    bank_name: str,
    card_name: str,
    last_4_digits: str,
    cardholder: str,
) -> dict:
    bank = bank_name.strip().upper()
    if bank not in ALLOWED_BANKS:
        raise ValueError(f"bank_name must be one of {ALLOWED_BANKS}")
    last4 = re.sub(r"\D", "", last_4_digits)[-4:]
    holder = cardholder.strip()
    name = card_name.strip()
    if not name or not holder:
        raise ValueError("card_name and cardholder are required")
    card_id = make_card_id(bank, last4, holder)
    try:
        conn.execute(
            """
            INSERT INTO credit_cards
                (card_id, bank_name, card_name, last_4_digits, cardholder, is_active)
            VALUES (?, ?, ?, ?, ?, TRUE)
            """,
            [card_id, bank, name, last4, holder],
        )
    except duckdb.ConstraintException as exc:
        raise CardExistsError(
            "A card with this bank, last 4 digits, and cardholder already exists"
        ) from exc
    return get_card(conn, card_id)


def get_card(conn: duckdb.DuckDBPyConnection, card_id: str) -> dict:
    rows = fetch_dicts(conn, "SELECT * FROM credit_cards WHERE card_id = ?", [card_id])
    if not rows:
        raise CardNotFoundError(f"Unknown card_id: {card_id}")
    return rows[0]


def list_cards(conn: duckdb.DuckDBPyConnection, *, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM credit_cards"
    if active_only:
        sql += " WHERE is_active = TRUE"
    sql += " ORDER BY cardholder, bank_name, card_name"
    return fetch_dicts(conn, sql)


def set_card_active(conn: duckdb.DuckDBPyConnection, card_id: str, is_active: bool) -> dict:
    get_card(conn, card_id)
    conn.execute("UPDATE credit_cards SET is_active = ? WHERE card_id = ?", [is_active, card_id])
    return get_card(conn, card_id)


def soft_delete_card(conn: duckdb.DuckDBPyConnection, card_id: str) -> dict:
    return set_card_active(conn, card_id, False)


def reactivate_card(conn: duckdb.DuckDBPyConnection, card_id: str) -> dict:
    return set_card_active(conn, card_id, True)
