import altair as alt
import pandas as pd
import streamlit as st

from fraud import ai, logic, source, ui

m = source.model()
sc, merchants = m["SCORED"], m["MERCHANTS"].set_index("MERCHANT_ID")
alerts = source.alerts(m["DAY"])
holders = m["CARDHOLDERS"].set_index("CARDHOLDER_ID")
cards = m["CARDS"].set_index("CARD_ID")
metros = m["METROS"]

if alerts.empty:
    st.info("No alerts at the current threshold.", icon=":material/info:")
    st.stop()
ids = list(alerts.TXN_ID)
if st.session_state.txn_id not in ids:
    st.session_state.txn_id = ids[0]
label = {r.TXN_ID: f"{r.TXN_ID} · {r.CARD_ID} · ${r.AMOUNT:,.2f} · score {int(r.RISK_SCORE)}" for r in alerts.itertuples()}


def _sync():
    st.session_state.txn_id = st.session_state.case_pick


st.selectbox("Alert", ids, index=ids.index(st.session_state.txn_id), format_func=label.get, key="case_pick", on_change=_sync)
row = alerts.set_index("TXN_ID").loc[st.session_state.txn_id]
row = pd.concat([pd.Series({"TXN_ID": st.session_state.txn_id}), row])
card = cards.loc[row.CARD_ID]
holder = holders.loc[card.CARDHOLDER_ID]

with st.container(horizontal=True):
    st.metric("Risk score", int(row.RISK_SCORE), border=True)
    st.metric("Amount", f"${row.AMOUNT:,.2f}", border=True)
    st.metric("Typical for this card", f"${row.TYPICAL_AMOUNT:,.2f}", border=True)
    st.metric("Pattern", row.PATTERN, border=True)

st.caption(f"{holder.FIRST_NAME} {holder.LAST_NAME} · {ui.card_number(card.LAST4)} · home {row.HOME_METRO} · "
           f"{merchants.loc[row.MERCHANT_ID].MERCHANT_NAME} · {row.TS:%Y-%m-%d %H:%M}")

