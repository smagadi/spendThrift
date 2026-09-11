from __future__ import annotations

from datetime import date

import plotly.express as px
import streamlit as st

from backend.api import SpendAPI
from ui.formatters import MONTH_ORDER, mom_aggregate_chart_rows, mom_by_card_chart_rows, inr


def _select_dashboard_year(years: list[int]) -> int:
    today = date.today().year
    if "dashboard_year" not in st.session_state or st.session_state.dashboard_year not in years:
        st.session_state.dashboard_year = today if today in years else years[0]
    return st.selectbox(
        "Year",
        years,
        index=years.index(st.session_state.dashboard_year),
        format_func=str,
    )


def render(api: SpendAPI) -> None:
    cards = api.list_cards()
    years = api.available_years()
    holders = sorted({c["cardholder"] for c in cards})
    card_labels = {c["card_id"]: f"{c['card_name']} · {c['cardholder']} · {c['last_4_digits']}" for c in cards}

    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    year = _select_dashboard_year(years)
    st.session_state.dashboard_year = year
    user = c2.selectbox("User", ["All"] + holders)
    card_choice = c3.selectbox("Card", ["All"] + [card_labels[i] for i in card_labels])
    pending = api.unidentified_count()
    c4.metric("Unidentified", pending)
    if pending:
        st.warning(f"{pending} transactions need category review.")

    cardholder = None if user == "All" else user
    card_id = None
    if card_choice != "All":
        card_id = next(cid for cid, lab in card_labels.items() if lab == card_choice)

    data = api.dashboard_payload(year, cardholder, card_id)

    m1, m2, m3 = st.columns(3)
    m1.metric(f"{year} spend", inr(data["ytd_total"]))
    top_card = data["top_card"]
    m2.metric(
        "Top spending card",
        f"{top_card['card_name']} ({top_card['cardholder']})" if top_card else "—",
        inr(top_card["total"]) if top_card else None,
    )
    top_cat = data["top_category"]
    m3.metric(
        "Top category",
        top_cat["category"] if top_cat else "—",
        inr(top_cat["total"]) if top_cat else None,
    )

    st.subheader("Advisory")
    for line in data["advice"]:
        st.write(line)

    left, right = st.columns(2)
    with left:
        st.subheader(f"Spend by card ({year})")
        st.dataframe(data["yearly_by_card"], hide_index=True, use_container_width=True)
    with right:
        st.subheader(f"Spend by user ({year})")
        st.dataframe(data["yearly_by_user"], hide_index=True, use_container_width=True)

    st.subheader(f"Month-on-month spend ({year})")
    mom = mom_aggregate_chart_rows(data["mom_aggregate"])
    if mom:
        fig = px.bar(mom, x="month", y="total", category_orders={"month": MONTH_ORDER})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No expenses for this year yet.")

    st.subheader(f"MoM by card ({year})")
    mom_cards = mom_by_card_chart_rows(data["mom_by_card"])
    if mom_cards:
        st.plotly_chart(
            px.line(
                mom_cards,
                x="month",
                y="total",
                color="card",
                markers=True,
                category_orders={"month": MONTH_ORDER},
            ),
            use_container_width=True,
        )

    st.subheader("Top transactions")
    st.dataframe(data["top_transactions"], hide_index=True, use_container_width=True)
    st.subheader("Top merchant drains")
    st.dataframe(data["top_merchants"], hide_index=True, use_container_width=True)

    st.subheader("Category mix")
    breakdown = data["category_breakdown"]
    if breakdown:
        st.plotly_chart(
            px.pie(breakdown, names="category", values="total", hole=0.45),
            use_container_width=True,
        )
    c_a, c_b = st.columns(2)
    with c_a:
        st.caption("By card")
        st.dataframe(data["category_by_card"], hide_index=True, use_container_width=True)
    with c_b:
        st.caption("By user")
        st.dataframe(data["category_by_user"], hide_index=True, use_container_width=True)

    st.subheader("Recurring merchants")
    st.dataframe(data["recurring"], hide_index=True, use_container_width=True)
