import pandas as pd
import streamlit as st

from fraud import source, ui

m = source.model()
alerts = source.alerts(m["DAY"]).head(12)
cards = m["CARDS"].set_index("CARD_ID")
holders = m["CARDHOLDERS"].set_index("CARDHOLDER_ID")

st.markdown("Card data is among the most sensitive data a bank holds. Who sees which fields is enforced on the data "
            "itself. Switch roles to compare views, then review every action taken on a case.")

role = st.segmented_control("View as", ui.ROLES, default="Fraud analyst", required=True, key="gov_role")
rows = []
for r in alerts.itertuples():
    c = cards.loc[r.CARD_ID]
    h = holders.loc[c.CARDHOLDER_ID]
    rows.append({"Payment": r.TXN_ID, "Cardholder": ui.mask_name(h.FIRST_NAME, h.LAST_NAME, role),
                 "Card number": ui.card_number(c.LAST4, role), "Email": ui.mask_email(h.EMAIL, role),
                 "Amount": r.AMOUNT, "Score": int(r.RISK_SCORE)})
st.dataframe(pd.DataFrame(rows), hide_index=True, alt=f"Today's top alerts as seen by the {role} role",
             column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")})
st.caption("This switcher simulates each role. In live mode, masking policies in sql/fraud_setup.sql evaluate the "
           "querying role automatically. Card numbers are display-only on the 400000 test BIN; only the last 4 digits are stored.")

with st.expander("Policy summary", icon=":material/policy:"):
    st.table(pd.DataFrame([
        ("Card number", "BIN and last 4", "Last 4", "Hidden"),
        ("Cardholder name", "Full", "Full", "Initials"),
        ("Email", "Full", "Full", "Domain only"),
    ], columns=["Data", *ui.ROLES]), hide_index=True, alt="What each role can see")

st.subheader("Audit trail", anchor=False)
if source.is_live():
    trail = source.live_actions()
    st.caption("Read from FRAUD_DEMO_DB.CARDS.CASE_ACTIONS.")
else:
    trail = pd.DataFrame(st.session_state.get("audit", []))
    st.caption("Actions recorded in this browser session. In live mode they are written to a Snowflake table.")
if trail.empty:
    st.caption("No actions yet. Work a case on the case review page, then come back.")
else:
    st.dataframe(trail, hide_index=True, alt="Audit trail of analyst actions")

st.subheader("Data lineage", anchor=False)
st.markdown("""```mermaid
flowchart LR
  T[Transactions] --> S[TXN_SCORED view]
  P[Card profiles] --> S
  M[Merchants] --> S
  S --> Q[Alert queue]
  Q --> C[Case review]
  C --> A[Case actions and audit]
  N[Analyst notes] --> G[Pattern summary]
```""")

if source.is_live():
    with st.expander("Policies attached in this account", icon=":material/ac_unit:"):
        st.dataframe(source._conn().query(
            "SELECT REF_ENTITY_NAME AS TABLE_NAME, REF_COLUMN_NAME AS COLUMN_NAME, POLICY_NAME, POLICY_KIND "
            "FROM TABLE(FRAUD_DEMO_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(REF_ENTITY_NAME => 'FRAUD_DEMO_DB.CARDS.CARDHOLDERS', "
            "REF_ENTITY_DOMAIN => 'table'))", ttl=0), hide_index=True, alt="Policies attached to the cardholders table")

ui.snowflake_callout(
    "governance that travels with the data",
    "Masking policies follow the tables into every tool: this app, notebooks, BI and the servicing desk. Access History "
    "records who read which columns, and every analyst action is kept in a table that auditors can query.",
)
