"""FastAPI service — deployable to any cloud (the hackathon asks for a
deployed project; a one-file FastAPI app deploys anywhere Python runs).

Run:  uvicorn sehatsathi.api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from .agent import SehatSathiAgent

app = FastAPI(title="SehatSathi", version="1.0.0",
              description="AI follow-up agent for India's frontline health workers (ASHA/ANM).")
agent = SehatSathiAgent()
_SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample_notes.txt"


class PlanRequest(BaseModel):
    notes: str
    today: str | None = None  # YYYY-MM-DD, optional — for reproducible demos


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "sehatsathi", "offline_core": True}


@app.post("/plan")
def plan(req: PlanRequest) -> dict:
    today = date.fromisoformat(req.today) if req.today else date.today()
    return agent.run(req.notes, today=today).to_dict()


@app.get("/demo")
def demo() -> dict:
    notes = _SAMPLE.read_text(encoding="utf-8") if _SAMPLE.exists() else ""
    return agent.run(notes, today=date(2026, 11, 2)).to_dict()
