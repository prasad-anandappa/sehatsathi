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
- [ ] Deploy API (any cloud; Dockerfile included) → live demo link.
- [ ] Record 2–3 min demo per DEMO-SCRIPT.md.
- [ ] File submission issue (SUBMISSION.md fields) before 15 Nov 2026.
