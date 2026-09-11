from __future__ import annotations

import streamlit as st

from backend.api import SpendAPI
from backend.cards import ALLOWED_BANKS
from backend.errors import CardExistsError, SpendError


def render(api: SpendAPI) -> None:
    st.subheader("Register card")
    with st.form("create_card"):
        bank = st.selectbox("Bank", list(ALLOWED_BANKS))
        name = st.text_input("Card name / nickname")
        last4 = st.text_input("Last 4 digits", max_chars=4)
        holder = st.text_input("Cardholder")
        if st.form_submit_button("Save card"):
            try:
                card = api.create_card(
                    bank_name=bank,
                    card_name=name,
                    last_4_digits=last4,
                    cardholder=holder,
                )
                st.success(f"Saved {card['card_id']}")
            except (CardExistsError, ValueError, SpendError) as exc:
                st.error(str(exc))

    st.subheader("Cards")
    for card in api.list_cards():
        status = "Active" if card["is_active"] else "Inactive"
        cols = st.columns([4, 1, 1])
        cols[0].write(
            f"**{card['card_name']}** · {card['bank_name']} · "
            f"*{card['last_4_digits']}* · {card['cardholder']} · {status}"
        )
        if card["is_active"]:
            if cols[1].button("Soft delete", key=f"del_{card['card_id']}"):
                api.soft_delete_card(card["card_id"])
                st.rerun()
        else:
            if cols[2].button("Reactivate", key=f"on_{card['card_id']}"):
                api.reactivate_card(card["card_id"])
                st.rerun()
