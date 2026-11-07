"""FastAPI service — SehatSathi production API (v1.4.0).

Run:  uvicorn sehatsathi.api:app --host 0.0.0.0 --port 8105
Docs: http://localhost:8105/docs
UI:   http://localhost:8105/  (phone-browser demo pages, no JavaScript)

Production posture (changed in v1.4.0 — the v1.3.0 header warned the
demo store was in-memory and unsuitable for real patient data):

- The screening-to-care loop is DURABLE: one DurableScreeningLoop per
  worker, mirrored into SQLAlchemy (SQLite file by default, Postgres
  via SEHATSATHI_DATABASE_URL). Restarts no longer clear records.
- Worker endpoints require a login when SEHATSATHI_AUTH_MODE=otp:
  phone + one-time code, session tokens, per-worker case isolation,
  and a read-only supervisor role (aggregate counts + closure
  summaries — never visit-note contents).
- /plan submissions by a signed-in worker are stored as that worker's
  visit-note history (notes + generated plan).
- The public judge surfaces (/demo and /loop/demo, and the no-JS
  /loop/ui pages) stay open and run on synthetic / throwaway DEMO
  data only — they never touch a worker's real records.
- App-level rate limiting + security headers are applied here; the
  nginx vhost adds the edge layer (see AUDIT.md).

In stub auth mode (default; local dev + tests) identity comes from
X-Worker-Phone / X-Worker-Id headers and defaults to a shared
"local-worker".
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from . import ui
from .agent import SehatSathiAgent
from .auth import AuthService, WorkerContext, make_current_worker
from .config import Settings
from .db import Store, make_session_factory
from .helplines import HELPLINES
from .loop import ScreeningLoop
from .loop_store import DurableScreeningLoop
from .otp import OtpSenderChain

_SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_notes.txt"
_SAMPLE_SCREENING = (Path(__file__).resolve().parents[2]
                     / "data" / "sample_screening_list.txt")

# Audit M5: a day's notes are a page of text, never 100 KB. Anything
# larger is a mistake or abuse on a public endpoint.
MAX_NOTES_CHARS = 100_000


class PlanRequest(BaseModel):
    notes: str
    today: str | None = None  # YYYY-MM-DD, optional — for reproducible demos


class IntakeRequest(BaseModel):
    list_text: str
    today: str | None = None  # YYYY-MM-DD, optional — for reproducible demos


class AdvanceRequest(BaseModel):
    name: str
    village: str = ""
    today: str | None = None


class OtpRequest(BaseModel):
    phone: str
    email: str | None = None


class OtpVerifyRequest(BaseModel):
    phone: str
    code: str


def _parse_today(raw: str | None) -> date:
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=400,
                            detail="today must be a date like 2026-11-02")


def _check_size(notes: str) -> None:
    if len(notes) > MAX_NOTES_CHARS:
        raise HTTPException(status_code=413,
                            detail="notes are too long — send one day's "
                                   "notes at a time")


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window limit. /health is exempt; the OTP
    request endpoint gets its own stricter bucket (on top of the
    per-phone hourly cap in the auth service)."""

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _allowed(self, key: str, limit: int, now: float) -> bool:
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/health":
            ip = (request.headers.get("x-forwarded-for", "")
                  .split(",")[0].strip()
                  or (request.client.host if request.client else "unknown"))
            now = time.monotonic()
            if not self._allowed(f"all:{ip}",
                                 self.settings.rate_limit_per_minute, now):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests — slow down "
                                       "and retry in a minute."})
            if request.url.path == "/auth/request-otp" and not self._allowed(
                    f"otp:{ip}", self.settings.otp_rate_limit_per_minute,
                    now):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many code requests — retry "
                                       "in a minute."})
        return await call_next(request)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(make_session_factory(settings.database_url))
    auth = AuthService(settings, store, OtpSenderChain(settings))
    agent = SehatSathiAgent()
    current_worker = make_current_worker(settings, auth)

    app = FastAPI(
        title="SehatSathi", version="1.4.0",
        description="AI follow-up agent for India's frontline health "
                    "workers (ASHA/ANM).")
    app.add_middleware(GZipMiddleware, minimum_size=512)
    app.add_middleware(_SecurityHeadersMiddleware)
    app.add_middleware(_RateLimitMiddleware, settings=settings)
    app.state.settings = settings
    app.state.store = store
    app.state.auth = auth

    # One durable loop per worker, cached; the lock serialises loop
    # mutations (sync endpoints run in a threadpool).
    _loops: dict[str, DurableScreeningLoop] = {}
    _loops_lock = threading.Lock()

    def worker_loop(worker_id: str) -> DurableScreeningLoop:
        with _loops_lock:
            loop_obj = _loops.get(worker_id)
            if loop_obj is None:
                loop_obj = DurableScreeningLoop(store, worker_id)
                _loops[worker_id] = loop_obj
            return loop_obj

    # Demo loop for the public no-JS UI: synthetic data only, clearly
    # labelled on the page, never a worker's real records.
    demo_loop = ScreeningLoop()

    # ---- public / demo surfaces -------------------------------------

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "sehatsathi",
                "offline_core": True, "version": "1.4.0",
                "storage": "durable", "auth_mode": settings.auth_mode}

    @app.get("/demo")
    def demo() -> dict:
        """Judge surface: the sample-notes plan. Synthetic data only."""
        notes = _SAMPLE.read_text(encoding="utf-8") if _SAMPLE.exists() else ""
        return agent.run(notes, today=date(2026, 11, 2)).to_dict()

    @app.get("/helplines")
    def helplines() -> dict:
        return {"helplines": HELPLINES,
                "note": "National numbers. 102 and 104 run in many states — "
                        "confirm the local equivalent at the PHC."}

    @app.get("/", response_class=HTMLResponse)
    def index(lang: str = "en") -> str:
        return ui.index_page(lang)

    @app.post("/ui", response_class=HTMLResponse)
    async def ui_plan(request: Request) -> str:
        # The browser form posts application/x-www-form-urlencoded.
        # Parsed with the stdlib on purpose: FastAPI's Form() would add
        # a python-multipart dependency for a two-field form. This page
        # is a stateless demo surface — nothing submitted is stored.
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode("utf-8", "replace"))
        notes = fields.get("notes", [""])[0]
        today = fields.get("today", [""])[0]
        lang = fields.get("lang", ["en"])[0]
        _check_size(notes)
        report = agent.run(notes, today=_parse_today(today))
        return ui.result_page(report, lang)

    # ---- auth ---------------------------------------------------------

    @app.post("/auth/request-otp")
    def request_otp(req: OtpRequest) -> dict:
        return auth.request_otp(req.phone, req.email)

    @app.post("/auth/verify-otp")
    def verify_otp(req: OtpVerifyRequest) -> dict:
        return auth.verify_otp(req.phone, req.code)

    @app.get("/auth/me")
    def me(worker: WorkerContext = Depends(current_worker)) -> dict:
        return {"worker": {"id": worker.id, "phone": worker.phone,
                           "role": worker.role}}

    @app.post("/auth/logout")
    def logout(request: Request) -> dict:
        header = request.headers.get("Authorization", "")
        token = (header[7:].strip()
                 if header.lower().startswith("bearer ") else "")
        auth.logout(token)
        return {"logged_out": True}

    # ---- the notes flow (per-worker history) ---------------------------

    @app.post("/plan")
    def plan(req: PlanRequest,
             worker: WorkerContext = Depends(current_worker)) -> dict:
        _check_size(req.notes)
        today = _parse_today(req.today)
        report = agent.run(req.notes, today=today).to_dict()
        store.save_visit_note(worker.id, req.notes,
                              today.isoformat(), report)
        return report

    # ---- screening-to-care loop (durable, per worker) -------------------

    @app.post("/screening/intake")
    def screening_intake(req: IntakeRequest,
                         worker: WorkerContext = Depends(current_worker)
                         ) -> dict:
        _check_size(req.list_text)
        loop_obj = worker_loop(worker.id)
        result = loop_obj.intake(req.list_text, _parse_today(req.today))
        return {"intake": result, "loop": loop_obj.to_dict()}

    @app.get("/loop")
    def loop_state(worker: WorkerContext = Depends(current_worker)) -> dict:
        return worker_loop(worker.id).to_dict()

    @app.post("/loop/refer")
    def loop_refer(req: AdvanceRequest,
                   worker: WorkerContext = Depends(current_worker)) -> dict:
        loop_obj = worker_loop(worker.id)
        try:
            rec = loop_obj.refer(req.name, _parse_today(req.today),
                                 req.village)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"record": rec.to_dict(), "loop": loop_obj.to_dict()}

    @app.post("/loop/confirm")
    def loop_confirm(req: AdvanceRequest,
                     worker: WorkerContext = Depends(current_worker)) -> dict:
        loop_obj = worker_loop(worker.id)
        try:
            rec = loop_obj.confirm_care(req.name, _parse_today(req.today),
                                        req.village)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"record": rec.to_dict(), "loop": loop_obj.to_dict()}

    @app.get("/loop/closure")
    def loop_closure(today: str | None = None,
                     worker: WorkerContext = Depends(current_worker)
                     ) -> dict:
        return worker_loop(worker.id).closure_summary(_parse_today(today))

    @app.post("/loop/reset")
    def loop_reset(worker: WorkerContext = Depends(current_worker)) -> dict:
        loop_obj = worker_loop(worker.id)
        loop_obj.reset()
        return {"loop": loop_obj.to_dict()}

    # ---- supervisor (read-only, aggregates only) -------------------------

    @app.get("/supervisor/summary")
    def supervisor_summary(today: str | None = None,
                           worker: WorkerContext = Depends(current_worker)
                           ) -> dict:
        """Aggregate counts + per-worker closure summaries across all
        workers. Visit-note CONTENTS are never included — counts of
        stored note-days only."""
        if worker.role != "supervisor":
            raise HTTPException(
                status_code=403,
                detail="supervisor role required for the aggregate view")
        day = _parse_today(today)
        totals = {"tracked": 0, "open": 0,
                  "by_state": {"screened": 0, "referred": 0,
                               "care confirmed": 0}}
        per_worker = []
        for worker_id in store.loop_worker_ids():
            loop_obj = DurableScreeningLoop(store, worker_id)
            counts = loop_obj.counts()
            totals["tracked"] += counts["tracked"]
            totals["open"] += counts["open"]
            for state, n in counts["by_state"].items():
                totals["by_state"][state] += n
            per_worker.append({
                "worker_id": worker_id,
                "counts": counts,
                "closure": loop_obj.closure_summary(day),
            })
        return {
            "date": day.isoformat(),
            "totals": totals,
            "workers": per_worker,
            "visit_note_days_stored": store.visit_note_count(),
            "note": "Aggregate view only — visit-note contents are "
                    "never shown to supervisors.",
        }

    # ---- loop demo + UI (synthetic data only) -----------------------------

    @app.get("/loop/demo")
    def loop_demo() -> dict:
        """End-to-end loop demo on the synthetic camp list, in a
        throwaway ScreeningLoop: intake → one referral recorded → one
        care confirmation → closure summary. Demo data only — no
        worker's real records are touched."""
        throwaway = ScreeningLoop()
        text = _SAMPLE_SCREENING.read_text(encoding="utf-8") \
            if _SAMPLE_SCREENING.exists() else ""
        day = date(2026, 11, 6)
        intake = throwaway.intake(text, day)
        throwaway.refer("Rekha Kumari", day)
        throwaway.confirm_care("Rekha Kumari", day)
        return {"demo_data": True,
                "note": "Synthetic demo data only — not a real "
                        "worker's records.",
                "intake": intake, "loop": throwaway.to_dict(),
                "closure": throwaway.closure_summary(day),
                "closure_report": throwaway.closure_report(day)}

    @app.get("/loop/ui", response_class=HTMLResponse)
    def loop_ui() -> str:
        return ui.loop_page(demo_loop, date.today(), demo=True)

    @app.post("/loop/ui/intake", response_class=HTMLResponse)
    async def loop_ui_intake(request: Request) -> str:
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode("utf-8", "replace"))
        text = fields.get("list", [""])[0]
        today_raw = fields.get("today", [""])[0]
        _check_size(text)
        today = _parse_today(today_raw)
        result = demo_loop.intake(text, today)
        msg = (f"Intake done: {len(result['added'])} added"
               + (f", {len(result['duplicates_skipped'])} already tracked "
                  "(kept as-is)" if result["duplicates_skipped"] else "")
               + (f", {len(result['unparsed_lines'])} line(s) could not "
                  "be read" if result["unparsed_lines"] else "") + ".")
        return ui.loop_page(demo_loop, today, message=msg, demo=True)

    @app.post("/loop/ui/advance", response_class=HTMLResponse)
    async def loop_ui_advance(request: Request) -> str:
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode("utf-8", "replace"))
        name = fields.get("name", [""])[0]
        action = fields.get("action", [""])[0]
        today = _parse_today(fields.get("today", [""])[0])
        try:
            if action == "refer":
                demo_loop.refer(name, today)
                msg = f"{name}: marked referred."
            elif action == "confirm":
                demo_loop.confirm_care(name, today)
                msg = f"{name}: care confirmed — loop closed."
            else:
                msg = "Unknown action."
        except (KeyError, ValueError) as e:
            msg = str(e)
        return ui.loop_page(demo_loop, today, message=msg, demo=True)

    return app


app = create_app()
