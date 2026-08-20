"""HeatOps — Streamlit demo UI (this is your live demo link).

Run:  streamlit run app.py
Deploy free on Streamlit Community Cloud for the submission's live link.
"""

import json

import streamlit as st

from heatops.agent import LLM_BASE_URL, MODEL, HeatOpsAgent

st.set_page_config(
    page_title="HeatOps — Agentic Urban Heat Analyst",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.block-container { max-width: 980px; padding-top: 1.5rem; }

/* ---- hero header ---- */
.ho-hero {
    padding: 1.6rem 1.8rem;
    border-radius: 16px;
    background: linear-gradient(135deg, #1a1205 0%, #14202e 55%, #0e1620 100%);
    border: 1px solid rgba(255,107,53,.25);
    margin-bottom: 1.2rem;
}
.ho-hero h1 {
    margin: 0; padding: 0;
    font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em;
    background: linear-gradient(90deg, #ff6b35, #ffb347 60%, #ffd28a);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.ho-hero p { margin: .45rem 0 0 0; color: #9aa7b4; font-size: .92rem; }
.ho-badges { margin-top: .8rem; }
.ho-badge {
    display: inline-block; margin-right: .4rem; padding: .18rem .6rem;
    border-radius: 999px; font-size: .72rem; font-weight: 600;
    color: #ffb347; background: rgba(255,107,53,.12);
    border: 1px solid rgba(255,107,53,.35);
}
.ho-badge.blue  { color:#7cc4ff; background:rgba(56,139,253,.12); border-color:rgba(56,139,253,.35); }
.ho-badge.green { color:#7ee2a8; background:rgba(46,160,67,.12);  border-color:rgba(46,160,67,.35);  }

/* ---- sidebar ---- */
[data-testid="stSidebar"] { border-right: 1px solid rgba(255,255,255,.06); }
.ho-side-title { font-size: 1.25rem; font-weight: 800; letter-spacing: -.02em; }
.ho-kv { font-size: .78rem; color: #9aa7b4; margin: .15rem 0; }
.ho-kv b { color: #e6e9ef; font-weight: 600; }

/* ---- chat ---- */
[data-testid="stChatMessage"] {
    background: #121820; border: 1px solid rgba(255,255,255,.06);
    border-radius: 14px; padding: 1rem 1.1rem; margin-bottom: .6rem;
}
[data-testid="stChatInput"] { border-radius: 14px; }

/* ---- status / activity feed ---- */
[data-testid="stStatusWidget"] { font-size: .85rem; }
.ho-step { font-size: .85rem; color: #c7d0d9; margin: .15rem 0; }
.ho-step code { color: #ffb347; }

/* buttons */
.stButton > button {
    border-radius: 10px; border: 1px solid rgba(255,255,255,.1);
    background: #161d26; color: #c7d0d9; font-size: .8rem; text-align: left;
}
.stButton > button:hover { border-color: #ff6b35; color: #ffb347; }
</style>
""",
    unsafe_allow_html=True,
)

EXAMPLES = [
    "Rank these Phoenix bus stops by 2pm heat on 2025-07-15 and say which "
    "two to shade first: (33.4484,-112.0740), (33.4550,-112.0660), "
    "(33.4300,-112.0900)",
    "Analyze the heat over the polygon (-80.23,25.72),(-80.15,25.72),"
    "(-80.15,25.8),(-80.23,25.8) in Miami for the whole day 2026-08-20 and "
    "tell me the hottest spot and where to add shade first.",
    "Give me a heat brief for a construction site at (25.7617,-80.1918) in "
    "Miami this afternoon at 14:00 — should outdoor work be rescheduled?",
]

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.markdown('<div class="ho-side-title">🌡️ HeatOps</div>', unsafe_allow_html=True)
    st.caption("Agentic Urban Heat Analyst · FortyGuard Hackathon '26")

    st.divider()
    st.markdown("**Agent backend**")
    backend = "Local gateway" if LLM_BASE_URL else "Anthropic"
    st.markdown(
        f'<div class="ho-kv">Model &nbsp;<b>{MODEL}</b></div>'
        f'<div class="ho-kv">Backend &nbsp;<b>{backend}</b></div>'
        f'<div class="ho-kv">Data &nbsp;<b>FortyGuard Temperature API</b></div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("**Example briefs**")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex[:72] + "…", key=f"ex{i}", use_container_width=True):
            st.session_state["pending"] = ex

    st.divider()
    st.markdown("**Coverage**")
    st.markdown(
        '<div class="ho-kv">Region &nbsp;<b>United States</b></div>'
        '<div class="ho-kv">Dates &nbsp;<b>2021-01-01 → now +12 h</b></div>'
        '<div class="ho-kv">AOI &nbsp;<b>≤ ~130 km² per heatmap</b></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption("Every number in an answer cites the activity_id of the API call that produced it.")

# ------------------------------------------------------------------- hero --
st.markdown(
    """
<div class="ho-hero">
  <h1>HeatOps — Agentic Urban Heat Analyst</h1>
  <p>Describe your heat question in plain language. The agent plans the analysis,
     sequences FortyGuard's Temperature API endpoints, and returns a ranked,
     source-cited action plan.</p>
  <div class="ho-badges">
    <span class="ho-badge">⚡ Autonomous planning</span>
    <span class="ho-badge blue">🛰️ Hyperlocal ~2 m data</span>
    <span class="ho-badge green">🔍 Audit-trailed answers</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------- chat --
if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    avatar = "🧑‍💼" if turn["role"] == "user" else "🌡️"
    with st.chat_message(turn["role"], avatar=avatar):
        st.markdown(turn["text"])
        if turn.get("trail"):
            with st.expander(f"🔍 Audit trail — {len(turn['trail'])} API call(s)"):
                st.json(turn["trail"])

brief = st.chat_input("Describe your heat question…")
if not brief and "pending" in st.session_state:
    brief = st.session_state.pop("pending")

if brief:
    st.session_state.history.append({"role": "user", "text": brief})
    st.chat_message("user", avatar="🧑‍💼").markdown(brief)

    with st.chat_message("assistant", avatar="🌡️"):
        status = st.status("🧠 Agent planning the analysis…", expanded=True)
        stream_box = st.empty()
        step_count = 0

        def on_event(msg: str) -> None:
            global step_count
            stream_box.empty()  # a new step started — clear partial text
            if msg.startswith("[tool ]"):
                step_count += 1
                call = msg[7:].strip()
                status.update(label=f"🔧 Step {step_count} — calling FortyGuard…")
                status.markdown(
                    f'<div class="ho-step">🔧 <code>{call}</code></div>',
                    unsafe_allow_html=True,
                )
            else:
                text = msg.replace("[agent]", "").strip()
                status.markdown(
                    f'<div class="ho-step">🧠 {text}</div>', unsafe_allow_html=True
                )

        def on_token(text: str) -> None:
            stream_box.markdown(text + " ▌")

        agent = HeatOpsAgent()
        try:
            answer = agent.run(brief, on_event=on_event, on_token=on_token)
            status.update(
                label=f"✅ Analysis complete — {len(agent.audit_trail)} API call(s)",
                state="complete",
                expanded=False,
            )
        except Exception as e:
            status.update(label="❌ Agent error", state="error", expanded=True)
            status.error(f"{type(e).__name__}: {e}")
            answer = (
                "The agent hit an error while running the analysis — see the "
                "log above. Please try again or rephrase the brief."
            )

        stream_box.markdown(answer)
        trail = agent.audit_trail
        if trail:
            with st.expander(f"🔍 Audit trail — {len(trail)} API call(s)"):
                st.json(trail)

    st.session_state.history.append(
        {"role": "assistant", "text": answer, "trail": trail}
    )
