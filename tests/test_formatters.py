from ui.formatters import mom_aggregate_chart_rows, mom_by_card_chart_rows


def test_mom_aggregate_chart_rows_calendar_order():
    rows = mom_aggregate_chart_rows(
        [{"month": 2, "total": 100}, {"month": 1, "total": 50}, {"month": 12, "total": 5}]
    )
    assert [r["month"] for r in rows] == ["Jan", "Feb", "Dec"]
    assert [r["total"] for r in rows] == [50, 100, 5]


def test_mom_by_card_chart_rows_fill_months_per_card():
    rows = mom_by_card_chart_rows(
        [
            {"card_id": "a", "card_name": "Regalia", "cardholder": "Ada", "month": 1, "total": 1000},
            {"card_id": "b", "card_name": "UPI", "cardholder": "Ada", "month": 2, "total": 200},
        ]
    )
    assert len(rows) == 24
    regalia_jan = next(r for r in rows if r["card"] == "Regalia (Ada)" and r["month"] == "Jan")
    regalia_feb = next(r for r in rows if r["card"] == "Regalia (Ada)" and r["month"] == "Feb")
    upi_jan = next(r for r in rows if r["card"] == "UPI (Ada)" and r["month"] == "Jan")
    assert regalia_jan["total"] == 1000
    assert regalia_feb["total"] == 0
    assert upi_jan["total"] == 0
