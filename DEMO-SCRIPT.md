# Demo video script — 2–3 minutes (record screen + voice)

**0:00–0:25 — Problem.** "India has about ten lakh ASHA health workers.
Each one tracks hundreds of mothers, TB patients and children from paper
registers. Miss one follow-up and it isn't a missed appointment — it can
be a mother who bleeds, TB that turns drug-resistant, a child left
unvaccinated. This is SehatSathi — her follow-up agent."

**0:25–0:50 — Input.** Show `data/sample_notes.txt`. "This is one real
evening's notes, the way a worker actually writes them — one line per
patient, simple words. Ten patients, three villages' worth of problems
hidden in plain text."

**0:50–1:30 — Escalations.** Run:
`PYTHONPATH=src python3 -m sehatsathi.cli --notes data/sample_notes.txt --date 2026-11-02`
"Before tomorrow is even planned, SehatSathi stops her: THREE women and
patients need help TODAY — a pregnant mother with severe headache and
swelling, a TB patient coughing blood, a new mother whose baby won't
feed. Each gets an escalation action and an urgent message — call 108,
go to the PHC, do not wait."

**1:30–2:10 — The plan.** Scroll the route table. "Then tomorrow builds
itself: ten visits, timed from 9 AM, danger first, risk next, and
villages grouped so she walks one route. Every ranking shows its reason —
no black box a health worker has to trust blindly."

**2:10–2:40 — Reminders + offline.** Show the bilingual reminders.
"Every patient gets a reminder in simple English and Hindi, ready for
SMS or WhatsApp. And all of this runs offline — pure Python, no internet,
no API key — because that's the reality of the villages she serves."

**2:40–3:00 — Close.** Show tests passing + repo. "Eighteen automated
tests, MIT open source, built in AgentFoundry for Code for a Billion.
SehatSathi — a companion for the worker, so she can be there for
everyone else."
