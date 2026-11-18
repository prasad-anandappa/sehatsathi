"""v1.6.0 — overdue flagging + case ownership (Future Health review).

Reviewer feedback asked for three things on the screening-to-care
loop: (1) a follow-up whose expected result / follow-up date has
passed unconfirmed is flagged DELAYED, (2) a referred case whose
visit date has passed unconfirmed is flagged MISSED VISIT, and
(3) every case has a named owner, shown prominently on flagged
cases. Flags are computed from the recorded due date — for a
referred case that date is the referral visit date.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from sehatsathi import api as api_module
from sehatsathi.loop import FLAG_DELAYED, FLAG_MISSED_VISIT, ScreeningLoop
from sehatsathi.ui import loop_page

INTAKE_DAY = date(2026, 11, 6)
LATER = date(2026, 11, 10)          # four days after intake
OWNER = "Kavita (ASHA, Rampur)"

LIST = """# synthetic camp list — v1.6 flag tests
Asha Rani, Rampur, pregnant 5 months, iron tablets follow-up due on 2026-11-08
Sunita Devi, Rampur, pregnant 8 months, ANC checkup due on 2026-11-08, referred to PHC
Ramesh Kumar, Kishanpur, TB patient, DOTS review due on 2026-11-20
Kamla Bai, Rampur, 62 years, BP medicine refill, no date recorded
"""


def _loop(owner: str = OWNER) -> ScreeningLoop:
    loop = ScreeningLoop(owner=owner)
    loop.intake(LIST, INTAKE_DAY)
    return loop


def _rec(loop, name):
    return next(r for r in loop.records() if r.patient.name == name)


# ---- delayed-result flagging -----------------------------------------

def test_screened_case_past_its_due_date_is_delayed():
    loop = _loop()
    rec = _rec(loop, "Asha Rani")
    assert rec.flags(LATER) == [FLAG_DELAYED]
    assert "DELAYED" in rec.flag_labels(LATER)[0]


def test_no_flag_before_or_on_the_due_date():
    loop = _loop()
    rec = _rec(loop, "Asha Rani")
    assert rec.flags(date(2026, 11, 7)) == []    # before
    assert rec.flags(date(2026, 11, 8)) == []    # the day itself


def test_case_without_a_due_date_is_never_flagged():
    loop = _loop()
    assert _rec(loop, "Kamla Bai").flags(LATER) == []
    assert _rec(loop, "Ramesh Kumar").flags(LATER) == []  # due 20th


def test_confirmed_case_is_never_flagged():
    loop = _loop()
    loop.refer("Asha Rani", INTAKE_DAY)
    loop.confirm_care("Asha Rani", date(2026, 11, 9))
    assert _rec(loop, "Asha Rani").flags(LATER) == []


# ---- missed-visit flagging ---------------------------------------------

def test_referred_case_past_its_visit_date_is_missed_visit():
    loop = _loop()
    rec = _rec(loop, "Sunita Devi")
    assert rec.flags(LATER) == [FLAG_MISSED_VISIT]
    assert "MISSED VISIT" in rec.flag_labels(LATER)[0]


def test_referred_case_within_window_is_not_flagged():
    loop = _loop()
    assert _rec(loop, "Sunita Devi").flags(date(2026, 11, 8)) == []


def test_missed_visit_takes_precedence_over_delayed():
    # A referred case past its date is the more specific failure —
    # exactly one flag, and it is the missed visit.
    loop = _loop()
    assert _rec(loop, "Sunita Devi").flags(LATER) == [FLAG_MISSED_VISIT]
    assert _rec(loop, "Asha Rani").flags(LATER) == [FLAG_DELAYED]


# ---- closure summary ----------------------------------------------------

def test_closure_summary_carries_flags_and_owner():
    loop = _loop()
    s = loop.closure_summary(LATER)
    assert s["delayed"] == ["Asha Rani"]
    assert s["missed_visits"] == ["Sunita Devi"]
    assert s["flag_counts"] == {"delayed": 1, "missed_visit": 1}
    flagged = {d["name"]: d for d in s["flagged"]}
    assert flagged["Asha Rani"]["owner"] == OWNER
    assert flagged["Sunita Devi"]["owner"] == OWNER
    assert flagged["Sunita Devi"]["flags"] == [FLAG_MISSED_VISIT]
    # Every still-open entry names its owner, flagged or not.
    assert all(d["owner"] == OWNER for d in s["still_open"])


def test_closure_report_names_flag_owner():
    report = _loop().closure_report(LATER)
    assert "MISSED VISIT" in report and "DELAYED" in report
    assert f"Owner: {OWNER}" in report


def test_closure_summary_before_due_dates_has_no_flags():
    s = _loop().closure_summary(INTAKE_DAY)
    assert s["flagged"] == [] and s["delayed"] == [] \
        and s["missed_visits"] == []


# ---- ownership -----------------------------------------------------------

def test_owner_defaults_to_the_loops_worker():
    loop = _loop()
    assert all(r.owner == OWNER for r in loop.records())
    assert all(r.owner_display == OWNER for r in loop.records())
    assert all(r.to_dict(LATER)["owner"] == OWNER
               for r in loop.records())


def test_bare_loop_owner_is_unassigned_not_blank():
    loop = ScreeningLoop()
    loop.intake(LIST, INTAKE_DAY)
    assert all(r.owner_display == "Unassigned" for r in loop.records())


def test_record_dict_carries_flags():
    d = _rec(_loop(), "Sunita Devi").to_dict(LATER)
    assert d["flags"] == [FLAG_MISSED_VISIT]
    assert d["flag_labels"] and "MISSED VISIT" in d["flag_labels"][0]
    assert d["owner"] == OWNER


def test_durable_loop_owner_is_the_worker_and_survives_reload(tmp_path):
    from sehatsathi.db import Store, make_session_factory
    from sehatsathi.loop_store import DurableScreeningLoop
    store = Store(make_session_factory(f"sqlite:///{tmp_path}/t.db"))
    store.upsert_worker("worker:919999900001", "919999900001", "worker")
    loop = DurableScreeningLoop(store, "worker:919999900001")
    assert loop.owner == "919999900001"     # profile phone = the worker
    loop.intake(LIST, INTAKE_DAY)
    reloaded = DurableScreeningLoop(store, "worker:919999900001")
    rec = _rec(reloaded, "Sunita Devi")
    assert rec.owner_display == "919999900001"
    assert rec.flags(LATER) == [FLAG_MISSED_VISIT]


# ---- tracker UI -----------------------------------------------------------

def test_loop_page_shows_flags_and_owner_prominently():
    page = loop_page(_loop(), LATER, demo=True)
    assert "DELAYED" in page and "MISSED VISIT" in page
    assert f"Owner: {OWNER}" in page
    # The closure section on the same page names flagged owners too.
    assert "Flagged overdue" in page


def test_loop_page_unflagged_day_shows_no_flag_banner():
    page = loop_page(_loop(), INTAKE_DAY, demo=True)
    assert "MISSED VISIT" not in page and "Flagged overdue" not in page
    assert f"Owner: {OWNER}" in page        # owner still on every card


# ---- API -------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    from sehatsathi.config import Settings
    settings = Settings(database_url=f"sqlite:///{tmp_path}/test.db")
    return TestClient(api_module.create_app(settings))


def test_api_loop_payload_carries_flags_and_owner(client):
    client.post("/screening/intake",
                json={"list_text": LIST, "today": "2026-11-06"})
    body = client.get("/loop", params={"today": "2026-11-10"}).json()
    by_name = {r["name"]: r for r in body["records"]}
    assert by_name["Asha Rani"]["flags"] == [FLAG_DELAYED]
    assert by_name["Sunita Devi"]["flags"] == [FLAG_MISSED_VISIT]
    assert by_name["Asha Rani"]["owner"] == "local-worker"
    assert "MISSED VISIT" in by_name["Sunita Devi"]["flag_labels"][0]


def test_api_closure_carries_flag_rollup(client):
    client.post("/screening/intake",
                json={"list_text": LIST, "today": "2026-11-06"})
    s = client.get("/loop/closure", params={"today": "2026-11-10"}).json()
    assert s["delayed"] == ["Asha Rani"]
    assert s["missed_visits"] == ["Sunita Devi"]
    assert s["flagged"][0]["owner"] == "local-worker"


def test_api_loop_demo_flags_the_overdue_referred_case(client):
    # The bundled synthetic camp list (intake day 2026-11-06) has one
    # referred case whose visit date (2026-11-01) has already passed.
    body = client.get("/loop/demo").json()
    assert body["closure"]["missed_visits"] == ["Priya"]
    assert body["closure"]["flagged"][0]["owner"] == \
        "Demo health worker (synthetic)"


def test_health_reports_v16(client):
    body = client.get("/health").json()
    assert body["version"] == "1.6.0"
