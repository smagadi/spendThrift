from __future__ import annotations

from backend import analytics


def generate_advice(conn, year: int, cardholder=None, card_id=None) -> list[str]:
    lines: list[str] = []
    total = analytics.ytd_total(conn, year, cardholder, card_id)
    if total <= 0:
        return [f"No expense spend recorded for {year}."]

    cat = analytics.top_spending_category(conn, year, cardholder, card_id)
    if cat:
        lines.append(
            f"{cat['category']} is your top spending category this year (₹{cat['total']:.2f})."
        )
    merch = analytics.top_merchants(conn, year, cardholder, card_id, limit=1)
    if merch:
        m = merch[0]
        lines.append(
            f"{m['merchant']} is your top merchant drain this year (₹{m['total']:.2f})."
        )
    card = analytics.top_spending_card(conn, year, cardholder, card_id)
    if card:
        lines.append(
            f"{card['card_name']} ({card['cardholder']}) is your top spending card this year "
            f"(₹{card['total']:.2f})."
        )
    return lines
