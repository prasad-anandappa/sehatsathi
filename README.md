# SehatSathi — an AI follow-up agent for India's frontline health workers

**Code for a Billion — Bharat Agentic-AI Hackathon 2026 (Code for India) · Health impact area**
Author: **Prasad Dimba Anandappa** · GitHub: [@prasad-anandappa](https://github.com/prasad-anandappa) · License: MIT

> An ASHA worker ends her day with a page of hand-written visit notes and a
> register she must somehow turn into tomorrow's plan. SehatSathi does that
> turning for her: paste the day's notes, and the agent extracts every patient
> who needs follow-up, ranks them by explainable risk, **flags danger signs
> for same-day escalation**, builds tomorrow's village-by-village route, and
> writes a simple reminder for every patient — in English and Hindi.

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
| Perceive | `extract.py` | Rule-based parser for free-text / voice-transcript-style notes (English + common Hindi words, Hindi digits too). Finds category (pregnant / TB / child / postpartum / elderly), due dates ("due in 3 days", "overdue by 10 days", ISO dates), missed doses, risk factors, and **14 danger-sign patterns**. Never invents a patient who is not in the notes. |
| Reason | `risk.py` | Deterministic, **explainable** scoring: every point carries a written reason ("DANGER SIGN: severe headache…", "immunization overdue by 10 days"). Danger sign ⇒ `CRITICAL`, always first. |
| Act — plan | `planner.py` | Tomorrow's route: danger first, then risk, villages grouped so the worker walks one sane route; 40-minute slots from 09:00 with a midday break. |
| Act — remind | `messages.py` | Per-patient reminders in simple English + simple Hindi (Devanagari), ready to copy into SMS/WhatsApp. Critical cases get an urgent "call 108 / go to PHC" message. |
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
pytest -q            # 18 tests

# 3) API / deployed form
uvicorn sehatsathi.api:app --port 8000     # after: pip install -e ".[api]"
#    → GET /health · GET /demo · POST /plan {"notes": "...", "today": "2026-11-02"}
#    → interactive docs at http://localhost:8000/docs
```

Sample output (from `data/sample_notes.txt`, 10 patients): **3 same-day
escalations** found (a pregnant mother with severe headache + swelling, a TB
patient coughing blood, a postpartum mother whose baby is not feeding), a
10-visit timed route for the next day, and 10 bilingual reminders.

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
                 llm.py (optional) · agent.py (orchestrator) · cli.py · api.py
tests/           18 pytest tests (extraction, agent, API)
data/            sample_notes.txt — one synthetic day of ASHA notes
```

Built for **Code for a Billion 2026**. Sehat = health, Sathi = companion —
a companion for the worker, so the worker can be there for everyone else.
