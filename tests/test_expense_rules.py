from datetime import date

import pytest

from backend.api import SpendAPI
from backend.expense_rules import is_icici_merchant_refund, is_icici_non_expense_row
from backend.ingest import NormalizedTxn

REFUND_DESC = "WIDGET SHOP REFUND BANGALORE IN"
SPEND_LAST4 = "5678"


def test_icici_payment_patterns():
    assert is_icici_non_expense_row("INFINITY PAYMENT RECEIVED THANK YOU", "")
    assert is_icici_non_expense_row("Fuel Surcharges", "CR")
    assert not is_icici_non_expense_row("SWIGGY BANGALORE", "")
    assert is_icici_merchant_refund(REFUND_DESC)
    assert not is_icici_merchant_refund("SWIGGY BANGALORE")


def test_refund_category_excluded_from_analytics():
    api = SpendAPI(":memory:")
    card = api.create_card(
        bank_name="ICICI",
        card_name="Test",
        last_4_digits=SPEND_LAST4,
        cardholder="Alex",
    )
    api.ingest_normalized(
        card["card_id"],
        "a.csv",
        b"x",
        [NormalizedTxn(date(2026, 1, 1), "SHOP", 100)],
    )
    api.ingest_normalized(
        card["card_id"],
        "b.csv",
        b"y",
        [NormalizedTxn(date(2026, 1, 2), "RETURN SHOP", 50)],
    )
    rows = api.unidentified_transactions()
    by_desc = {r["description"]: r for r in rows}
    api.save_mappings(
        [
            {"transaction_id": by_desc["SHOP"]["id"], "category": "Shopping & E-Commerce"},
            {"transaction_id": by_desc["RETURN SHOP"]["id"], "category": "Refund"},
        ]
    )
    assert api.dashboard_payload(2026)["ytd_total"] == 100
    api.close()


def test_purge_removes_payments():
    api = SpendAPI(":memory:")
    card = api.create_card(
        bank_name="ICICI",
        card_name="Test",
        last_4_digits=SPEND_LAST4,
        cardholder="Alex",
    )
    api.conn.execute(
        """
        INSERT INTO statement_uploads VALUES ('u1', ?, 'f.csv', 'h', now(), 2, 'loaded', NULL)
        """,
        [card["card_id"]],
    )
    api.conn.execute(
        """
        INSERT INTO credit_card_transactions VALUES
        ('1', ?, 'u1', 'f.csv', '2026-01-01', 'INFINITY PAYMENT RECEIVED THANK YOU', 5000, 'Unidentified', 'Credit'),
        ('2', ?, 'u1', 'f.csv', '2026-01-02', 'SWIGGY', 200, 'Unidentified', 'One-Time'),
        ('3', ?, 'u1', 'f.csv', '2026-02-19', ?, 500, 'Refund', 'One-Time'),
        ('4', ?, 'u1', 'f.csv', '2026-02-20', ?, 100, 'Unidentified', 'One-Time')
        """,
        [card["card_id"], card["card_id"], card["card_id"], REFUND_DESC, card["card_id"], REFUND_DESC],
    )
    result = api.purge_non_expense_transactions()
    assert result["payments_removed"] == 1
    assert result["refunds_synced"] == 1
    assert result["refunds_repaired"] == 1
    assert api.dashboard_payload(2026)["ytd_total"] == 200
    remaining = api.conn.execute(
        "SELECT description, category, spend_type FROM credit_card_transactions ORDER BY description"
    ).fetchall()
    assert (REFUND_DESC, "Refund", "Refund") in remaining
    api.close()


def test_refund_description_excluded_from_dashboard_when_unidentified():
    from backend import analytics

    api = SpendAPI(":memory:")
    card = api.create_card(
        bank_name="ICICI", card_name="X", last_4_digits=SPEND_LAST4, cardholder="Alex"
    )
    api.ingest_normalized(
        card["card_id"],
        "a.csv",
        b"x",
        [NormalizedTxn(date(2026, 2, 19), REFUND_DESC, 500, spend_type="One-Time")],
    )
    assert analytics.ytd_total(api.conn, 2026) == 0
    payload = api.dashboard_payload(2026)
    assert payload["ytd_total"] == 0
    assert payload["top_transactions"] == []
    assert payload["top_merchants"] == []
    assert payload["mom_aggregate"] == []
    repaired = api.conn.execute(
        "SELECT category, spend_type FROM credit_card_transactions"
    ).fetchone()
    assert repaired == ("Refund", "Refund")
    api.close()
