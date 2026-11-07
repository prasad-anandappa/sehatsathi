"""Screening-to-care loop layer — Future Health challenge build tests.

Covers the three committed features: screening intake, the three-state
loop tracker (screened → referred → care confirmed), and the day-end
closure summary that names everyone still open.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from sehatsathi import api as api_module
from sehatsathi.loop import LoopState, ScreeningLoop

DAY = date(2026, 11, 6)

CAMP_LIST = """# camp register — synthetic
Sunita Devi, Rampur, pregnant 8 months, high BP, severe headache, ANC checkup due in 2 days, referred to PHC
Rekha Kumari, Rampur, pregnant 5 months, low HB, iron tablets follow-up due in 4 days
Ramesh Kumar, Kishanpur, TB patient, missed 2 doses, DOTS review due tomorrow
Priya, Kishanpur, child 9 months, immunization overdue by 5 days, not referred
"""


def _loop() -> ScreeningLoop:
    loop = ScreeningLoop()
    loop.intake(CAMP_LIST, DAY)
    return loop


# ---- intake ---------------------------------------------------------

def test_intake_creates_one_record_per_person():
    loop = ScreeningLoop()
    result = loop.intake(CAMP_LIST, DAY)
    assert len(result["added"]) == 4
    assert loop.counts() == {"tracked": 4, "open": 4, "by_state": {
        "screened": 3, "referred": 1, "care confirmed": 0}}


def test_intake_line_marked_referred_starts_referred():
    loop = _loop()
    rec = next(r for r in loop.records() if r.patient.name == "Sunita Devi")
    assert rec.state is LoopState.REFERRED
    assert rec.referred_on == DAY
    # Danger sign survives intake and drives priority + reminder.
    assert rec.followup.priority.value == "CRITICAL"
    assert rec.followup.reminders["en"]


def test_intake_negated_referral_stays_screened():
    loop = _loop()
    rec = next(r for r in loop.records() if r.patient.name == "Priya")
    assert rec.state is LoopState.SCREENED


def test_intake_never_overwrites_a_tracked_person():
    loop = _loop()
    loop.refer("Rekha Kumari", DAY)
    result = loop.intake(CAMP_LIST, DAY)
    assert len(result["duplicates_skipped"]) == 4
    rec = next(r for r in loop.records() if r.patient.name == "Rekha Kumari")
    assert rec.state is LoopState.REFERRED  # state survived the re-intake


def test_intake_all_23_language_reminders_present():
    from sehatsathi.i18n import LANGUAGES
    loop = _loop()
    for rec in loop.records():
        assert set(rec.followup.reminders) == set(LANGUAGES)


# ---- state machine ----------------------------------------------------

def test_full_loop_screened_to_confirmed():
    loop = _loop()
    loop.refer("Rekha Kumari", DAY)
    rec = loop.confirm_care("Rekha Kumari", DAY)
    assert rec.state is LoopState.CARE_COMPLETED
    assert not rec.is_open
    assert [h["state"] for h in rec.history] == [
        "screened", "referred", "care confirmed"]


def test_confirm_before_referral_is_rejected():
    loop = _loop()
    with pytest.raises(ValueError, match="not been referred"):
        loop.confirm_care("Rekha Kumari", DAY)


def test_double_referral_is_rejected():
    loop = _loop()
    with pytest.raises(ValueError, match="already referred"):
        loop.refer("Sunita Devi", DAY)  # entered the loop already referred


def test_closed_loop_cannot_advance():
    loop = _loop()
    loop.refer("Rekha Kumari", DAY)
    loop.confirm_care("Rekha Kumari", DAY)
    with pytest.raises(ValueError):
        loop.refer("Rekha Kumari", DAY)
    with pytest.raises(ValueError):
        loop.confirm_care("Rekha Kumari", DAY)


def test_unknown_person_raises_keyerror():
    loop = _loop()
    with pytest.raises(KeyError):
        loop.refer("Nobody Here", DAY)


# ---- daily plan + closure ----------------------------------------------

def test_daily_plan_driven_by_unconfirmed_only():
    loop = _loop()
    loop.refer("Rekha Kumari", DAY)
    loop.confirm_care("Rekha Kumari", DAY)
    names = [f.patient.name for f in loop.daily_plan(DAY)]
    assert "Rekha Kumari" not in names          # confirmed → out of the plan
    assert names[0] == "Sunita Devi"            # danger sign ranks first


def test_closure_summary_names_everyone_still_open():
    loop = _loop()
    s = loop.closure_summary(DAY)
    assert s["screened_today"] == 4
    assert {d["name"] for d in s["still_open"]} == {
        "Sunita Devi", "Rekha Kumari", "Ramesh Kumar", "Priya"}
    assert s["open_escalations"] == ["Sunita Devi"]
    assert s["loop_fully_closed"] is False


def test_closure_report_names_open_and_closes_cleanly():
    loop = _loop()
    report = loop.closure_report(DAY)
    assert "Priya" in report and "Still open" in report
    for name in ("Sunita Devi", "Rekha Kumari", "Ramesh Kumar", "Priya"):
        loop.refer(name, DAY) if name != "Sunita Devi" else None
        loop.confirm_care(name, DAY)
    s = loop.closure_summary(DAY)
    assert s["loop_fully_closed"] is True
    assert "Loop fully closed" in loop.closure_report(DAY)


# ---- API -----------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    # v1.4.0: the loop store is durable (per-worker, in the DB), so
    # isolation = a fresh app on a throwaway database file per test.
    from sehatsathi.config import Settings
    settings = Settings(database_url=f"sqlite:///{tmp_path}/test.db")
    return TestClient(api_module.create_app(settings))


def test_api_loop_flow(client):
    r = client.post("/screening/intake",
                    json={"list_text": CAMP_LIST, "today": "2026-11-06"})
    assert r.status_code == 200
    body = r.json()
    assert body["loop"]["counts"]["tracked"] == 4

    r = client.post("/loop/refer", json={"name": "Rekha Kumari",
                                         "today": "2026-11-06"})
    assert r.status_code == 200
    r = client.post("/loop/confirm", json={"name": "Rekha Kumari",
                                           "today": "2026-11-06"})
    assert r.status_code == 200
    assert r.json()["record"]["state"] == "care confirmed"

    r = client.get("/loop/closure", params={"today": "2026-11-06"})
    assert r.status_code == 200
    assert len(r.json()["still_open"]) == 3


def test_api_loop_error_codes(client):
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": "2026-11-06"})
    r = client.post("/loop/confirm", json={"name": "Rekha Kumari"})
    assert r.status_code == 409                      # not referred yet
    r = client.post("/loop/refer", json={"name": "Ghost Person"})
    assert r.status_code == 404                      # unknown person


def test_api_loop_demo_is_self_contained(client):
    r = client.get("/loop/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["intake"]["added"] and body["closure"]["still_open"]
    assert "Still open" in body["closure_report"]
    # The demo ran in a throwaway loop — the shared store stays empty.
    assert client.get("/loop").json()["counts"]["tracked"] == 0


def test_loop_ui_intake_and_advance(client):
    r = client.get("/loop/ui")
    assert r.status_code == 200 and "<script" not in r.text
    r = client.post("/loop/ui/intake",
                    data={"list": CAMP_LIST, "today": "2026-11-06"})
    assert r.status_code == 200
    assert "Sunita Devi" in r.text and "Referred" in r.text
    assert "Still open" in r.text                    # closure section renders
    r = client.post("/loop/ui/advance",
                    data={"name": "Rekha Kumari", "action": "refer",
                          "today": "2026-11-06"})
    assert r.status_code == 200 and "marked referred" in r.text


def test_index_links_to_loop_mode(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/loop/ui"' in r.text
