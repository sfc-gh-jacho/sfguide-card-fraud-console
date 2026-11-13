import altair as alt
import pandas as pd
import streamlit as st

from fraud import data, source, ui

m = source.model()
sc, day = m["SCORED"], m["DAY"]
labels = m["FRAUD_LABELS"].set_index("TXN_ID").IS_FRAUD
alerts_today = source.alerts(day)
acted = set(m["ACTIONS"])

st.markdown(
    "A fictional card issuer processes about 1,800 payments a day across 2,700 cards. Every payment is scored as it "
    "arrives, suspicious ones land in an analyst's queue, and the team tunes the threshold that balances fraud caught "
    "against good customers interrupted."
)

with st.container(horizontal=True):
    st.metric("Payments today", f"{len(day):,}", border=True)
    st.metric("Alerts today", len(alerts_today), border=True, help=f"Risk score of {source.threshold()} or more")
    st.metric("Open alerts", int((~alerts_today.TXN_ID.isin(acted)).sum()), border=True)
    st.metric("Dollars at risk", f"${alerts_today.AMOUNT.sum():,.0f}", border=True, help="Total value of today's alerted payments")
    st.metric("Approval rate", f"{100 * (1 - len(alerts_today) / max(len(day), 1)):.1f}%", border=True,
              help="Payments that pass without an alert, in this synthetic data set")

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader("Alerts over the last 30 days")
        hist = sc[sc.RISK_SCORE >= source.threshold()].assign(DAY=lambda d: d.TS.dt.date)
        daily = hist.groupby(["DAY", "PATTERN"]).size().rename("ALERTS").reset_index()
        st.altair_chart(alt.Chart(daily).mark_bar().encode(
            x=alt.X("DAY:T", title=None), y=alt.Y("ALERTS:Q", title="Alerts"),
            color=alt.Color("PATTERN:N", title=None), tooltip=["DAY:T", "PATTERN", "ALERTS"]).properties(height=270),
            alt="Daily alerts by pattern over 30 days")
with right:
    with st.container(border=True):
        st.subheader("Today's top alerts")
        top = alerts_today.head(8).merge(m["MERCHANTS"][["MERCHANT_ID", "MERCHANT_NAME"]], on="MERCHANT_ID")
        st.dataframe(top[["TS", "CARD_ID", "MERCHANT_NAME", "AMOUNT", "RISK_SCORE", "PATTERN"]], hide_index=True, height=270,
                     alt="Today's highest-scoring alerts",
                     column_config={"TS": st.column_config.TimeColumn("Time", format="HH:mm"), "CARD_ID": "Card",
                                    "MERCHANT_NAME": "Merchant", "AMOUNT": st.column_config.NumberColumn("Amount", format="$%.2f"),
                                    "RISK_SCORE": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                                    "PATTERN": "Pattern"})

stories = ", ".join(f"{k} ({v.split(':')[0].lower()})" for k, v in data.PLANTED.items())
st.caption(f"Planted stories to explore: {stories}. "
           "Fraud labels are synthetic ground truth so the tuning page can show trade-offs; counts are not performance claims.")

c1, c2, c3 = st.columns(3)
with c1:
    ui.snowflake_callout("one governed copy", "Payments, cards, merchants and customer profiles sit side by side, so the "
                         "fraud, servicing and audit teams all work from the same records.")
with c2:
    ui.snowflake_callout("scoring in SQL", "In live mode a SQL view scores every payment with window functions and "
                         "HAVERSINE distance, and a Dynamic Table can keep it current as payments stream in.")
with c3:
    ui.snowflake_callout("AI next to the data", "Cortex AI_COMPLETE explains individual alerts and AI_AGG summarizes "
                         "analyst notes, without the data leaving Snowflake.")
