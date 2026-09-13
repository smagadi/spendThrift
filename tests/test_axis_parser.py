from pathlib import Path

import pytest

from backend.api import SpendAPI
from backend.errors import ParseError
from backend.parsers.axis import axis_statement_summary, parse_axis_xls

FIXTURE = Path(__file__).parent / "fixtures" / "axis_sample.xlsx"
AXIS_LAST4 = "9102"


@pytest.fixture
def api():
    instance = SpendAPI(":memory:")
    yield instance
    instance.close()


def test_axis_fixture_skips_mb_payment_and_parses_expenses():
    rows = parse_axis_xls(FIXTURE.read_bytes(), last_4_digits=AXIS_LAST4)
    assert [r.description for r in rows] == [
        "BOOKSTORE BANGALORE",
        "WIDGET SHOP REFUND BANGALORE IN",
    ]
    assert rows[0].amount == pytest.approx(551)
    assert rows[0].spend_type == "One-Time"
    assert rows[1].spend_type == "Refund"


def test_axis_wrong_last4_rejected():
    with pytest.raises(ParseError, match=AXIS_LAST4):
        parse_axis_xls(FIXTURE.read_bytes(), last_4_digits="4521")


def test_axis_fixture_summary():
    summary = axis_statement_summary(FIXTURE.read_bytes())
    assert summary["card_last4"] == AXIS_LAST4


def test_axis_ingest_fixture(api):
    card = api.create_card(
        bank_name="Axis",
        card_name="Select",
        last_4_digits=AXIS_LAST4,
        cardholder="Alex",
    )
    result = api.ingest_axis_xls(card["card_id"], "sample.xlsx", FIXTURE.read_bytes())
    assert result.row_count == 2
    assert api.dashboard_payload(2025)["ytd_total"] == pytest.approx(551.0)


def test_axis_wrong_bank_rejected(api):
    card = api.create_card(
        bank_name="HDFC",
        card_name="Regalia",
        last_4_digits=AXIS_LAST4,
        cardholder="Alex",
    )
    with pytest.raises(ParseError, match="Axis"):
        api.ingest_axis_xls(card["card_id"], "x.xlsx", FIXTURE.read_bytes())
