"""Shared UI pieces: Snowflake callouts, AI labels, masking."""

from __future__ import annotations

import streamlit as st

SCORE_COLOR = lambda s: "red" if s >= 70 else "orange" if s >= 40 else "green"  # noqa: E731


def snowflake_callout(title: str, body: str) -> None:
    with st.container(border=True):
        st.markdown(f":blue[:material/ac_unit:] **Powered by Snowflake: {title}**")
        st.caption(body)


def ai_label(kind: str) -> None:
    if kind == "live":
        st.badge("Live Cortex AI output", icon=":material/auto_awesome:", color="violet")
    elif kind == "captured":
        st.badge("Captured AI output from a real Snowflake Cortex run", icon=":material/history:", color="gray")
    elif kind == "template":
        st.badge("Template text, not AI-generated", icon=":material/text_snippet:", color="gray")


def card_number(last4: str, role: str = "Fraud analyst") -> str:
    """Synthetic display number on the 400000 test BIN. Never a real card number."""
    if role == "Fraud analyst":
        return f"4000 00•• •••• {last4}"
    if role == "Customer service":
        return f"•••• •••• •••• {last4}"
    return "•••• •••• •••• ••••"


ROLES = ["Fraud analyst", "Customer service", "Auditor"]


def mask_email(v: str, role: str) -> str:
    return v if role in ("Fraud analyst", "Customer service") else "****@" + v.split("@")[-1]


def mask_name(first: str, last: str, role: str) -> str:
    return f"{first} {last}" if role != "Auditor" else f"{first[0]}. {last[0]}."
