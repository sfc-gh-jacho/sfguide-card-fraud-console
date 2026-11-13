import altair as alt
import pandas as pd
import streamlit as st

from fraud import data, source, ui

m = source.model()
day, merchants = m["DAY"], m["MERCHANTS"].set_index("MERCHANT_ID")
start = pd.Timestamp(f"{data.AS_OF} 00:00")

st.markdown("Replay today's payments as they arrive. Each one is scored the moment it lands; anything at or above the "
            "threshold turns red and goes to the analyst queue.")

with st.container(horizontal=True, vertical_alignment="bottom"):
    st.toggle("Play", key="playing", help="Advance the clock automatically")
    speed = st.segmented_control("Speed", [15, 30, 60], default=30, required=True, key="speed",
                                 format_func=lambda v: f"{v} min per second")
    if st.button("Reset to midnight", icon=":material/restart_alt:"):
        st.session_state.replay_min = 0
        st.session_state.playing = False
        st.rerun()


@st.fragment(run_every="1s" if st.session_state.playing else None)
def feed():
    if st.session_state.playing:
        st.session_state.replay_min = min(24 * 60, st.session_state.replay_min + st.session_state.speed)
        if st.session_state.replay_min >= 24 * 60:
            st.session_state.playing = False
    now = start + pd.Timedelta(minutes=st.session_state.replay_min)
    seen = day[day.TS <= now]
    alerts = seen[seen.RISK_SCORE >= source.threshold()]

    with st.container(horizontal=True):
        st.metric("Clock", now.strftime("%H:%M"), border=True)
        st.metric("Payments so far", f"{len(seen):,}", border=True)
        st.metric("Alerts so far", len(alerts), border=True)
        st.metric("Dollars stopped for review", f"${alerts.AMOUNT.sum():,.0f}", border=True)

    left, right = st.columns([3, 2])
    with left:
        recent = seen.tail(14).iloc[::-1].copy()
        recent["MERCHANT"] = recent.MERCHANT_ID.map(merchants.MERCHANT_NAME)
        recent["FLAG"] = recent.RISK_SCORE.map(lambda s: "Alert" if s >= source.threshold() else "")
        st.dataframe(recent[["TS", "CARD_ID", "MERCHANT", "CHANNEL", "AMOUNT", "RISK_SCORE", "FLAG"]], hide_index=True,
                     height=420, alt="Most recent payments with their risk scores",
                     column_config={"TS": st.column_config.TimeColumn("Time", format="HH:mm:ss"), "CARD_ID": "Card",
                                    "MERCHANT": "Merchant", "CHANNEL": "Channel",
                                    "AMOUNT": st.column_config.NumberColumn("Amount", format="$%.2f"),
                                    "RISK_SCORE": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                                    "FLAG": "Status"})
    with right:
        per_hour = seen.assign(HOUR=seen.TS.dt.floor("h"), ALERT=seen.RISK_SCORE >= source.threshold())
        g = per_hour.groupby("HOUR").agg(PAYMENTS=("TXN_ID", "size"), ALERTS=("ALERT", "sum")).reset_index()
        if g.empty:
            st.caption("Press Play to start the day.")
        else:
            base = alt.Chart(g).encode(x=alt.X("HOUR:T", title=None, scale=alt.Scale(domain=[start, start + pd.Timedelta(hours=24)])))
            st.altair_chart(
                (base.mark_bar(color="#29B5E8", opacity=0.55).encode(y=alt.Y("PAYMENTS:Q", title="Payments per hour"))
                 + base.mark_circle(color="#DE350B", size=90).encode(y="PAYMENTS:Q", size=alt.Size("ALERTS:Q", legend=None),
                                                                      opacity=alt.condition("datum.ALERTS > 0", alt.value(1), alt.value(0)),
                                                                      tooltip=["HOUR:T", "PAYMENTS", "ALERTS"]))
                .properties(height=360), alt="Payments per hour, with red dots sized by alerts")
            st.caption("Red dots mark hours with alerts. The dot grows with the number of alerts.")


feed()

ui.snowflake_callout(
    "near-real-time scoring",
    "In live mode the scores come from a SQL view that applies time-window functions and HAVERSINE distance to every "
    "payment. In production, a Dynamic Table or Snowpipe Streaming would keep it a few seconds behind the card network. "
    "This replay shows the same day's data arriving over time.",
)
