"""Phase 2 (2026-11-03) HTML UI — audit M2 regression tests.

The UI must work with no JavaScript, stay small enough for patchy
connections, and never let note text break out into raw HTML.
"""
from fastapi.testclient import TestClient

from sehatsathi.api import app

client = TestClient(app)


def test_index_is_a_plain_form_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<form" in r.text and 'name="notes"' in r.text
    assert "<script" not in r.text            # zero JavaScript by design
    assert len(r.content) < 30_000            # low-bandwidth budget


def test_ui_plan_renders_escalation_route_and_kannada():
    r = client.post("/ui", data={
        "notes": "Sunita Devi, Rampur, pregnant 8 months, severe headache, "
                 "swelling in face, ANC checkup due in 2 days",
        "today": "2026-11-02",
    })
    assert r.status_code == 200
    assert "Escalate TODAY" in r.text
    assert "Sunita Devi" in r.text
    assert "Namaste Sunita" in r.text          # English reminder (default)
    assert "112" in r.text                    # helpline footer present
    r = client.post("/ui", data={
        "notes": "Sunita Devi, Rampur, pregnant 8 months, severe headache, "
                 "swelling in face, ANC checkup due in 2 days",
        "today": "2026-11-02",
        "lang": "kn",
    })
    assert r.status_code == 200
    assert "ನಮಸ್ಕಾರ" in r.text                 # Kannada reminder when chosen
    assert 'lang="kn"' in r.text


def test_ui_escapes_user_html():
    r = client.post("/ui", data={
        "notes": "<script>alert(1)</script>, Rampur, pregnant 4 months, "
                 "ANC due in 5 days",
        "today": "2026-11-02",
    })
    assert r.status_code == 200
    # .title() in the parser capitalises the name, so check
    # case-insensitively: the raw tag must not survive anywhere,
    # and the escaped form must be what is rendered.
    assert "<script" not in r.text.lower()
    assert "&lt;" in r.text
