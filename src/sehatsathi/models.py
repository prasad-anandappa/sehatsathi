"""Core data models for SehatSathi.

Plain dataclasses, no external dependencies — the whole deterministic
core runs offline on a low-end phone/laptop, which is the reality for
frontline health workers with patchy connectivity.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date


class Category(str, enum.Enum):
    PREGNANT = "pregnant"
    TB = "tb"
    CHILD = "child"
    POSTPARTUM = "postpartum"
    ELDERLY = "elderly"
    GENERAL = "general"


class Priority(str, enum.Enum):
    CRITICAL = "CRITICAL"   # danger sign present — escalate today
    HIGH = "HIGH"           # overdue or high-risk
    MEDIUM = "MEDIUM"       # due within the planning window
    LOW = "LOW"             # routine / future


@dataclass
class Patient:
    name: str
    category: Category = Category.GENERAL
    village: str = ""
    age_years: float | None = None
    age_months: int | None = None          # for children
    phone: str = ""
    abha_id: str = ""                      # only as written in the note —
                                           # recorded, never verified
                                           # (no ABDM integration)
    due_date: date | None = None           # next checkup / dose / vaccine
    due_label: str = ""                    # human label, e.g. "ANC checkup"
    risk_factors: list[str] = field(default_factory=list)
    danger_signs: list[str] = field(default_factory=list)
    missed_doses: int = 0                  # TB / medication adherence
    months_pregnant: int | None = None
    raw_note: str = ""


@dataclass
class FollowUp:
    patient: Patient
    priority: Priority
    score: int                             # deterministic, explainable
    reasons: list[str] = field(default_factory=list)
    action: str = ""                       # what the worker should do
    # Reminders in every shipped language: {lang_code: text} — English,
    # Hindi, Kannada and all other Eighth-Schedule languages (i18n.py).
    reminders: dict = field(default_factory=dict)
    # Family-facing notes, same {lang_code: text} shape, for categories
    # where a family member is usually the one who must act
    # (child / postpartum / elderly); empty dict otherwise.
    caregiver_notes: dict = field(default_factory=dict)

    @property
    def reminder_en(self) -> str:
        return self.reminders.get("en", "")

    @property
    def reminder_hi(self) -> str:
        return self.reminders.get("hi", "")

    @property
    def reminder_kn(self) -> str:
        return self.reminders.get("kn", "")

    @property
    def caregiver_note(self) -> dict:
        """The original EN/HI/KN view of caregiver_notes."""
        if not self.caregiver_notes:
            return {}
        return {k: self.caregiver_notes[k]
                for k in ("en", "hi", "kn") if k in self.caregiver_notes}


@dataclass
class VisitSlot:
    order: int
    time_label: str
    followup: FollowUp


@dataclass
class Report:
    plan_date: date
    followups: list[FollowUp]
    escalations: list[FollowUp]            # subset: CRITICAL
    plan: list[VisitSlot]
    summary: dict

    def to_dict(self) -> dict:
        def fu(f: FollowUp) -> dict:
            return {
                "name": f.patient.name,
                "village": f.patient.village,
                "category": f.patient.category.value,
                "priority": f.priority.value,
                "score": f.score,
                "due_date": f.patient.due_date.isoformat() if f.patient.due_date else None,
                "due_label": f.patient.due_label,
                "danger_signs": f.patient.danger_signs,
                "reasons": f.reasons,
                "action": f.action,
                "reminder_en": f.reminder_en,
                "reminder_hi": f.reminder_hi,
                "reminder_kn": f.reminder_kn,
                "reminders": f.reminders,
                "caregiver_note": f.caregiver_note or None,
                "caregiver_notes": f.caregiver_notes or None,
                "abha_id_from_notes": f.patient.abha_id or None,
            }
        return {
            "plan_date": self.plan_date.isoformat(),
            "summary": self.summary,
            "escalations": [fu(f) for f in self.escalations],
            "followups": [fu(f) for f in self.followups],
            "plan": [
                {"order": s.order, "time": s.time_label, **fu(s.followup)}
                for s in self.plan
            ],
        }
