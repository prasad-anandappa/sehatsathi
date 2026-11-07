"""Screening-to-care loop layer — the Future Health challenge build.

Built during the Future Health Digital Innovation Challenge 2026 window
for the statement "[Population Health] Closing the Screening-to-Care
Loop". The pre-existing SehatSathi core (extract → risk → reminders) is
the foundation and is reused unchanged; this module adds the front half
of the loop and its closure mechanics:

  1. Screening intake — a camp / PHC screening list (one person per
     line, the register format workers already keep) becomes one
     tracked record per screened person.
  2. A three-state loop tracker per person:
         screened → referred → care confirmed
     The daily plan and reminders are driven by whoever is still
     unconfirmed — an open record never silently disappears.
  3. A day-end closure summary a worker or supervisor can review,
     naming everyone still open.

Safety fence (unchanged from the core product): records, tracking and
reminders only. Nothing here diagnoses, advises treatment, or replaces
the worker / PHC medical officer; danger signs in a screening line are
flagged for same-day human referral exactly as in the notes flow.

Storage: deliberately in-memory and dependency-free, like the rest of
the core. A ScreeningLoop instance holds its records in a dict; the
API layer keeps one instance per process (a prototype demo store —
restarting the service clears it, which the API docstring states).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date

from . import extract, risk
from .messages import make_caregiver_note, make_reminders
from .models import FollowUp, Patient, Priority


class LoopState(str, enum.Enum):
    SCREENED = "screened"
    REFERRED = "referred"
    CARE_COMPLETED = "care_completed"

    @property
    def label(self) -> str:
        return {LoopState.SCREENED: "screened",
                LoopState.REFERRED: "referred",
                LoopState.CARE_COMPLETED: "care confirmed"}[self]


# Forward-only transitions. A record moves one step at a time so the
# day-end summary can always say who was referred and who is still
# waiting — skipping a step in the data would hide a real gap in care.
_NEXT = {LoopState.SCREENED: LoopState.REFERRED,
         LoopState.REFERRED: LoopState.CARE_COMPLETED}


def _initial_state(line: str) -> LoopState:
    """State a screening-list line starts in.

    Camp registers often record the referral on the same line
    ("…, referred to PHC"). A negated mention ("not referred") is the
    worker recording that no referral happened — the person stays in
    SCREENED, never REFERRED.
    """
    low = line.lower()
    if any(p in low for p in ("care confirmed", "care completed",
                              "care received", "seen at phc")):
        return LoopState.CARE_COMPLETED
    if "referred" in low and "not referred" not in low \
            and "no referral" not in low:
        return LoopState.REFERRED
    return LoopState.SCREENED


@dataclass
class LoopRecord:
    patient: Patient
    followup: FollowUp                 # scored at intake; re-scored on demand
    state: LoopState
    screened_on: date
    referred_on: date | None = None
    care_confirmed_on: date | None = None
    history: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return (self.patient.name.strip().lower() + "|"
                + self.patient.village.strip().lower())

    @property
    def is_open(self) -> bool:
        return self.state is not LoopState.CARE_COMPLETED

    def to_dict(self) -> dict:
        p = self.patient
        return {
            "name": p.name,
            "village": p.village,
            "category": p.category.value,
            "state": self.state.label,
            "priority": self.followup.priority.value,
            "score": self.followup.score,
            "due_date": p.due_date.isoformat() if p.due_date else None,
            "due_label": p.due_label,
            "danger_signs": p.danger_signs,
            "reasons": self.followup.reasons,
            "action": self.followup.action,
            "reminder_en": self.followup.reminder_en,
            "screened_on": self.screened_on.isoformat(),
            "referred_on": self.referred_on.isoformat() if self.referred_on else None,
            "care_confirmed_on": (self.care_confirmed_on.isoformat()
                                  if self.care_confirmed_on else None),
            "history": self.history,
        }


class ScreeningLoop:
    """One screening camp / PHC list, tracked until every loop closes."""

    def __init__(self) -> None:
        self._records: dict[str, LoopRecord] = {}

    # ---- intake ----------------------------------------------------

    def intake(self, list_text: str, today: date) -> dict:
        """Create one tracked record per person on a screening list.

        Lines are parsed with the same deterministic extractor as visit
        notes. A person already tracked (same name + village) is NOT
        overwritten — the existing record and its state survive; the
        duplicate is counted and reported, never silently merged.
        """
        added, duplicates, unparsed = [], [], []
        for raw in list_text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            patient = extract.parse_line(line, today)
            if patient is None:
                unparsed.append(line)
                continue
            fu = risk.score_patient(patient, today)
            fu.reminders = make_reminders(fu)
            fu.caregiver_notes = make_caregiver_note(fu)
            rec = LoopRecord(patient=patient, followup=fu,
                             state=_initial_state(line), screened_on=today)
            if rec.key in self._records:
                duplicates.append(patient.name)
                continue
            rec.history.append({"date": today.isoformat(),
                                "state": LoopState.SCREENED.label,
                                "note": "screened — entered from screening list"})
            if rec.state is LoopState.REFERRED:
                rec.referred_on = today
                rec.history.append({"date": today.isoformat(),
                                    "state": LoopState.REFERRED.label,
                                    "note": "referral recorded on the screening list"})
            elif rec.state is LoopState.CARE_COMPLETED:
                rec.referred_on = today
                rec.care_confirmed_on = today
                rec.history.append({"date": today.isoformat(),
                                    "state": LoopState.CARE_COMPLETED.label,
                                    "note": "care already confirmed at intake"})
            self._records[rec.key] = rec
            added.append(patient.name)
        return {"added": added, "duplicates_skipped": duplicates,
                "unparsed_lines": unparsed,
                "total_tracked": len(self._records)}

    # ---- transitions -------------------------------------------------

    def _find(self, name: str, village: str = "") -> LoopRecord:
        key = name.strip().lower() + "|" + village.strip().lower()
        if key in self._records:
            return self._records[key]
        matches = [r for r in self._records.values()
                   if r.patient.name.strip().lower() == name.strip().lower()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise KeyError(f"no tracked person named {name!r} — "
                           "check the name against the screening list")
        raise KeyError(f"{name!r} matches more than one village — "
                       "pass the village to say which person")

    def advance(self, name: str, on: date, village: str = "",
                note: str = "") -> LoopRecord:
        """Move one person one step forward: screened → referred →
        care confirmed. Backward or skipped steps raise ValueError —
        the tracker must never pretend a referral happened."""
        rec = self._find(name, village)
        nxt = _NEXT.get(rec.state)
        if nxt is None:
            raise ValueError(f"{rec.patient.name}: loop already closed "
                             "(care confirmed) — nothing further to record")
        rec.state = nxt
        if nxt is LoopState.REFERRED:
            rec.referred_on = on
        else:
            rec.care_confirmed_on = on
        rec.history.append({"date": on.isoformat(), "state": nxt.label,
                            "note": note or f"marked {nxt.label}"})
        return rec

    def refer(self, name: str, on: date, village: str = "") -> LoopRecord:
        rec = self._find(name, village)
        if rec.state is not LoopState.SCREENED:
            raise ValueError(f"{rec.patient.name} is already "
                             f"{rec.state.label} — cannot be referred again")
        return self.advance(name, on, village, note="referred")

    def confirm_care(self, name: str, on: date, village: str = "") -> LoopRecord:
        rec = self._find(name, village)
        if rec.state is LoopState.SCREENED:
            raise ValueError(f"{rec.patient.name} has not been referred yet — "
                             "record the referral first, then confirm care")
        if rec.state is LoopState.CARE_COMPLETED:
            raise ValueError(f"{rec.patient.name}: care already confirmed")
        return self.advance(name, on, village, note="care confirmed")

    def remove(self, name: str, village: str = "") -> LoopRecord:
        """Remove ONE tracked record — the worker correcting her own
        register (a mistyped line, a duplicate under a spelling
        variant). As-user audit 2026-11-06: until now the only remedy
        for a wrong entry was wiping the whole loop. Nothing is ever
        removed automatically; this is the worker's deliberate act,
        and intake still never drops a line on its own."""
        rec = self._find(name, village)
        del self._records[rec.key]
        return rec

    # ---- views -------------------------------------------------------

    def records(self) -> list[LoopRecord]:
        """Open records first (highest score first), then closed ones."""
        open_ = sorted((r for r in self._records.values() if r.is_open),
                       key=lambda r: -r.followup.score)
        closed = sorted((r for r in self._records.values() if not r.is_open),
                        key=lambda r: r.patient.name)
        return open_ + closed

    def open_records(self) -> list[LoopRecord]:
        return [r for r in self.records() if r.is_open]

    def daily_plan(self, today: date) -> list[FollowUp]:
        """Today's follow-ups for everyone still unconfirmed, re-scored
        against today so overdue counts stay honest."""
        fus = [risk.score_patient(r.patient, today)
               for r in self._records.values() if r.is_open]
        return sorted(fus, key=lambda f: -f.score)

    def counts(self) -> dict:
        by_state = {s.label: 0 for s in LoopState}
        for r in self._records.values():
            by_state[r.state.label] += 1
        return {"tracked": len(self._records), "by_state": by_state,
                "open": sum(1 for r in self._records.values() if r.is_open)}

    def to_dict(self) -> dict:
        return {"counts": self.counts(),
                "records": [r.to_dict() for r in self.records()]}

    # ---- day-end closure ----------------------------------------------

    def closure_summary(self, day: date) -> dict:
        """Day-end review: what moved today, and — the point of the
        exercise — the named list of everyone whose loop is STILL OPEN,
        worst-first, so nobody is silently dropped overnight."""
        still_open = []
        for rec in self._records.values():
            if not rec.is_open:
                continue
            fu = risk.score_patient(rec.patient, day)
            still_open.append({
                "name": rec.patient.name, "village": rec.patient.village,
                "category": rec.patient.category.value,
                "state": rec.state.label,
                "priority": fu.priority.value, "score": fu.score,
                "due_label": rec.patient.due_label,
                "danger_signs": rec.patient.danger_signs,
                "reasons": fu.reasons,
            })
        still_open.sort(key=lambda d: -d["score"])
        return {
            "date": day.isoformat(),
            "counts": self.counts(),
            "screened_today": sum(1 for r in self._records.values()
                                  if r.screened_on == day),
            "referred_today": sum(1 for r in self._records.values()
                                  if r.referred_on == day),
            "care_confirmed_today": sum(1 for r in self._records.values()
                                        if r.care_confirmed_on == day),
            "still_open": still_open,
            "open_escalations": [d["name"] for d in still_open
                                 if d["priority"] == Priority.CRITICAL.value],
            "loop_fully_closed": not still_open and bool(self._records),
            "note": ("Anyone listed under still_open carries forward to "
                     "tomorrow's plan — the loop closes only when care "
                     "is confirmed or a supervisor takes the case."),
        }

    def closure_report(self, day: date) -> str:
        """The closure summary as a readable day-end sheet."""
        s = self.closure_summary(day)
        c = s["counts"]["by_state"]
        lines = [f"# Screening-to-care loop — day-end closure, {s['date']}", "",
                 f"Tracked: **{s['counts']['tracked']}** · Screened: {c['screened']} · "
                 f"Referred: {c['referred']} · Care confirmed: {c['care confirmed']}", "",
                 f"Today: {s['screened_today']} screened · "
                 f"{s['referred_today']} referred · "
                 f"{s['care_confirmed_today']} care confirmed", ""]
        if s["open_escalations"]:
            lines += ["## 🚨 Still open WITH danger signs — hand to the ANM/PHC tonight",
                      ""]
            for d in s["still_open"]:
                if d["priority"] == Priority.CRITICAL.value:
                    lines.append(f"- **{d['name']}** ({d['village']}) — "
                                 f"{', '.join(d['danger_signs'])} · state: {d['state']}")
            lines.append("")
        if s["still_open"]:
            lines += ["## ⏳ Still open — carries to tomorrow, named here so nobody is dropped",
                      "", "| # | Patient | Village | State | Priority | Why |",
                      "|---|---------|---------|-------|----------|-----|"]
            for i, d in enumerate(s["still_open"], 1):
                lines.append(f"| {i} | {d['name']} | {d['village']} | {d['state']} | "
                             f"{d['priority']} | {'; '.join(d['reasons'])} |")
            lines.append("")
        else:
            lines += ["## ✅ Loop fully closed",
                      "", "Every screened person has confirmed care. Nothing carried over.", ""]
        lines += ["---", "SehatSathi tracks and reminds only — it gives no "
                  "diagnosis and no treatment advice. Open cases stay with "
                  "the worker and the PHC medical officer."]
        return "\n".join(lines)
