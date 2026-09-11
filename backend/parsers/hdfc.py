"""HDFC credit-card CSV only (~|~ delimiter). Visa and UPI cards share this layout."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from backend.errors import ParseError
from backend.expense_rules import is_hdfc_merchant_refund, is_hdfc_non_expense_row
from backend.ingest import NormalizedTxn

DELIM = "~|~"
TXN_SECTION_TITLE = "domestic / international transactions"

USE_DATE = "date"
USE_DESCRIPTION = "description"
USE_AMOUNT = "amt"
USE_DEBIT_CREDIT = "debit /credit"

_SECTION_STOP_MARKERS = (
    "reward points summary",
    "rewards program points summary",
    "state account branch gstn",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _read_lines(file_bytes: bytes) -> list[str]:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return file_bytes.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1").splitlines()


def _split_row(line: str) -> list[str]:
    return line.split(DELIM)


def _parse_amount(raw: str) -> float:
    cleaned = raw.strip().replace(",", "")
    if not cleaned:
        raise ParseError("HDFC transaction row is missing amount")
    try:
        return abs(float(cleaned))
    except ValueError as exc:
        raise ParseError(f"Invalid HDFC amount: {raw!r}") from exc


def _parse_date(raw: str) -> date:
    text = raw.strip().split()[0]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Unrecognized HDFC date: {raw!r}")


def _card_last4_from_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.lower().startswith("card no:"):
        return None
    token = stripped.split(":", 1)[1]
    digits = re.sub(r"\D", "", token)
    return digits[-4:] if len(digits) >= 4 else None


def _find_card_last4(lines: list[str]) -> str | None:
    for line in lines:
        last4 = _card_last4_from_line(line)
        if last4:
            return last4
    return None


def _find_transaction_header(lines: list[str]) -> tuple[int, list[str]]:
    in_section = False
    for idx, line in enumerate(lines):
        if _norm(line) == TXN_SECTION_TITLE:
            in_section = True
            continue
        if not in_section or DELIM not in line:
            continue
        cells = _split_row(line)
        if cells and _norm(cells[0]) == "transaction type":
            return idx, cells
    raise ParseError("HDFC transaction header not found")


def _colmap(header: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, name in enumerate(header):
        key = _norm(name)
        if key and key not in mapping:
            mapping[key] = idx
    required = (USE_DATE, USE_DESCRIPTION, USE_AMOUNT, USE_DEBIT_CREDIT)
    missing = [c for c in required if c not in mapping]
    if missing:
        raise ParseError(f"HDFC header missing columns: {', '.join(missing)}")
    return mapping


def _is_section_stop(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if DELIM not in stripped:
        lower = stripped.lower()
        return any(lower.startswith(marker) for marker in _SECTION_STOP_MARKERS)
    return False


def _scan_file(file_bytes: bytes) -> tuple[list[str], int, list[str], str | None]:
    lines = _read_lines(file_bytes)
    header_idx, header = _find_transaction_header(lines)
    card_last4 = _find_card_last4(lines)
    return lines, header_idx, header, card_last4


def hdfc_statement_summary(file_bytes: bytes) -> dict:
    _, _, _, card_last4 = _scan_file(file_bytes)
    return {"card_last4": card_last4}


@dataclass
class HdfcParseResult:
    rows: list[NormalizedTxn]
    note: str | None = None


def parse_hdfc_csv(file_bytes: bytes, *, last_4_digits: str | None = None) -> list[NormalizedTxn]:
    return parse_hdfc_csv_detail(file_bytes, last_4_digits=last_4_digits).rows


def parse_hdfc_csv_detail(
    file_bytes: bytes, *, last_4_digits: str | None = None
) -> HdfcParseResult:
    lines, header_idx, header, card_last4 = _scan_file(file_bytes)
    cols = _colmap(header)
    want_last4 = re.sub(r"\D", "", last_4_digits or "")[-4:] if last_4_digits else None
    note: str | None = None

    if want_last4 and card_last4 and want_last4 != card_last4:
        raise ParseError(
            f"Statement is for card ending {card_last4}, not registered card ending {want_last4}."
        )
    if want_last4 and not card_last4:
        raise ParseError("Could not find HDFC Card No line in statement.")

    out: list[NormalizedTxn] = []
    for line in lines[header_idx + 1 :]:
        if _is_section_stop(line):
            break
        if DELIM not in line:
            continue
        row = _split_row(line)
        try:
            date_raw = row[cols[USE_DATE]]
            details = row[cols[USE_DESCRIPTION]]
            amount_raw = row[cols[USE_AMOUNT]]
            sign_raw = row[cols[USE_DEBIT_CREDIT]] if cols[USE_DEBIT_CREDIT] < len(row) else ""
        except IndexError as exc:
            raise ParseError("HDFC row is shorter than the header") from exc
        if not date_raw.strip() or not details.strip():
            continue
        if is_hdfc_non_expense_row(details, sign_raw):
            continue
        spend_type = "Refund" if is_hdfc_merchant_refund(details) else "One-Time"
        out.append(
            NormalizedTxn(
                date=_parse_date(date_raw),
                description=details.strip(),
                amount=_parse_amount(amount_raw),
                spend_type=spend_type,
            )
        )

    if want_last4 and not out:
        raise ParseError(f"No expense transactions for card ending {want_last4} in this statement.")
    return HdfcParseResult(rows=out, note=note)
