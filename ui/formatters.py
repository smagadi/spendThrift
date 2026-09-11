from __future__ import annotations


def inr(value) -> str:
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_ORDER = MONTHS[1:]


def mom_aggregate_chart_rows(rows: list[dict]) -> list[dict]:
    """Calendar-order months for household MoM bar chart."""
    by_month = {int(r["month"]): float(r["total"]) for r in rows}
    return [{"month": MONTHS[m], "total": by_month[m]} for m in sorted(by_month)]


def mom_by_card_chart_rows(rows: list[dict]) -> list[dict]:
    """One Jan–Dec series per card so MoM lines are ordered and comparable."""
    if not rows:
        return []
    cards: dict[str, tuple[str, str]] = {}
    totals: dict[tuple[str, int], float] = {}
    for row in rows:
        cards[row["card_id"]] = (row["card_name"], row["cardholder"])
        totals[(row["card_id"], int(row["month"]))] = float(row["total"])
    out: list[dict] = []
    for card_id, (card_name, cardholder) in sorted(cards.items(), key=lambda x: x[1][0].lower()):
        label = f"{card_name} ({cardholder})"
        for month in range(1, 13):
            out.append(
                {
                    "month": MONTHS[month],
                    "card": label,
                    "total": totals.get((card_id, month), 0.0),
                }
            )
    return out
