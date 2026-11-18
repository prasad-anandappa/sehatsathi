# Build log — SehatSathi

**2026-11-02 (Mon, America/Phoenix)** — initial build, 13 days before the
15 Nov 2026 submission deadline.

## What was done
1. **Rules verified** from official sources (codeforindia.org/hackathon,
   submission hub `karlmehta/code-for-a-billion` README + JUDGING.md):
   build in AgentFoundry, public GitHub repo + README, 2–3 min demo or live
   link, structured GitHub submission form, MIT/Apache-2.0, judging
   25×4 (size, severity, solution quality, proven impact).
2. **AgentFoundry scouted** (web only, no sign-in) — see
   `AGENTFOUNDRY-ACCESS.md`. Verdict: open-signup indicated ("full IDE free
   for everyone — no trial, no expiry", wiki), downloadable IDE,
   GitHub-connect + real terminal ⇒ this codebase can be opened/continued
   there. **Remaining human step: Prasad's own sign-up + project creation
   under his account.**
3. **Agent built** — deterministic offline core (stdlib only):
   extract → explainable risk score → village-grouped route plan →
   EN/HI reminders; optional env-gated LLM rephrasing behind an interface;
   FastAPI shell + CLI + Dockerfile for "deployed on any cloud".
4. **Tests: 18 passed** (`pytest -q`, extraction/agent/API). Live demo on
   sample notes: 10 patients → 3 CRITICAL escalations, 10-visit plan.
5. **Pushed public** to GitHub under `prasad-anandappa` (repo URL in
   README/SUBMISSION.md) and verified public + contents via `gh`.

## Data honesty
All patients in `data/` are synthetic. No real patient data, no field
deployment claimed — README and SUBMISSION.md both state this plainly.

## Remaining (owner / parent)
- [ ] Prasad: sign up at agentfoundry.me, create "SehatSathi" project,
      open this repo inside the IDE, screenshot (build-evidence).
- [x] Deploy API (any cloud; Dockerfile included) → live demo link.
  Done 2026-11-06: http://139.84.151.153:8105 (VPS, systemd
  `sehatsathi.service`, port 8105, enabled at boot).
- [ ] Record 2–3 min demo per DEMO-SCRIPT.md.
- [ ] File submission issue (SUBMISSION.md fields) before 15 Nov 2026.

## 2026-11-03 — Phase 2 (audit fixes) + Phase 2b (23 languages)

- Full audit written (workspace: hackathons/sehatsathi/AUDIT-2026-11-03.md).
  Two HIGH clinical-safety fixes: danger-sign matching is now
  negation-aware ("no bleeding" no longer escalates), and swelling only
  counts as the face/hands pattern taught in ASHA training.
- Route-cap deferrals are now reported by name (summary.visits_deferred),
  never silently truncated.
- New: phone-browser UI at GET / (no JavaScript, <30 KB), helplines
  directory (GET /helplines), Kannada reminders, family/caregiver notes,
  ABHA id recorded from notes (no ABDM integration claimed), API
  hardening (bad date -> 400, oversized notes -> 413, gzip).
- Phase 2b: reminders, caregiver notes and UI chrome in all 22
  Eighth-Schedule languages + English (langs/ package + i18n registry).
  15 languages maintainer desk-checked ("verified"), 8 marked
  "provisional" in i18n.py pending native-speaker review (Bodo, Dogri,
  Kashmiri, Maithili, Manipuri, Sanskrit, Santali, Sindhi). Per-language
  automated tests: completeness, placeholders, 112/108 presence,
  native-script Unicode blocks, UTF-8 cleanliness, live formatting.
- Tests: 18 -> 39 (Phase 2) -> 49 (Phase 2b). Version 1.2.0.

- Calibration (same day): after the translation squads' self-ratings
  were reviewed, Assamese, Odia and Konkani moved from "verified" to
  "provisional" — their own translators rated them medium confidence.
  Verified set is now 12 (en, hi, kn, bn, gu, mr, pa, ta, te, ml, ne,
  ur); provisional 11. Status lives in i18n.py LANGUAGE_META.

## v1.3.0 — 2026-11-06 · Screening-to-care loop layer (Future Health challenge window)

- New module `loop.py`: screening-intake mode (a camp/PHC list becomes
  one tracked record per person; a line marked "referred" enters as
  referred, "not referred" stays screened; re-intake never overwrites
  a tracked record), a forward-only three-state tracker (screened →
  referred → care confirmed) whose daily plan is driven by whoever is
  still unconfirmed, and a day-end closure summary + readable closure
  report naming everyone still open.
