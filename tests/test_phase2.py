from datetime import date
from pathlib import Path

import pytest

from backend.api import SpendAPI
from backend.errors import (
    BackupError,
    CardExistsError,
    CategoryError,
    DuplicateStatementError,
    InactiveCardError,
)
from backend.ingest import NormalizedTxn


@pytest.fixture
def api():
    instance = SpendAPI(":memory:")
    yield instance
    instance.close()


def _card(api, holder="Ada", last4="1234", name="Regalia"):
    return api.create_card(
        bank_name="HDFC",
        card_name=name,
        last_4_digits=last4,
        cardholder=holder,
    )


def test_schema_idempotent_and_card_unique(api):
    a = _card(api)
    assert a["card_id"] == "HDFC_1234_ADA"
    assert a["is_active"] is True
    with pytest.raises(CardExistsError):
        _card(api)
    other = api.create_card(
        bank_name="HDFC",
        card_name="Regalia",
        last_4_digits="1234",
        cardholder="Bob",
    )
    assert other["card_id"] == "HDFC_1234_BOB"


def test_soft_delete_blocks_ingest(api):
    card = _card(api)
    api.soft_delete_card(card["card_id"])
    listed = api.list_cards(active_only=True)
    assert listed == []
    assert api.list_cards()[0]["is_active"] is False
    with pytest.raises(InactiveCardError):
        api.ingest_normalized(
            card["card_id"],
            "stmt.csv",
            b"aaa",
            [NormalizedTxn(date(2026, 1, 2), "ZEPTO", 100)],
        )
    api.reactivate_card(card["card_id"])
    result = api.ingest_normalized(
        card["card_id"],
        "stmt.csv",
        b"aaa",
        [NormalizedTxn(date(2026, 1, 2), "ZEPTO", 100)],
    )
    assert result.status == "loaded"
    assert result.row_count == 1


def test_ingest_reject_same_hash_replace_same_name(api):
    card = _card(api)
    rows = [
        NormalizedTxn(date(2026, 3, 1), "SWIGGY  A", 349),
        NormalizedTxn(date(2026, 3, 1), "SWIGGY A", 349),
    ]
    first = api.ingest_normalized(card["card_id"], "mar.csv", b"file-v1", rows)
    assert first.status == "loaded"
    assert first.row_count == 2
    with pytest.raises(DuplicateStatementError):
        api.ingest_normalized(card["card_id"], "mar-renamed.csv", b"file-v1", rows)
    replaced = api.ingest_normalized(
        card["card_id"],
        "mar.csv",
        b"file-v2",
        [NormalizedTxn(date(2026, 3, 2), "NETFLIX", 199)],
    )
    assert replaced.status == "replaced"
    assert replaced.row_count == 1
    assert api.unidentified_count() == 1


def test_categorizer_batch_custom_and_recategorize(api):
    card = _card(api)
    api.ingest_normalized(
        card["card_id"],
        "a.csv",
        b"bytes1",
        [
            NormalizedTxn(date(2026, 1, 1), "ZEPTO STORE", 50),
            NormalizedTxn(date(2026, 2, 1), "ZEPTO STORE", 60),
        ],
    )
    unidentified = api.unidentified_transactions()
    assert len(unidentified) == 2
    api.save_mappings(
        [{"transaction_id": unidentified[0]["id"], "category": "Groceries & Supermarket"}]
    )
    api.ingest_normalized(
        card["card_id"],
        "b.csv",
        b"bytes2",
        [NormalizedTxn(date(2026, 3, 1), "ZEPTO STORE", 70)],
    )
    rows = api.search_transactions(keyword="ZEPTO")
    assert all(r["category"] == "Groceries & Supermarket" for r in rows if r["date"].month == 3)
    still = [r for r in api.search_transactions(keyword="ZEPTO") if r["category"] == "Unidentified"]
    assert len(still) == 1
    updated = api.recategorize("ZEPTO STORE", "Shopping & E-Commerce", apply_existing=True)
    assert updated == 3
    api.add_custom_category("Kids School")
    with pytest.raises(CategoryError):
        api.add_custom_category("kids school")
    assert "Kids School" in api.dropdown_categories()


def test_top_merchants_merges_normalized_descriptions(api):
    from backend import analytics

    hdfc = api.create_card(
        bank_name="HDFC", card_name="UPI", last_4_digits="8837", cardholder="Alex"
    )
    icici = api.create_card(
        bank_name="ICICI", card_name="Primary", last_4_digits="5678", cardholder="Alex"
    )
    api.ingest_normalized(
        hdfc["card_id"],
        "a.csv",
        b"a",
        [NormalizedTxn(date(2026, 1, 1), "VILLAGE NATURALS BANGALORE", 100)],
    )
    api.ingest_normalized(
        icici["card_id"],
        "b.csv",
        b"b",
        [NormalizedTxn(date(2026, 1, 2), "VILLAGE NATURALS BANGALORE IN", 200)],
    )
    rows = analytics.top_merchants(api.conn, 2026, limit=5)
    assert len(rows) == 1
    assert rows[0]["merchant"] == "VILLAGE NATURALS"
    assert rows[0]["total"] == pytest.approx(300)


def test_analytics_expenses_only_calendar_year_recurring_search(api):
    card = _card(api)
    api.ingest_normalized(
        card["card_id"],
        "y.csv",
        b"y1",
        [
            NormalizedTxn(date(2026, 1, 10), "NETFLIX", 199),
            NormalizedTxn(date(2026, 2, 10), "NETFLIX", 210),
            NormalizedTxn(date(2025, 6, 1), "OLD SHOP", 5000),
            NormalizedTxn(date(2026, 1, 15), "PAYMENT THANK YOU", 199, spend_type="Payment"),
        ],
    )
    payload = api.dashboard_payload(2026)
    assert payload["ytd_total"] == pytest.approx(409)
    assert payload["top_merchants"][0]["merchant"] == "NETFLIX"
    assert "NETFLIX" in payload["advice"][1]
    recurring = payload["recurring"]
    assert recurring[0]["merchant"] == "NETFLIX"
    assert recurring[0]["total_spent"] == pytest.approx(409)
    assert payload["unidentified_count"] == 4
    found = api.search_transactions(keyword="NET", year=2026, amount_min=200)
    assert len(found) == 1
    assert found[0]["amount"] == pytest.approx(210)


def test_backup_file_db(tmp_path):
    db = tmp_path / "spends.duckdb"
    api = SpendAPI(db)
    _card(api)
    api.conn.execute("CHECKPOINT")
    dest = api.backup_database(tmp_path / "backups")
    assert Path(dest).exists()
    mem = SpendAPI(":memory:")
    with pytest.raises(BackupError):
        mem.backup_database(tmp_path / "nope.duckdb")
    api.close()
    mem.close()
