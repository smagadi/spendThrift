from __future__ import annotations

from datetime import date

import streamlit as st

from backend.api import SpendAPI
from backend.errors import BackupError


def render(api: SpendAPI) -> None:
    st.subheader("Search")
    keyword = st.text_input("Description contains")
    c1, c2, c3, c4 = st.columns(4)
    date_from = c1.date_input("From", value=date(2025, 1, 1))
    date_to = c2.date_input("To", value=date.today())
    amount_min = c3.number_input("Min amount", min_value=0.0, value=0.0, step=100.0)
    amount_max = c4.number_input("Max amount", min_value=0.0, value=1_000_000.0, step=100.0)
    rows = api.search_transactions(
        keyword=keyword or None,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min if amount_min else None,
        amount_max=amount_max if amount_max else None,
    )
    st.dataframe(rows, hide_index=True, use_container_width=True)

    st.subheader("Backup")
    path = st.text_input("Copy database to folder or file path")
    if st.button("Backup now") and path.strip():
        try:
            dest = api.backup_database(path.strip())
            st.success(f"Copied to {dest}")
        except BackupError as exc:
            st.error(str(exc))
