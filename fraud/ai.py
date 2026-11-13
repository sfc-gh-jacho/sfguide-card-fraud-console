"""Cortex AI calls (live mode) with captured or template fallbacks (sample mode)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from fraud import logic, source

MODEL = "llama3.3-70b"
PATTERN_TASK = ("These are fraud analysts' notes on reviewed card payments. In 4 short bullet points, summarize the "
                "fraud patterns confirmed, what tended to be a false positive, and one thing analysts should watch for "
                "next. Only use what the notes say. Respond with only the bullets.")


def case_facts(sc: pd.DataFrame, row: pd.Series) -> str:
    hist = sc[(sc.CARD_ID == row.CARD_ID) & (sc.TS < row.TS)].tail(8)
    lines = [
        f"Flagged payment {row.TXN_ID}: ${row.AMOUNT:,.2f} at a {row.CATEGORY.replace('_', ' ').lower()} merchant, "
        f"{'in person in ' + str(row.MERCHANT_METRO) if row.CHANNEL == 'CARD_PRESENT' else 'online'}, at {row.TS:%H:%M} on {row.TS:%Y-%m-%d}.",
        f"Risk score {int(row.RISK_SCORE)} of 100. Pattern: {row.PATTERN}.",
        "Signals: " + "; ".join(f"{label} (+{p})" for label, p in logic.reasons(row)) + ".",
        f"This card's typical payment is ${row.TYPICAL_AMOUNT:,.2f}; home is {row.HOME_METRO}.",
        "Previous payments on this card: " + "; ".join(
            f"{h.TS:%m-%d %H:%M} ${h.AMOUNT:,.2f} {h.CATEGORY.replace('_', ' ').lower()} "
            f"{'in ' + str(h.MERCHANT_METRO) if h.CHANNEL == 'CARD_PRESENT' else 'online'}" for h in hist.itertuples()) + ".",
    ]
    return "\n".join(lines)


def _prompt(facts: str) -> str:
    return ("You are assisting a card fraud analyst. Using ONLY the facts below, explain in 3 short bullet points: "
            "what looks unusual, what could be an innocent explanation, and what the analyst should check with the "
            "customer before blocking the card. Respond with only the three bullets, no introduction. Do not invent "
            "facts, names or numbers. This is synthetic data for a demonstration.\n\nFACTS:\n" + facts)


def explanation(txn_id: str, facts: str) -> tuple[str | None, str]:
    if source.is_live():
        return st.session_state.get(f"ai_{txn_id}"), "live"
    cap = source.captured_ai()["explanations"].get(txn_id)
    if cap:
        return cap["text"], "captured"
    return "\n".join(f"- {line}" for line in facts.splitlines()[1:3]), "template"


def run_explanation(txn_id: str, facts: str) -> str:
    text = source._conn().query("SELECT AI_COMPLETE(?, ?, {'temperature': 0, 'max_tokens': 260})::STRING",
                                params=[MODEL, _prompt(facts)], ttl=0).iloc[0, 0].strip()
    st.session_state[f"ai_{txn_id}"] = text
    return text


def patterns_summary() -> tuple[str | None, str]:
    if source.is_live():
        return st.session_state.get("ai_patterns"), "live"
    cap = source.captured_ai().get("patterns")
    return (cap["text"], "captured") if cap else (None, "none")


def run_patterns_summary() -> str:
    text = source._conn().query(
        f"""SELECT AI_AGG('Outcome ' || OUTCOME || ' on ' || t.CATEGORY || ' $' || t.AMOUNT || ': ' || NOTE, ?)::STRING
            FROM {source.DB}.ANALYST_NOTES n JOIN {source.DB}.TRANSACTIONS t USING (TXN_ID)""",
        params=[PATTERN_TASK], ttl=0).iloc[0, 0].strip()
    st.session_state["ai_patterns"] = text
    return text
