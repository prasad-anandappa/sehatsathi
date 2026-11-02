"""SehatSathi agent — orchestrates extraction → scoring → plan → messages.

This is the agentic loop in one honest, inspectable pass:
PERCEIVE the day's notes, REASON about risk with explainable rules,
ACT by producing tomorrow's route plan, escalation list and patient
reminders. Every step is a separate, unit-tested tool function.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import extract, planner, risk
from .llm import ReminderEnhancer, get_enhancer
from .messages import make_reminders
from .models import Priority, Report


class SehatSathiAgent:
    def __init__(self, enhancer: ReminderEnhancer | None = None):
        self.enhancer = enhancer if enhancer is not None else get_enhancer()

    def run(self, notes: str, today: date | None = None) -> Report:
        today = today or date.today()
        plan_date = today + timedelta(days=1)
        patients = extract.parse_notes(notes, today)
        followups = [risk.score_patient(p, today) for p in patients]
        for fu in followups:
            en, hi = make_reminders(fu)
            fu.reminder_en, fu.reminder_hi = self.enhancer.enhance(en, hi)
        followups.sort(key=lambda f: -f.score)
        escalations = [f for f in followups if f.priority == Priority.CRITICAL]
        plan = planner.build_plan(followups)
        by_cat: dict[str, int] = {}
        for f in followups:
            by_cat[f.patient.category.value] = by_cat.get(f.patient.category.value, 0) + 1
        summary = {
            "patients_found": len(patients),
            "escalations": len(escalations),
            "high_priority": sum(1 for f in followups if f.priority == Priority.HIGH),
            "visits_planned": len(plan),
            "villages": sorted({f.patient.village for f in followups if f.patient.village}),
            "by_category": by_cat,
            "est_worker_minutes_saved": 25 * max(len(patients) - 1, 0),
            "note": ("Minutes-saved estimate: manual register sorting + reminder "
                     "writing ≈ 25 min/patient vs. one pasted note list."),
        }
        return Report(plan_date=plan_date, followups=followups,
                      escalations=escalations, plan=plan, summary=summary)

    def render_markdown(self, report: Report) -> str:
        lines = [f"# SehatSathi — Visit plan for {report.plan_date.isoformat()}",
                 "", f"Patients: **{report.summary['patients_found']}** · "
                 f"Escalations: **{report.summary['escalations']}** · "
                 f"Visits planned: **{report.summary['visits_planned']}**", ""]
        if report.escalations:
            lines += ["## 🚨 ESCALATE TODAY — do not wait for tomorrow", ""]
            for f in report.escalations:
                lines.append(f"- **{f.patient.name}** ({f.patient.village}) — "
                             f"{', '.join(f.patient.danger_signs)} → {f.action}")
            lines.append("")
        lines += ["## Tomorrow's route", "",
                  "| # | Time | Patient | Village | Priority | Why |",
                  "|---|------|---------|---------|----------|-----|"]
        for s in report.plan:
            f = s.followup
            lines.append(f"| {s.order} | {s.time_label} | {f.patient.name} | "
                         f"{f.patient.village} | {f.priority.value} | "
                         f"{'; '.join(f.reasons)} |")
        lines += ["", "## Patient reminders (copy → SMS/WhatsApp)", ""]
        for f in report.followups:
            lines.append(f"**{f.patient.name}:** {f.reminder_en}")
            lines.append(f"> {f.reminder_hi}")
            lines.append("")
        return "\n".join(lines)
