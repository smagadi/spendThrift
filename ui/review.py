from __future__ import annotations

import streamlit as st

from backend.api import SpendAPI
from backend.errors import CategoryError


def render(api: SpendAPI) -> None:
    st.subheader("Unidentified review")
    rows = api.unidentified_transactions()
    cats = api.dropdown_categories()
    if not rows:
        st.success("No unidentified transactions.")
    else:
        mappings = []
        for row in rows:
            cols = st.columns([2, 4, 2, 3])
            cols[0].write(str(row["date"]))
            cols[1].write(row["description"])
            cols[2].write(f"₹{row['amount']:,.2f}")
            chosen = cols[3].selectbox(
                "Category",
                cats,
                key=f"cat_{row['id']}",
                label_visibility="collapsed",
            )
            mappings.append({"transaction_id": row["id"], "category": chosen})
        if st.button("Save mappings"):
            n = api.save_mappings(mappings)
            synced = api.sync_refund_spend_types()
            msg = f"Saved {n} mappings."
            if synced:
                msg += f" Synced {synced} Refund row(s) out of spend totals."
            st.success(msg)
            st.rerun()

    st.subheader("Add custom category")
    new_name = st.text_input("Name")
    if st.button("Add category") and new_name.strip():
        try:
            api.add_custom_category(new_name)
            st.success("Added")
            st.rerun()
        except CategoryError as exc:
            st.error(str(exc))

    st.subheader("Recategorize cached merchant")
    cache = api.list_category_cache()
    if not cache:
        st.caption("No cache entries yet.")
        return
    labels = [f"{r['merchant_pattern']} → {r['assigned_category']}" for r in cache]
    picked = st.selectbox("Existing mapping", labels)
    pattern = cache[labels.index(picked)]["merchant_pattern"]
    new_cat = st.selectbox("New category", cats, key="re_cat")
    apply = st.checkbox("Apply to existing rows", value=True)
    if st.button("Update mapping"):
        try:
            n = api.recategorize(pattern, new_cat, apply_existing=apply)
            st.success(f"Updated. Matching rows now: {n}")
            st.rerun()
        except CategoryError as exc:
            st.error(str(exc))
