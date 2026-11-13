"""Sample data in the app, or live Snowflake tables in FRAUD_DEMO_DB.CARDS.

Sample mode needs no account and is the only mode in the browser (stlite).
Live mode reads the tables built by sql/fraud_setup.sql, loaded from the same
generator, and reads fraud scores from the TXN_SCORED view, which computes the
same signals in SQL.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from fraud import data, logic

IN_BROWSER = sys.platform == "emscripten"
DB = "FRAUD_DEMO_DB.CARDS"
TABLES = ["METROS", "CARDHOLDERS", "CARDS", "MERCHANTS", "CARD_PROFILES", "TRANSACTIONS", "FRAUD_LABELS", "ANALYST_NOTES"]
ROOT = Path(__file__).resolve().parents[1]


def _conn():
    return st.connection("snowflake")


@st.cache_data(ttl=300, show_spinner=False)
def live_status() -> str:
    """'unavailable', 'empty' (tables exist but no rows) or 'ready'."""
    if IN_BROWSER or os.getenv("FRAUD_SAMPLE_ONLY"):
        return "unavailable"
    try:
        n = _conn().query(f"SELECT COUNT(*) AS N FROM {DB}.TRANSACTIONS", ttl=0).iloc[0, 0]
    except Exception:
        return "unavailable"
    return "ready" if n else "empty"


def is_live() -> bool:
    return st.session_state.get("mode", "sample") == "live"


@st.cache_data(show_spinner="Generating synthetic payments...")
def _sample() -> dict[str, pd.DataFrame]:
    t = data.generate()
    t["SCORED"] = logic.score(logic.features(t["TRANSACTIONS"], t["CARD_PROFILES"]))
    return t


@st.cache_data(ttl=600, show_spinner="Reading from Snowflake...")
def _live() -> dict[str, pd.DataFrame]:
    out = {t: _conn().query(f"SELECT * FROM {DB}.{t}", ttl=0) for t in TABLES}
    scored = _conn().query(f"SELECT * FROM {DB}.TXN_SCORED", ttl=0)
    for c in [c for c in scored.columns if c.startswith("SIG_")]:
        scored[c] = scored[c].astype(bool)
    scored["TS"] = pd.to_datetime(scored.TS)
    scored["PATTERN"] = [logic.pattern(r) for r in scored.itertuples()]
    out["SCORED"] = scored.sort_values(["CARD_ID", "TS", "TXN_ID"], kind="stable").reset_index(drop=True)
    return out


def tables() -> dict[str, pd.DataFrame]:
    return _live() if is_live() else _sample()


def threshold() -> int:
    return st.session_state.get("threshold", logic.DEFAULT_THRESHOLD)


def model() -> dict:
    t = dict(tables())
    sc = t["SCORED"]
    day = sc[sc.TS.dt.date == data.AS_OF]
    t["DAY"] = day.sort_values("TS").reset_index(drop=True)
    actions = {a["TXN_ID"]: a for a in st.session_state.get("audit", [])[::-1] if a.get("TXN_ID")}
    if is_live():
        for a in live_actions().to_dict("records"):
            actions[a["TXN_ID"]] = a
    t["ACTIONS"] = actions
    return t


def alerts(day: pd.DataFrame, upto: pd.Timestamp | None = None) -> pd.DataFrame:
    a = day[day.RISK_SCORE >= threshold()]
    if upto is not None:
        a = a[a.TS <= upto]
    return a.sort_values(["RISK_SCORE", "TS"], ascending=[False, True])


# ── Writes ──

def record(txn_id: str, card_id: str, actor: str, action: str, note: str) -> None:
    now = dt.datetime.now().replace(microsecond=0)
    st.session_state.setdefault("audit", []).insert(0, {
        "EVENT_TS": now, "TXN_ID": txn_id, "CARD_ID": card_id, "ACTOR": actor, "ACTION": action, "NOTE": note,
        "WRITTEN_TO": "Snowflake" if is_live() else "This browser session"})
    if is_live():
        _conn().cursor().execute(
            f"INSERT INTO {DB}.CASE_ACTIONS (EVENT_TS, TXN_ID, CARD_ID, ACTOR, ACTION, NOTE) VALUES (?, ?, ?, ?, ?, ?)",
            (now, txn_id, card_id, actor, action, note))
        live_actions.clear()


@st.cache_data(ttl=30, show_spinner=False)
def live_actions() -> pd.DataFrame:
    return _conn().query(f"SELECT * FROM {DB}.CASE_ACTIONS ORDER BY EVENT_TS DESC LIMIT 200", ttl=0)


def load_into_snowflake() -> dict[str, int]:
    """Load the synthetic tables into the empty tables created by sql/fraud_setup.sql."""
    from snowflake.connector.pandas_tools import write_pandas

    raw = _conn().raw_connection
    counts = {}
    for name, df in data.generate().items():
        write_pandas(raw, df.copy(), name, database="FRAUD_DEMO_DB", schema="CARDS",
                     auto_create_table=False, overwrite=False, use_logical_type=True)
        counts[name] = len(df)
    live_status.clear()
    _live.clear()
    return counts


@st.cache_data(show_spinner=False)
def captured_ai() -> dict:
    p = ROOT / "data" / "captured_ai.json"
    return json.loads(p.read_text()) if p.exists() else {"explanations": {}, "patterns": None}
