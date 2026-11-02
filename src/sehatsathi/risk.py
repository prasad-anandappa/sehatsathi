"""Explainable risk scoring.

Every point in the score maps to a written reason, so a health worker
(or a judge, or a medical officer) can see *why* a patient is ranked
first. No black box: in primary care, an unexplained ranking is a
ranking nobody trusts.
"""
from __future__ import annotations

from datetime import date

from .models import Category, FollowUp, Patient, Priority


def score_patient(p: Patient, today: date) -> FollowUp:
    score, reasons = 0, []
    if p.danger_signs:
        score += 100
        reasons.append("DANGER SIGN: " + ", ".join(p.danger_signs) +
                       " — escalate to PHC/ANM today, do not wait")
    if p.due_date is not None:
        delta = (p.due_date - today).days
        if delta < 0:
            score += 40 + min(-delta, 20)
            reasons.append(f"{p.due_label} is overdue by {-delta} day(s)")
        elif delta == 0:
            score += 35
            reasons.append(f"{p.due_label} is due today")
        elif delta <= 3:
            score += 25
            reasons.append(f"{p.due_label} due in {delta} day(s)")
        elif delta <= 7:
            score += 12
            reasons.append(f"{p.due_label} due in {delta} day(s)")
    if p.category == Category.PREGNANT:
        if p.months_pregnant and p.months_pregnant >= 8:
            score += 15
            reasons.append("late pregnancy (8+ months) — delivery planning needed")
        if p.risk_factors:
            score += 8 * len(p.risk_factors)
            reasons.append("risk factors: " + ", ".join(p.risk_factors))
    if p.category == Category.TB and p.missed_doses:
        score += 10 * p.missed_doses
        reasons.append(f"missed {p.missed_doses} TB dose(s) — treatment interruption risk")
    if p.category == Category.CHILD and p.age_months is not None and p.age_months < 24:
        score += 6
        reasons.append("under-2 child — immunization window is time-critical")
    if p.category == Category.ELDERLY:
        score += 4
        reasons.append("elderly patient")

    if p.danger_signs:
        priority = Priority.CRITICAL
    elif score >= 45:
        priority = Priority.HIGH
    elif score >= 20:
        priority = Priority.MEDIUM
    else:
        priority = Priority.LOW

    action = _action(p, priority)
    return FollowUp(patient=p, priority=priority, score=score,
                    reasons=reasons or ["routine follow-up"], action=action)


def _action(p: Patient, priority: Priority) -> str:
    if priority == Priority.CRITICAL:
        return ("ESCALATE TODAY: call the ANM/PHC medical officer now, "
                "arrange referral transport (108 ambulance if needed), "
                "stay with the patient until handed over.")
    if p.category == Category.PREGNANT:
        return "Home visit: check BP, swelling, fetal movement; confirm ANC date at PHC."
    if p.category == Category.TB:
        return "Home visit: observed dose, ask about side-effects, motivate adherence."
    if p.category == Category.CHILD:
        return "Home visit: remind caregiver, check vaccine card, confirm session site/date."
    if p.category == Category.POSTPARTUM:
        return "Home visit: check mother and baby — feeding, bleeding, fever."
    return "Home visit: review medicines and symptoms, confirm next PHC visit."
