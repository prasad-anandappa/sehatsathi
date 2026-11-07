# SehatSathi — production audit (v1.4.0, 2026-11-06)

State of the deployed service after the production-hardening pass.
Deployed at `http://139.84.151.153:8105` (VPS, systemd
`sehatsathi.service`, code at `/opt/sehatsathi/app`, data at
`/opt/sehatsathi/data/sehatsathi.db`).

## What changed (v1.3.0 → v1.4.0)

| Area | v1.3.0 (demo) | v1.4.0 (production) |
|---|---|---|
| Loop storage | In-memory dict; a restart cleared every record | `DurableScreeningLoop` per worker, mirrored to SQLAlchemy after every mutation (SQLite file; Postgres via `SEHATSATHI_DATABASE_URL`) |
| Auth | None — the module docstring warned against real data | Phone + OTP login (`SEHATSATHI_AUTH_MODE=otp`): SHA-256-hashed codes, 10-min expiry, 5-attempt cap, 5 requests/hour/phone, hashed 30-day session tokens |
| Roles | — | `worker` (own cases only, enforced) and `supervisor` (phones in `SEHATSATHI_SUPERVISOR_PHONES`): read-only aggregates + closure summaries; visit-note contents are never served to supervisors |
| Visit notes | Stateless, discarded | Stored per worker (notes + generated plan) as durable history |
| Demo surfaces | The shared store *was* the demo | `/demo`, `/loop/demo`, `/loop/ui` run on synthetic/throwaway data only and are labelled demo on the page/response |
| Hardening | — | App-level rate limiting (global + stricter OTP bucket), security headers (nosniff / DENY framing / no-referrer), `.env` via 600-perm EnvironmentFile, log file + logrotate, nightly SQLite backup (cron 03:45, keep 7, InvoicePilot pattern) |

The deterministic core (extract → risk → planner → messages) is
unchanged and still dependency-free. The safety fence is unchanged
and absolute: records, tracking and reminders only — no diagnosis,
no treatment advice anywhere in the new code (the only "treat" hit
in a fence grep is the phrase "treat stored values as UTC" in a
datetime helper). The 23-language honesty labelling is untouched:
12 desk-verified, 11 marked `provisional` in `i18n.py`.

## Tests

79 passed (67 pre-existing + 12 new in `tests/test_production.py`):
durable-store round-trip and worker isolation, API-level restart
survival over the same DB file, guarded transitions through the API,
full OTP flow, wrong-code attempt cap, expired code, per-phone
request rate limit, honest-503 in production without a delivery
channel, supervisor aggregate with a marker-note leak check, visit
-note persistence, demo surfaces open in OTP mode.

One pre-existing fixture was adapted, assertions untouched:
`tests/test_loop.py` used to isolate tests by swapping a module-global
in-memory loop (`api_module.loop = ScreeningLoop()`); that global no
longer exists by design, so the fixture now builds a fresh app on a
throwaway DB file per test — same isolation intent.

## Live verification (2026-11-06, on the VPS)

Verified over HTTP against the deployed build (production service on
:8105 via localhost + public-IP hairpin; agent-VM egress cannot reach
raw-IP ports directly, so external vantage = the hairpin check, 200):

- Production service: `/health` → `version 1.4.0, storage durable,
  auth_mode otp`; `/loop` without a token → 401; `/demo` 200;
  `/loop/demo` 200 with `demo_data: true`; security headers present;
  `/auth/request-otp` → **503** (no delivery channel configured —
  honest refusal, see Remaining steps).
- Full flow on a temporary instance bound to the **production
  database** (dev-mode log sender with codes captured by the test
  harness; test accounts 919999900001/2): OTP login (worker) →
  `/plan` stored → intake 4 cases → refer → confirm → closure
  (3 still open, the danger-sign case named as the open escalation).
- **Restart survival**: the instance was killed and restarted; the
  same session token read back all 4 records with correct states and
  full history; the case confirmed before the restart stayed
  "care confirmed".
- Supervisor login → `/supervisor/summary`: totals tracked 4 / open
  3, visit-note-days 1, and the marker string planted in a visit note
  verified ABSENT from the response.
- Cleanup: harness stopped, all test rows deleted — production DB
  tables verified back to 0; production service restarted healthy;
  first backup written (`backups/sehatsathi-20261107-013420.db`).

## Remaining steps (external / credential, in order)

1. **DNS — the one external step for HTTPS**: add an A record
   `sehatsathi → 139.84.151.153` in the Namecheap zone for
   nammaprojects.com. The nginx vhost + rate-limit zone are already
   prepared at `/opt/sehatsathi/nginx/` (not enabled); the file's
   header lists the exact enable sequence (certbot → copy confs →
   bind uvicorn to 127.0.0.1 → reload). **Do not remove the Google
   Search Console TXT record in that zone.**
2. **OTP delivery credential**: this VPS's Exim refuses
   unauthenticated local submission (verified 2026-11-06:
   `550 127.0.0.1 is _my_ address`), so set ONE channel in
   `/opt/sehatsathi/app.env` and restart: an SMTP mailbox user +
   password on this box (`SEHATSATHI_SMTP_*`, sender
   `sehatsathi@webnetism.in`), or `SEHATSATHI_BREVO_API_KEY`, or
   Twilio (`SEHATSATHI_TWILIO_*`). Until then OTP login is fully
   functional but codes cannot leave the box (503, stated above).
3. **Supervisor phones**: set `SEHATSATHI_SUPERVISOR_PHONES` to the
   real supervisors' numbers and restart.
4. A medical review of danger-sign lists before any clinical
   deployment (standing requirement from the README; unchanged).
