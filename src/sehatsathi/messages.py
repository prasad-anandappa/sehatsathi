"""Per-patient reminder messages in simple language.

Written to be read aloud or sent as SMS/WhatsApp by the worker: short,
plain words, English + simple Hindi (Devanagari). A patient who cannot
read long English text still gets the date, the place and the one
action that matters.
"""
from __future__ import annotations

from .models import Category, FollowUp, Priority

_HI_ACTION = {
    Category.PREGNANT: "garbhavastha ki jaanch",
    Category.TB: "TB ki dawai aur jaanch",
    Category.CHILD: "bachche ka teeka",
    Category.POSTPARTUM: "maa aur bachche ki jaanch",
    Category.ELDERLY: "dawai aur jaanch",
    Category.GENERAL: "jaanch",
}


def make_reminders(fu: FollowUp) -> tuple[str, str]:
    p = fu.patient
    due = p.due_date.strftime("%d %b %Y") if p.due_date else "soon"
    if fu.priority == Priority.CRITICAL:
        en = (f"URGENT: Namaste {p.name} ji, your health worker will visit you TODAY. "
              f"Signs noted: {', '.join(p.danger_signs)}. Please do not wait — "
              f"if symptoms worsen, call 108 or go to the nearest PHC immediately.")
        hi = (f"ज़रूरी: नमस्ते {p.name} जी, आपकी स्वास्थ्य कार्यकर्ता आज ही आपसे मिलेंगी। "
              f"लक्षण: {', '.join(p.danger_signs)}। कृपया इंतज़ार न करें — "
              f"तबीयत बिगड़े तो 108 पर कॉल करें या नज़दीकी PHC जाएँ।")
        return en, hi
    en = (f"Namaste {p.name} ji, reminder from your ASHA didi: your {p.due_label} "
          f"is due on {due}. Please keep your card/paper ready. "
          f"We will visit you before that. Take care!")
    hi_action = _HI_ACTION.get(p.category, "jaanch")
    hi = (f"नमस्ते {p.name} जी, आपकी आशा दीदी की ओर से याद दिलाना है: आपकी "
          f"{hi_action} की तारीख़ {due} है। कृपया अपना कार्ड तैयार रखें। "
          f"हम उससे पहले आपसे मिलने आएँगे। अपना ध्यान रखें!")
    return en, hi
