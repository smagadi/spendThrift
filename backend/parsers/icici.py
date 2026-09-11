"""ICICI credit-card CSV only. Do not reuse for HDFC/Axis."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import IO

from backend.errors import ParseError
from backend.expense_rules import is_icici_merchant_refund, is_icici_non_expense_row
from backend.ingest import NormalizedTxn

IGNORED_COLUMNS = {
    "customer name",
    "customer name:",
    "address",
    "address:",
    "accountno",
    "accountno:",
    "reward point header",
    "intl.amount",
    "there",
    "sr.no.",
    "sr.no",
}

USE_DATE = "date"
USE_DETAILS = "transaction details"
USE_AMOUNT = "amount(in rs)"
USE_SIGN = "billingamountsign"

# Masked card line only (must include X/*), not raw Accountno digits.
CARD_HEADER_RE = re.compile(r"^[0-9Xx*]{12,19}$")


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower()).replace(":", "")


def _open_text(file_bytes: bytes) -> IO[str]:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return io.StringIO(file_bytes.decode(enc))
        except UnicodeDecodeError:
            continue
    return io.StringIO(file_bytes.decode("latin-1"))


def _read_rows(file_bytes: bytes) -> list[list[str]]:
    reader = csv.reader(_open_text(file_bytes))
    return [row for row in reader if row and not all(not cell.strip() for cell in row)]


def _is_card_section(row: list[str]) -> str | None:
    if not row:
        return None
    token = row[0].strip().strip('"')
    compact = token.replace(" ", "")
    if not CARD_HEADER_RE.match(compact):
        return None
    if "X" not in compact.upper() and "*" not in compact:
        return None
    digits = re.sub(r"\D", "", token)
    if len(digits) >= 4:
        return digits[-4:]
    return None


def _parse_account_last4(row: list[str]) -> str | None:
    if len(row) < 2 or _norm(row[0]) != "accountno":
        return None
    digits = re.sub(r"\D", "", row[1])
    return digits[-4:] if len(digits) >= 4 else None


def _parse_amount(raw: str) -> float:
    cleaned = raw.strip().replace(",", "")
    if not cleaned:
        raise ParseError("Empty amount")
    return abs(float(cleaned))


def _parse_date(raw: str):
    text = raw.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"Unrecognized ICICI date: {raw}")


def _colmap(header: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, col in enumerate(header):
        key = _norm(col)
        if key in IGNORED_COLUMNS:
            continue
        mapping[key] = i
    needed = {
        USE_DATE: mapping.get(USE_DATE),
        USE_DETAILS: mapping.get(USE_DETAILS),
        USE_AMOUNT: mapping.get(USE_AMOUNT),
        USE_SIGN: mapping.get(USE_SIGN),
    }
    missing = [k for k, v in needed.items() if v is None]
    if missing:
        raise ParseError(f"ICICI CSV missing columns: {missing}")
    return needed  # type: ignore[return-value]


def _find_transaction_header(rows: list[list[str]]) -> tuple[int, list[str]]:
    for i, row in enumerate(rows):
        cells = [_norm(cell) for cell in row]
        if "date" in cells and "transaction details" in cells:
            return i, row
    raise ParseError("ICICI CSV has no Transaction Details header")


def _scan_file(file_bytes: bytes) -> tuple[list[list[str]], int, list[str], str | None, dict[str, int]]:
    rows = _read_rows(file_bytes)
    header_idx, header = _find_transaction_header(rows)
    account_last4: str | None = None
    for row in rows[:header_idx]:
        acct = _parse_account_last4(row)
        if acct:
            account_last4 = acct
    cols = _colmap(header)
    sections: list[str] = []
    counts: dict[str, int] = {}
    current: str | None = None
    for row in rows[header_idx + 1 :]:
        section = _is_card_section(row)
        if section:
            current = section
            if section not in counts:
                sections.append(section)
                counts[section] = 0
            continue
        if not current:
            continue
        try:
            date_raw = row[cols[USE_DATE]]
            details = row[cols[USE_DETAILS]]
            sign_raw = row[cols[USE_SIGN]] if cols[USE_SIGN] < len(row) else ""
            if row[cols[USE_DATE]].strip() and row[cols[USE_DETAILS]].strip():
                if not is_icici_non_expense_row(details, sign_raw):
                    counts[current] = counts.get(current, 0) + 1
        except IndexError:
            continue
    return rows, header_idx, sections, account_last4, counts


def discover_icici_sections(file_bytes: bytes) -> list[str]:
    _, _, sections, _, _ = _scan_file(file_bytes)
    return sections


def icici_statement_summary(file_bytes: bytes) -> dict:
    _, _, sections, account_last4, counts = _scan_file(file_bytes)
    primary = max(sections, key=lambda s: counts.get(s, 0)) if sections else None
    return {
        "account_last4": account_last4,
        "sections": sections,
        "primary_last4": primary,
        "row_counts": counts,
    }


def _primary_section(sections: list[str], counts: dict[str, int]) -> str:
    if not sections:
        raise ParseError("No masked card line found under Transaction Details")
    return max(sections, key=lambda s: counts.get(s, 0))


def _resolve_target_last4(
    want_last4: str,
    sections: list[str],
    counts: dict[str, int],
    account_last4: str | None,
) -> tuple[str, str | None]:
    """One card per ICICI statement file: use the spend section with the most rows."""
    primary = _primary_section(sections, counts)
    if want_last4 in sections:
        return want_last4, None
    note = f"Using spend section ending {primary} (registered card ending {want_last4}"
    if account_last4 and want_last4 == account_last4:
        note += "; matches billing Accountno"
    note += ")."
    return primary, note


@dataclass
class IciciParseResult:
    rows: list[NormalizedTxn]
    note: str | None = None


def parse_icici_csv(file_bytes: bytes, *, last_4_digits: str | None = None) -> list[NormalizedTxn]:
    return parse_icici_csv_detail(file_bytes, last_4_digits=last_4_digits).rows


def parse_icici_csv_detail(
    file_bytes: bytes, *, last_4_digits: str | None = None
) -> IciciParseResult:
    rows, header_idx, sections, account_last4, counts = _scan_file(file_bytes)
    _, header = _find_transaction_header(rows)
    cols = _colmap(header)
    want_last4 = re.sub(r"\D", "", last_4_digits or "")[-4:] if last_4_digits else None
    note: str | None = None
    target_last4: str | None = None
    if want_last4:
        target_last4, note = _resolve_target_last4(want_last4, sections, counts, account_last4)

    current_last4: str | None = None
    out: list[NormalizedTxn] = []

    for row in rows[header_idx + 1 :]:
        section = _is_card_section(row)
        if section:
            current_last4 = section
            continue
        if target_last4 and current_last4 != target_last4:
            continue
        try:
            date_raw = row[cols[USE_DATE]]
            details = row[cols[USE_DETAILS]]
            amount_raw = row[cols[USE_AMOUNT]]
            sign_raw = row[cols[USE_SIGN]] if cols[USE_SIGN] < len(row) else ""
        except IndexError as exc:
            raise ParseError("ICICI row is shorter than the header") from exc
        if not date_raw.strip() or not details.strip():
            continue
        if is_icici_non_expense_row(details, sign_raw):
            continue
        spend_type = "Refund" if is_icici_merchant_refund(details) else "One-Time"
        out.append(
            NormalizedTxn(
                date=_parse_date(date_raw),
                description=details,
                amount=_parse_amount(amount_raw),
                spend_type=spend_type,
            )
        )

    if want_last4 and not out:
        primary = _primary_section(sections, counts) if sections else "?"
        raise ParseError(
            f"No transactions for card ending {target_last4 or want_last4}. "
            f"Statement spend is under masked line ending {primary}."
        )
    return IciciParseResult(rows=out, note=note)
