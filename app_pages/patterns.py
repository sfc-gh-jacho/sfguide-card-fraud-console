import altair as alt
import pandas as pd
import streamlit as st

from fraud import ai, data, source, ui

m = source.model()
sc, merchants = m["SCORED"], m["MERCHANTS"].set_index("MERCHANT_ID")
today = source.alerts(m["DAY"])

st.markdown("Step back from single alerts. Which patterns are growing, and is there a merchant where many of today's "
            "compromised cards were used recently? That's often where card details were stolen.")

left, right = st.columns([2, 3])
with left:
    with st.container(border=True, height="stretch"):
        st.subheader("Today's alerts by pattern", anchor=False)
        p = today.groupby("PATTERN").size().rename("ALERTS").reset_index()
        bars = alt.Chart(p).encode(x=alt.X("ALERTS:Q", title="Alerts", axis=alt.Axis(tickMinStep=1)),
                                   y=alt.Y("PATTERN:N", sort="-x", title=None))
        st.altair_chart((bars.mark_bar(color="#29B5E8") + bars.mark_text(align="left", dx=4, color="#11567F").encode(text="ALERTS:Q"))
                        .properties(height=40 * len(p) + 30), alt="Today's alerts by pattern")
with right:
    with st.container(border=True, height="stretch"):
        st.subheader("Common point of purchase", anchor=False)
        hit_cards = set(today.CARD_ID)
        before = sc[(sc.CARD_ID.isin(hit_cards)) & (sc.CHANNEL == "CARD_PRESENT") & (sc.TS.dt.date < data.AS_OF)]
        cpp = (before.groupby("MERCHANT_ID").CARD_ID.nunique().rename("ALERTED_CARDS").reset_index()
               .sort_values("ALERTED_CARDS", ascending=False).head(6))
        cpp["MERCHANT"] = cpp.MERCHANT_ID.map(merchants.MERCHANT_NAME)
        cpp["SHARE"] = (cpp.ALERTED_CARDS / max(len(hit_cards), 1) * 100).round(0)
        st.dataframe(cpp[["MERCHANT", "MERCHANT_ID", "ALERTED_CARDS", "SHARE"]], hide_index=True, alt="Merchants most visited by today's alerted cards",
                     column_config={"MERCHANT": "Merchant", "MERCHANT_ID": "ID", "ALERTED_CARDS": "Alerted cards seen here",
                                    "SHARE": st.column_config.ProgressColumn("Share of alerted cards", min_value=0, max_value=100, format="%d%%")})
        top = cpp.iloc[0]
        st.warning(f"{int(top.ALERTED_CARDS)} of today's {len(hit_cards)} alerted cards were used in person at "
                   f"{top.MERCHANT} in the last 30 days. Consider proactive reissue for its other recent customers.",
                   title="Possible compromised merchant", icon=":material/storefront:")

with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("What analysts have been seeing", anchor=False, width="content")
        text, kind = ai.patterns_summary()
        if text:
            ui.ai_label(kind)
    if source.is_live():
        if st.button("Summarize analyst notes with Cortex AI_AGG", icon=":material/auto_awesome:", type="primary"):
            with st.spinner("Calling AI_AGG over the notes..."):
                text = ai.run_patterns_summary()
    if text:
        st.markdown(text)
    elif not source.is_live():
        st.caption("No captured summary available.")
    with st.expander(f"Analyst notes ({len(m['ANALYST_NOTES'])})", icon=":material/notes:"):
        st.dataframe(m["ANALYST_NOTES"], hide_index=True, alt="Analyst notes on past reviewed payments")

ui.snowflake_callout(
    "patterns across the whole book",
    "The common-point-of-purchase check is one SQL join across every alerted card's history. Cortex AI_AGG reads all "
    "of the analyst notes in a single aggregate call, and it isn't limited by a single prompt's size.",
)
