"""Axis Bank credit-card Excel (.xlsx / .xls). Transactions Summary sheet."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from backend.errors import ParseError
from backend.expense_rules import is_axis_merchant_refund, is_axis_non_expense_row
from backend.ingest import NormalizedTxn

USE_DATE = "date"
USE_DETAILS = "transaction details"
USE_AMOUNT = "amount (inr)"
USE_DEBIT_CREDIT = "debit/credit"

END_MARKER = "** end of statement **"
CARD_NUMBER_RE = re.compile(r"credit card number:\s*([^\n\r]+)", re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def _read_sheet(file_bytes: bytes) -> pd.DataFrame:
    bio = io.BytesIO(file_bytes)
    try:
        return pd.read_excel(bio, sheet_name=0, header=None, engine=None)
    except ImportError as exc:
        raise ParseError(
            "Axis Excel requires openpyxl for .xlsx (and xlrd for legacy .xls). "
            "Install project dependencies."
        ) from exc
    except ValueError as exc:
        raise ParseError(f"Could not read Axis statement Excel: {exc}") from exc


def _cell_str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _parse_amount(raw: str) -> float:
    cleaned = raw.replace("₹", "").replace(",", "").strip()
    if not cleaned:
        raise ParseError("Axis transaction row is missing amount")
    try:
        return abs(float(cleaned))
    except ValueError as exc:
        raise ParseError(f"Invalid Axis amount: {raw!r}") from exc


def _parse_date(raw: str) -> date:
    text = raw.strip()
    for fmt in ("%d %b '%y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Unrecognized Axis date: {raw!r}")


def _find_card_last4(df: pd.DataFrame) -> str | None:
    scan_rows = min(8, len(df))
    scan_cols = min(6, df.shape[1])
    for i in range(scan_rows):
        for j in range(scan_cols):
            text = _cell_str(df.iloc[i, j])
            if not text:
                continue
            match = CARD_NUMBER_RE.search(text)
            if match:
                digits = re.sub(r"\D", "", match.group(1))
                if len(digits) >= 4:
                    return digits[-4:]
    return None


def _find_header_row(df: pd.DataFrame) -> tuple[int, dict[str, int]]:
    for idx in range(len(df)):
        row = [_cell_str(df.iloc[idx, c]) for c in range(df.shape[1])]
        mapping: dict[str, int] = {}
        for col_idx, cell in enumerate(row):
            key = _norm(cell)
            if key and key not in mapping:
                mapping[key] = col_idx
        if USE_DATE in mapping and USE_DETAILS in mapping and USE_AMOUNT in mapping:
            if USE_DEBIT_CREDIT not in mapping:
                raise ParseError("Axis header missing Debit/Credit column")
            return idx, mapping
    raise ParseError("Axis transaction header not found")


def _scan_file(file_bytes: bytes) -> tuple[pd.DataFrame, int, dict[str, int], str | None]:
    df = _read_sheet(file_bytes)
    header_idx, colmap = _find_header_row(df)
    card_last4 = _find_card_last4(df)
    return df, header_idx, colmap, card_last4


def axis_statement_summary(file_bytes: bytes) -> dict:
    _, _, _, card_last4 = _scan_file(file_bytes)
    return {"card_last4": card_last4}


@dataclass
class AxisParseResult:
    rows: list[NormalizedTxn]
    note: str | None = None


def parse_axis_xls(file_bytes: bytes, *, last_4_digits: str | None = None) -> list[NormalizedTxn]:
    return parse_axis_xls_detail(file_bytes, last_4_digits=last_4_digits).rows


def parse_axis_xls_detail(
    file_bytes: bytes, *, last_4_digits: str | None = None
) -> AxisParseResult:
    df, header_idx, cols, card_last4 = _scan_file(file_bytes)
    want_last4 = re.sub(r"\D", "", last_4_digits or "")[-4:] if last_4_digits else None

    if want_last4 and card_last4 and want_last4 != card_last4:
        raise ParseError(
            f"Statement is for card ending {card_last4}, not registered card ending {want_last4}."
        )
    if want_last4 and not card_last4:
        raise ParseError("Could not find Axis Credit Card Number in statement.")

    out: list[NormalizedTxn] = []
    for idx in range(header_idx + 1, len(df)):
        date_raw = _cell_str(df.iloc[idx, cols[USE_DATE]])
        details = _cell_str(df.iloc[idx, cols[USE_DETAILS]])
        amount_raw = _cell_str(df.iloc[idx, cols[USE_AMOUNT]])
        sign_raw = _cell_str(df.iloc[idx, cols[USE_DEBIT_CREDIT]])

        if _norm(date_raw) == END_MARKER or END_MARKER in _norm(details):
            break
        if not date_raw or not details:
            continue
        if is_axis_non_expense_row(details, sign_raw):
            continue

        spend_type = "Refund" if is_axis_merchant_refund(details) else "One-Time"
        out.append(
            NormalizedTxn(
                date=_parse_date(date_raw),
                description=details,
                amount=_parse_amount(amount_raw),
                spend_type=spend_type,
            )
        )

    if want_last4 and not out:
        raise ParseError(f"No expense transactions for card ending {want_last4} in this statement.")
    return AxisParseResult(rows=out, note=None)
