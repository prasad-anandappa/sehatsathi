# Improvement Pack #1 — SehatSathi (Code for a Billion, deadline 15 Nov 2026)

**Status:** Pass #1 proposals — DIFFED, NOT YET APPLIED. Parent applies these to
`SUBMISSION.md` / `README.md` / `DEMO-SCRIPT.md` at filing time, after Prasad's
AgentFoundry step. Nothing here changes code.
**Verification basis (3 Nov 2026):** every number below was re-checked against a
live local run — `pytest -q` → **18 passed**; CLI on `data/sample_notes.txt`
(2026-11-02) → **10 patients · 3 escalations · 10 visits planned**, villages =
Rampur + Kishanpur (2); `est_worker_minutes_saved` basis read in `src/sehatsathi/agent.py`.
**Code polish verdict:** none. `py_compile` clean, no TODO/stub markers, 18/18
tests pass — working code is not churned in this pass.

---

## A. SUBMISSION.md improvements

### S1 — Add an explicit judging-criteria map (currently absent; judges must infer it)
Insert after the problem statement, before the honesty line:

```diff
+**How this maps to the judging criteria (25% each):**
+- **Problem size:** ~10 lakh ASHA workers, each personally tracking follow-ups
+  for 1,000–2,500 people — antenatal checkups, TB doses, immunizations,
+  postnatal visits — from paper registers and memory.
+- **Problem severity:** a missed follow-up is not a missed appointment — it is
+  a pregnancy danger sign seen a day late, TB treatment interrupted (breeding
+  drug resistance), or a vaccine window closed for good.
+- **Solution quality:** a working perceive → reason → act agent — notes in;
+  (1) same-day danger-sign escalations, (2) a risk-ranked, village-grouped
+  plan for tomorrow with a written reason for every ranking, (3) an
+  English+Hindi reminder per patient — fully offline, deterministic and
+  explainable, with 18 automated tests. No LLM ever decides priority, danger
+  signs, or dates.
+- **Proven impact:** on the bundled sample day, 10 notes become 3 same-day
+  escalations, a 10-visit timed route, and 10 bilingual reminders (run it:
+  see Demo). No field deployment is claimed yet — a one-PHC pilot is next.
```
**Rationale:** the event judges score 25×4 (size / severity / solution quality / proven impact, per BUILD-LOG); naming each criterion with its proof makes scoring effortless instead of inferential.

### S2 — Lead the problem statement with the verified sample result
Append to the end of the existing problem statement paragraph:

```diff
  English+Hindi reminder for every patient. It runs fully offline with
  explainable, deterministic rules — because the villages it serves have the
  least connectivity and the most at stake.
+On the bundled sample day that is concrete: 10 handwritten-style notes in →
+3 patients escalated the same day, a timed 10-visit route for tomorrow, and
+10 bilingual reminders out.
```
**Rationale:** moves the submission from describing a promise to quoting a reproducible result a judge can re-run in under a minute.

### S3 — Replace the vague Demo field with exact judge instructions
```diff
-- **Demo:** 2–3 min video (record per `DEMO-SCRIPT.md`) or live link —
-  run the repo's API and open `/demo`.
+- **Demo:** 2–3 min video (script: `DEMO-SCRIPT.md` in the repo). No-video
+  fallback, zero install: clone the repo and run
+  `PYTHONPATH=src python3 -m sehatsathi.cli --notes data/sample_notes.txt --date 2026-11-02`
+  — the first screen is the proof: 10 patients, 3 same-day escalations.
+  API form: `pip install -e ".[api]"`, `uvicorn sehatsathi.api:app --port 8000`,
+  then open `/demo`.
```
**Rationale:** the current field tells a judge to "run the API" with no command; the replacement gives a zero-install path first, so the demo cannot fail on setup.

### S4 — Expand the honesty line into a Proven / Not-yet / Next triad
```diff
-**Proven-impact honesty line (keep in the submission):** tested working
-agent, 18 automated tests, synthetic sample data; no real-patient field
-deployment is claimed yet — a one-PHC pilot is the next step.
+**Proven impact — stated plainly:** *Proven today:* a working, tested agent
+(18 automated tests) that turns one day of synthetic ASHA notes into 3
+same-day escalations, a timed 10-visit route, and 10 bilingual reminders;
+its summary also reports estimated worker-minutes saved (≈25 min per patient
+of register-sorting and reminder-writing, per the basis stated in the code).
+*Not yet claimed:* any real-patient field deployment — all sample data is
+synthetic. *Next step:* a one-PHC pilot.
```
**Rationale:** "proven impact" is a scored criterion; separating what is proven, what is not claimed, and what is next scores the honesty instead of burying it in one line.

### S5 — Make the AgentFoundry line true at the moment of filing (apply LAST, after Prasad's step)
```diff
-- **Built with:** AgentFoundry (official IDE) — project continued/deployed
-  from the AgentFoundry IDE; see `AGENTFOUNDRY-ACCESS.md` in the repo.
+- **Built with:** AgentFoundry (official IDE) — the SehatSathi project was
+  created under the author's account in AgentFoundry and this public repo
+  was opened/continued there; the exact flow is documented in
+  `AGENTFOUNDRY-ACCESS.md` in the repo.
```
**Rationale:** the current wording can be read as claiming a completed deployment before it happens; this version states exactly the step Prasad performs, and must only be pasted once he has performed it.

---

## B. README.md improvements

### R1 — Add the same judging map to the README, right after the intro quote
Insert before `## The problem`:

