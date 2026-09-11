"""Which rows count as household spend vs payment/refund/credit."""

from __future__ import annotations

REFUND_CATEGORY = "Refund"

_REFUND_DESC_PATTERNS = (
    "description ILIKE '% REFUND%'",
    "description ILIKE '% REFUND'",
)


def _refund_description_sql(alias: str) -> str:
    checks = " OR ".join(f"{alias}.{p}" for p in _REFUND_DESC_PATTERNS)
    return f"NOT ({checks})"


def expense_filter_sql(alias: str = "t") -> str:
    """SQL predicate: row counts toward dashboard spend."""
    refund_desc = _refund_description_sql(alias)
    return f"""
trim({alias}.spend_type) NOT IN ('Payment', 'Refund', 'Credit', 'Rewards')
AND lower(trim({alias}.category)) <> 'refund'
AND {refund_desc}
""".strip()


def expense_filter_bare() -> str:
    return expense_filter_sql("credit_card_transactions").replace(
        "credit_card_transactions.", ""
    )


EXPENSE_FILTER_SQL = expense_filter_sql("t")
EXPENSE_FILTER_BARE = expense_filter_bare()


def is_refund_category(category: str | None) -> bool:
    return (category or "").strip().lower() == "refund"


def category_to_spend_type(category: str) -> str:
    if is_refund_category(category):
        return "Refund"
    return "One-Time"


def is_icici_non_expense_row(description: str, billing_sign: str) -> bool:
    """Skip ICICI card payments and billing credits (CR). Not merchant spend."""
    if billing_sign.strip().upper() == "CR":
        return True
    upper = description.upper()
    return "PAYMENT RECEIVED" in upper or "INFINITY PAYMENT" in upper


def is_icici_merchant_refund(description: str) -> bool:
    """ICICI merchant refunds that post without BillingAmountSign=CR."""
    upper = description.upper()
    return " REFUND" in upper or upper.endswith(" REFUND")


def is_hdfc_non_expense_row(description: str, debit_credit: str) -> bool:
    """Skip HDFC card payments and billing credits (Cr). Not merchant spend."""
    if debit_credit.strip().lower() in ("cr", "credit"):
        return True
    upper = description.upper()
    return "CREDIT CARD PAYMENT" in upper or "PAYMENT RECEIVED" in upper


def is_hdfc_merchant_refund(description: str) -> bool:
    upper = description.upper()
    return " REFUND" in upper or upper.endswith(" REFUND")
