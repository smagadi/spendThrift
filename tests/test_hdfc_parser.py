from pathlib import Path

import pytest

from backend.api import SpendAPI
from backend.errors import ParseError
from backend.parsers.hdfc import hdfc_statement_summary, parse_hdfc_csv

FIXTURE = Path(__file__).parent / "fixtures" / "hdfc_sample.csv"
HDFC_LAST4 = "4521"


@pytest.fixture
def api():
    instance = SpendAPI(":memory:")
    yield instance
    instance.close()


def test_hdfc_fixture_skips_payment_and_parses_expenses():
    rows = parse_hdfc_csv(FIXTURE.read_bytes(), last_4_digits=HDFC_LAST4)
    assert [r.description for r in rows] == ["COFFEE SHOP BANGALORE", "UPI-GROCERY STORE"]
    assert rows[0].amount == pytest.approx(250)
    assert rows[1].amount == pytest.approx(910)


def test_hdfc_wrong_last4_rejected():
    with pytest.raises(ParseError, match=HDFC_LAST4):
        parse_hdfc_csv(FIXTURE.read_bytes(), last_4_digits="8837")


def test_hdfc_fixture_summary():
    summary = hdfc_statement_summary(FIXTURE.read_bytes())
    assert summary["card_last4"] == HDFC_LAST4


def test_hdfc_ingest_fixture(api):
    card = api.create_card(
        bank_name="HDFC",
        card_name="Regalia",
        last_4_digits=HDFC_LAST4,
        cardholder="Alex",
    )
    result = api.ingest_hdfc_csv(card["card_id"], "sample.csv", FIXTURE.read_bytes())
    assert result.row_count == 2
    assert api.dashboard_payload(2026)["ytd_total"] == pytest.approx(1160.0)


def test_hdfc_wrong_bank_rejected(api):
    card = api.create_card(
        bank_name="ICICI",
        card_name="Primary",
        last_4_digits=HDFC_LAST4,
        cardholder="Alex",
    )
    with pytest.raises(ParseError, match="HDFC"):
        api.ingest_hdfc_csv(card["card_id"], "x.csv", FIXTURE.read_bytes())