```diff
+## For the judges — the 60-second version
+
+| Criterion (25% each) | Where to see it |
+|---|---|
+| Problem size | ~10 lakh ASHA workers × 1,000–2,500 people each, tracked on paper — §The problem |
+| Problem severity | Missed danger sign → maternal/infant risk; interrupted TB → drug resistance — §The problem |
+| Solution quality | Offline, deterministic, explainable agent; every ranking carries its reason — §The solution |
+| Proven impact | Bundled sample: 10 notes → 3 same-day escalations, 10-visit route, 10 bilingual reminders; 18 tests — §Run it, §Honest impact note |
+
```
**Rationale:** judges land on the README first; a criteria-to-section index routes them to the evidence instead of hoping they read linearly.

### R2 — Add a "60-second judge demo" ahead of the 15-minute run section
Insert at the top of `## Run it in under 15 minutes (judges)`:

```diff
+**60-second version (zero install, stdlib only):**
+```bash
+PYTHONPATH=src python3 -m sehatsathi.cli --notes data/sample_notes.txt --date 2026-11-02
+```
+Expected first lines: `Patients: **10** · Escalations: **3** · Visits planned: **10**` —
+then the three escalations (a pregnant mother with severe headache + swelling,
+a TB patient coughing blood, a postpartum mother whose baby is not feeding),
+tomorrow's timed route with a written reason per visit, and 10 English+Hindi
+reminders. The full setup below adds the tests and the API.
+
```
**Rationale:** the README currently opens the judge path with a clone + install sequence; a single-command, expected-output-stated demo proves the project before any setup friction.

### R3 — De-jargon the Demo section's first bullet
```diff
-- **Live-shaped demo:** run the API and open `/demo` — it runs the agent on
-  the sample day-notes and returns the full plan as JSON.
+- **No-recording demo:** run the API (`pip install -e ".[api]"`, then
+  `uvicorn sehatsathi.api:app --port 8000`) and open
+  `http://localhost:8000/demo` — it runs the agent on the sample day-notes
+  and returns the full plan as JSON.
```
**Rationale:** "live-shaped" is internal shorthand a judge cannot parse, and the bullet omitted the actual command and URL it asks them to use.

### R4 — Make the minutes-saved claim in the Honest impact note checkable
```diff
-This is a working, tested agent with synthetic sample data — **no field
-deployment with real patients is claimed**, and no real patient data is in
-this repo. The impact path is concrete: the agent removes the nightly
-register-sorting work (the report estimates worker-minutes saved per day),
-and — more importantly — makes the three highest-severity misses (danger
-signs, TB interruption, overdue immunization) structurally hard to miss.
+This is a working, tested agent with synthetic sample data — **no field
+deployment with real patients is claimed**, and no real patient data is in
+this repo. The impact path is concrete: the agent removes the nightly
+register-sorting work (every report summary carries an explicit
+estimated-minutes-saved figure — basis stated in the code: ≈25 min per
+patient of manual register sorting + reminder writing vs. one pasted note
+list), and — more importantly — makes the three highest-severity misses
+(danger signs, TB interruption, overdue immunization) structurally hard
+to miss.
```
**Rationale:** the current parenthetical asserts an estimate without its basis; naming the basis (and where it lives in the code) turns a soft claim into a verifiable one.

### R5 — State the sample result once, numerically, under the title quote
Append to the blockquote intro:

```diff
 > writes a simple reminder for every patient — in English and Hindi.
+>
+> **On the bundled sample day:** 10 notes → **3 same-day escalations**,
+> a timed **10-visit route** for tomorrow, and **10 bilingual reminders** —
+> offline, in one command (see *Run it* below).
```
**Rationale:** the README's strongest proof currently sits mid-page in prose; surfacing the verified 10 → 3 / 10 / 10 result at the top gives a skimming judge the outcome before the argument.

---

## C. DEMO-SCRIPT.md — two factual defects to fix in the same pass (demo asset)

### D1 — The sample notes are synthetic, and cover two villages — not "one real evening", not three
```diff
-**0:25–0:50 — Input.** Show `data/sample_notes.txt`. "This is one real
-evening's notes, the way a worker actually writes them — one line per
-patient, simple words. Ten patients, three villages' worth of problems
-hidden in plain text."
+**0:25–0:50 — Input.** Show `data/sample_notes.txt`. "This is one
+evening's notes — synthetic sample data, written the way a worker
+actually writes them — one line per patient, simple words. Ten patients,
+two villages' worth of problems hidden in plain text."
```
**Rationale:** the current line contradicts the repo's own synthetic-data honesty claim (data header, README, BUILD-LOG) and miscounts the sample's villages (Rampur + Kishanpur = 2) — both are judge-visible credibility risks in a recorded demo.

### D2 — Fix the garbled escalation line (the 3 escalations are two women and one man)
```diff
-"Before tomorrow is even planned, SehatSathi stops her: THREE women and
-patients need help TODAY — a pregnant mother with severe headache and
-swelling, a TB patient coughing blood, a new mother whose baby won't
-feed. Each gets an escalation action and an urgent message — call 108,
-go to the PHC, do not wait."
+"Before tomorrow is even planned, SehatSathi stops her: THREE patients
+need help TODAY — a pregnant mother with severe headache and swelling,
+a TB patient coughing blood, a new mother whose baby won't feed. Each
+gets an escalation action and an urgent message — call 108, go to the
+PHC, do not wait."
```
**Rationale:** "THREE women and patients" is both garbled and inaccurate against the verified sample output; the replacement matches the three named escalations exactly.

---

## Suggested Pass #2 (after Prasad's AgentFoundry step — parent's lane)
Insert the real artefacts this pass cannot invent: AgentFoundry screenshot
evidence, the deployed `/demo` live link, and the recorded demo-video URL into
S3/R3's fields; then re-verify SUBMISSION.md reads true end-to-end before filing.
