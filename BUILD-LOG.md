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
