"""Durable screening-to-care loop — the production store.

v1.3.0's ScreeningLoop kept every tracked record in a dict in process
memory (the module says so itself: a prototype demo store, cleared by
a restart). This subclass keeps the exact same intake / transition /
closure logic — guarded forward-only transitions included — and
mirrors the state into the SQLAlchemy store after every mutation, so
a worker's cases survive service restarts, deploys and crashes.

One DurableScreeningLoop exists per worker: records are scoped by
worker_id, so one worker never sees another's cases. Rehydration is
exact — the patient snapshot, the scored follow-up (reasons, action,
reminders in every language) and the full state history round-trip
through JSON columns.
"""
from __future__ import annotations

from datetime import date

from .db import Store
from .loop import LoopRecord, LoopState, ScreeningLoop
from .models import Category, FollowUp, Patient, Priority


def _patient_to_dict(p: Patient) -> dict:
    return {
        "name": p.name,
        "category": p.category.value,
        "village": p.village,
        "age_years": p.age_years,
        "age_months": p.age_months,
        "phone": p.phone,
        "abha_id": p.abha_id,
        "due_date": p.due_date.isoformat() if p.due_date else None,
        "due_label": p.due_label,
        "risk_factors": list(p.risk_factors),
        "danger_signs": list(p.danger_signs),
        "missed_doses": p.missed_doses,
        "months_pregnant": p.months_pregnant,
        "raw_note": p.raw_note,
    }


def _patient_from_dict(d: dict) -> Patient:
    return Patient(
        name=d["name"],
        category=Category(d.get("category", "general")),
        village=d.get("village", ""),
        age_years=d.get("age_years"),
        age_months=d.get("age_months"),
        phone=d.get("phone", ""),
        abha_id=d.get("abha_id", ""),
        due_date=(date.fromisoformat(d["due_date"])
                  if d.get("due_date") else None),
        due_label=d.get("due_label", ""),
        risk_factors=list(d.get("risk_factors", [])),
        danger_signs=list(d.get("danger_signs", [])),
        missed_doses=d.get("missed_doses", 0),
        months_pregnant=d.get("months_pregnant"),
        raw_note=d.get("raw_note", ""),
    )


def _record_to_row(rec: LoopRecord) -> dict:
    f = rec.followup
    return {
        "record_key": rec.key,
        "patient": _patient_to_dict(rec.patient),
        "followup": {
            "priority": f.priority.value,
            "score": f.score,
            "reasons": list(f.reasons),
            "action": f.action,
            "reminders": dict(f.reminders),
            "caregiver_notes": dict(f.caregiver_notes),
        },
        "state": rec.state.value,
        "screened_on": rec.screened_on.isoformat(),
        "referred_on": (rec.referred_on.isoformat()
                        if rec.referred_on else None),
        "care_confirmed_on": (rec.care_confirmed_on.isoformat()
                              if rec.care_confirmed_on else None),
        "history": list(rec.history),
    }


def _record_from_row(row: dict) -> LoopRecord:
    patient = _patient_from_dict(row["patient"])
    fd = row["followup"]
    followup = FollowUp(
        patient=patient,
        priority=Priority(fd["priority"]),
        score=fd["score"],
        reasons=list(fd.get("reasons", [])),
        action=fd.get("action", ""),
        reminders=dict(fd.get("reminders", {})),
        caregiver_notes=dict(fd.get("caregiver_notes", {})),
    )
    return LoopRecord(
        patient=patient,
        followup=followup,
        state=LoopState(row["state"]),
        screened_on=date.fromisoformat(row["screened_on"]),
        referred_on=(date.fromisoformat(row["referred_on"])
                     if row.get("referred_on") else None),
        care_confirmed_on=(date.fromisoformat(row["care_confirmed_on"])
                           if row.get("care_confirmed_on") else None),
        history=list(row.get("history", [])),
    )


class DurableScreeningLoop(ScreeningLoop):
    """A ScreeningLoop whose every mutation is persisted per worker."""

    def __init__(self, store: Store, worker_id: str) -> None:
        super().__init__()
        self._store = store
        self._worker_id = worker_id
        for row in store.load_loop_records(worker_id):
            rec = _record_from_row(row)
            self._records[rec.key] = rec

    def _sync(self) -> None:
        self._store.sync_loop_records(
            self._worker_id,
            [_record_to_row(r) for r in self._records.values()])

    # ---- mutations: run the guarded in-memory logic, then persist ----

    def intake(self, list_text: str, today: date) -> dict:
        result = super().intake(list_text, today)
        self._sync()
        return result

    def advance(self, name: str, on: date, village: str = "",
                note: str = "") -> LoopRecord:
        rec = super().advance(name, on, village, note)
        self._sync()
        return rec

    def reset(self) -> None:
        """Drop every tracked record for this worker (memory + DB)."""
        self._records.clear()
        self._sync()