- API: POST /screening/intake · GET /loop · POST /loop/refer ·
  POST /loop/confirm · GET /loop/closure · POST /loop/reset ·
  GET /loop/demo (throwaway-loop demo on the synthetic camp list).
  Loop store is in-memory per process (prototype demo store — a
  restart clears it; stated in the API docstring).
- UI: "Screening camp mode" page at /loop/ui (no JavaScript, same
  design rules): intake form, tracked-record cards with refer/confirm
  buttons, day-end closure section. Linked from the index page.
- Sample data: `data/sample_screening_list.txt` (8 synthetic camp
  entries). Tests: 49 → 67 (18 new in tests/test_loop.py), all green.
- Deployed: /opt/sehatsathi on the VPS, venv + systemd service on
  port 8105; public URL verified end-to-end (intake → refer →
  confirm → closure over the public interface).

## v1.5.0 — 2026-11-10 · Evidence + depth pass (Code for a Billion)

Universal rule-set pass on Prasad's order (theme-fit re-verified
first-hand against the CFI page + JUDGING.md: FIT, Health area).

- Evidence: `impact.py` + `GET /impact`, `/impact/ui`, `/deployment`
  — live deployment aggregates (counts only) + the reproducible
  benchmark, computed at request time. `benchmark.py` +
  `benchmarks/run_benchmark.py`: 41 hand-labelled lines → danger
  recall 1.0, false escalations 0, category accuracy 1.0; the script
  exits non-zero if a safety threshold fails.
- Schedules: `schedule.py` (UIP / ANC / PNC / TB checkpoints) wired
  into the extractor as a labelled fallback when a note gives a
  stage but no date; risk reasons carry the confirm-on-card line.
  New Patient fields: due_source, days_since_delivery,
  treatment_month (loop_store round-trips them).
- Intake depth: spoken-number parsing; duplicate-line merging in
  the agent (summary counts merges); referral slips (EN/HI/KN,
  fence on the slip's face) for escalations; loop closure aging +
  days-open; intake needs-review flags.
- Surfaces: supervisor page `/supervisor`, worker register CSV,
  printable day sheets, one-tap `/demo/ui`, WhatsApp deep links,
  grouped helplines, script-aware display language, <30 KB page
  budget test.
- Tests: 89 → 117 (tests/test_v15_features.py, 28 new), all green;
  benchmark safety gate PASS; sample day unchanged (10/3/10).
- Safety fence unchanged: records, reminders, scheduling only.

## v1.6.0 — 2026-11-18 · Overdue flagging + case ownership (Future Health final)

Reviewer feedback on the screening-to-care loop, answered:

- Flags computed (never stored) from the recorded due date in
  `loop.py`: open + due date passed + not care-confirmed →
  **DELAYED** (result / follow-up overdue); referred + referral
  visit date (same recorded due date) passed + not confirmed →
  **MISSED VISIT** (takes precedence — the more specific failure).
  Due today ≠ passed; confirmed cases never flag.
- Surfaces: record `to_dict(on)` gains `owner` / `flags` /
  `flag_labels`; closure summary gains `flagged` (with owners),
  `delayed`, `missed_visits`, `flag_counts`; closure report gains a
  flagged section + Owner column; tracker UI cards show a flag
  banner with **Owner: <name>** on flagged cases and the owner on
  every card; closure section + printable day sheet name flagged
  owners; worker register CSV gains owner + flags columns.
- Ownership: `LoopRecord.owner`, set at intake from the loop's
  worker. `DurableScreeningLoop` derives it from the worker profile
  (display name → phone → worker id) and adopts pre-v1.6.0 records
  on load — no DB schema change (owner is the loop's worker by
  construction). Demo loops use the labelled synthetic owner
  "Demo health worker (synthetic)".
- Version 1.5.0 → 1.6.0 (pyproject, `__init__.__version__`, FastAPI
  title + `/health`); the v1.5 health-version test updated to pin
  1.6.0. Tests: 117 → 137 (tests/test_v15_features.py version pin +
  tests/test_v16_features.py, 20 new), all green; benchmark gate
  PASS. Safety fence unchanged.
- Deployed 2026-11-18 (commit 129f041): prior app backed up to
  `/opt/sehatsathi/app.bak-20261118-v150` on the VPS, release copied
  to `/opt/sehatsathi/app`, `sehatsathi.service` restarted.
  Verified live: `https://sehatsathi.nammaprojects.com/health` →
  version 1.6.0; `/loop/demo` closure flags Priya as missed_visit
  with the demo owner; the demo tracker page, intaked with
  synthetic past-due cases, renders both the DELAYED and
  MISSED VISIT banners, each with `Owner: Demo health worker
  (synthetic)`, plus the closure "Flagged overdue" roll-up.
