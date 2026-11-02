"""Next-day visit plan.

Ordering rule, in plain words: danger first, then highest risk score,
and within the same priority, patients in the same village are kept
together so the worker walks one route instead of criss-crossing the
area. Time slots start at 09:00, 40 minutes per visit (typical ASHA
home-visit + walking time), with a midday break after slot 5.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import FollowUp, Priority, VisitSlot

_ORDER = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}


def build_plan(followups: list[FollowUp], max_visits: int = 12) -> list[VisitSlot]:
    ordered = sorted(
        followups,
        key=lambda f: (_ORDER[f.priority], -f.score, f.patient.village, f.patient.name),
    )
    # Stable village-grouping inside each priority band: keeps the route sane
    # without ever letting geography outrank danger or risk.
    grouped: list[FollowUp] = []
    for band in (Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW):
        band_items = [f for f in ordered if f.priority == band]
        seen_villages: list[str] = []
        for f in band_items:
            if f.patient.village not in seen_villages:
                seen_villages.append(f.patient.village)
        grouped.extend(sorted(band_items, key=lambda f: seen_villages.index(f.patient.village)))

    start = datetime(2000, 1, 1, 9, 0)
    slots, current = [], start
    for i, fu in enumerate(grouped[:max_visits]):
        if i == 5:  # lunch / rest break
            current += timedelta(minutes=45)
        slots.append(VisitSlot(order=i + 1,
                               time_label=current.strftime("%I:%M %p"),
                               followup=fu))
        current += timedelta(minutes=40)
    return slots
