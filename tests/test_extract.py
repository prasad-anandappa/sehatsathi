from datetime import date, timedelta

from sehatsathi.extract import parse_line, parse_notes
from sehatsathi.models import Category

TODAY = date(2026, 11, 2)


def test_pregnant_with_danger_signs():
    p = parse_line("Sunita Devi, Rampur, pregnant 8 months, swelling in face, "
                   "severe headache, ANC checkup due in 2 days", TODAY)
    assert p.category == Category.PREGNANT
    assert p.months_pregnant == 8
    assert "severe headache" in p.danger_signs
    assert "swelling of face/hands" in p.danger_signs
    assert p.due_date == TODAY + timedelta(days=2)
    assert p.village == "Rampur"


def test_tb_missed_doses():
    p = parse_line("Ramesh Kumar, Kishanpur, TB patient, missed 2 doses, "
                   "DOTS review due tomorrow", TODAY)
    assert p.category == Category.TB
    assert p.missed_doses == 2
    assert p.due_date == TODAY + timedelta(days=1)


def test_child_immunization_iso_date():
    p = parse_line("Aarav, Rampur, child 18 months, measles vaccine due on 2026-11-05", TODAY)
    assert p.category == Category.CHILD
    assert p.age_months == 18
    assert p.due_date == date(2026, 11, 5)


def test_overdue_parsing():
    p = parse_line("Priya, Kishanpur, child 9 months, immunization overdue by 10 days", TODAY)
    assert p.due_date == TODAY - timedelta(days=10)


def test_elderly_from_age():
    p = parse_line("Kamla Bai, Rampur, 62 years, BP medicine refill due in 3 days", TODAY)
    assert p.category == Category.ELDERLY
    assert p.age_years == 62


def test_hindi_danger_words():
    p = parse_line("Gita Devi, Rampur, pregnant 6 months, tez bukhar, behosh", TODAY)
    assert "high fever" in p.danger_signs
    assert "unconscious" in p.danger_signs


def test_parse_notes_skips_comments_and_blanks():
    patients = parse_notes("# header\n\nRamesh Kumar, TB patient, due today\n", TODAY)
    assert len(patients) == 1
    assert patients[0].due_date == TODAY


def test_phone_extraction():
    p = parse_line("Lata Devi, Rampur, pregnant 4 months, 9812345678, due in 5 days", TODAY)
    assert p.phone == "9812345678"
