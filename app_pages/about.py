import streamlit as st

from fraud import source

st.markdown(
    "This is an illustrative example of a card-fraud operations workflow on Snowflake. Everything in it is synthetic: "
    "cardholders, cards, merchants, payments and fraud labels are generated, locations are coded metros, emails use "
    "example.com, and card numbers are display-only on the 400000 test BIN with only the last four digits stored."
)

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True, height="stretch"):
        st.subheader("Sample data mode", icon=":material/science:", anchor=False)
        st.markdown("- Runs with no Snowflake account, including entirely in your browser\n"
                    "- Scores are computed in Python with the same signals as the SQL view\n"
                    "- AI outputs are **captured from a real Snowflake Cortex run** and labeled, or are template text\n"
                    "- Actions stay in your browser session")
with c2:
    with st.container(border=True, height="stretch"):
        st.subheader("Live Snowflake mode", icon=":material/ac_unit:", anchor=False)
        st.markdown("- Reads `FRAUD_DEMO_DB.CARDS`, built by `sql/fraud_setup.sql`\n"
                    "- Scores come from the `TXN_SCORED` SQL view\n"
                    "- Calls Cortex `AI_COMPLETE` and `AI_AGG` live\n"
                    "- Writes case actions to a Snowflake table")

status = source.live_status()
if status == "empty":
    st.subheader("Load the synthetic data into Snowflake", anchor=False)
    st.markdown("The setup script created empty tables with their policies attached. Load the same synthetic data this "
                "app generates so both modes show identical payments.")
    if st.button("Load synthetic data", type="primary", icon=":material/upload:"):
        with st.spinner("Writing tables..."):
            counts = source.load_into_snowflake()
        st.success("Loaded: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()), icon=":material/check_circle:")
        st.session_state.mode = "live"
        st.rerun()
elif status == "ready":
    st.success("Connected to Snowflake, and the synthetic data is loaded.", icon=":material/check_circle:")

st.subheader("Run it in your own account", anchor=False)
st.markdown("1. Run `sql/fraud_setup.sql` in a Snowsight worksheet (Enterprise Edition for masking policies).\n"
            "2. Deploy the app with `snow streamlit deploy --replace` (see the README).\n"
            "3. Open the app, go to this page and select **Load synthetic data**.\n"
            "4. When you're done, run the cleanup block at the end of the script.")

st.subheader("Learn more", anchor=False)
with st.container(horizontal=True):
    st.link_button("Window functions", "https://docs.snowflake.com/en/sql-reference/functions-window-syntax", icon=":material/open_in_new:")
    st.link_button("HAVERSINE", "https://docs.snowflake.com/en/sql-reference/functions/haversine", icon=":material/open_in_new:")
    st.link_button("AI_COMPLETE", "https://docs.snowflake.com/en/sql-reference/functions/ai_complete", icon=":material/open_in_new:")
    st.link_button("AI_AGG", "https://docs.snowflake.com/en/sql-reference/functions/ai_agg", icon=":material/open_in_new:")
    st.link_button("Masking policies", "https://docs.snowflake.com/en/user-guide/security-column-ddm-intro", icon=":material/open_in_new:")

st.caption("Illustrative example provided as-is. Not an official Snowflake product, not supported by Snowflake "
           "Support, and not a production fraud system or regulatory advice. Signals and weights are simplified.")
