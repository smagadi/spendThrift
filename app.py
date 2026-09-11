"""Thin Streamlit shell. No SQL. No bank parsers."""

from __future__ import annotations

import duckdb
import streamlit as st

from backend.api import SpendAPI
from ui import cards, dashboard, review, search, upload

st.set_page_config(page_title="Spend analyzer", layout="wide")

API_SESSION_VERSION = 3  # bump when DB connection / UDF registration rules change


def _open_api() -> SpendAPI:
    prior = st.session_state.get("api")
    if prior is not None and st.session_state.get("api_version") == API_SESSION_VERSION:
        return prior
    if prior is not None:
        prior.close()
    st.session_state.api = SpendAPI()
    st.session_state.api_version = API_SESSION_VERSION
    return st.session_state.api


if "api" not in st.session_state or st.session_state.get("api_version") != API_SESSION_VERSION:
    try:
        api = _open_api()
    except duckdb.IOException as exc:
        if "Conflicting lock" in str(exc) or "Could not set lock" in str(exc):
            st.error(
                "Database is locked by another process. "
                "Stop other Streamlit tabs/terminals and quit `duckdb data/spends.duckdb` if open, then refresh."
            )
        else:
            st.error(str(exc))
        st.stop()
    except duckdb.CatalogException as exc:
        st.error(f"Database catalog error: {exc}. Stop Streamlit, run `make run` once, and refresh.")
        st.stop()
else:
    api = st.session_state.api
pending = api.unidentified_count()
st.sidebar.caption(f"Unidentified: {pending}")
nav_options = [
    "Dashboard",
    "Card manager",
    "Statement upload",
    "Category review",
    "Search / settings",
]
if "nav_page" not in st.session_state:
    st.session_state.nav_page = nav_options[0]
page = st.sidebar.radio("Navigate", nav_options, key="nav_page")

if page == "Dashboard":
    dashboard.render(api)
elif page == "Card manager":
    cards.render(api)
elif page == "Statement upload":
    upload.render(api)
elif page == "Category review":
    review.render(api)
else:
    search.render(api)
