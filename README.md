# SehatSathi — an AI follow-up agent for India's frontline health workers

**Code for a Billion — Bharat Agentic-AI Hackathon 2026 (Code for India) · Health impact area**
Author: **Prasad Dimba Anandappa** · GitHub: [@prasad-anandappa](https://github.com/prasad-anandappa) · License: MIT

> An ASHA worker ends her day with a page of hand-written visit notes and a
> register she must somehow turn into tomorrow's plan. SehatSathi does that
> turning for her: paste the day's notes, and the agent extracts every patient
> who needs follow-up, ranks them by explainable risk, **flags danger signs
> for same-day escalation**, builds tomorrow's village-by-village route, and
> writes a simple reminder for every patient — in **all 22 scheduled Indian
> languages plus English**, each in its native script.

---

## The problem (judging: size + severity)

- India has **about 10 lakh (≈1 million) ASHA frontline workers**, each
  serving a village population of roughly **1,000–2,500 people** — the
  backbone of primary care for hundreds of millions of rural citizens.
- Their follow-up load is unforgiving and easy to drop: pregnant mothers due
  for antenatal (ANC) checkups, TB patients who must not miss DOTS doses,
  children inside narrow immunization windows, new mothers in the risky
  first days after delivery.
- The failure modes are severe, not clerical: a missed danger sign
  (bleeding, convulsions, reduced fetal movement, a baby not feeding) can
  become a maternal or infant death; interrupted TB treatment breeds
  drug-resistant TB; a missed vaccine window leaves a child unprotected.
- The constraint is real-world: **patchy connectivity, low-end phones,
  paper-first workflows.** A solution that needs a cloud LLM to rank a
  register will fail exactly where it is needed most.

## The solution

An agent loop in one inspectable pass — **perceive → reason → act**:

| Step | Tool | What it does |
|---|---|---|
| Perceive | `extract.py` | Rule-based parser for free-text / voice-transcript-style notes (English + common Hindi words, Hindi digits too). Finds category (pregnant / TB / child / postpartum / elderly), due dates ("due in 3 days", "overdue by 10 days", ISO dates), missed doses, risk factors, and **14 danger-sign patterns**. Danger-sign matching is **negation-aware** ("no bleeding" never escalates) and swelling only counts as taught in ASHA training (face/hands). An **ABHA id written in a note is recorded as written** — no ABDM lookup, no verification claimed. Never invents a patient who is not in the notes. |
| Reason | `risk.py` | Deterministic, **explainable** scoring: every point carries a written reason ("DANGER SIGN: severe headache…", "immunization overdue by 10 days"). Danger sign ⇒ `CRITICAL`, always first. |
| Act — plan | `planner.py` | Tomorrow's route: danger first, then risk, villages grouped so the worker walks one sane route; 40-minute slots from 09:00 with a midday break. The route cap (12) is explicit: anyone beyond it is **named in the report as deferred**, never silently dropped. |
| Act — remind | `messages.py` + `langs/` | Per-patient reminders in **23 languages** (all 22 Eighth-Schedule languages + English), simple words, native script, ready to copy into SMS/WhatsApp. Critical cases carry **112 + 108** in every language. Child/postpartum/elderly follow-ups also get a **family/caregiver note**. |
| Helplines | `helplines.py` | Verified Indian helpline directory (112 · 108 · 102 · 104 · PM-JAY 14555 · Nikshay TB 1800-11-6666 · Child 1098 · Women 181 · Tele-MANAS 14416 · Elder 14567), routed by situation. |
| UI | `ui.py` | Phone-browser page over the same core: inline CSS, **no JavaScript**, under 30 KB, works on low-end phones and patchy connections. Language picker is a plain form — it works with JavaScript disabled. Nothing typed is stored. |
| Optional LLM | `llm.py` | Env-gated, OpenAI-compatible rephrasing for warmth **only**. An LLM never decides priority, danger signs or dates. Off by default; silent fallback to templates. |

**Offline by design:** the core is pure Python stdlib — no dependencies, no
API key, no network. The FastAPI layer is a thin shell for cloud deployment.

## Run it in under 15 minutes (judges)

```bash
git clone https://github.com/prasad-anandappa/sehatsathi.git
cd sehatsathi

# 1) Zero-install demo (stdlib only)
PYTHONPATH=src python3 -m sehatsathi.cli --notes data/sample_notes.txt --date 2026-11-02

# 2) Tests (needs pytest; API tests also need fastapi/httpx)
pip install -e ".[dev,api]"
pytest -q            # 79 tests

# 3) API / deployed form
uvicorn sehatsathi.api:app --port 8000     # after: pip install -e ".[api]"
#    → GET /health · GET /demo · POST /plan {"notes": "...", "today": "2026-11-02"}
#    → screening-to-care loop: POST /screening/intake · GET /loop ·
#      POST /loop/refer · POST /loop/confirm · GET /loop/closure
#    → interactive docs at http://localhost:8000/docs
```

Sample output (from `data/sample_notes.txt`, 10 patients): **3 same-day
escalations** found (a pregnant mother with severe headache + facial
swelling, a TB patient coughing blood, a postpartum mother whose baby is
not feeding), a 10-visit timed route for the next day, and 10 reminders —
each written in all 23 languages.

## Production build (v1.4.0)

The screening-to-care loop shipped in v1.3.0 for the Future Health
challenge as an **in-memory demo store**. v1.4.0 makes the deployed
service production-shaped (full detail + verification evidence in
[`AUDIT.md`](AUDIT.md)):

- **Durable storage** — one `DurableScreeningLoop` per worker, mirrored
  into SQLAlchemy (SQLite file by default, Postgres via
  `SEHATSATHI_DATABASE_URL`) after every mutation: cases, guarded
  state transitions (screened → referred → care confirmed), visit
  notes and follow-up plans all survive restarts. Nightly on-box DB
  backups (InvoicePilot pattern).
- **Worker accounts** — phone + OTP login (`SEHATSATHI_AUTH_MODE=otp`):
  hashed codes with expiry + attempt caps, hashed expiring session
  tokens, per-worker case isolation. A **supervisor** role (phones in
  `SEHATSATHI_SUPERVISOR_PHONES`) gets a read-only aggregate view —
  counts and closure summaries, **never visit-note contents**.
- **Demo surfaces stay demo** — `/demo`, `/loop/demo` and the no-JS
  loop UI run on synthetic/throwaway data only, labelled as such.
- **Hardening** — app-level rate limiting, security headers, `.env`
  via a 600-permission EnvironmentFile, log rotation.
- **Live at https://sehatsathi.nammaprojects.com** — DNS A record in
  place, nginx vhost + rate-limit zone enabled, Let's Encrypt cert
  (expires 2027-02-05, auto-renew), uvicorn bound to localhost
  behind nginx (the raw `:8105` port is no longer public). OTP
  *delivery* is configured: the app submits via local Exim with
  SMTP AUTH using a dedicated mailbox (`sehatsathi@webnetism.in`),
  and Exim relays out through the Brevo smarthost — the full
  request → email → verify → session flow is proven end-to-end on
  the deployed service (see `AUDIT.md`). The only operator input
  left is the real supervisors' phone numbers
  (`SEHATSATHI_SUPERVISOR_PHONES`, currently unset).

## Languages (23)

Reminders, caregiver notes and the web UI ship in English + all 22
Eighth-Schedule languages: Assamese · Bengali · Bodo · Dogri · Gujarati ·
Hindi · Kannada · Kashmiri · Konkani · Maithili · Malayalam · Manipuri
(Meitei Mayek) · Marathi · Nepali · Odia · Punjabi · Sanskrit · Santali
(Ol Chiki) · Sindhi · Tamil · Telugu · Urdu.

Honesty note: every language is covered by automated tests (string
completeness, placeholders, native-script rendering, encoding). Twelve
were additionally desk-checked string-by-string against the English
source by the maintainers; **eleven — Assamese, Bodo, Dogri, Kashmiri,
Konkani, Maithili, Manipuri, Odia, Sanskrit, Santali, Sindhi — are
marked `provisional` in `src/sehatsathi/i18n.py` and need a
native-speaker read before field use** (their translators rated them
medium confidence or lower). That status is recorded in the code,
not hidden.

## Demo

- **Live-shaped demo:** run the API and open `/demo` — it runs the agent on
  the sample day-notes and returns the full plan as JSON.
- **Video script:** [`DEMO-SCRIPT.md`](DEMO-SCRIPT.md) — the exact 2–3 minute
  walkthrough to record (problem → notes in → escalations → route → reminders).
- **Submission pack:** [`SUBMISSION.md`](SUBMISSION.md) — every field of the
  official GitHub submission form, filled in and ready to paste.

## Built in AgentFoundry

This project is built for the hackathon's official IDE, **AgentFoundry.me**.
The code here is the project's real codebase (plain Python, no lock-in);
[`AGENTFOUNDRY-ACCESS.md`](AGENTFOUNDRY-ACCESS.md) documents exactly how it is
opened/continued inside the AgentFoundry IDE (sign-up → create project →
connect this GitHub repo → build/deploy), including the one step that needs
the author's own account sign-in.

## Honest impact note (judging: proven impact)

This is a working, tested agent with synthetic sample data — **no field
deployment with real patients is claimed**, and no real patient data is in
this repo. The impact path is concrete: the agent removes the nightly
register-sorting work (the report estimates worker-minutes saved per day),
and — more importantly — makes the three highest-severity misses (danger
signs, TB interruption, overdue immunization) structurally hard to miss.
A pilot with one PHC cluster is the stated next step after the hackathon;
the offline design means a pilot needs no infrastructure beyond a phone.

## Safety & scope

- SehatSathi **supports, never replaces,** the health worker and the PHC
  medical officer. Every escalation instructs human referral — the agent
  gives no diagnosis and no treatment advice.
- Danger-sign lists follow the red flags taught in ASHA training; a medical
  review is required before any clinical deployment.
- Synthetic data only in this repository.

## Layout

```
src/sehatsathi/  extract.py · risk.py · planner.py · messages.py
                 helplines.py · ui.py · i18n.py · langs/ (23 languages)
                 llm.py (optional) · agent.py (orchestrator) · cli.py
                 api.py (FastAPI shell) · loop.py (loop logic) ·
                 loop_store.py (durable per-worker store) · db.py ·
                 auth.py · otp.py · config.py (production layer)
tests/           79 pytest tests (extraction, risk, India features,
                 languages, UI, API, loop, production layer)
data/            sample_notes.txt — one synthetic day of ASHA notes
```

Built for **Code for a Billion 2026**. Sehat = health, Sathi = companion —
a companion for the worker, so the worker can be there for everyone else.
