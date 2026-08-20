# 🌡️ HeatOps Agent

**An agentic urban-heat analyst built on FortyGuard's Temperature API** — FortyGuard Hackathon '26, Track 6 (Agentic).

Give it a plain-language brief ("find the hottest bus stops in Phoenix at 2pm last July and tell me which two to shade first") and the agent plans the analysis, chooses and sequences the right FortyGuard endpoints, executes them with polite polling and disk caching, and returns a **ranked, source-cited action plan** — every quantitative claim cites the `activity_id` of the API call that produced it, so the output is fully auditable.

## Problem → User → FortyGuard usage → Result

- **Problem:** Urban-heat decisions (where to add shade, when to halt outdoor work, which route to cool) require hyperlocal data analysis that most city staff can't do by hand.
- **User:** City planners, HSE managers, and logistics operators who can describe a goal in English but not write GIS pipelines.
- **FortyGuard usage:** `/v1/heatmap` (polygon thermal analysis), `/v1/env_params` (point-level heat index & environment), `/v1/status/{id}` (async polling), `/v1/system/fetch-api-key-usage` (credit awareness before batches).
- **Result:** Plain brief in → ranked, audit-trailed intervention list out, in minutes.

## Architecture

```
brief ──► LLM planner (Claude tool-use loop)
              │  plans steps, picks tools
              ▼
        ToolRunner ──► FortyGuardClient (submit ─► poll /v1/status)
              │              │  disk cache: never pay twice
              │              ▼
              │        audit trail (activity_ids)
              ▼
   ranked action plan, every number cited [act: …]
```

- `heatops/fg_client.py` — API client: submit-then-poll, exponential backoff, SHA-keyed disk cache.
- `heatops/tools.py` — tool schemas exposed to the model + safe dispatcher + audit trail.
- `heatops/agent.py` — the agent loop and system policy (coverage guardrails: U.S.-only, 2021→now+12h, ≤130 km² AOIs).
- `app.py` — Streamlit chat UI with live tool-call log and audit-trail viewer (the demo link).
- `cli.py` — terminal runner for quick tests and the demo video.

## Setup

```bash
git clone <this-repo> && cd heatops-agent
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # paste your FortyGuard key + LLM credentials (see below)
streamlit run app.py    # or: python cli.py "your brief here"
```

### LLM backend

The agent brain is pluggable via `.env`:

- **Anthropic (default):** set `ANTHROPIC_API_KEY`; uses native tool calling
  with `claude-sonnet-4-6`.
- **Any OpenAI-compatible endpoint** (vLLM, LiteLLM, a self-hosted gateway):
  set `HEATOPS_LLM_BASE_URL`, `HEATOPS_LLM_API_KEY`, and `HEATOPS_MODEL`.
  Native tool calling is **not** required — tools are negotiated through a
  prompt-based JSON protocol that the agent loop parses, with automatic
  continuation when a completion is truncated mid-thought.

Large heatmap results (~1.4 MB of tile GeoJSON) are summarized to ~1 KB of
statistics (overall min/max/mean/σ plus the hottest and coolest tiles with
centroids) before being fed back to the model, so any 32k-context model can
reason over city-scale analyses.

### Deploy on Streamlit Community Cloud

1. Push this repo to GitHub and create the app at share.streamlit.io
   (branch `main`, main file `app.py`).
2. In the app's **Settings → Secrets**, add your keys in TOML form —
   never commit them to the repo:

   ```toml
   FORTYGUARD_API_KEY = "..."
   ANTHROPIC_API_KEY = "sk-ant-..."   # or the HEATOPS_LLM_* trio instead
   ```

   Configuration is read from environment variables first and falls back
   to `st.secrets` (see `heatops/config.py`), so the same code runs
   locally with `.env` and on the cloud with Secrets. Note that an
   OpenAI-compatible gateway used in the cloud must be publicly
   reachable — private/campus-network hosts won't work from Streamlit's
   servers.

## Notes for judges

- Failed FortyGuard tasks cost nothing; the client logs `activity_id` on every call for debugging and audit.
- All analysis respects platform constraints: U.S. geographies, dates 2021-01-01 → now (+12 h heatmap forecast), AOIs under ~130 km².
- The cache means re-running the demo consumes zero additional credits.
