"""Per-patient reminder messages in all 22 scheduled languages + English.

Written to be read aloud or sent as SMS/WhatsApp by the worker: short,
plain words in the patient's own language and native script. The
string tables live in ``langs/`` (see ``i18n.py``); danger-sign labels
stay in English in every language because they are the worker's
clinical shorthand shared with the PHC. Every critical message carries
112 + 108 in every language.

For child / postpartum / elderly patients the person who must act is
usually a family member, so those follow-ups also carry a caregiver
note addressed to the family, in the same set of languages.
"""
from __future__ import annotations

from .i18n import LANGUAGES
from .models import Category, FollowUp, Priority

# Categories where a family caregiver is usually the actor.
_CAREGIVER_CATEGORIES = (Category.CHILD, Category.POSTPARTUM, Category.ELDERLY)


def _fields(fu: FollowUp, strings: dict) -> dict:
    p = fu.patient
    return {
        "name": p.name,
        "first": p.name.split()[0] if p.name.split() else p.name,
        "action": strings["actions"].get(p.category.value, strings["actions"]["general"]),
        "due": p.due_date.strftime("%d %b %Y") if p.due_date else "soon",
        "signs": ", ".join(p.danger_signs),
        "place": f" ({p.village})" if p.village else "",
    }


def make_reminders(fu: FollowUp) -> dict[str, str]:
    """Reminder text per language code, for every shipped language."""
    key = ("reminder_critical" if fu.priority == Priority.CRITICAL
           else "reminder_normal")
    return {code: s[key].format(**_fields(fu, s))
            for code, s in LANGUAGES.items()}


def make_caregiver_note(fu: FollowUp) -> dict[str, str]:
    """Family-facing note per language code.

    Returns {} for categories where the patient acts for herself.
    """
    if fu.patient.category not in _CAREGIVER_CATEGORIES:
        return {}
    key = ("caregiver_critical" if fu.priority == Priority.CRITICAL
           else "caregiver_normal")
    return {code: s[key].format(**_fields(fu, s))
            for code, s in LANGUAGES.items()}
