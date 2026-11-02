# AgentFoundry access — scouting report (researched 2026-11-02)

Researched with web search + page fetches only (no sign-in attempted, per
scope). Note: the `browser.open` text-fetch tool errored on all three target
sites during this pass (tool-side failure, `browser-service exited`), so
findings below rest on search-index extracts of the official pages, quoted
verbatim. A rendered-page confirmation of the sign-up screen is the one
remaining verification (see Blocker).

## What AgentFoundry.me is

- The **official IDE of Code for a Billion**: *"Sign up on AgentFoundry.me,
  create a project in the IDE, invite your collaborators, and get 1M
  smart-code tokens free."* — https://codeforindia.org/hackathon
- *"About AgentFoundry.me: AgentFoundry.me is an AI-native development
  environment that lets builders create agentic applications, collaborate
  with teammates, and deploy to any cloud. It is the official build platform
  for Code for a Billion 2026."* — launch release, 14 Aug 2026 (multiple
  Indian news outlets carrying the CFI release).
- Its own wiki (https://wiki.agentfoundry.me/) describes *"the dual-mode IDE
  for shipping apps and AI agents"* and states: **"v0.1.68 is live. The full
  IDE is now free for everyone — no trial, no expiry. Build an agent by
  describing it in plain language and it scaffolds real code and runs
  keyless."**
- Wiki structure (from the same page): **Get Started** = *"Download →
  install → connect Slack/GitHub/Jira → ship your first app and your first
  agent"* / *"Get Started in 5 minutes"*; **Build your first app** =
  *"Describe → Build → Run — no API key needed. Or take the Advanced path to
  pick a harness (Claude Agent SDK, Cursor SDK, Microsoft Agent Framework,
  Google ADK)"*; **Connect** section = *"Slack, GitHub, Jira, custom MCP"*.
- Product model (wiki): multi-project tabs (*"open every codebase you work
  in side-by-side. Each tab keeps its own AI model, MCP connections,
  terminal, agent state"*), *"real terminal, real deploys"*, four SDK
  scaffolds, agent runs captured as replayable JSONL, and a Sidecar mode to
  *"push skills + guardrails into agents deployed in your own
  AWS / GCP / Azure cloud"*.

Interpretation: AgentFoundry is a **downloadable desktop IDE** (download →
install flow), not only a web app. Projects are **real codebases** (real
terminal, multi-project tabs over existing codebases, GitHub is a
first-class Connect integration). Deployment target is **"any cloud"** —
matching the hackathon rule *"Projects must be deployed on any cloud"*,
i.e. AgentFoundry does not have to host the app.

## Exact access path (what public sources say)

1. Go to https://codeforindia.org/hackathon → **"Start building in
   AgentFoundry"** → https://agentfoundry.me
   (CFI: *"Sign up at AgentFoundry.me, create a project inside the IDE,
   invite your team collaborators, and start building. That's your
   hackathon entry."*)
2. Sign up on AgentFoundry.me (participant account).
3. Download + install the IDE (wiki "Get Started in 5 minutes").
4. Create a project in the IDE — the 1M free smart-code tokens are credited
   per participant (*"Every participant gets 1M smart-code tokens on
   AgentFoundry.me at no cost"* — CFI FAQ).
5. Connect GitHub (wiki Connect section) and build/deploy.

**Waitlist / approval?** No public page found mentions a waitlist, invite,
or approval gate. The wiki's current line — *"The full IDE is now free for
everyone — no trial, no expiry"* — points the other way (open access).
This could not be confirmed on the rendered sign-up screen itself (see
Blocker), so treat "open signup" as **strongly indicated, not yet
eye-verified**.

## The blocker (precise)

> **The only step that cannot be done by an agent on Prasad's behalf is
> Prasad's own sign-up / sign-in at agentfoundry.me** (his personal
> account, his credentials/OTP) **and the one-time project creation under
> that account.** No other person's sign-in can substitute, because the
> hackathon entry, the 1M tokens and the "built in AgentFoundry" evidence
> must attach to the author of record's account.
> Secondary gap: the sign-up page itself was not rendered during scouting
> (text-fetch tool failure), so whether signup is instant self-serve vs.
> email-verification-first is unverified. **Parent/user action: open
> agentfoundry.me in a real browser, sign up, and note what the account
> page shows — 2 minutes.**

## Can work built outside be brought in?

Evidence says **yes, by design** (confidence: high, with one caveat):

- GitHub is a documented Connect integration; the flow is "connect
  Slack/GitHub/Jira", and projects live as real codebases with a real
  terminal — an existing repo can be connected/opened/cloned into a
  project tab. SehatSathi is deliberately plain, dependency-light Python
  (stdlib core) so nothing about it is AgentFoundry-hostile.
- Deployment is "to any cloud", and the submission itself is a **public
  GitHub repo + demo + GitHub submission issue** — the repo is the artefact
  of record regardless of IDE.
- Caveat: no public doc found spells out a literal "Import existing
  project" button. The step-by-step below therefore uses the GitHub-connect
  / open-folder paths the wiki documents; if the IDE's New Project dialog
  offers only from-scratch scaffolds, the fallback is: create the project,
  then clone this repo into its workspace from the IDE's real terminal
  (`git clone https://github.com/prasad-anandappa/sehatsathi`) — the
  project is then genuinely built/continued/deployed inside AgentFoundry.

## Step-by-step: finish SehatSathi inside the IDE (≈20 min, Prasad)

1. Sign up at https://agentfoundry.me (his account) → download/install IDE.
2. New Project → name it **SehatSathi** (this creates the hackathon entry;
   confirm the 1M smart-code tokens show on the account).
3. Connect GitHub (Connect → GitHub) and open/clone
   `prasad-anandappa/sehatsathi` in the project — or use the IDE terminal:
   `git clone https://github.com/prasad-anandappa/sehatsathi.git`
4. In the IDE terminal, verify the exact judge flow:
   `PYTHONPATH=src python3 -m sehatsathi.cli --notes data/sample_notes.txt --date 2026-11-02`
   and `pip install -e ".[dev,api]" && pytest -q` (expect 18 passed).
5. Ask the IDE's assistant to run the API (`uvicorn sehatsathi.api:app
   --port 8000`) and open `/demo` in its browser panel — screenshot this
   for the demo/submission (evidence of building in AgentFoundry).
6. Deploy from the IDE to any cloud (or keep the GitHub repo + `/demo`
   endpoint as the live link), record the 2–3 min demo (DEMO-SCRIPT.md).
7. Submit: open the structured submission form at
   https://github.com/karlmehta/code-for-a-billion/issues/new?template=submission.yml
   and paste the fields from SUBMISSION.md. Deadline **15 Nov 2026**.

## Official rules recap (sources)

- Steps: *"1. Build in AgentFoundry · 2. Publish your repo — Push to a
  public GitHub repository with a README explaining how to run it ·
  3. Record a demo — A 2–3 minute video or a live link · 4. Submit on
  GitHub"* — submission hub README,
  https://github.com/karlmehta/code-for-a-billion
- Judging: four criteria × 25% — problem size, problem severity, solution
  quality, proven impact — https://codeforindia.org/hackathon and
  JUDGING.md in the submission hub.
- License: *"Projects are released open-source (Apache-2.0 or MIT) to the
  Code for India GitHub organization"* — CFI FAQ. This repo: **MIT**.
- Cost: *"Free. Every participant gets 1M smart-code tokens on
  AgentFoundry.me at no cost."* Prizes ₹18 lakh / $17,500 pool; winners
  5 Dec 2026.