left, right = st.columns([1, 1])
with left:
    with st.container(border=True, height="stretch"):
        st.subheader("Why it was flagged", anchor=False)
        r = pd.DataFrame(logic.reasons(row), columns=["SIGNAL", "POINTS"])
        st.altair_chart(alt.Chart(r).mark_bar(color="#DE350B").encode(
            x=alt.X("POINTS:Q", title="Points"), y=alt.Y("SIGNAL:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320, labelOverlap=False)),
            tooltip=["SIGNAL", "POINTS"]).properties(height=46 * len(r) + 30), alt="Signals contributing to the risk score")
with right:
    with st.container(border=True, height="stretch"):
        st.subheader("Where this card has been", anchor=False)
        hist = sc[(sc.CARD_ID == row.CARD_ID) & (sc.TS <= row.TS)].tail(25)
        pts = hist[hist.CHANNEL == "CARD_PRESENT"][["LAT", "LON", "TS", "AMOUNT"]].assign(KIND="Earlier in-person payment")
        if row.CHANNEL == "CARD_PRESENT":
            pts.loc[pts.index[-1], "KIND"] = "Flagged payment"
        home = pd.DataFrame([{"LAT": row.HOME_LAT, "LON": row.HOME_LON, "KIND": "Home"}])
        scale = alt.Scale(domain=["Home", "Earlier in-person payment", "Flagged payment"], range=["#36B37E", "#29B5E8", "#DE350B"])
        labels = alt.Chart(metros).mark_text(color="#9AB", fontSize=10, dy=-11).encode(longitude="LON:Q", latitude="LAT:Q", text="METRO:N")
        ring = alt.Chart(home).mark_point(shape="circle", size=650, strokeWidth=3, filled=False).encode(
            longitude="LON:Q", latitude="LAT:Q", color=alt.Color("KIND:N", title=None, scale=scale))
        dots = alt.Chart(pts).mark_circle(size=150, opacity=0.95).encode(
            longitude="LON:Q", latitude="LAT:Q", color=alt.Color("KIND:N", title=None, scale=scale), tooltip=["KIND", "TS:T", "AMOUNT"])
        layers = [labels, ring, dots]
        if row.CHANNEL == "CARD_PRESENT" and len(pts) >= 2:
            hop = pts.tail(2)[["LAT", "LON"]].reset_index(drop=True).assign(ORDER=[0, 1])
            layers.insert(1, alt.Chart(hop).mark_line(color="#DE350B", strokeDash=[6, 4], strokeWidth=2).encode(
                longitude="LON:Q", latitude="LAT:Q", order="ORDER:O"))
        st.altair_chart(alt.layer(*layers).project("albersUsa").properties(height=260), alt="Coded metro locations for this card")
        st.caption("Metros are coded synthetic locations. Online payments have no location.")

with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("Analyst explanation", anchor=False, width="content")
        facts = ai.case_facts(sc, row)
        text, kind = ai.explanation(row.TXN_ID, facts)
        if text:
            ui.ai_label(kind)
    if source.is_live():
        if st.button("Explain with Cortex AI_COMPLETE", icon=":material/auto_awesome:", type="primary"):
            with st.spinner("Calling AI_COMPLETE..."):
                text = ai.run_explanation(row.TXN_ID, facts)
    if text:
        st.markdown(text)
    with st.expander("Facts given to the model", icon=":material/fact_check:"):
        st.code(facts, language=None, wrap_lines=True)

with st.container(border=True):
    st.subheader("Recent payments on this card", anchor=False)
    h = sc[sc.CARD_ID == row.CARD_ID].tail(12).iloc[::-1].copy()
    h["MERCHANT"] = h.MERCHANT_ID.map(merchants.MERCHANT_NAME)
    st.dataframe(h[["TS", "MERCHANT", "CATEGORY", "CHANNEL", "MERCHANT_METRO", "AMOUNT", "RISK_SCORE"]], hide_index=True,
                 alt="Recent payments on the flagged card",
                 column_config={"TS": st.column_config.DatetimeColumn("Time", format="MMM D HH:mm"), "MERCHANT": "Merchant",
                                "CATEGORY": "Category", "CHANNEL": "Channel", "MERCHANT_METRO": "Metro",
                                "AMOUNT": st.column_config.NumberColumn("Amount", format="$%.2f"),
                                "RISK_SCORE": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d")})

with st.container(border=True):
    st.subheader("Action", anchor=False)
    prior = m["ACTIONS"].get(row.TXN_ID)
    if prior:
        st.success(f"{prior['ACTION']} by {prior['ACTOR']}: {prior['NOTE'] or 'no note'}", icon=":material/task_alt:")
    with st.form(f"act_{row.TXN_ID}", border=False):
        c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
        act = c1.segmented_control("Decision", ["Block card", "Confirm with customer", "Clear as legitimate"], key=f"a_{row.TXN_ID}")
        who = c2.selectbox("Analyst", ["Analyst 1", "Analyst 2", "Team lead"], key=f"w_{row.TXN_ID}")
        note = st.text_input("Note", key=f"n_{row.TXN_ID}", placeholder="e.g. customer confirmed travel to METRO_G")
        if st.form_submit_button("Record action", type="primary", icon=":material/gavel:"):
            if not act:
                st.error("Choose a decision.", icon=":material/error:")
            else:
                source.record(row.TXN_ID, row.CARD_ID, who, act, note.strip())
                st.toast(f"{row.TXN_ID}: {act}", icon=":material/check:")
                st.rerun()

ui.snowflake_callout(
    "explainable alerts with Cortex AI",
    "The score is a sum of named signals computed in SQL, so the reasons are exact. Cortex AI_COMPLETE turns them into a "
    "plain-English briefing grounded only in the facts shown. The analyst makes the decision, and in live mode it is "
    "written to a Snowflake table.",
)
