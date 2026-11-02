from fastapi.testclient import TestClient

from sehatsathi.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["offline_core"] is True


def test_plan_endpoint():
    r = client.post("/plan", json={
        "notes": "Sunita Devi, Rampur, pregnant 8 months, severe headache, "
                 "swelling, ANC checkup due in 2 days",
        "today": "2026-11-02",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["escalations"] == 1
    assert body["followups"][0]["priority"] == "CRITICAL"


def test_demo_endpoint():
    r = client.get("/demo")
    assert r.status_code == 200
    assert r.json()["summary"]["patients_found"] >= 8
