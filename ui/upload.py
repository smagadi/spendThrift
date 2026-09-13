from __future__ import annotations

from datetime import date

import streamlit as st

from backend.api import SpendAPI
from backend.errors import DuplicateStatementError, InactiveCardError, ParseError, SpendError
from backend.parsers.icici import icici_statement_summary


def _show_ingest_notice() -> None:
    notice = st.session_state.pop("ingest_notice", None)
    if not notice:
        return
    st.success(
        f"{notice['status'].title()}: {notice['row_count']} rows ingested from {notice['filename']}."
    )
    unidentified = notice["unidentified"]
    if unidentified:
        st.warning(
            f"{unidentified} transaction(s) need categories. "
            "Use **Category review** in the sidebar, assign categories, then click **Save mappings**."
        )
        if st.button("Go to Category review", type="primary"):
            st.session_state.nav_page = "Category review"
            st.rerun()
    else:
        st.info("All rows matched saved categories. Open **Dashboard** to see updated spend.")


def render(api: SpendAPI) -> None:
    _show_ingest_notice()

    active = api.list_cards(active_only=True)
    if not active:
        st.info("Register an active card first.")
        return

    labels = {
        c["card_id"]: f"{c['bank_name']} {c['card_name']} · {c['cardholder']} · {c['last_4_digits']}"
        for c in active
    }
    choice = st.selectbox("Active card", list(labels.values()))
    card_id = next(cid for cid, lab in labels.items() if lab == choice)
    card = next(c for c in active if c["card_id"] == card_id)
    bank = card["bank_name"].upper()

    if bank not in {"ICICI", "HDFC", "AXIS"}:
        st.warning("Only ICICI, HDFC, and Axis statement import are supported.")
        return

    if bank == "ICICI":
        st.caption(
            "ICICI CSV under Transaction Details. Use the last 4 from the masked card line "
            "(e.g. XXXX5678), or billing Accountno last 4 — spend rows are picked automatically."
        )
    elif bank == "AXIS":
        st.caption(
            "Axis Excel (Transactions Summary). Match registered last 4 to Credit Card Number "
            "in the statement. MB PAYMENT and credit rows are skipped."
        )

    upload_types = ["csv"] if bank in {"ICICI", "HDFC"} else ["xlsx", "xls"]
    uploaded = st.file_uploader("Statement file", type=upload_types)
    if uploaded and bank == "ICICI":
        data = uploaded.getvalue()
        summary = icici_statement_summary(data)
        primary = summary["primary_last4"]
        account = summary["account_last4"]
        if primary:
            hint = f"Spend rows in this file: masked card ending **{primary}**."
            if account and account != primary:
                hint += f" Billing Accountno ends **{account}** (not the spend line)."
            st.info(hint)

    if uploaded and st.button("Ingest"):
        try:
            if bank == "ICICI":
                result = api.ingest_icici_csv(card_id, uploaded.name, uploaded.getvalue())
            elif bank == "HDFC":
                result = api.ingest_hdfc_csv(card_id, uploaded.name, uploaded.getvalue())
            else:
                result = api.ingest_axis_xls(card_id, uploaded.name, uploaded.getvalue())
            st.session_state.ingest_notice = {
                "status": result.status,
                "row_count": result.row_count,
                "filename": uploaded.name,
                "unidentified": api.unidentified_count(),
            }
            st.session_state.dashboard_year = date.today().year
            st.rerun()
        except DuplicateStatementError as exc:
            st.error(str(exc))
        except (ParseError, InactiveCardError, SpendError) as exc:
            st.error(str(exc))
