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

from datetime import date

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


# Referral slips (v1.5.0) — hand-written in EN/HI/KN like the other
# worker-facing fixed texts (the helpline footer in agent.py). A slip
# is a RECORDS hand-over note: it states what the worker noted and
# that the patient was referred today. It is not a diagnosis, not a
# prescription, and says so on its face in all three languages.
_SLIP_TEMPLATES = {
    "en": (
        "REFERRAL SLIP — SehatSathi record\n"
        "Patient: {name}{place}\nDate: {date}\n"
        "Noted by the health worker: {signs}\n"
        "Referred to the PHC / ANM today. Please carry this slip and "
        "the health card.\n"
        "Emergency: 112 · Ambulance: 108\n"
        "This slip only records what the health worker noted. It is "
        "not a diagnosis."
    ),
    "hi": (
        "रेफ़रल पर्ची — SehatSathi रिकॉर्ड\n"
        "मरीज़: {name}{place}\nदिनांक: {date}\n"
        "स्वास्थ्य कार्यकर्ता ने दर्ज किया: {signs}\n"
        "आज PHC / ANM के पास भेजा गया है। कृपया यह पर्ची और "
        "स्वास्थ्य कार्ड साथ ले जाएँ।\n"
        "आपातकाल: 112 · एंबुलेंस: 108\n"
        "यह पर्ची केवल वही दर्ज करती है जो स्वास्थ्य कार्यकर्ता ने "
        "नोट किया। यह कोई निदान (diagnosis) नहीं है।"
    ),
    "kn": (
        "ರೆಫರಲ್ ಚೀಟಿ — SehatSathi ದಾಖಲೆ\n"
        "ರೋಗಿ: {name}{place}\nದಿನಾಂಕ: {date}\n"
        "ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆ ದಾಖಲಿಸಿದ್ದು: {signs}\n"
        "ಇಂದು PHC / ANM ಬಳಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಈ ಚೀಟಿ ಮತ್ತು "
        "ಆರೋಗ್ಯ ಕಾರ್ಡ್ ತೆಗೆದುಕೊಂಡು ಹೋಗಿ.\n"
        "ತುರ್ತು: 112 · ಆಂಬ್ಯುಲೆನ್ಸ್: 108\n"
        "ಈ ಚೀಟಿ ಆರೋಗ್ಯ ಕಾರ್ಯಕರ್ತೆ ದಾಖಲಿಸಿದ್ದನ್ನು ಮಾತ್ರ ತೋರಿಸುತ್ತದೆ. "
        "ಇದು ರೋಗನಿರ್ಣಯ (diagnosis) ಅಲ್ಲ."
    ),
}


def make_referral_slip(fu: FollowUp, on: date) -> dict[str, str]:
    """Referral slip text per language (en/hi/kn) for a CRITICAL
    follow-up; {} for anything else — slips exist only where a
    same-day human referral is being recorded."""
    if fu.priority != Priority.CRITICAL:
        return {}
    p = fu.patient
    fields = {
        "name": p.name,
        "place": f" ({p.village})" if p.village else "",
        "date": on.strftime("%d %b %Y"),
        "signs": ", ".join(p.danger_signs) or "danger sign noted",
    }
    return {code: tpl.format(**fields)
            for code, tpl in _SLIP_TEMPLATES.items()}


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
