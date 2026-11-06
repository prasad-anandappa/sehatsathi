"""FastAPI service — deployable to any cloud (the hackathon asks for a
deployed project; a one-file FastAPI app deploys anywhere Python runs).

Run:  uvicorn sehatsathi.api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
UI:   http://localhost:8000/  (phone-browser form, no JavaScript)

Security note: this demo service has NO authentication and must not be
exposed publicly with real patient notes. The /plan flow is stateless —
nothing submitted is stored. The /loop endpoints (screening-to-care
tracker) keep records in process memory only, for the demo; a restart
clears them, and they are equally unsuitable for real patient data.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import ui
from .agent import SehatSathiAgent
from .helplines import HELPLINES
from .loop import ScreeningLoop

app = FastAPI(title="SehatSathi", version="1.3.0",
              description="AI follow-up agent for India's frontline health workers (ASHA/ANM).")
app.add_middleware(GZipMiddleware, minimum_size=512)
agent = SehatSathiAgent()
_SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_notes.txt"
_SAMPLE_SCREENING = (Path(__file__).resolve().parents[2]
                     / "data" / "sample_screening_list.txt")

# Screening-to-care loop store (Future Health challenge build). One
# in-memory ScreeningLoop per process: a prototype demo store. NOTHING
# here is durable — restarting the service clears every tracked record,
# and it must never be used with real patient data.
loop = ScreeningLoop()

# Audit M5: a day's notes are a page of text, never 100 KB. Anything
# larger is a mistake or abuse on a public endpoint.
MAX_NOTES_CHARS = 100_000


class PlanRequest(BaseModel):
    notes: str
    today: str | None = None  # YYYY-MM-DD, optional — for reproducible demos


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "sehatsathi", "offline_core": True}


@app.post("/plan")
def plan(req: PlanRequest) -> dict:
    _check_size(req.notes)
    return agent.run(req.notes, today=_parse_today(req.today)).to_dict()


@app.get("/demo")
def demo() -> dict:
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


# ---- Screening-to-care loop (Future Health challenge build) --------

class IntakeRequest(BaseModel):
    list_text: str
    today: str | None = None  # YYYY-MM-DD, optional — for reproducible demos


class AdvanceRequest(BaseModel):
    name: str
    village: str = ""
    today: str | None = None


@app.post("/screening/intake")
def screening_intake(req: IntakeRequest) -> dict:
    _check_size(req.list_text)
    result = loop.intake(req.list_text, _parse_today(req.today))
    return {"intake": result, "loop": loop.to_dict()}


@app.get("/loop")
def loop_state() -> dict:
    return loop.to_dict()


@app.post("/loop/refer")
def loop_refer(req: AdvanceRequest) -> dict:
    try:
        rec = loop.refer(req.name, _parse_today(req.today), req.village)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"record": rec.to_dict(), "loop": loop.to_dict()}


@app.post("/loop/confirm")
def loop_confirm(req: AdvanceRequest) -> dict:
    try:
        rec = loop.confirm_care(req.name, _parse_today(req.today), req.village)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"record": rec.to_dict(), "loop": loop.to_dict()}


@app.get("/loop/closure")
def loop_closure(today: str | None = None) -> dict:
    return loop.closure_summary(_parse_today(today))


@app.post("/loop/reset")
def loop_reset() -> dict:
    global loop
    loop = ScreeningLoop()
    return {"loop": loop.to_dict()}


@app.get("/loop/demo")
def loop_demo() -> dict:
    """End-to-end loop demo on the synthetic camp list, in a throwaway
    ScreeningLoop so the shared store is untouched: intake → one
    referral recorded → one care confirmation → closure summary."""
    demo_loop = ScreeningLoop()
    text = _SAMPLE_SCREENING.read_text(encoding="utf-8") \
        if _SAMPLE_SCREENING.exists() else ""
    day = date(2026, 11, 6)
    intake = demo_loop.intake(text, day)
    demo_loop.refer("Rekha Kumari", day)
    demo_loop.confirm_care("Rekha Kumari", day)
    return {"intake": intake, "loop": demo_loop.to_dict(),
            "closure": demo_loop.closure_summary(day),
            "closure_report": demo_loop.closure_report(day)}


@app.get("/loop/ui", response_class=HTMLResponse)
def loop_ui() -> str:
    return ui.loop_page(loop, date.today())


@app.post("/loop/ui/intake", response_class=HTMLResponse)
async def loop_ui_intake(request: Request) -> str:
    from urllib.parse import parse_qs
    fields = parse_qs((await request.body()).decode("utf-8", "replace"))
    text = fields.get("list", [""])[0]
    today_raw = fields.get("today", [""])[0]
    _check_size(text)
    today = _parse_today(today_raw)
    result = loop.intake(text, today)
    msg = (f"Intake done: {len(result['added'])} added"
           + (f", {len(result['duplicates_skipped'])} already tracked (kept as-is)"
              if result["duplicates_skipped"] else "")
           + (f", {len(result['unparsed_lines'])} line(s) could not be read"
              if result["unparsed_lines"] else "") + ".")
    return ui.loop_page(loop, today, message=msg)


@app.post("/loop/ui/advance", response_class=HTMLResponse)
async def loop_ui_advance(request: Request) -> str:
    from urllib.parse import parse_qs
    fields = parse_qs((await request.body()).decode("utf-8", "replace"))
    name = fields.get("name", [""])[0]
    action = fields.get("action", [""])[0]
    today = _parse_today(fields.get("today", [""])[0])
    try:
        if action == "refer":
            loop.refer(name, today)
            msg = f"{name}: marked referred."
        elif action == "confirm":
            loop.confirm_care(name, today)
            msg = f"{name}: care confirmed — loop closed."
        else:
            msg = "Unknown action."
    except (KeyError, ValueError) as e:
        msg = str(e)
    return ui.loop_page(loop, today, message=msg)


@app.post("/ui", response_class=HTMLResponse)
async def ui_plan(request: Request) -> str:
    # The browser form posts application/x-www-form-urlencoded. Parsed
    # with the stdlib on purpose: FastAPI's Form() would add a
    # python-multipart dependency for a two-field form.
    from urllib.parse import parse_qs
    fields = parse_qs((await request.body()).decode("utf-8", "replace"))
    notes = fields.get("notes", [""])[0]
    today = fields.get("today", [""])[0]
    lang = fields.get("lang", ["en"])[0]
    _check_size(notes)
    report = agent.run(notes, today=_parse_today(today))
    return ui.result_page(report, lang)
