"""Reproducible effectiveness benchmark (v1.5.0).

JUDGING.md asks for proof the solution works, measurably. The unit
tests prove individual behaviours; this harness proves them in
aggregate, on a labelled corpus, with numbers a judge can re-run:

    PYTHONPATH=src python3 benchmarks/run_benchmark.py

The corpus is synthetic and hand-labelled: danger-sign lines (every
sign in the extractor's table), the same signs NEGATED the way
workers write them ("no bleeding", "khoon nahi hai") — a false
escalation there is the one error this product must never make —
category lines, spoken-number lines, and schedule-fallback lines.
Every metric is computed by running the real extractor + scorer;
nothing is hard-coded, and the tests assert the safety thresholds
(danger recall 1.0, negated-line false escalations 0).
"""
from __future__ import annotations

import time
from datetime import date

from . import extract, risk
from .agent import SehatSathiAgent

# (line, expected category, danger sign expected?)
CORPUS: list[tuple[str, str, bool]] = [
    # --- danger signs, one per extractor table entry ----------------
    ("Sunita Devi, Rampur, pregnant 7 months, bleeding, ANC due in 2 days", "pregnant", True),
    ("Gita Devi, Rampur, pregnant 8 months, severe headache, ANC due in 2 days", "pregnant", True),
    ("Anita Devi, Rampur, pregnant 6 months, blurred vision, ANC due in 3 days", "pregnant", True),
    ("Rekha Kumari, Rampur, pregnant 8 months, swelling in face, ANC due in 2 days", "pregnant", True),
    ("Kamla Devi, Rampur, pregnant 7 months, had fits yesterday, ANC due in 2 days", "pregnant", True),
    ("Farida Bano, Rampur, pregnant 9 months, baby not moving, ANC due in 1 day", "pregnant", True),
    ("Sita Devi, Kishanpur, postpartum, delivered 5 days ago, high fever, postnatal checkup due today", "postpartum", True),
    ("Munni Devi, Rampur, pregnant 5 months, severe abdominal pain, ANC due in 2 days", "pregnant", True),
    ("Ramesh Kumar, Kishanpur, TB patient, coughing blood, DOTS review due tomorrow", "tb", True),
    ("Mohan Lal, Kishanpur, 70 years, breathless, sugar test due in 2 days", "elderly", True),
    ("Hari Prasad, Rampur, 66 years, chest pain, BP check due in 2 days", "elderly", True),
    ("Lakshmi Bai, Rampur, postpartum, delivered 2 days ago, was unconscious, postnatal checkup due today", "postpartum", True),
    ("Priya Devi, Kishanpur, postpartum, delivered 10 days ago, baby not feeding, postnatal checkup due today", "postpartum", True),
    ("Radha Devi, Rampur, pregnant 4 months, severe vomiting, ANC due in 2 days", "pregnant", True),
    # --- the same signs, negated as workers write them --------------
    ("Sunita Devi, Rampur, pregnant 6 months, no bleeding, ANC due in 5 days", "pregnant", False),
    ("Gita Devi, Rampur, pregnant 8 months, no severe headache, ANC due in 5 days", "pregnant", False),
    ("Anita Devi, Rampur, pregnant 6 months, no blurred vision, ANC due in 5 days", "pregnant", False),
    ("Rekha Kumari, Rampur, pregnant 8 months, no swelling in face, ANC due in 5 days", "pregnant", False),
    ("Kamla Devi, Rampur, pregnant 7 months, no fits, ANC due in 5 days", "pregnant", False),
    ("Farida Bano, Rampur, pregnant 9 months, baby moving well, no reduced fetal movement, ANC due in 5 days", "pregnant", False),
    ("Sita Devi, Kishanpur, postpartum, delivered 5 days ago, no high fever, postnatal checkup due in 3 days", "postpartum", False),
    ("Munni Devi, Rampur, pregnant 5 months, no severe abdominal pain, ANC due in 5 days", "pregnant", False),
    ("Ramesh Kumar, Kishanpur, TB patient, cough clear, khaansi mein khoon nahi, DOTS review due in 4 days", "tb", False),
    ("Mohan Lal, Kishanpur, 70 years, no breathlessness, sugar test due in 5 days", "elderly", False),
    ("Hari Prasad, Rampur, 66 years, no chest pain, BP check due in 5 days", "elderly", False),
    ("Lakshmi Bai, Rampur, conscious and alert, not unconscious, medicine refill due in 5 days", "general", False),
    ("Priya Devi, Kishanpur, postpartum, delivered 10 days ago, baby feeding well, postnatal checkup due in 3 days", "postpartum", False),
    ("Radha Devi, Rampur, pregnant 4 months, no severe vomiting, ANC due in 5 days", "pregnant", False),
    # --- plain category lines ---------------------------------------
    ("Meena Kumari, Rampur, pregnant 4 months, ANC checkup due in 9 days", "pregnant", False),
    ("Sita Ram, Kishanpur, TB patient, DOTS review due in 2 days", "tb", False),
    ("Aarav, Rampur, child 12 months, vaccine due in 3 days", "child", False),
    ("Kavita Devi, Kishanpur, postpartum, postnatal checkup due in 4 days", "postpartum", False),
    ("Bhola Ram, Rampur, 68 years, BP medicine refill due in 5 days", "elderly", False),
    ("Ravi Kumar, Kishanpur, medicine refill due in 2 days", "general", False),
    # --- spoken-number lines -----------------------------------------
    ("Sunita Devi, Rampur, pregnant seven months, ANC due in two days", "pregnant", False),
    ("Ramesh Kumar, Kishanpur, TB patient, missed three doses, DOTS review due tomorrow", "tb", False),
    ("Priya, Kishanpur, child nine months, immunization overdue by ten days", "child", False),
    # --- schedule-fallback lines (stage given, no explicit date) -----
    ("Aarav, Rampur, child 9 months, brought for checkup", "child", False),
    ("Meena Kumari, Rampur, pregnant 5 months, first ANC visit pending", "pregnant", False),
    ("Kavita Devi, Kishanpur, postpartum, delivered 5 days ago, resting at home", "postpartum", False),
    ("Sita Ram, Kishanpur, TB patient, treatment month 1, DOTS review pending", "tb", False),
]

