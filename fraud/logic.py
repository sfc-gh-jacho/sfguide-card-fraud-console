"""Explainable fraud scoring, identical in Python (sample mode) and SQL (live mode).

Every point comes from a named signal so an analyst can see why a payment was
flagged. sql/fraud_setup.sql defines the same signals in the TXN_SCORED view.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_THRESHOLD = 40
SMALL_AMOUNT = 2.00          # card-testing probes
RISKY_MCC = ("ELECTRONICS", "GIFT_CARDS")

# (column, label, points)
SIGNALS = [
    ("SIG_AMOUNT_10X", "Amount 10x or more above this card's typical spend", 25),
    ("SIG_AMOUNT_5X", "Amount 5x to 10x above typical spend", 15),
    ("SIG_AMOUNT_3X", "Amount 3x to 5x above typical spend", 8),
    ("SIG_RISKY_MCC", "Resellable goods (electronics or gift cards)", 10),
    ("SIG_NEW_DEVICE", "Online payment from a device this customer hasn't used", 20),
    ("SIG_NIGHT", "Between midnight and 5 a.m.", 8),
    ("SIG_FAR_FROM_HOME", "In person, more than 500 km from home", 12),
    ("SIG_IMPOSSIBLE_TRAVEL", "Too far from the last in-person payment to travel there in time", 35),
    ("SIG_CARD_TESTING", "Three or more charges under $2 on this card in the last 30 minutes", 30),
    ("SIG_VELOCITY", "Four or more payments on this card in the last hour", 10),
]
POINTS = {c: p for c, _, p in SIGNALS}
LABELS = {c: l for c, l, _ in SIGNALS}


def haversine_km(lat1, lon1, lat2, lon2):
    """Matches Snowflake HAVERSINE (earth radius 6371 km)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def _window_count(ts: pd.Series, flag: pd.Series, minutes: int) -> np.ndarray:
    """Per card: count of flagged rows in (ts - minutes, ts], like RANGE BETWEEN INTERVAL PRECEDING."""
    t = ts.values.astype("datetime64[s]").astype(np.int64)
    f = flag.values.astype(np.int64)
    c = np.concatenate([[0], np.cumsum(f)])
    lo = np.searchsorted(t, t - minutes * 60, side="left")
    hi = np.searchsorted(t, t, side="right")
    return c[hi] - c[lo]


def features(tx: pd.DataFrame, profiles: pd.DataFrame) -> pd.DataFrame:
    d = tx.merge(profiles, on="CARD_ID", how="left").sort_values(["CARD_ID", "TS", "TXN_ID"], kind="stable").reset_index(drop=True)
    d["TS"] = pd.to_datetime(d.TS)
    ratio = d.AMOUNT / d.TYPICAL_AMOUNT
    d["AMOUNT_RATIO"] = ratio.round(1)
    d["SIG_AMOUNT_10X"] = ratio >= 10
    d["SIG_AMOUNT_5X"] = (ratio >= 5) & (ratio < 10)
    d["SIG_AMOUNT_3X"] = (ratio >= 3) & (ratio < 5)
    d["SIG_RISKY_MCC"] = d.CATEGORY.isin(RISKY_MCC)
    d["SIG_NEW_DEVICE"] = (d.CHANNEL == "ONLINE") & (d.DEVICE_ID != d.USUAL_DEVICE)
    d["SIG_NIGHT"] = d.TS.dt.hour < 5
    cp = d.CHANNEL == "CARD_PRESENT"
    d["KM_FROM_HOME"] = np.where(cp, haversine_km(d.HOME_LAT, d.HOME_LON, d.LAT, d.LON), np.nan)
    d["SIG_FAR_FROM_HOME"] = cp & (d.KM_FROM_HOME > 500)

    # Impossible travel: compare with this card's previous in-person payment
    p = d[cp][["CARD_ID", "TS", "LAT", "LON"]].copy()
    g = p.groupby("CARD_ID")
    p["PREV_TS"], p["PREV_LAT"], p["PREV_LON"] = g.TS.shift(), g.LAT.shift(), g.LON.shift()
    km = haversine_km(p.PREV_LAT, p.PREV_LON, p.LAT, p.LON)
    hours = (p.TS - p.PREV_TS).dt.total_seconds() / 3600
    p["KMH"] = np.where(hours > 0, km / hours.clip(lower=1 / 60), np.nan)
    d["IMPLIED_KMH"] = p.KMH.reindex(d.index)
    d["SIG_IMPOSSIBLE_TRAVEL"] = (d.IMPLIED_KMH > 900).fillna(False).astype(bool) & (km.reindex(d.index).fillna(0) > 500)

    small = np.zeros(len(d), dtype=np.int64)
    burst = np.zeros(len(d), dtype=np.int64)
    for _, idx in d.groupby("CARD_ID").indices.items():
        sub = d.iloc[idx]
        small[idx] = _window_count(sub.TS, sub.AMOUNT < SMALL_AMOUNT, 30)
        burst[idx] = _window_count(sub.TS, pd.Series(np.ones(len(sub), dtype=bool)), 60)
    d["SMALL_30M"], d["TXNS_60M"] = small, burst
    d["SIG_CARD_TESTING"] = d.SMALL_30M >= 3
    d["SIG_VELOCITY"] = d.TXNS_60M >= 4
    return d


def score(feat: pd.DataFrame) -> pd.DataFrame:
    s = sum(feat[c].astype(int) * p for c, p in POINTS.items())
    out = feat.assign(RISK_SCORE=np.minimum(100, s))
    out["PATTERN"] = [pattern(r) for r in out.itertuples()]
    return out


def pattern(r) -> str:
    if r.SIG_CARD_TESTING:
        return "Card testing"
    if r.SIG_IMPOSSIBLE_TRAVEL:
        return "Impossible travel"
    if r.SIG_NEW_DEVICE and r.SIG_RISKY_MCC:
        return "Account takeover"
    if r.SIG_FAR_FROM_HOME:
        return "Unusual location"
    if r.SIG_AMOUNT_10X or r.SIG_AMOUNT_5X:
        return "Unusual amount"
    return "Other"


def reasons(row) -> list[tuple[str, int]]:
    return [(LABELS[c], p) for c, p in POINTS.items() if bool(row[c])]


def tradeoff(scored: pd.DataFrame, labels: pd.DataFrame, thresholds=range(10, 101, 5)) -> pd.DataFrame:
    """Fraud caught vs good payments declined, by threshold, using the synthetic labels."""
    d = scored[["TXN_ID", "AMOUNT", "RISK_SCORE"]].merge(labels, on="TXN_ID")
    days = max(1, pd.to_datetime(scored.TS).dt.normalize().nunique())
    fraud_amt = d.loc[d.IS_FRAUD, "AMOUNT"].sum()
    rows = []
    for t in thresholds:
        hit = d.RISK_SCORE >= t
        rows.append({
            "THRESHOLD": t,
            "FRAUD_CAUGHT_PCT": round(100 * d.loc[hit & d.IS_FRAUD, "AMOUNT"].sum() / fraud_amt, 1) if fraud_amt else 0,
            "GOOD_DECLINED": int((hit & ~d.IS_FRAUD).sum()),
            "ALERTS_PER_DAY": round(hit.sum() / days, 1),
            "PRECISION_PCT": round(100 * (hit & d.IS_FRAUD).sum() / hit.sum(), 1) if hit.sum() else 0,
        })
    return pd.DataFrame(rows)

