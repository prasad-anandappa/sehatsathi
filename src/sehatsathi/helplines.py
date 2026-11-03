"""Verified Indian health & emergency helplines.

National numbers, checked 2026-11-03 against official sources
(Central TB Division / MoHFW for Nikshay Sampark, a Lok Sabha answer
for Tele-MANAS, National Health Authority channels for PM-JAY).
102 and 104 run in *many* states (not all) — the wording says so,
and a worker should always confirm the local equivalent at the PHC.
Static reference data only: no lookup, no dialling, no integration.
"""
from __future__ import annotations

from .models import Category

HELPLINES: list[dict] = [
    {"name": "Emergency (police, fire, ambulance)", "number": "112",
     "note": "One national emergency number, works across India."},
    {"name": "Ambulance", "number": "108",
     "note": "Free ambulance in most states."},
    {"name": "Pregnancy & sick-infant transport", "number": "102",
     "note": "Janani/child transport ambulance — runs in many states."},
    {"name": "Health information helpline", "number": "104",
     "note": "Health advice & facility information — runs in many states."},
    {"name": "Ayushman Bharat PM-JAY", "number": "14555",
     "note": "Eligibility, Ayushman card, empanelled hospitals (toll-free)."},
    {"name": "TB helpline — Nikshay Sampark", "number": "1800-11-6666",
     "note": "TB counselling, treatment support, notification (toll-free)."},
    {"name": "Child Helpline", "number": "1098",
     "note": "For any child in distress, 24x7."},
    {"name": "Women Helpline", "number": "181",
     "note": "For women in distress."},
    {"name": "Mental health — Tele-MANAS", "number": "14416",
     "note": "Free, confidential mental-health support, 24x7."},
    {"name": "Senior citizens — Elder Line", "number": "14567",
     "note": "Support and information for elderly people (toll-free)."},
]

_BY_NUMBER = {h["number"]: h for h in HELPLINES}

# The lines most relevant to each patient category, shown alongside
# that patient's follow-up. 112 + 108 are always included.
_RELEVANT = {
    Category.PREGNANT: ["14555", "102"],
    Category.TB: ["1800-11-6666", "14555"],
    Category.CHILD: ["1098", "102"],
    Category.POSTPARTUM: ["102", "181"],
    Category.ELDERLY: ["14567", "14555"],
    Category.GENERAL: ["104"],
}


def helplines_for(category: Category) -> list[dict]:
    """112/108 always first, then the category-relevant lines."""
    numbers = ["112", "108"] + _RELEVANT.get(category, [])
    return [_BY_NUMBER[n] for n in numbers]