BENCHMARK_DATE = date(2026, 11, 2)


def run_benchmark(sample_notes: str = "") -> dict:
    """Run the corpus (and optionally the sample day) through the real
    pipeline and return the measured metrics as plain data."""
    danger_total = danger_caught = 0
    escalations = false_escalations = 0
    category_right = parsed = schedule_dated = 0
    for line, expected_category, danger in CORPUS:
        patient = extract.parse_line(line, BENCHMARK_DATE)
        if patient is None:
            continue
        parsed += 1
        if patient.category.value == expected_category:
            category_right += 1
        if patient.due_source == "schedule":
            schedule_dated += 1
        fu = risk.score_patient(patient, BENCHMARK_DATE)
        if danger:
            danger_total += 1
            if fu.priority.value == "CRITICAL":
                danger_caught += 1
        if fu.priority.value == "CRITICAL":
            escalations += 1
            if not danger:
                false_escalations += 1
    result = {
        "corpus_lines": len(CORPUS),
        "parsed": parsed,
        "danger_sign_lines": danger_total,
        "danger_signs_caught": danger_caught,
        "danger_recall": (danger_caught / danger_total) if danger_total else None,
        "escalations": escalations,
        "false_escalations": false_escalations,
        "category_accuracy": (category_right / parsed) if parsed else None,
        "schedule_fallback_dates": schedule_dated,
    }
    if sample_notes:
        start = time.perf_counter()
        report = SehatSathiAgent().run(sample_notes, today=BENCHMARK_DATE)
        result["sample_day"] = {
            "patients": report.summary["patients_found"],
            "escalations": report.summary["escalations"],
            "visits_planned": report.summary["visits_planned"],
            "reminder_languages_per_patient": len(
                report.followups[0].reminders) if report.followups else 0,
            "est_worker_minutes_saved": report.summary[
                "est_worker_minutes_saved"],
            "runtime_ms": round((time.perf_counter() - start) * 1000, 1),
        }
    return result
