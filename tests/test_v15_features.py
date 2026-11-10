"""v1.5.0 — Code for a Billion feature pass.

Covers: programme-schedule due dates (UIP / ANC / PNC / TB),
spoken-number parsing, duplicate-line merging, referral slips,
loop closure aging + intake needs-review flags, the reproducible
benchmark's safety thresholds, the /impact evidence surfaces,
the supervisor HTML page, the worker register CSV + print sheet,
one-tap demo UI, script-aware display language, WhatsApp deep
links, helpline groups, and the page-weight budget.
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from sehatsathi import api as api_module
from sehatsathi.agent import SehatSathiAgent
from sehatsathi.benchmark import run_benchmark
from sehatsathi.config import Settings
from sehatsathi.extract import parse_line
from sehatsathi.i18n import detect_display_lang
from sehatsathi.loop import ScreeningLoop
from sehatsathi.messages import make_referral_slip

TODAY = date(2026, 11, 2)
SUPERVISOR_PHONE = "919123456780"
WORKER_PHONE = "919876543210"

CAMP_LIST = """# camp register — synthetic
Sunita Devi, Rampur, pregnant 8 months, high BP, severe headache, ANC checkup due in 2 days, referred to PHC
Rekha Kumari, Rampur, pregnant 5 months, low HB, iron tablets follow-up due in 4 days
"""


def _settings(tmp_path, **overrides) -> Settings:
    base = {"database_url": f"sqlite:///{tmp_path}/v15.db",
            "supervisor_phones": frozenset({SUPERVISOR_PHONE})}
    base.update(overrides)
    return Settings(**base)


def _client(tmp_path, **overrides) -> TestClient:
    return TestClient(api_module.create_app(_settings(tmp_path, **overrides)))


# ---- programme schedules ---------------------------------------------

def test_child_without_due_date_gets_uip_schedule_date():
    p = parse_line("Aarav, Rampur, child 9 months, brought for checkup", TODAY)
    assert p.due_source == "schedule"
    assert p.due_date is not None and p.due_date > TODAY
    assert "immunization" in p.due_label


def test_pregnancy_without_due_date_gets_anc_window():
    p = parse_line("Meena Kumari, Rampur, pregnant 5 months, first ANC visit pending", TODAY)
    assert p.due_source == "schedule"
    assert p.due_date is not None
    assert "ANC visit" in p.due_label


def test_postpartum_gets_pnc_day_from_delivery_age():
    p = parse_line("Kavita Devi, Kishanpur, postpartum, delivered 5 days ago, resting at home", TODAY)
    assert p.days_since_delivery == 5
    assert p.due_source == "schedule"
    assert p.due_date == TODAY + timedelta(days=2)  # day-7 visit


def test_tb_treatment_month_gets_sputum_checkpoint():
    p = parse_line("Sita Ram, Kishanpur, TB patient, treatment month 1, DOTS review pending", TODAY)
    assert p.treatment_month == 1
    assert p.due_source == "schedule"
    assert "sputum" in p.due_label


def test_explicit_due_date_beats_schedule():
    p = parse_line("Aarav, Rampur, child 9 months, vaccine due in 3 days", TODAY)
    assert p.due_source == "notes"
    assert p.due_date == TODAY + timedelta(days=3)


def test_schedule_reason_tells_worker_to_confirm():
    from sehatsathi.risk import score_patient
    p = parse_line("Aarav, Rampur, child 9 months, brought for checkup", TODAY)
    fu = score_patient(p, TODAY)
    assert any("programme schedule" in r for r in fu.reasons)


# ---- spoken numbers ----------------------------------------------------

def test_spoken_numbers_parse():
    p = parse_line("Sunita Devi, Rampur, pregnant seven months, ANC due in two days", TODAY)
    assert p.months_pregnant == 7
    assert p.due_date == TODAY + timedelta(days=2)
    p = parse_line("Ramesh Kumar, Kishanpur, TB patient, missed three doses, DOTS review due tomorrow", TODAY)
    assert p.missed_doses == 3
    p = parse_line("Priya, Kishanpur, child nine months, immunization overdue by ten days", TODAY)
    assert p.age_months == 9
    assert p.due_date == TODAY - timedelta(days=10)


# ---- duplicate-line merging ---------------------------------------------

def test_duplicate_lines_merge_keeping_worst_facts():
    notes = ("Sunita Devi, Rampur, pregnant 8 months, ANC checkup due in 2 days\n"
             "Sunita Devi, Rampur, pregnant 8 months, severe headache, ANC checkup due in 5 days\n")
    report = SehatSathiAgent().run(notes, today=TODAY)
    assert report.summary["patients_found"] == 1
    assert report.summary["duplicate_lines_merged"] == 1
    fu = report.followups[0]
    assert fu.patient.danger_signs == ["severe headache"]
    assert fu.patient.due_date == TODAY + timedelta(days=2)  # earliest
    assert fu.priority.value == "CRITICAL"


def test_same_name_different_village_not_merged():
    notes = ("Sunita Devi, Rampur, pregnant 8 months, ANC checkup due in 2 days\n"
             "Sunita Devi, Kishanpur, pregnant 8 months, ANC checkup due in 2 days\n")
    report = SehatSathiAgent().run(notes, today=TODAY)
    assert report.summary["patients_found"] == 2


# ---- referral slips -------------------------------------------------------

def test_referral_slip_only_for_critical_and_states_the_fence():
    report = SehatSathiAgent().run(
        "Sunita Devi, Rampur, pregnant 8 months, severe headache, ANC due in 2 days\n"
        "Rekha Kumari, Rampur, pregnant 5 months, iron tablets follow-up due in 4 days\n",
        today=TODAY)
    crit = report.escalations[0]
    assert set(crit.referral_slips) == {"en", "hi", "kn"}
    assert "not a diagnosis" in crit.referral_slips["en"]
    assert "Sunita Devi" in crit.referral_slips["en"]
    routine = report.followups[-1]
    assert routine.referral_slips == {}
    assert make_referral_slip(routine, TODAY) == {}


# ---- loop: aging + needs-review -------------------------------------------

def test_closure_summary_ages_open_records():
    loop = ScreeningLoop()
    loop.intake(CAMP_LIST, date(2026, 11, 2))
    s = loop.closure_summary(date(2026, 11, 7))  # 5 days later
    assert s["aging"] == {"opened_today": 0, "open_2_3_days": 0,
                          "open_4_plus_days": 2}
    assert all(d["days_open"] == 5 for d in s["still_open"])
    report = loop.closure_report(date(2026, 11, 7))
    assert "| 5d |" in report


def test_intake_flags_lines_with_nothing_to_act_on():
    loop = ScreeningLoop()
    result = loop.intake("Geeta Rani, Rampur\n" + CAMP_LIST, TODAY)
    assert result["needs_review"] == ["Geeta Rani"]
    assert "Sunita Devi" not in result["needs_review"]


# ---- benchmark --------------------------------------------------------------

def test_benchmark_safety_thresholds():
    result = run_benchmark()
    assert result["danger_recall"] == 1.0
    assert result["false_escalations"] == 0
    assert result["category_accuracy"] >= 0.97
    assert result["schedule_fallback_dates"] == 4


def test_benchmark_sample_day_matches_filing_numbers():
    from pathlib import Path
    notes = (Path(__file__).resolve().parents[1]
             / "data" / "sample_notes.txt").read_text(encoding="utf-8")
    day = run_benchmark(notes)["sample_day"]
    assert day["patients"] == 10
    assert day["escalations"] == 3
    assert day["visits_planned"] == 10
    assert day["reminder_languages_per_patient"] == 23


# ---- impact surfaces ----------------------------------------------------------

def test_impact_endpoint_shape(tmp_path):
    client = _client(tmp_path)
    r = client.get("/impact")
    assert r.status_code == 200
    body = r.json()
    assert body["deployment"]["workers_registered"] == 0
    assert body["reproducible_benchmark"]["danger_recall"] == 1.0
    assert body["languages_shipped"] == 23
    assert "synthetic" in body["honesty"]


def test_impact_page_renders(tmp_path):
    client = _client(tmp_path)
    r = client.get("/impact/ui")
    assert r.status_code == 200
    assert "Impact &amp; evidence" in r.text
    assert "False escalations" in r.text


def test_deployment_counts_reflect_store(tmp_path):
    client = _client(tmp_path)
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": "2026-11-06"},
                headers={"X-Worker-Phone": WORKER_PHONE})
    body = client.get("/deployment").json()
    assert body["loop_records_tracked"] == 2
    assert body["loop_records_open"] == 2
    assert body["by_village"]["Rampur"]["tracked"] == 2


# ---- supervisor page -------------------------------------------------------------

def test_supervisor_page_role_gated_and_aggregate(tmp_path):
    client = _client(tmp_path)
    assert client.get("/supervisor").status_code == 403
    r = client.get("/supervisor",
                   headers={"X-Worker-Phone": SUPERVISOR_PHONE})
    assert r.status_code == 200
    assert "Supervisor view" in r.text
    assert "By village" in r.text or "Workers" in r.text


def test_supervisor_summary_gains_outcome_metrics(tmp_path):
    client = _client(tmp_path)
    headers = {"X-Worker-Phone": WORKER_PHONE}
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": "2026-11-06"},
                headers=headers)
    client.post("/loop/refer", json={"name": "Sunita Devi", "today": "2026-11-06"},
                headers=headers)
    client.post("/loop/confirm", json={"name": "Sunita Devi", "today": "2026-11-08"},
                headers=headers)
    r = client.get("/supervisor/summary",
                   headers={"X-Worker-Phone": SUPERVISOR_PHONE})
    assert r.status_code == 200
    body = r.json()
    assert body["by_village"]["Rampur"]["closed"] == 1
    assert body["totals"]["mean_days_screened_to_care_confirmed"] == 2.0


# ---- worker register + print -------------------------------------------------------

def _worker_with_cases(tmp_path):
    client = _client(tmp_path)
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": "2026-11-06"},
                headers={"X-Worker-Phone": WORKER_PHONE})
    return client


def test_register_csv_is_the_workers_own(tmp_path):
    # Stub auth mode: /worker pages use the shared local worker, so
    # seed through the same surface the page reads.
    client = _client(tmp_path)
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": "2026-11-06"})
    r = client.get("/worker/register.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "Sunita Devi,Rampur,pregnant,referred,CRITICAL" in r.text


def test_print_sheets_render(tmp_path):
    client = _worker_with_cases(tmp_path)
    r = client.get("/loop/ui/print")
    assert r.status_code == 200 and "day sheet" in r.text
    r = client.get("/worker/print")
    assert r.status_code == 200 and "my day sheet" in r.text


# ---- demo / UI surfaces --------------------------------------------------------------

def test_demo_ui_one_tap_sample_day(tmp_path):
    client = _client(tmp_path)
    r = client.get("/demo/ui")
    assert r.status_code == 200
    assert "Sunita Devi" in r.text
    assert "Referral slip" in r.text  # escalations carry slips now


def test_whatsapp_link_only_when_phone_in_note(tmp_path):
    client = _client(tmp_path)
    notes = ("Sunita Devi, Rampur, pregnant 8 months, severe headache, "
             "ANC due in 2 days, 9876543210\n"
             "Rekha Kumari, Rampur, pregnant 5 months, iron tablets "
             "follow-up due in 4 days\n")
    r = client.post("/ui", data={"notes": notes, "today": "2026-11-02",
                                 "lang": "en"})
    assert r.status_code == 200
    assert "https://wa.me/919876543210" in r.text
    assert r.text.count("wa.me") == 1  # Rekha has no phone in her note


def test_script_detection_picks_display_language():
    assert detect_display_lang("सुनीता देवी, रामपुर, गर्भवती") == "hi"
    assert detect_display_lang("ಸುನೀತಾ ದೇವಿ, ರಾಮಪುರ") == "kn"
    assert detect_display_lang("Sunita Devi, Rampur, pregnant") is None
    assert detect_display_lang("a क") is None  # too little script to commit


def test_ui_post_in_devanagari_renders_hindi_page(tmp_path):
    client = _client(tmp_path)
    notes = ("सुनीता देवी, रामपुर, pregnant 8 months, severe headache, "
             "ANC due in 2 days")
    r = client.post("/ui", data={"notes": notes, "today": "2026-11-02",
                                 "lang": "en"})
    assert r.status_code == 200
    assert '<html lang="hi"' in r.text


def test_helplines_grouped(tmp_path):
    client = _client(tmp_path)
    body = client.get("/helplines").json()
    assert body["groups"]["emergency"][0]["number"] == "112"
    assert body["groups"]["tb"][0]["number"] == "1800-11-6666"


def test_health_reports_new_version(tmp_path):
    client = _client(tmp_path)
    assert client.get("/health").json()["version"] == "1.5.0"


def test_public_pages_stay_light(tmp_path):
    """The README's low-bandwidth promise, enforced: every public
    page under 30 KB of HTML."""
    client = _client(tmp_path)
    for path in ("/", "/demo/ui", "/impact/ui", "/loop/ui", "/login"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert len(r.content) < 30_000, (path, len(r.content))
