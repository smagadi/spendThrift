"""Merchant display keys for analytics rollups (raw descriptions stay on rows)."""

from __future__ import annotations

import re

import duckdb

_US_SUFFIX = re.compile(r"\s+US\*?\s*$", re.IGNORECASE)

# Trailing location / statement noise tokens (matched on uppercased words).
_TRAILING_STOPWORDS = frozenset(
    {
        "IN",
        "INDIA",
        "BANGALORE",
        "BENGALURU",
        "MUMBAI",
        "DELHI",
        "GURGAON",
        "HYDERABAD",
        "CHENNAI",
        "KOLKATA",
        "PUNE",
        "MYSORE",
        "KODAGU",
        "SAMBALPUR",
        "COORG",
    }
)

_KEEP_TRAILING = frozenset({"AND", "INC", "LTD", "PVT", "THE", "LLP"})


def _should_drop_trailing_token(token: str) -> bool:
    if token in _TRAILING_STOPWORDS:
        return True
    if len(token) <= 2:
        return True
    if len(token) == 3 and token.isalpha() and token not in _KEEP_TRAILING:
        return True
    return False


def _clean_description(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def normalize_merchant(raw: str) -> str:
    """Canonical merchant label for grouping across banks/cards."""
    text = _clean_description(raw)
    text = _US_SUFFIX.sub("", text)
    text = text.upper()
    tokens = text.split()
    while tokens:
        last = tokens[-1]
        if _should_drop_trailing_token(last):
            tokens.pop()
        else:
            break
    if not tokens:
        return _clean_description(raw).upper()
    return " ".join(tokens)


def register_merchant_functions(conn) -> None:
    """Bind normalize_merchant for analytics SQL (once per connection)."""
    try:
        conn.remove_function("normalize_merchant")
    except Exception:
        pass
    try:
        conn.create_function("normalize_merchant", normalize_merchant, return_type="VARCHAR")
    except (duckdb.CatalogException, duckdb.NotImplementedException) as exc:
        msg = str(exc).lower()
        if "already exists" not in msg and "already created" not in msg:
            raise
