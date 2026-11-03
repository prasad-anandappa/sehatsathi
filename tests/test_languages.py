"""All-23-languages gate (user order 2026-11-03).

A language counts as DONE only when these pass for it: full string
table present, placeholders intact, emergency numbers present, text
renders in the language's native script (Unicode block check), clean
UTF-8 (no replacement chars), templates actually format, and the
agent/API/UI carry the language end to end.
"""
from datetime import date

from fastapi.testclient import TestClient

from sehatsathi.agent import SehatSathiAgent
from sehatsathi.api import app
from sehatsathi.i18n import LANGUAGE_META, LANGUAGES, SCRIPT_RANGE

client = TestClient(app)

SCHEDULED_22 = {
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "kok", "ks", "mai",
    "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta",
    "te", "ur",
}
CATEGORIES = {"pregnant", "tb", "child", "postpartum", "elderly", "general"}
UI_KEYS = {"tagline", "notes_label", "date_label", "button", "demo_note",
           "plan_for", "escalate", "route", "deferred_title", "back",
           "emergency_line"}
FIELDS = {"name": "Test Name", "first": "Test", "action": "X",
          "due": "05 Nov 2026", "signs": "bleeding", "place": " (Rampur)"}


def test_registry_covers_22_scheduled_plus_english():
    assert set(LANGUAGES) == SCHEDULED_22 | {"en"}
    assert set(LANGUAGE_META) == SCHEDULED_22 | {"en"}
    assert len(LANGUAGES) == 23


def test_every_language_table_is_complete():
    for code, s in LANGUAGES.items():
        assert s["native_name"].strip(), code
        assert set(s["actions"]) == CATEGORIES, code
        assert all(v.strip() for v in s["actions"].values()), code
        assert set(s["ui"]) == UI_KEYS, code
        assert all(str(v).strip() for v in s["ui"].values()), code
        for key in ("reminder_normal", "reminder_critical",
                    "caregiver_normal", "caregiver_critical"):
            assert s[key].strip(), (code, key)


def test_placeholders_and_emergency_numbers_survive_translation():
    for code, s in LANGUAGES.items():
        for token in ("{name}", "{action}", "{due}"):
            assert token in s["reminder_normal"], (code, token)
        for token in ("{name}", "{signs}"):
            assert token in s["reminder_critical"], (code, token)
        for token in ("{name}", "{place}", "{first}", "{action}", "{due}"):
            assert token in s["caregiver_normal"], (code, token)
        for token in ("{name}", "{place}", "{first}", "{signs}"):
            assert token in s["caregiver_critical"], (code, token)
        for key in ("reminder_critical", "caregiver_normal",
                    "caregiver_critical"):
            assert "112" in s[key], (code, key)
        assert "108" in s["reminder_critical"], code
        assert "112" in s["ui"]["emergency_line"], code


def test_native_script_rendering():
    for code, s in LANGUAGES.items():
        lo, hi = SCRIPT_RANGE[code]
        probe = s["actions"]["pregnant"] + s["native_name"]
        in_script = [c for c in probe if lo <= ord(c) <= hi]
        assert len(in_script) >= 2, (code, probe)


def test_clean_utf8_no_replacement_chars():
    def walk(v):
        if isinstance(v, str):
            assert "\ufffd" not in v
            v.encode("utf-8")  # must not raise
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    for s in LANGUAGES.values():
        walk(s)


def test_templates_format_and_carry_patient_fields():
    for code, s in LANGUAGES.items():
        normal = s["reminder_normal"].format(**FIELDS)
        assert "Test Name" in normal and "05 Nov 2026" in normal, code
        critical = s["reminder_critical"].format(**FIELDS)
        assert "112" in critical and "bleeding" in critical, code
        care = s["caregiver_normal"].format(**FIELDS)
        assert "Rampur" in care and "112" in care, code
        care_c = s["caregiver_critical"].format(**FIELDS)
        assert "112" in care_c and "bleeding" in care_c, code


def test_agent_emits_all_23_languages():
    notes = ("Sunita Devi, Rampur, pregnant 8 months, severe headache, "
             "ANC checkup due in 2 days\n"
             "Kiran Kumar, Rampur, child 14 months, vaccination due in 2 days")
    report = SehatSathiAgent().run(notes, today=date(2026, 11, 2))
    assert report.followups
    for fu in report.followups:
        assert set(fu.reminders) == set(LANGUAGES), fu.patient.name
        assert all(t.strip() for t in fu.reminders.values())
    child = next(f for f in report.followups
                 if f.patient.category.value == "child")
    assert set(child.caregiver_notes) == set(LANGUAGES)
    d = report.to_dict()
    assert set(d["followups"][0]["reminders"]) == set(LANGUAGES)


def test_language_picker_is_plain_form_no_js():
    r = client.get("/")
    assert r.status_code == 200
    assert "<script" not in r.text
    assert '<select id="lang" name="lang">' in r.text
    assert r.text.count("<option") == 23


def test_index_localises_and_falls_back():
    r = client.get("/?lang=ta")
    assert r.status_code == 200
    lo, hi = SCRIPT_RANGE["ta"]
    assert any(lo <= ord(c) <= hi for c in r.text)   # Tamil chrome
    r = client.get("/?lang=xx")
    assert r.status_code == 200
    assert "Demo with synthetic data only" in r.text  # English fallback


def test_ui_rtl_for_urdu_and_reminder_in_marathi():
    r = client.post("/ui", data={
        "notes": "Sunita Devi, Rampur, pregnant 8 months, severe headache, "
                 "ANC checkup due in 2 days",
        "today": "2026-11-02", "lang": "ur"})
    assert r.status_code == 200
    assert 'dir="rtl"' in r.text
    r = client.post("/ui", data={
        "notes": "Sunita Devi, Rampur, pregnant 8 months, ANC checkup due in 2 days",
        "today": "2026-11-02", "lang": "mr"})
    assert r.status_code == 200
    lo, hi = SCRIPT_RANGE["mr"]
    assert any(lo <= ord(c) <= hi for c in r.text)
