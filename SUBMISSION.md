# HeatOps — FortyGuard Hackathon '26 Submission Materials

## Written summary (498 words)

**Problem.** Cities are making billion-dollar heat-mitigation decisions —
where to install shade, when to halt outdoor work, which corridors to cool —
with data their staff cannot analyze. Hyperlocal temperature intelligence
exists, but turning it into a decision requires choosing the right endpoints,
building polygons, polling async tasks, and aggregating tile-level results:
a GIS pipeline most city planners, HSE managers, and logistics operators
will never write.

**User.** Anyone who can describe a heat question in plain English but not
code the analysis: a transit planner deciding which bus stops to shade, a
construction HSE manager deciding whether the afternoon shift is safe, a
facilities team choosing where trees go first.

**What HeatOps does.** HeatOps is an autonomous agent on top of FortyGuard's
Temperature API. The user types a brief; the agent restates the goal, writes
a numbered plan, then selects and sequences FortyGuard calls on its own —
submitting tasks, polling `/v1/status/{id}` with exponential backoff, and
caching every completed result on disk so repeated analyses never spend
credits twice. Every quantitative claim in the final answer cites the
`activity_id` of the API call that produced it, making the output fully
auditable — the UI exposes the complete audit trail alongside the answer.

**FortyGuard endpoints used.** `/v1/heatmap` (polygon thermal analysis;
the agent auto-builds and auto-closes GeoJSON polygons from plain-language
locations), `/v1/env_params` (point-level apparent temperature, wet-bulb,
humidity, AQI, solar irradiance), `/v1/status/{id}` (async polling), and
`/v1/system/fetch-api-key-usage` (credit awareness before batches). Because
a city-scale heatmap returns ~1.4 MB of tile GeoJSON (3,430 tiles in our
Miami run), HeatOps compresses each result to ~1 KB of statistics — overall
min/max/mean/σ plus the hottest and coolest tiles with centroid coordinates —
so the agent reasons over city-scale data without drowning in it.

**Measured results.** (1) *Phoenix bus stops:* given three stops and one
sentence of intent, the agent made three `env_params` calls and ranked them:
the hottest stop (33.4550, −112.0660) hit **41.4 °C apparent temperature**
at 14:00 on 2025-07-15 — **1.1 °C hotter than the coolest** — and it
recommended the top two for shading, each figure cited to its activity_id.
(2) *Miami district heatmap:* a full-day `/v1/heatmap` over ~65 km² returned
3,430 tiles; the agent located the hottest cluster at (25.726, −80.157),
averaging **30.8 °C with peaks above 33 °C, ~2.8 °C hotter than the coolest
tile**, and recommended it as the first shading site. (3) *Construction
brief:* from apparent temperature 38.1 °C and wet-bulb 26.2 °C the agent
returned a reschedule verdict with work-rest cycles and hydration protocol.

**Why it matters.** HeatOps turns FortyGuard from an API into an analyst:
plain brief in, ranked and fully auditable intervention plan out, in
minutes — with disk caching that makes every re-run free.

---

## Demo video script (~3 min)

**0:00–0:15 — Context (Dashboard).** Screen on the FortyGuard dashboard
heatmap of San Jose. Voiceover: "This is hyperlocal heat data — 2-meter
resolution. Powerful, but turning it into a decision takes a GIS pipeline.
HeatOps makes it a conversation."

**0:15–0:35 — Problem & user.** Cut to the HeatOps UI. "City planners and
safety managers know their question — which bus stops do we shade first? —
but not the API calls. HeatOps is an agent that plans the analysis itself."

**0:35–1:40 — The agent working.** Type the Phoenix brief (or click the
sidebar example): *"Rank these Phoenix bus stops by 2pm heat on 2025-07-15
and say which two to shade first: (33.4484,−112.0740), (33.4550,−112.0660),
(33.4300,−112.0900)."* Let the live tool-call log run. Voiceover while it
streams: "Watch the log — the agent states a plan, then calls FortyGuard's
env_params endpoint for each stop, submitting each task and polling its
status. Failed tasks cost nothing; completed ones are cached on disk, so
re-running this demo is free."

**1:40–2:20 — The answer.** Scroll the final answer. "Every number here
came from the API — the hottest stop hit 41.4 degrees apparent temperature,
1.1 degrees above the coolest — and every claim carries the activity_id of
the call that produced it." Point at an `[act: …]` citation.

**2:20–2:50 — Audit trail.** Expand the audit-trail panel. "This is the
full record: every endpoint, every argument, every activity_id, and whether
it came from cache. The output isn't just actionable — it's auditable."

**2:50–3:00 — Close.** "HeatOps: plain-language brief in, source-cited heat
intervention plan out, built on FortyGuard's Temperature API."

---

## Submission checklist

- [ ] Push repo to GitHub (**verify `.env` is NOT in the repo** — it is
      gitignored; `.env.example` now contains placeholders only).
- [ ] Add `Hackathon-FG` (hackathon@fortyguard.com) as a repo collaborator.
- [ ] Deploy on share.streamlit.io from `app.py`; put keys in app Secrets.
- [ ] Record the 3-minute video against the deployed app.
- [ ] Paste the written summary into the hackathon form.
