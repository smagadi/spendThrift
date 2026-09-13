"""Python function facade for Streamlit. No HTTP. No SQL in callers."""

from __future__ import annotations

from pathlib import Path

import duckdb

from backend import advisory, analytics, backup, cards, categorizer, cleanup, ingest, search
from backend.cards import get_card
from backend.database import connect
from backend.errors import ParseError
from backend.ingest import NormalizedTxn
from backend.parsers.axis import parse_axis_xls_detail
from backend.parsers.hdfc import parse_hdfc_csv_detail
from backend.parsers.icici import parse_icici_csv_detail


class SpendAPI:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path
        self.conn: duckdb.DuckDBPyConnection = connect(db_path)

    def close(self) -> None:
        self.conn.close()

    def create_card(self, **kwargs) -> dict:
        return cards.create_card(self.conn, **kwargs)

    def list_cards(self, active_only: bool = False) -> list[dict]:
        return cards.list_cards(self.conn, active_only=active_only)

    def soft_delete_card(self, card_id: str) -> dict:
        return cards.soft_delete_card(self.conn, card_id)

    def reactivate_card(self, card_id: str) -> dict:
        return cards.reactivate_card(self.conn, card_id)

    def ingest_normalized(
        self,
        card_id: str,
        filename: str,
        file_bytes: bytes,
        rows: list[NormalizedTxn],
        statement_period: str | None = None,
    ):
        return ingest.ingest_normalized(
            self.conn,
            card_id=card_id,
            filename=filename,
            file_bytes=file_bytes,
            rows=rows,
            statement_period=statement_period,
        )

    def ingest_icici_csv(
        self,
        card_id: str,
        filename: str,
        file_bytes: bytes,
        statement_period: str | None = None,
    ):
        card = get_card(self.conn, card_id)
        if card["bank_name"].upper() != "ICICI":
            raise ParseError("ingest_icici_csv is only for ICICI cards")
        parsed = parse_icici_csv_detail(file_bytes, last_4_digits=card["last_4_digits"])
        result = self.ingest_normalized(
            card_id, filename, file_bytes, parsed.rows, statement_period=statement_period
        )
        if parsed.note:
            result.message = f"{result.message}. {parsed.note}"
        return result

    def ingest_hdfc_csv(
        self,
        card_id: str,
        filename: str,
        file_bytes: bytes,
        statement_period: str | None = None,
    ):
        card = get_card(self.conn, card_id)
        if card["bank_name"].upper() != "HDFC":
            raise ParseError("ingest_hdfc_csv is only for HDFC cards")
        parsed = parse_hdfc_csv_detail(file_bytes, last_4_digits=card["last_4_digits"])
        result = self.ingest_normalized(
            card_id, filename, file_bytes, parsed.rows, statement_period=statement_period
        )
        if parsed.note:
            result.message = f"{result.message}. {parsed.note}"
        return result

    def ingest_axis_xls(
        self,
        card_id: str,
        filename: str,
        file_bytes: bytes,
        statement_period: str | None = None,
    ):
        card = get_card(self.conn, card_id)
        if card["bank_name"].upper() != "AXIS":
            raise ParseError("ingest_axis_xls is only for Axis cards")
        parsed = parse_axis_xls_detail(file_bytes, last_4_digits=card["last_4_digits"])
        result = self.ingest_normalized(
            card_id, filename, file_bytes, parsed.rows, statement_period=statement_period
        )
        if parsed.note:
            result.message = f"{result.message}. {parsed.note}"
        return result

    def unidentified_transactions(self, card_id: str | None = None) -> list[dict]:
        return categorizer.unidentified_transactions(self.conn, card_id)

    def unidentified_count(self) -> int:
        return categorizer.unidentified_count(self.conn)

    def list_category_cache(self) -> list[dict]:
        return categorizer.list_category_cache(self.conn)

    def dropdown_categories(self) -> list[str]:
        return categorizer.all_dropdown_categories(self.conn)

    def add_custom_category(self, name: str) -> str:
        return categorizer.add_custom_category(self.conn, name)

    def save_mappings(self, mappings: list[dict]) -> int:
        return categorizer.save_mappings(self.conn, mappings)

    def recategorize(self, merchant_pattern: str, category: str, apply_existing: bool = True) -> int:
        return categorizer.recategorize(
            self.conn, merchant_pattern, category, apply_existing=apply_existing
        )

    def available_years(self) -> list[int]:
        from datetime import date

        years = analytics.available_years(self.conn)
        return years or [date.today().year]

    def dashboard_payload(self, year: int, cardholder: str | None = None, card_id: str | None = None) -> dict:
        cleanup.ensure_expense_ledger(self.conn)
        return {
            "ytd_total": analytics.ytd_total(self.conn, year, cardholder, card_id),
            "top_card": analytics.top_spending_card(self.conn, year, cardholder, card_id),
            "top_category": analytics.top_spending_category(self.conn, year, cardholder, card_id),
            "yearly_by_card": analytics.yearly_by_card(self.conn, year, cardholder, card_id),
            "yearly_by_user": analytics.yearly_by_user(self.conn, year, cardholder, card_id),
            "mom_aggregate": analytics.mom_aggregate(self.conn, year, cardholder, card_id),
            "mom_by_card": analytics.mom_by_card(self.conn, year, cardholder, card_id),
            "mom_by_user": analytics.mom_by_user(self.conn, year, cardholder, card_id),
            "quarterly": analytics.quarterly_totals(self.conn, year, cardholder, card_id),
            "top_transactions": analytics.top_transactions(self.conn, year, cardholder, card_id),
            "top_merchants": analytics.top_merchants(self.conn, year, cardholder, card_id),
            "category_breakdown": analytics.category_breakdown(self.conn, year, cardholder, card_id),
            "category_by_card": analytics.category_by_card(self.conn, year, cardholder, card_id),
            "category_by_user": analytics.category_by_user(self.conn, year, cardholder, card_id),
            "recurring": analytics.recurring_merchants(self.conn, year, cardholder, card_id),
            "advice": advisory.generate_advice(self.conn, year, cardholder, card_id),
            "unidentified_count": categorizer.unidentified_count(self.conn),
            "years": analytics.available_years(self.conn),
        }

    def search_transactions(self, **kwargs) -> list[dict]:
        return search.search_transactions(self.conn, **kwargs)

    def backup_database(self, destination: str | Path) -> str:
        self.conn.execute("CHECKPOINT")
        return backup.backup_database(destination, db_path=self.db_path)

    def purge_non_expense_transactions(self) -> dict[str, int]:
        return cleanup.purge_non_expense_transactions(self.conn)

    def sync_refund_spend_types(self) -> int:
        return cleanup.sync_refund_spend_types(self.conn)


NormalizedTxn = NormalizedTxn
