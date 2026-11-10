"""Standard programme schedules — records arithmetic, nothing more.

When a worker's note gives a person's stage (a child's age in months,
a pregnancy's month, days since delivery, a TB treatment month) but no
explicit due date, the next checkpoint on the standard national
programme schedule is a matter of published record — the same table
printed on the MCP card and the immunization chart on the PHC wall:

- UIP immunization checkpoints (birth, 6/10/14 weeks, 9 months,
  16–24 months, 5–6 years),
- the standard ANC visit windows (by 12, 26 and 34 weeks, then term),
- postnatal home-visit days (1, 3, 7, 14, 21, 28, 42 after delivery),
- TB follow-up checkpoints (month-2 sputum review, end of treatment).

This module only computes the next checkpoint date from the stage.
It never decides anything clinical: every date it produces is labelled
``due_source="schedule"`` and the worker is told, in the risk reasons,
to confirm it on the child's MCP card / the register at the visit —
cards get updated, schedules get revised, and the card in the mother's
hand is the record that counts.
"""
from __future__ import annotations

from datetime import date, timedelta

_DAYS_PER_MONTH = 30.44  # average month, for age→date arithmetic

# (age in months at the checkpoint, what is due) — Universal
# Immunization Programme, simplified to the checkpoints an ASHA
# tracks day to day.
IMMUNIZATION_CHECKPOINTS: list[tuple[float, str]] = [
    (0.0, "birth doses"),
    (1.5, "6-week vaccines"),
    (2.5, "10-week vaccines"),
    (3.5, "14-week vaccines"),
    (9.0, "9-month vaccines (MR-1)"),
    (16.0, "16-month vaccines (MR-2 + boosters)"),
    (60.0, "5-year booster (DPT)"),
]

# (pregnancy week by which the visit is due, label) — the standard
# ANC visit windows every ASHA register carries.
ANC_CHECKPOINT_WEEKS: list[tuple[int, str]] = [
    (12, "ANC visit 1 (by 12 weeks)"),
    (26, "ANC visit 2 (by 26 weeks)"),
    (34, "ANC visit 3 (by 34 weeks)"),
    (40, "ANC visit 4 / delivery planning (by 40 weeks)"),
]

# Days after delivery on which a postnatal home visit is scheduled.
PNC_VISIT_DAYS: list[int] = [1, 3, 7, 14, 21, 28, 42]

# (treatment month, what is due) — TB regimen follow-up checkpoints.
TB_CHECKPOINTS: list[tuple[int, str]] = [
    (2, "month-2 sputum follow-up"),
    (6, "end-of-treatment review"),
]


def _next_after(checkpoints, value):
    for cp in checkpoints:
        if value < cp[0]:
            return cp
    return None


def next_immunization(age_months: int, today: date) -> tuple[date, str] | None:
    """Next UIP checkpoint for a child of `age_months`, as a due date.

    Returns None when the child is past the last checkpoint this
    table tracks (5-year booster) — the agent then says nothing
    rather than inventing a date.
    """
    cp = _next_after(IMMUNIZATION_CHECKPOINTS, float(age_months))
    if cp is None:
        return None
    days = round((cp[0] - age_months) * _DAYS_PER_MONTH)
    return today + timedelta(days=max(days, 0)), f"immunization — {cp[1]}"


def next_anc_visit(months_pregnant: int, today: date) -> tuple[date, str] | None:
    """Next ANC window for a pregnancy of `months_pregnant` months."""
    weeks = months_pregnant * 4.345  # average weeks per month
    cp = _next_after(ANC_CHECKPOINT_WEEKS, weeks)
    if cp is None:
        return None
    days = round((cp[0] - weeks) * 7)
    return today + timedelta(days=max(days, 0)), cp[1]


def next_pnc_visit(days_since_delivery: int, today: date) -> tuple[date, str] | None:
    """Next postnatal home-visit day for a mother `days_since_delivery`
    days past delivery."""
    for cp_day in PNC_VISIT_DAYS:
        if days_since_delivery < cp_day:
            return (today + timedelta(days=cp_day - days_since_delivery),
                    f"postnatal home visit (day {cp_day})")
    return None


def next_tb_checkpoint(treatment_month: int, today: date) -> tuple[date, str] | None:
    """Next TB follow-up checkpoint for a patient in `treatment_month`
    of the standard regimen."""
    cp = _next_after(TB_CHECKPOINTS, treatment_month)
    if cp is None:
        return None
    days = round((cp[0] - treatment_month) * _DAYS_PER_MONTH)
    return today + timedelta(days=max(days, 0)), cp[1]
