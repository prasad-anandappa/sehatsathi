# Submission pack — Code for a Billion 2026

Submit at: https://github.com/karlmehta/code-for-a-billion/issues/new?template=submission.yml
Deadline: **15 November 2026** · Author of record: **Prasad Dimba Anandappa**

- **Project name:** SehatSathi
- **Impact area:** Health
- **GitHub repo:** https://github.com/prasad-anandappa/sehatsathi
- **Built with:** AgentFoundry (official IDE) — project continued/deployed
  from the AgentFoundry IDE; see `AGENTFOUNDRY-ACCESS.md` in the repo.
- **Demo:** 2–3 min video (record per `DEMO-SCRIPT.md`) or live link —
  run the repo's API and open `/demo`.
- **License:** MIT

**Problem statement (paste-ready):**
India's ~10 lakh ASHA frontline health workers each cover 1,000–2,500 people
and personally track who is due for what: antenatal checkups, TB doses,
immunizations, postnatal visits. That tracking lives in paper registers and
memory. When a follow-up is missed, the cost is not paperwork — a pregnancy
danger sign seen a day late, TB treatment interrupted, a vaccine window
closed. SehatSathi is an agent that takes the worker's end-of-day visit
notes and returns (1) same-day escalations for danger signs, (2) a
risk-ranked, village-grouped visit plan for tomorrow, and (3) a simple
a reminder for every patient in all 22 scheduled Indian languages plus
English, each in its native script. It runs fully offline with
explainable, deterministic rules — because the villages it serves have the
least connectivity and the most at stake.

**Proven-impact honesty line (keep in the submission):** tested working
agent, 117 automated tests, synthetic sample data; no real-patient field
deployment is claimed yet — a one-PHC pilot is the next step.

---

## Filing asset checklist (refresh/verify pass — 2026-11-07)

Verified against the live product on 2026-11-07: `GET
https://sehatsathi.nammaprojects.com/health` → `version 1.5.0,
storage durable, auth_mode otp`; local suite re-run → **117 passed**
(clean venv, `pip install -e ".[dev,api]"`). Repo above is this
checkout's `origin`. Everything agent-side below is filing-ready;
the only remaining step is the founder's own AgentFoundry sign-up +
project creation (see `AGENTFOUNDRY-ACCESS.md` §"The blocker").

Assets the filing needs, and their state:

- [x] This pack — every field paste-ready, facts refreshed to
      v1.5.0 / 117 tests (2026-11-10).
- [x] Public GitHub repo, README with run instructions, MIT licence.
- [x] Live demo link — https://sehatsathi.nammaprojects.com
      (`/demo` for the JSON plan, `/loop/ui` for the loop demo).
- [ ] **Demo video (2–3 min)** — a SehatSathi pitch video already
      exists (YouTube link carried in the Future Health pack; local
      MIT Solve pitch video in the workspace), but it is a pitch asset,
      not the CFB `DEMO-SCRIPT.md` product walkthrough; if the filing
      uses a video rather than the live link, record/refresh per
      `DEMO-SCRIPT.md` (script refreshed to 117 tests 2026-11-10).
- [ ] **Screenshots for the submission gallery** — no product-UI
      captures for this filing exist yet (branding/pitch images under
      `~/workspace/imagine_media/` are not UI captures); capture at
      filing time: (1) live home page
      (sehatsathi.nammaprojects.com), (2) `/loop/ui` demo with the
      sample camp list loaded, (3) a worker `/worker` page after
      OTP sign-in, (4) one localised reminder page (e.g. Kannada),
      (5) `pytest -q` output showing 117 passed.
- [ ] **AgentFoundry IDE screenshot** — evidence of the project open
      in the official IDE; can only be captured inside the
      founder's signed-in AgentFoundry session (see
      `IMPROVEMENT-PACK-1.md`).
