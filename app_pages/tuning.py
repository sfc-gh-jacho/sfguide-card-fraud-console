import altair as alt
import streamlit as st

from fraud import logic, source, ui

m = source.model()
curve = logic.tradeoff(m["SCORED"], m["FRAUD_LABELS"], range(10, 101, 5))

st.markdown("Every threshold is a trade-off. Lower it and you catch more fraud, but you decline more good customers and "
            "give analysts more alerts. Drag the threshold to see the effect across the last 30 days.")

t = st.slider("Alert threshold", 10, 100, source.threshold(), 5, key="threshold_slider")
st.session_state.threshold = t
row = curve[curve.THRESHOLD == t].iloc[0]

with st.container(horizontal=True):
    st.metric("Fraud dollars caught", f"{row.FRAUD_CAUGHT_PCT:.0f}%", border=True)
    st.metric("Good payments declined (30 days)", f"{int(row.GOOD_DECLINED):,}", border=True)
    st.metric("Alerts per day", f"{row.ALERTS_PER_DAY:.1f}", border=True)
    st.metric("Alerts that were fraud", f"{row.PRECISION_PCT:.0f}%", border=True)

with st.container(border=True):
    st.subheader("Fraud caught vs. customers interrupted", anchor=False)
    base = alt.Chart(curve).encode(x=alt.X("THRESHOLD:Q", title="Alert threshold"))
    caught = base.mark_line(color="#36B37E", strokeWidth=3, point=True).encode(
        y=alt.Y("FRAUD_CAUGHT_PCT:Q", title="Fraud dollars caught (%)"), tooltip=["THRESHOLD", "FRAUD_CAUGHT_PCT", "GOOD_DECLINED"])
    declined = base.mark_line(color="#DE350B", strokeWidth=3, point=True, strokeDash=[5, 3]).encode(
        y=alt.Y("GOOD_DECLINED:Q", title="Good payments declined", scale=alt.Scale(type="symlog")))
    rule = alt.Chart({"values": [{"T": t}]}).mark_rule(color="#11567F", strokeWidth=2).encode(x="T:Q")
    st.altair_chart(alt.layer(caught, declined, rule).resolve_scale(y="independent").properties(height=320),
                    alt="Fraud dollars caught and good payments declined by threshold")
    st.caption("Green, left axis: share of fraud dollars caught. Red dashed, right axis (log scale): good payments that "
               "would have been declined. The vertical line is your threshold.")

with st.expander("Full trade-off table", icon=":material/table:"):
    st.dataframe(curve, hide_index=True, alt="Trade-off by threshold",
                 column_config={"THRESHOLD": "Threshold", "FRAUD_CAUGHT_PCT": "Fraud $ caught %", "GOOD_DECLINED": "Good declined",
                                "ALERTS_PER_DAY": "Alerts/day", "PRECISION_PCT": "Alerts that were fraud %"})

st.caption("Measured against synthetic fraud labels in this example data set. Real portfolios need their own labeled "
           "history, and the threshold is a business decision that balances losses, customer experience and team capacity.")

ui.snowflake_callout(
    "what-if analysis at full scale",
    "The trade-off is recomputed across every payment for every threshold. In Snowflake the same comparison runs over "
    "years of history on an elastic warehouse, and the chosen threshold can be stored in a table the scoring view reads.",
)
