STRINGS = {
    "native_name": "English",
    "actions": {
        "pregnant": "pregnancy checkup",
        "tb": "TB medicine and checkup",
        "child": "child's vaccination",
        "postpartum": "mother and baby checkup",
        "elderly": "medicine and checkup",
        "general": "checkup",
    },
    "reminder_normal": (
        "Namaste {name} ji, a reminder from your ASHA didi: your {action} "
        "is due on {due}. Please keep your card/paper ready. We will visit "
        "you before that. Take care!"
    ),
    "reminder_critical": (
        "URGENT: Namaste {name} ji, your health worker will visit you "
        "TODAY. Signs noted: {signs}. Please do not wait — if symptoms "
        "worsen, call 112 or 108, or go to the nearest PHC immediately."
    ),
    "caregiver_normal": (
        "For the family of {name}{place}: {action} is due on {due}. "
        "Please keep {first} at home when the health worker visits and "
        "keep the health card ready. For any emergency, call 112 or 108."
    ),
    "caregiver_critical": (
        "URGENT — for the family of {name}{place}: the health worker has "
        "noted danger signs ({signs}) and will come TODAY. Please stay "
        "with {first} and be ready to leave for the PHC. If things get "
        "worse, call 112 or 108 at once — do not wait."
    ),
    "ui": {
        "tagline": "Health companion for frontline health workers",
        "notes_label": "Today's notes",
        "date_label": "Today's date (optional)",
        "button": "Make tomorrow's plan",
        "demo_note": (
            "Demo with synthetic data only. Nothing you type is stored. "
            "SehatSathi supports the health worker — it does not diagnose "
            "or replace the PHC medical officer."
        ),
        "plan_for": "Plan for {date}",
        "escalate": "Escalate TODAY — do not wait",
        "route": "Tomorrow's route",
        "deferred_title": "Not in tomorrow's route (day cap reached)",
        "back": "New plan",
        "emergency_line": "Emergency 112 · Ambulance 108",
    },
}
