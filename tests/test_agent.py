from datetime import date

from sehatsathi.agent import SehatSathiAgent
from sehatsathi.models import Priority

TODAY = date(2026, 11, 2)
NOTES = """Sunita Devi, Rampur, pregnant 8 months, high BP, swelling in feet, severe headache, ANC checkup due in 2 days
Ramesh Kumar, Kishanpur, TB patient, missed 2 doses, DOTS review due tomorrow
Aarav, Rampur, child 18 months, measles vaccine due on 2026-11-05
Anita Devi, Rampur, pregnant 3 months, first pregnancy, ANC checkup due in 12 days
"""


def run():
    return SehatSathiAgent().run(NOTES, today=TODAY)


def test_danger_sign_patient_is_critical_and_escalated():
    r = run()
    assert len(r.escalations) == 1
    assert r.escalations[0].patient.name == "Sunita Devi"
    assert r.escalations[0].priority == Priority.CRITICAL
    assert "108" in r.escalations[0].reminder_en


def test_plan_orders_critical_first_and_covers_all():
    r = run()
    assert r.plan[0].followup.patient.name == "Sunita Devi"
    assert len(r.plan) == 4
    assert [s.order for s in r.plan] == [1, 2, 3, 4]
    assert r.plan[0].time_label == "09:00 AM"


def test_reminders_bilingual_and_dated():
    r = run()
    aarav = next(f for f in r.followups if f.patient.name == "Aarav")
    assert "05 Nov 2026" in aarav.reminder_en
    assert aarav.reminder_hi  # Hindi reminder present
    assert "नमस्ते" in aarav.reminder_hi


def test_summary_counts():
    r = run()
    assert r.summary["patients_found"] == 4
    assert r.summary["escalations"] == 1
    assert r.summary["by_category"]["pregnant"] == 2
    assert r.plan_date.isoformat() == "2026-11-03"


def test_tb_adherence_raises_priority():
    r = run()
    ramesh = next(f for f in r.followups if f.patient.name == "Ramesh Kumar")
    assert any("missed 2" in reason for reason in ramesh.reasons)
    assert ramesh.priority in (Priority.HIGH, Priority.MEDIUM)
    assert ramesh.score >= 45


def test_markdown_render_has_escalation_section():
    agent = SehatSathiAgent()
    md = agent.render_markdown(agent.run(NOTES, today=TODAY))
    assert "ESCALATE TODAY" in md
    assert "Tomorrow's route" in md


def test_report_to_dict_is_json_safe():
    import json
    json.dumps(run().to_dict())
