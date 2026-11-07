"""FastAPI service — SehatSathi production API (v1.4.1).

Run:  uvicorn sehatsathi.api:app --host 0.0.0.0 --port 8105
Docs: http://localhost:8105/docs
UI:   http://localhost:8105/  (phone-browser demo pages, no JavaScript)
      http://localhost:8105/login (worker sign-in — OTP form, no JS)

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

import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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


def _detail(e: BaseException) -> str:
    """User-facing message for an exception. str(KeyError) wraps the
    message in repr quotes ('\"no tracked person named ...\"'), which
    leaked into API details and page messages — unwrap it."""
    if isinstance(e, KeyError) and e.args:
        return str(e.args[0])
    return str(e)


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
        title="SehatSathi", version="1.4.1",
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

    # Demo loops for the public no-JS UI: synthetic data only, clearly
    # labelled on the page, never a worker's real records.
    # As-user audit 2026-11-06 (HIGH): this used to be ONE loop shared
    # by every visitor on Earth — anything one visitor typed was
    # listed to all the others, and the home page pitched the page as
    # the way to "track" a camp list. Each browser now gets its own
    # demo loop, keyed by an opaque cookie; the cap keeps a busy day
    # from growing the dict without bound (oldest evicted first).
    class _DemoLoops:
        def __init__(self, cap: int = 100):
            self._loops: dict[str, ScreeningLoop] = {}
            self._cap = cap

        def get(self, token: str | None) -> tuple[str, ScreeningLoop, bool]:
            if token and token in self._loops:
                return token, self._loops[token], False
            token = secrets.token_urlsafe(16)
            loop_obj = ScreeningLoop()
            self._loops[token] = loop_obj
            while len(self._loops) > self._cap:
                self._loops.pop(next(iter(self._loops)))
            return token, loop_obj, True

    demo_loops = _DemoLoops()

    def _demo_response(page: str, token: str, is_new: bool) -> HTMLResponse:
        resp = HTMLResponse(page)
        if is_new:
            resp.set_cookie("ss_demo", token, max_age=7 * 24 * 3600,
                            path="/loop", httponly=True, samesite="lax")
        return resp

    # ---- public / demo surfaces -------------------------------------

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "sehatsathi",
                "offline_core": True, "version": "1.4.1",
                "storage": "durable", "auth_mode": settings.auth_mode}

    @app.get("/demo")
    def demo() -> dict:
        """Judge surface: the sample-notes plan. Synthetic data only —
        and now labelled in the payload itself, not just on the web
        page (as-user audit 2026-11-06)."""
        notes = _SAMPLE.read_text(encoding="utf-8") if _SAMPLE.exists() else ""
        report = agent.run(notes, today=date(2026, 11, 2)).to_dict()
        return {"demo_data": True,
                "note": "Synthetic sample notes only — not a real "
                        "worker's records.",
                **report}

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
        try:
            _check_size(notes)
            report = agent.run(notes, today=_parse_today(today))
        except HTTPException as e:
            # Browser form: a raw JSON error body is a dead end on a
            # phone — re-render the page with the message instead.
            return ui.index_page(lang, message=str(e.detail))
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

    # ---- worker sign-in + pages (HTML, no-JS) -------------------------
    # As-user audit 2026-11-06 (MAJOR): OTP login existed only as a
    # JSON API — a health worker with a phone browser could not sign
    # in or reach her own durable records at all. These routes are
    # the browser door: the same AuthService, with the session token
    # in an HttpOnly cookie (SameSite=Lax, so other sites' forms
    # cannot ride it) instead of an Authorization header.

    def _ui_worker(request: Request) -> WorkerContext | None:
        if settings.auth_mode != "otp":
            return WorkerContext(id="local-worker", phone="", role="worker")
        return auth.worker_for_token(request.cookies.get("ss_session", ""))

    async def _form_fields(request: Request) -> dict:
        from urllib.parse import parse_qs
        fields = parse_qs((await request.body()).decode("utf-8", "replace"))
        return {k: v[0] for k, v in fields.items()}

    def _intake_message(result: dict) -> str:
        return (f"Intake done: {len(result['added'])} added"
                + (f", {len(result['duplicates_skipped'])} already tracked "
                   "(kept as-is)" if result["duplicates_skipped"] else "")
                + (f", {len(result['unparsed_lines'])} line(s) could not "
                   "be read" if result["unparsed_lines"] else "") + ".")

    @app.get("/login", response_class=HTMLResponse)
    def login_form() -> str:
        return ui.login_page()

    @app.post("/login/request", response_class=HTMLResponse)
    async def login_request(request: Request) -> str:
        fields = await _form_fields(request)
        try:
            result = auth.request_otp(fields.get("phone", ""),
                                      fields.get("email", "") or None)
        except HTTPException as e:
            return ui.login_page(message=str(e.detail))
        return ui.otp_page(result["phone"],
                           message="Code sent — check your email.")

    @app.post("/login/verify")
    async def login_verify(request: Request):
        fields = await _form_fields(request)
        phone = fields.get("phone", "")
        try:
            result = auth.verify_otp(phone, fields.get("code", ""))
        except HTTPException as e:
            return HTMLResponse(ui.otp_page(phone, message=str(e.detail)))
        resp = RedirectResponse("/worker", status_code=303)
        resp.set_cookie(
            "ss_session", result["token"],
            max_age=settings.session_token_days * 24 * 3600,
            path="/", httponly=True, samesite="lax",
            secure=settings.env == "production")
        return resp

    @app.post("/worker/logout")
    def worker_logout(request: Request):
        auth.logout(request.cookies.get("ss_session", ""))
        resp = RedirectResponse("/", status_code=303)
        resp.delete_cookie("ss_session", path="/")
        return resp

    def _worker_page(loop_obj, today, message: str = "", lang: str = "en",
                     worker: WorkerContext | None = None) -> str:
        return ui.loop_page(loop_obj, today, message=message, lang=lang,
                            base="/worker",
                            signed_in=(worker.phone or worker.id)
                            if worker else "")

    @app.get("/worker")
    def worker_home(request: Request, lang: str = "en"):
        worker = _ui_worker(request)
        if worker is None:
            return RedirectResponse("/login", status_code=303)
        return HTMLResponse(_worker_page(
            worker_loop(worker.id), date.today(), lang=lang, worker=worker))

    @app.post("/worker/intake")
    async def worker_intake(request: Request):
        worker = _ui_worker(request)
        if worker is None:
            return RedirectResponse("/login", status_code=303)
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        loop_obj = worker_loop(worker.id)
        try:
            _check_size(fields.get("list", ""))
            today = _parse_today(fields.get("today", ""))
            result = loop_obj.intake(fields.get("list", ""), today)
            msg = _intake_message(result)
        except HTTPException as e:
            return HTMLResponse(_worker_page(
                loop_obj, date.today(), message=str(e.detail), lang=lang,
                worker=worker))
        return HTMLResponse(_worker_page(
            loop_obj, today, message=msg, lang=lang, worker=worker))

    @app.post("/worker/advance")
    async def worker_advance(request: Request):
        worker = _ui_worker(request)
        if worker is None:
            return RedirectResponse("/login", status_code=303)
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        name = fields.get("name", "")
        loop_obj = worker_loop(worker.id)
        today = date.today()
        try:
            today = _parse_today(fields.get("today", ""))
            if fields.get("action", "") == "refer":
                loop_obj.refer(name, today)
                msg = f"{name}: marked referred."
            elif fields.get("action", "") == "confirm":
                loop_obj.confirm_care(name, today)
                msg = f"{name}: care confirmed — loop closed."
            else:
                msg = "Unknown action."
        except HTTPException as e:
            msg = str(e.detail)
        except (KeyError, ValueError) as e:
            msg = _detail(e)
        return HTMLResponse(_worker_page(
            loop_obj, today, message=msg, lang=lang, worker=worker))

    @app.post("/worker/remove")
    async def worker_remove(request: Request):
        worker = _ui_worker(request)
        if worker is None:
            return RedirectResponse("/login", status_code=303)
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        loop_obj = worker_loop(worker.id)
        try:
            rec = loop_obj.remove(fields.get("name", ""))
            msg = f"{rec.patient.name}: record removed."
        except KeyError as e:
            msg = _detail(e)
        return HTMLResponse(_worker_page(
            loop_obj, date.today(), message=msg, lang=lang, worker=worker))

    @app.post("/worker/plan", response_class=HTMLResponse)
    async def worker_plan(request: Request):
        worker = _ui_worker(request)
        if worker is None:
            return RedirectResponse("/login", status_code=303)
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        loop_obj = worker_loop(worker.id)
        try:
            _check_size(fields.get("notes", ""))
            today = _parse_today(fields.get("today", ""))
        except HTTPException as e:
            return _worker_page(loop_obj, date.today(),
                                message=str(e.detail), lang=lang,
                                worker=worker)
        report = agent.run(fields.get("notes", ""), today=today)
        store.save_visit_note(worker.id, fields.get("notes", ""),
                              today.isoformat(), report.to_dict())
        return ui.result_page(report, lang,
                              back_href="/worker?lang=" + lang)

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
            raise HTTPException(status_code=404, detail=_detail(e))
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
            raise HTTPException(status_code=404, detail=_detail(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"record": rec.to_dict(), "loop": loop_obj.to_dict()}

    @app.post("/loop/remove")
    def loop_remove(req: AdvanceRequest,
                    worker: WorkerContext = Depends(current_worker)) -> dict:
        """Remove ONE of the worker's own records (her correction of
        a mistyped/duplicate register line). Added by the as-user
        audit 2026-11-06 — before this, the only remedy was the
        all-or-nothing /loop/reset."""
        loop_obj = worker_loop(worker.id)
        try:
            rec = loop_obj.remove(req.name, req.village)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=_detail(e))
        return {"removed": rec.patient.name, "loop": loop_obj.to_dict()}

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

    @app.get("/loop/ui")
    def loop_ui(request: Request, lang: str = "en"):
        token, loop_obj, is_new = demo_loops.get(
            request.cookies.get("ss_demo"))
        return _demo_response(
            ui.loop_page(loop_obj, date.today(), demo=True, lang=lang),
            token, is_new)

    @app.post("/loop/ui/intake")
    async def loop_ui_intake(request: Request):
        token, loop_obj, is_new = demo_loops.get(
            request.cookies.get("ss_demo"))
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        try:
            _check_size(fields.get("list", ""))
            today = _parse_today(fields.get("today", ""))
            result = loop_obj.intake(fields.get("list", ""), today)
            msg = _intake_message(result)
        except HTTPException as e:
            return _demo_response(
                ui.loop_page(loop_obj, date.today(),
                             message=str(e.detail), demo=True, lang=lang),
                token, is_new)
        return _demo_response(
            ui.loop_page(loop_obj, today, message=msg, demo=True,
                         lang=lang),
            token, is_new)

    @app.post("/loop/ui/advance")
    async def loop_ui_advance(request: Request):
        token, loop_obj, is_new = demo_loops.get(
            request.cookies.get("ss_demo"))
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        name = fields.get("name", "")
        today = date.today()
        try:
            today = _parse_today(fields.get("today", ""))
            if fields.get("action", "") == "refer":
                loop_obj.refer(name, today)
                msg = f"{name}: marked referred."
            elif fields.get("action", "") == "confirm":
                loop_obj.confirm_care(name, today)
                msg = f"{name}: care confirmed — loop closed."
            else:
                msg = "Unknown action."
        except HTTPException as e:
            msg = str(e.detail)
        except (KeyError, ValueError) as e:
            msg = _detail(e)
        return _demo_response(
            ui.loop_page(loop_obj, today, message=msg, demo=True,
                         lang=lang),
            token, is_new)

    @app.post("/loop/ui/remove")
    async def loop_ui_remove(request: Request):
        token, loop_obj, is_new = demo_loops.get(
            request.cookies.get("ss_demo"))
        fields = await _form_fields(request)
        lang = fields.get("lang", "en")
        try:
            rec = loop_obj.remove(fields.get("name", ""))
            msg = f"{rec.patient.name}: record removed."
        except KeyError as e:
            msg = _detail(e)
        return _demo_response(
            ui.loop_page(loop_obj, date.today(), message=msg, demo=True,
                         lang=lang),
            token, is_new)

    return app


app = create_app()
