"""Phase 2 (2026-11-03) India-fit features — audit fix regression tests.

Covers: H1 negation-aware danger matching · H2 swelling split ·
M1 deferred visits surfaced · M4 helplines + 112 in escalations ·
M5 API input validation · L1 ABHA extraction · L2 caregiver notes ·
M3 Kannada reminders · demo-claim integrity (10 in → 3 escalations).
"""
from datetime import date

from fastapi.testclient import TestClient

from sehatsathi.agent import SehatSathiAgent
from sehatsathi.api import app
from sehatsathi.extract import parse_line
from sehatsathi.helplines import HELPLINES, helplines_for
from sehatsathi.models import Category, Priority

TODAY = date(2026, 11, 2)
client = TestClient(app, raise_server_exceptions=False)


# ---- H1: negation ----

def test_negated_signs_do_not_escalate():
    p = parse_line("Sunita Devi, Rampur, pregnant 5 months, no bleeding, "
                   "no swelling, ANC checkup due in 3 days", TODAY)
    assert p.danger_signs == []
    r = SehatSathiAgent().run(
        "Sunita Devi, Rampur, pregnant 5 months, no bleeding, "
        "ANC checkup due in 3 days", today=TODAY)
    assert r.escalations == []


def test_hindi_negation_after_sign():
    p = parse_line("Ramesh Kumar, Kishanpur, TB patient, khaansi mein "
                   "khoon nahi hai, DOTS review due tomorrow", TODAY)
    assert "coughing blood" not in p.danger_signs
    assert "vaginal bleeding" not in p.danger_signs


def test_real_sign_still_detected_next_to_negation():
    # One negated sign must not mask a real one in the same note.
    p = parse_line("Gita Devi, Rampur, pregnant 6 months, no bleeding, "
                   "severe headache, ANC due in 2 days", TODAY)
    assert "vaginal bleeding" not in p.danger_signs
    assert "severe headache" in p.danger_signs


# ---- H2: swelling split ----

def test_feet_swelling_is_risk_factor_not_danger():
    p = parse_line("Kamla Devi, Rampur, pregnant 6 months, swelling in "
                   "feet, ANC checkup due in 3 days", TODAY)
    assert "swelling of face/hands" not in p.danger_signs
    assert any("swelling noted" in r for r in p.risk_factors)
    r = SehatSathiAgent().run(
        "Kamla Devi, Rampur, pregnant 6 months, swelling in feet, "
        "ANC checkup due in 3 days", today=TODAY)
    assert r.followups[0].priority != Priority.CRITICAL


def test_face_swelling_is_danger():
    p = parse_line("Kamla Devi, Rampur, pregnant 6 months, swelling in "
                   "face, ANC checkup due in 3 days", TODAY)
    assert "swelling of face/hands" in p.danger_signs


# ---- M3 + M4: Kannada reminders, 112 in escalations ----

def test_kannada_reminder_present_and_dated():
    r = SehatSathiAgent().run(
        "Aarav, Rampur, child 18 months, measles vaccine due on 2026-11-05",
        today=TODAY)
    aarav = r.followups[0]
    assert aarav.reminder_kn
    assert "ನಮಸ್ಕಾರ" in aarav.reminder_kn
    assert "05 Nov 2026" in aarav.reminder_kn


def test_escalation_reminders_carry_112_and_108_all_languages():
    r = SehatSathiAgent().run(
        "Sunita Devi, Rampur, pregnant 8 months, severe headache, "
        "swelling in face, ANC checkup due in 2 days", today=TODAY)
    esc = r.escalations[0]
    for text in (esc.reminder_en, esc.reminder_hi, esc.reminder_kn):
        assert "112" in text and "108" in text


# ---- L2: caregiver notes ----

def test_caregiver_note_for_child_postpartum_elderly_only():
    r = SehatSathiAgent().run(
        "Aarav, Rampur, child 18 months, measles vaccine due on 2026-11-05\n"
        "Kamla Bai, Rampur, 62 years, BP medicine refill due in 3 days\n"
        "Anita Devi, Rampur, pregnant 3 months, ANC checkup due in 12 days",
        today=TODAY)
    by_name = {f.patient.name: f for f in r.followups}
    for name in ("Aarav", "Kamla Bai"):
        note = by_name[name].caregiver_note
        assert note and note["en"] and note["hi"] and note["kn"]
        assert "112" in note["en"]
    assert by_name["Anita Devi"].caregiver_note == {}


def test_caregiver_note_urgent_variant_for_critical():
    r = SehatSathiAgent().run(
        "Farida Bano, Rampur, postpartum, delivered 10 days ago, baby not "
        "feeding, postnatal checkup due today", today=TODAY)
    note = r.followups[0].caregiver_note
    assert note and "URGENT" in note["en"]


# ---- L1: ABHA extraction (recorded from notes only) ----

def test_abha_id_extracted_and_normalised():
    p = parse_line("Lata Devi, Rampur, pregnant 4 months, ABHA "
                   "12-3456-7890-1234, due in 5 days", TODAY)
    assert p.abha_id == "12-3456-7890-1234"
    assert p.phone == ""  # a 14-digit ABHA is not a phone number


def test_abha_address_extracted():
    p = parse_line("Lata Devi, Rampur, pregnant 4 months, abha "
                   "latadevi@abdm, due in 5 days", TODAY)
    assert p.abha_id == "latadevi@abdm"


# ---- M1: deferred visits surfaced ----

def test_plan_cap_defers_are_named_not_dropped():
    notes = "\n".join(
        f"Patient {i}, Rampur, pregnant 4 months, ANC due in {i} days"
        for i in range(1, 16))
    r = SehatSathiAgent().run(notes, today=TODAY)
    assert r.summary["patients_found"] == 15
    assert r.summary["visits_planned"] == 12
    assert r.summary["visits_deferred"] == 3
    assert len(r.summary["deferred_patients"]) == 3


# ---- M4: helplines ----

def test_helpline_numbers_verified_set():
    numbers = {h["number"] for h in HELPLINES}
    assert {"112", "108", "102", "104", "14555", "1800-11-6666",
            "1098", "181", "14416", "14567"} <= numbers


def test_helplines_for_category_starts_with_emergency():
    tb = helplines_for(Category.TB)
    assert [h["number"] for h in tb][:2] == ["112", "108"]
    assert "1800-11-6666" in [h["number"] for h in tb]


def test_helplines_endpoint():
    r = client.get("/helplines")
    assert r.status_code == 200
    assert any(h["number"] == "14555" for h in r.json()["helplines"])


# ---- M5: API validation ----

def test_bad_date_is_400_not_500():
    r = client.post("/plan", json={"notes": "x, due today",
                                   "today": "not-a-date"})
    assert r.status_code == 400


def test_oversized_notes_rejected():
    r = client.post("/plan", json={"notes": "x" * 100_001,
                                   "today": "2026-11-02"})
    assert r.status_code == 413


# ---- Claim integrity: the published demo numbers ----

def test_demo_claim_10_in_3_escalations():
    r = client.get("/demo")
    body = r.json()
    assert body["summary"]["patients_found"] == 10
    assert body["summary"]["escalations"] == 3
    assert body["summary"]["visits_planned"] == 10
