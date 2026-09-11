from pathlib import Path

import pytest

from backend.api import SpendAPI
from backend.errors import ParseError
from backend.parsers.icici import discover_icici_sections, icici_statement_summary, parse_icici_csv

FIXTURE = Path(__file__).parent / "fixtures" / "icici_sample.csv"
ACCOUNT_LAST4 = "2341"
SPEND_LAST4 = "5678"


@pytest.fixture
def api():
    instance = SpendAPI(":memory:")
    yield instance
    instance.close()


def test_icici_fixture_summary():
    summary = icici_statement_summary(FIXTURE.read_bytes())
    assert summary["account_last4"] == ACCOUNT_LAST4
    assert summary["primary_last4"] == SPEND_LAST4


def test_icici_discover_sections_from_fixture():
    sections = discover_icici_sections(FIXTURE.read_bytes())
    assert sections == ["3000", SPEND_LAST4]


def test_icici_parse_skips_ignored_columns_and_other_card():
    rows = parse_icici_csv(FIXTURE.read_bytes(), last_4_digits=SPEND_LAST4)
    assert [r.description for r in rows] == [
        "PAI VICEROY BENGALURU IN",
        "ADIDAS INDIA MARKETIN BENGALURU IN",
        "WIDGET SHOP REFUND BANGALORE IN",
    ]
    assert rows[-1].spend_type == "Refund"
    assert all("PAYMENT" not in r.description for r in rows)
    assert all("Fuel" not in r.description for r in rows)


def test_icici_wrong_last4_still_uses_primary_spend_section():
    rows = parse_icici_csv(FIXTURE.read_bytes(), last_4_digits="0000")
    assert len(rows) == 3


def test_icici_ingest_fixture(api):
    card = api.create_card(
        bank_name="ICICI",
        card_name="Primary",
        last_4_digits=ACCOUNT_LAST4,
        cardholder="Alex",
    )
    result = api.ingest_icici_csv(card["card_id"], "sample.csv", FIXTURE.read_bytes())
    assert result.row_count == 3
    assert SPEND_LAST4 in result.message
    refund = api.conn.execute(
        """
        SELECT category, spend_type FROM credit_card_transactions
        WHERE description = 'WIDGET SHOP REFUND BANGALORE IN'
        """
    ).fetchone()
    assert refund == ("Refund", "Refund")
    assert api.dashboard_payload(2026)["ytd_total"] == pytest.approx(910 + 1398.60)


def test_icici_ingest_expenses_exclude_credits(api):
    card = api.create_card(
        bank_name="ICICI",
        card_name="Amazon Pay",
        last_4_digits=SPEND_LAST4,
        cardholder="Alex",
    )
    result = api.ingest_icici_csv(card["card_id"], "sample.csv", FIXTURE.read_bytes())
    assert result.row_count == 3
    payload = api.dashboard_payload(2026)
    assert payload["ytd_total"] == pytest.approx(910 + 1398.60)


def test_icici_wrong_bank_rejected(api):
    card = api.create_card(
        bank_name="HDFC",
        card_name="Regalia",
        last_4_digits=SPEND_LAST4,
        cardholder="Alex",
    )
    with pytest.raises(ParseError):
        api.ingest_icici_csv(card["card_id"], "x.csv", FIXTURE.read_bytes())


def test_icici_empty_file():
    with pytest.raises(ParseError, match="Transaction Details"):
        parse_icici_csv(b"Accountno:,1234\n", last_4_digits="1234")
