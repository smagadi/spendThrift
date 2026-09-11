from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.cards import get_card
from backend.categorizer import UNIDENTIFIED, clean_description, lookup_category
from backend.expense_rules import REFUND_CATEGORY, category_to_spend_type, is_refund_category
from backend.database import fetch_dicts
from backend.errors import DuplicateStatementError, InactiveCardError

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class NormalizedTxn:
    date: date
    description: str
    amount: float
    spend_type: str = "One-Time"


@dataclass
class IngestResult:
    status: str
    upload_id: str | None
    row_count: int
    message: str


def file_fingerprint(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def ingest_normalized(
    conn: duckdb.DuckDBPyConnection,
    *,
    card_id: str,
    filename: str,
    file_bytes: bytes,
    rows: list[NormalizedTxn],
    statement_period: str | None = None,
) -> IngestResult:
    card = get_card(conn, card_id)
    if not card["is_active"]:
        raise InactiveCardError("Reactivate the card before uploading statements")

    fingerprint = file_fingerprint(file_bytes)
    name = filename.strip()
    now = datetime.now(IST).replace(tzinfo=None)

    same_hash = fetch_dicts(
        conn,
        """
        SELECT upload_id, uploaded_at, original_filename, status
        FROM statement_uploads
        WHERE card_id = ? AND file_fingerprint = ? AND status IN ('loaded', 'replaced')
        ORDER BY uploaded_at DESC
        """,
        [card_id, fingerprint],
    )
    if same_hash:
        prior = same_hash[0]["uploaded_at"]
        raise DuplicateStatementError(
            f"This document was already ingested on {prior}",
            uploaded_at=prior,
        )

    same_name = fetch_dicts(
        conn,
        """
        SELECT upload_id FROM statement_uploads
        WHERE card_id = ? AND original_filename = ? AND status IN ('loaded', 'replaced')
        """,
        [card_id, name],
    )
    replaced = bool(same_name)
    if replaced:
        for rec in same_name:
            uid = rec["upload_id"]
            conn.execute("DELETE FROM credit_card_transactions WHERE upload_id = ?", [uid])
            conn.execute("DELETE FROM statement_uploads WHERE upload_id = ?", [uid])

    upload_id = str(uuid.uuid4())
    status = "replaced" if replaced else "loaded"
    conn.execute(
        """
        INSERT INTO statement_uploads (
            upload_id, card_id, original_filename, file_fingerprint,
            uploaded_at, row_count, status, statement_period
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [upload_id, card_id, name, fingerprint, now, len(rows), status, statement_period],
    )

    inserted = 0
    for row in rows:
        desc = clean_description(row.description)
        category = lookup_category(conn, desc)
        spend_type = row.spend_type
        if is_refund_category(category) or spend_type == "Refund":
            category = REFUND_CATEGORY
            spend_type = "Refund"
        elif category != UNIDENTIFIED:
            spend_type = category_to_spend_type(category)
        conn.execute(
            """
            INSERT INTO credit_card_transactions (
                id, card_id, upload_id, source_filename, date, description,
                amount, category, spend_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                card_id,
                upload_id,
                name,
                row.date,
                desc,
                abs(float(row.amount)),
                category,
                spend_type,
            ],
        )
        inserted += 1

    if inserted != len(rows):
        conn.execute(
            "UPDATE statement_uploads SET row_count = ? WHERE upload_id = ?",
            [inserted, upload_id],
        )
    return IngestResult(
        status=status,
        upload_id=upload_id,
        row_count=inserted,
        message="Replaced prior file" if replaced else "Loaded",
    )
