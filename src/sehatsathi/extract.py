"""Deterministic extraction of follow-up patients from visit notes.

Input is the way ASHA/ANM workers actually write (or dictate) notes at
the end of a day — one patient per line, free text, mixed English/Hindi
words. This parser is rule-based on purpose: it must work offline, be
auditable, and never hallucinate a patient who is not in the notes.

Examples it understands:
  Sunita Devi, Rampur, pregnant 7 months, swelling in feet, severe
  headache, ANC checkup due in 3 days
  Ramesh Kumar, TB patient, missed 2 doses, DOTS review due tomorrow
  Aarav, child 18 months, Rampur, measles vaccine due on 2026-11-10
  Kamla Bai, 62 years, BP medicine refill due in 5 days
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .models import Category, Patient

# Danger signs — aligned with common maternal / TB / child red flags
# taught in ASHA training modules (bleeding, convulsions, reduced fetal
# movement, severe headache with swelling, coughing blood, high fever...).
DANGER_SIGNS: dict[str, list[str]] = {
    "vaginal bleeding": ["bleeding", "blood loss", "khoon"],
    "severe headache": ["severe headache", "tez sir dard"],
    "blurred vision": ["blurred vision", "dhundla dikh"],
    "swelling of face/hands/feet": ["swelling", "soojan"],
    "convulsions / fits": ["convulsion", "fits", "mirgi", "daura"],
    "reduced fetal movement": ["baby not moving", "reduced fetal movement",
                               "bachcha hil nahi"],
    "high fever": ["high fever", "tez bukhar", "fever 103", "fever 104"],
    "severe abdominal pain": ["severe abdominal pain", "severe stomach pain",
                              "tez pet dard"],
    "coughing blood": ["coughing blood", "blood in cough", "khaansi mein khoon"],
    "breathlessness": ["breathless", "difficulty breathing", "saans phool"],
    "chest pain": ["chest pain"],
    "unconscious": ["unconscious", "behosh"],
    "baby not feeding": ["baby not feeding", "not feeding", "doodh nahi pi"],
    "severe vomiting": ["severe vomiting", "cannot keep water"],
}

_HINDI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _norm(text: str) -> str:
    return text.translate(_HINDI_DIGITS).lower()


def _find_danger_signs(low: str) -> list[str]:
    found = []
    for label, variants in DANGER_SIGNS.items():
        if any(v in low for v in variants):
            found.append(label)
    return found


def _parse_due(low: str, today: date) -> date | None:
    m = re.search(r"due (?:on|by) (\d{4}-\d{2}-\d{2})", low)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    m = re.search(r"due in (\d+) days?", low)
    if m:
        return today + timedelta(days=int(m.group(1)))
    if "due tomorrow" in low:
        return today + timedelta(days=1)
    if "due today" in low or "due now" in low:
        return today
    m = re.search(r"overdue (?:by )?(\d+) days?", low)
    if m:
        return today - timedelta(days=int(m.group(1)))
    if "overdue" in low:
        return today - timedelta(days=1)
    return None


def _due_label(low: str, category: Category) -> str:
    for phrase in ("anc checkup", "anc visit", "immunization", "immunisation",
                   "vaccine", "vaccination", "dots review", "dots",
                   "medicine refill", "bp check", "sugar test", "scan",
                   "ultrasound", "iron tablets", "follow-up", "follow up",
                   "checkup", "delivery"):
        if phrase in low:
            return phrase.upper() if phrase in ("anc checkup", "anc visit", "dots", "dots review") else phrase
    return {
        Category.PREGNANT: "ANC checkup",
        Category.TB: "DOTS review",
        Category.CHILD: "immunization",
        Category.POSTPARTUM: "postnatal checkup",
    }.get(category, "follow-up visit")


def parse_line(line: str, today: date) -> Patient | None:
    line = line.strip(" \t-•*")
    if not line or line.startswith("#"):
        return None
    low = _norm(line)
    parts = [p.strip() for p in re.split(r"[,;]", line) if p.strip()]
    if not parts:
        return None
    name = parts[0].title()

    category = Category.GENERAL
    months_pregnant = None
    m = re.search(r"pregnan\w*(?:\s+of)?\s*(\d+)\s*month", low)
    if "pregnan" in low or "garbh" in low:
        category = Category.PREGNANT
        if m:
            months_pregnant = int(m.group(1))
    elif re.search(r"\btb\b", low) or "tuberculosis" in low or "dots" in low:
        category = Category.TB
    elif "postpartum" in low or "delivered" in low or "after delivery" in low:
        category = Category.POSTPARTUM
    elif "child" in low or "vaccine" in low or "immunis" in low or "immuniz" in low:
        category = Category.CHILD

    age_years, age_months = None, None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?|saal)\b", low)
    if m:
        age_years = float(m.group(1))
    m = re.search(r"child\s+(\d+)\s*months?", low) or re.search(r"(\d+)\s*months?\s*old", low)
    if m:
        age_months = int(m.group(1))
        if category == Category.GENERAL:
            category = Category.CHILD
    if age_years is not None and age_years >= 60 and category == Category.GENERAL:
        category = Category.ELDERLY

    missed = 0
    m = re.search(r"missed\s+(\d+)\s+dose", low)
    if m:
        missed = int(m.group(1))

    risks = []
    for key, label in (("high bp", "high BP"), ("hypertension", "hypertension"),
                       ("low hb", "low haemoglobin"), ("anaemia", "anaemia"),
                       ("anemia", "anaemia"), ("diabetes", "diabetes"),
                       ("previous c-section", "previous C-section"),
                       ("first pregnancy", "first pregnancy"),
                       ("twin", "twin pregnancy"), ("underweight", "underweight")):
        if key in low:
            risks.append(label)

    # Village = a capitalised token-part that is not the name and not a
    # keyword segment; simplest robust heuristic: second comma-part when
    # it is 1-3 words and contains no digit/keyword.
    village = ""
    keywords = ("pregnan", "tb", "child", "due", "missed", "vaccine", "year", "month")
    for part in parts[1:]:
        pl = part.lower()
        if len(part.split()) <= 3 and not any(k in pl for k in keywords) \
                and not re.search(r"\d", part):
            village = part.title()
            break

    phone_m = re.search(r"\b[6-9]\d{9}\b", line)
    return Patient(
        name=name, category=category, village=village,
        age_years=age_years, age_months=age_months,
        phone=phone_m.group(0) if phone_m else "",
        due_date=_parse_due(low, today),
        due_label=_due_label(low, category),
        risk_factors=risks, danger_signs=_find_danger_signs(low),
        missed_doses=missed, months_pregnant=months_pregnant,
        raw_note=line,
    )


def parse_notes(notes: str, today: date) -> list[Patient]:
    patients = []
    for line in notes.splitlines():
        p = parse_line(line, today)
        if p is not None:
            patients.append(p)
    return patients
