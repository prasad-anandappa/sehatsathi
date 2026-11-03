"""FastAPI service — deployable to any cloud (the hackathon asks for a
deployed project; a one-file FastAPI app deploys anywhere Python runs).

Run:  uvicorn sehatsathi.api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
UI:   http://localhost:8000/  (phone-browser form, no JavaScript)

Security note: this demo service has NO authentication and must not be
exposed publicly with real patient notes. It is stateless — nothing
submitted is stored anywhere.
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

app = FastAPI(title="SehatSathi", version="1.2.0",
              description="AI follow-up agent for India's frontline health workers (ASHA/ANM).")
app.add_middleware(GZipMiddleware, minimum_size=512)
agent = SehatSathiAgent()
_SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_notes.txt"

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
