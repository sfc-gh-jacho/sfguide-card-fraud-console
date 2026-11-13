import streamlit as st

from fraud import source

st.set_page_config(page_title="Card fraud analyst console", page_icon=":material/credit_card:", layout="wide")

if "mode" not in st.session_state:
    st.session_state.mode = "live" if source.live_status() == "ready" else "sample"
st.session_state.setdefault("replay_min", 0)
st.session_state.setdefault("playing", False)
st.session_state.setdefault("txn_id", None)

page = st.navigation(
    {
        "": [st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:", default=True)],
        "Investigate": [
            st.Page("app_pages/feed.py", title="1 · Live transaction feed", icon=":material/stream:"),
            st.Page("app_pages/queue.py", title="2 · Alert queue", icon=":material/notifications_active:"),
            st.Page("app_pages/case.py", title="3 · Case review", icon=":material/fact_check:"),
        ],
        "Improve": [
            st.Page("app_pages/tuning.py", title="4 · Threshold tuning", icon=":material/tune:"),
            st.Page("app_pages/patterns.py", title="5 · Patterns and merchants", icon=":material/hub:"),
        ],
        "Trust": [
            st.Page("app_pages/governance.py", title="Governance and audit", icon=":material/shield_lock:"),
            st.Page("app_pages/about.py", title="About this example", icon=":material/info:"),
        ],
    }
)

with st.sidebar:
    st.markdown("**Card fraud analyst console**")
    status = source.live_status()
    if status == "unavailable":
        st.badge("Sample data mode", icon=":material/science:", color="blue")
        st.caption("No Snowflake account needed." + (" Running entirely in your browser; nothing leaves this page." if source.IN_BROWSER else ""))
    else:
        choice = st.segmented_control("Data source", ["Sample data", "Live Snowflake"],
                                      default="Live Snowflake" if source.is_live() else "Sample data", required=True)
        st.session_state.mode = "live" if choice == "Live Snowflake" else "sample"
        if status == "empty" and source.is_live():
            st.warning("The Snowflake tables are empty. Load the synthetic data on the About page.", icon=":material/warning:")
            st.session_state.mode = "sample"
    st.caption(f"Alert threshold: **{source.threshold()}** (change it on the tuning page)")
    st.caption("All cardholders, cards, merchants and payments are synthetic. Card numbers are display-only on a test BIN.")

with st.container(horizontal=True, vertical_alignment="center"):
    st.title(page.title, icon=page.icon, width="content", anchor=False)
    st.space("small")
    if source.is_live():
        st.badge("Live Snowflake data", icon=":material/ac_unit:", color="blue")
    else:
        st.badge("Sample data mode", icon=":material/science:", color="gray")
    st.badge("Synthetic data", icon=":material/lab_profile:", color="orange")

page.run()
