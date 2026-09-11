"""Remove payment rows and sync Refund flags (Refund rows stay in DB but never count as spend)."""

from __future__ import annotations

import duckdb


def ensure_expense_ledger(conn: duckdb.DuckDBPyConnection) -> None:
    """Fix refund rows in DB before dashboard analytics."""
    repair_icici_merchant_refunds(conn)
    sync_refund_spend_types(conn)


def sync_refund_spend_types(conn: duckdb.DuckDBPyConnection) -> int:
    """Ensure category Refund rows have spend_type Refund so analytics exclude them."""
    before = conn.execute(
        """
        SELECT COUNT(*) FROM credit_card_transactions
        WHERE lower(trim(category)) = 'refund' AND spend_type <> 'Refund'
        """
    ).fetchone()[0]
    conn.execute(
        """
        UPDATE credit_card_transactions
        SET spend_type = 'Refund'
        WHERE lower(trim(category)) = 'refund' AND spend_type <> 'Refund'
        """
    )
    return int(before)


def repair_icici_merchant_refunds(conn: duckdb.DuckDBPyConnection) -> int:
    """Promote refund-like merchant lines still marked Unidentified."""
    before = conn.execute(
        """
        SELECT COUNT(*) FROM credit_card_transactions
        WHERE category = 'Unidentified'
          AND (
            description ILIKE '% REFUND%'
            OR description ILIKE '% REFUND'
          )
        """
    ).fetchone()[0]
    conn.execute(
        """
        UPDATE credit_card_transactions
        SET category = 'Refund', spend_type = 'Refund'
        WHERE category = 'Unidentified'
          AND (
            description ILIKE '% REFUND%'
            OR description ILIKE '% REFUND'
          )
        """
    )
    return int(before)


def purge_payment_rows(conn: duckdb.DuckDBPyConnection) -> int:
    before = conn.execute("SELECT COUNT(*) FROM credit_card_transactions").fetchone()[0]
    conn.execute(
        """
        DELETE FROM credit_card_transactions
        WHERE spend_type IN ('Payment', 'Credit', 'Rewards')
           OR description ILIKE '%PAYMENT RECEIVED%'
           OR description ILIKE '%INFINITY PAYMENT%'
        """
    )
    after = conn.execute("SELECT COUNT(*) FROM credit_card_transactions").fetchone()[0]
    return int(before - after)


def purge_non_expense_transactions(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    refunds_repaired = repair_icici_merchant_refunds(conn)
    refunds_synced = sync_refund_spend_types(conn)
    payments_removed = purge_payment_rows(conn)
    return {
        "payments_removed": payments_removed,
        "refunds_synced": refunds_synced,
        "refunds_repaired": refunds_repaired,
    }
