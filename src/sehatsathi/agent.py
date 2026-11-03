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
from .messages import make_caregiver_note, make_reminders
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
            reminders = make_reminders(fu)
            # The optional LLM enhancer may only touch EN/HI (its
            # original contract); every other language — Kannada
            # included — always stays the reviewed template.
            en, hi = self.enhancer.enhance(reminders["en"], reminders["hi"])
            reminders["en"], reminders["hi"] = en, hi
            fu.reminders = reminders
            fu.caregiver_notes = make_caregiver_note(fu)
        followups.sort(key=lambda f: -f.score)
        escalations = [f for f in followups if f.priority == Priority.CRITICAL]
        plan = planner.build_plan(followups)
        planned_names = {s.followup.patient.name for s in plan}
        deferred = [f.patient.name for f in followups
                    if f.patient.name not in planned_names]
        by_cat: dict[str, int] = {}
        for f in followups:
            by_cat[f.patient.category.value] = by_cat.get(f.patient.category.value, 0) + 1
        summary = {
            "patients_found": len(patients),
            "escalations": len(escalations),
            "high_priority": sum(1 for f in followups if f.priority == Priority.HIGH),
            "visits_planned": len(plan),
            # Audit M1: the route caps at planner.MAX_VISITS — anyone
            # beyond the cap is named here, never silently dropped.
            "visits_deferred": len(deferred),
            "deferred_patients": deferred,
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
            lines.append(f"> {f.reminder_kn}")
            if f.caregiver_note:
                lines.append(f"👨‍👩‍👧 *Family note:* {f.caregiver_note['en']}")
            lines.append("")
        if report.summary.get("visits_deferred"):
            lines += ["## ⏭️ Not in tomorrow's route (visit cap reached)", "",
                      "These follow-ups did not fit the day route — carry "
                      "them first the day after, or hand to the ANM: "
                      + ", ".join(report.summary["deferred_patients"]), ""]
        lines += ["---",
                  "Emergency: **112** · Ambulance: **108** · "
                  "Ayushman Bharat PM-JAY: **14555** · TB (Nikshay Sampark): "
                  "**1800-11-6666** · Child: **1098** · Women: **181** · "
                  "Mental health (Tele-MANAS): **14416**"]
        return "\n".join(lines)
