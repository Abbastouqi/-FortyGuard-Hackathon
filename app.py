"""HeatOps — Streamlit demo UI (this is your live demo link).

Run:  streamlit run app.py
Deploy free on Streamlit Community Cloud for the submission's live link.
"""

import streamlit as st

from heatops.agent import HeatOpsAgent

st.set_page_config(page_title="HeatOps Agent", page_icon="🌡️", layout="wide")
st.title("🌡️ HeatOps — Agentic Urban Heat Analyst")
st.caption(
    "Powered by FortyGuard's Temperature API. Ask a plain-language question; "
    "the agent plans, calls the right endpoints, and returns a source-cited "
    "action plan. Every number is traceable to an activity_id."
)

EXAMPLES = [
    "Rank these Phoenix bus stops by 2pm heat on 2025-07-15 and say which "
    "two to shade first: (33.4484,-112.0740), (33.4550,-112.0660), "
    "(33.4300,-112.0900)",
    "Was downtown Houston hotter at 14:00 on 2025-08-01 or 2024-08-01? "
    "Use a small polygon around (29.7604,-95.3698).",
    "Give me a heat brief for a construction site at (25.7617,-80.1918) in "
    "Miami tomorrow afternoon — should outdoor work be rescheduled?",
]

with st.sidebar:
    st.subheader("Example briefs")
    for ex in EXAMPLES:
        if st.button(ex[:70] + "…", use_container_width=True):
            st.session_state["pending"] = ex

if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    st.chat_message(role).markdown(text)

brief = st.chat_input("Describe your heat question…")
if not brief and "pending" in st.session_state:
    brief = st.session_state.pop("pending")

if brief:
    st.session_state.history.append(("user", brief))
    st.chat_message("user").markdown(brief)

    events: list[str] = []
    log_box = st.chat_message("assistant").empty()

    def on_event(msg: str) -> None:
        events.append(msg)
        log_box.markdown("```\n" + "\n".join(events[-12:]) + "\n```")

    agent = HeatOpsAgent()
    with st.spinner("Agent planning and calling FortyGuard…"):
        answer = agent.run(brief, on_event=on_event)

    log_box.markdown(answer)
    st.session_state.history.append(("assistant", answer))

    with st.expander("🔍 Audit trail (API calls made)"):
        st.json(agent.audit_trail)
