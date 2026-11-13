import streamlit as st

from fraud import source

m = source.model()
merchants = m["MERCHANTS"].set_index("MERCHANT_ID")
alerts = source.alerts(m["DAY"]).copy()
actions = m["ACTIONS"]

st.markdown("Every payment at or above the threshold, highest risk first. Select one to open the case.")

alerts["STATUS"] = alerts.TXN_ID.map(lambda t: actions[t]["ACTION"] if t in actions else "Open")
alerts["MERCHANT"] = alerts.MERCHANT_ID.map(merchants.MERCHANT_NAME)
with st.container(horizontal=True, vertical_alignment="bottom"):
    pats = st.pills("Pattern", sorted(alerts.PATTERN.unique()), selection_mode="multi", key="q_pattern")
    status = st.segmented_control("Status", ["Open", "Worked"], selection_mode="multi", key="q_status")
q = alerts
if pats:
    q = q[q.PATTERN.isin(pats)]
if status and len(status) == 1:
    q = q[q.STATUS == "Open"] if status == ["Open"] else q[q.STATUS != "Open"]

st.caption(f"{len(q)} alerts at a threshold of {source.threshold()}. Select a row, then open the case review.")
event = st.dataframe(
    q[["TS", "TXN_ID", "CARD_ID", "MERCHANT", "CHANNEL", "AMOUNT", "RISK_SCORE", "PATTERN", "STATUS"]],
    hide_index=True, on_select="rerun", selection_mode="single-row", key="queue_table", height=460,
    alt="Alert queue sorted by risk score",
    column_config={"TS": st.column_config.TimeColumn("Time", format="HH:mm"), "TXN_ID": "Payment", "CARD_ID": "Card",
                   "MERCHANT": "Merchant", "CHANNEL": "Channel", "AMOUNT": st.column_config.NumberColumn("Amount", format="$%.2f"),
                   "RISK_SCORE": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                   "PATTERN": "Pattern", "STATUS": "Status"},
)
if event.selection.rows:
    st.session_state.txn_id = q.iloc[event.selection.rows[0]].TXN_ID
    st.page_link("app_pages/case.py", label=f"Open case {st.session_state.txn_id}", icon=":material/arrow_forward:")
