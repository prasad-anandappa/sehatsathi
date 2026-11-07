"""Production layer (v1.4.0) — durable loop store, OTP auth, roles.

Covers what the hardening changed:
- loop records survive a brand-new app instance over the same DB
  (the unit-level proof of restart survival; the live restart check
  is in AUDIT.md),
- guarded forward-only transitions still hold through the API,
- per-worker isolation,
- phone + OTP login end-to-end (log sender), wrong/expired codes,
  attempt cap, request rate limit,
- supervisor aggregate view (counts + closure, NO note contents),
- visit notes persist per worker,
- public demo surfaces stay open in OTP mode.
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from sehatsathi import api as api_module
from sehatsathi.config import Settings
from sehatsathi.db import Store, make_session_factory
from sehatsathi.loop import LoopState
from sehatsathi.loop_store import DurableScreeningLoop

DAY = "2026-11-06"
CAMP_LIST = """# camp register — synthetic
Sunita Devi, Rampur, pregnant 8 months, high BP, severe headache, ANC checkup due in 2 days, referred to PHC
Rekha Kumari, Rampur, pregnant 5 months, low HB, iron tablets follow-up due in 4 days
Ramesh Kumar, Kishanpur, TB patient, missed 2 doses, DOTS review due tomorrow
Priya, Kishanpur, child 9 months, immunization overdue by 5 days, not referred
"""

WORKER_PHONE = "919876543210"
SUPERVISOR_PHONE = "919123456780"


def _settings(tmp_path, **overrides) -> Settings:
    base = {"database_url": f"sqlite:///{tmp_path}/prod.db",
            "supervisor_phones": frozenset({SUPERVISOR_PHONE})}
    base.update(overrides)
    return Settings(**base)


def _client(tmp_path, **overrides) -> TestClient:
    return TestClient(api_module.create_app(_settings(tmp_path, **overrides)))


def _otp_client(tmp_path, **overrides) -> TestClient:
    return _client(tmp_path, auth_mode="otp", env="dev", **overrides)


def _request_code(client: TestClient, phone: str, email=None) -> str:
    payload = {"phone": phone}
    if email:
        payload["email"] = email
    r = client.post("/auth/request-otp", json=payload)
    assert r.status_code == 200, r.text
    sent = client.app.state.auth.sender.log_sender.sent
    assert sent, "log sender should have recorded the code"
    return sent[-1]["code"]


def _login(client: TestClient, phone: str) -> str:
    code = _request_code(client, phone)
    r = client.post("/auth/verify-otp", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- durable loop store ---------------------------------------------------


def test_durable_loop_survives_new_instance(tmp_path):
    url = f"sqlite:///{tmp_path}/durable.db"
    store = Store(make_session_factory(url))
    loop1 = DurableScreeningLoop(store, "worker:1")
    loop1.intake(CAMP_LIST, date(2026, 11, 6))
    loop1.refer("Rekha Kumari", date(2026, 11, 6))

    # A fresh instance over the same DB = a service restart.
    loop2 = DurableScreeningLoop(store, "worker:1")
    assert loop2.counts()["tracked"] == 4
    rec = next(r for r in loop2.records()
               if r.patient.name == "Rekha Kumari")
    assert rec.state is LoopState.REFERRED
    assert rec.referred_on == date(2026, 11, 6)
    assert len(rec.history) == 2
    # Follow-up content round-trips (reasons + a reminder language).
    assert rec.followup.reasons
    assert rec.followup.reminders.get("en")

    loop2.confirm_care("Rekha Kumari", date(2026, 11, 6))
    loop3 = DurableScreeningLoop(store, "worker:1")
    rec3 = next(r for r in loop3.records()
                if r.patient.name == "Rekha Kumari")
    assert rec3.state is LoopState.CARE_COMPLETED


def test_durable_loop_workers_are_isolated(tmp_path):
    url = f"sqlite:///{tmp_path}/iso.db"
    store = Store(make_session_factory(url))
    DurableScreeningLoop(store, "worker:a").intake(CAMP_LIST,
                                                   date(2026, 11, 6))
    assert DurableScreeningLoop(store, "worker:b").counts()["tracked"] == 0


def test_api_loop_survives_app_restart(tmp_path):
    client1 = _client(tmp_path)
    r = client1.post("/screening/intake",
                     json={"list_text": CAMP_LIST, "today": DAY})
    assert r.status_code == 200
    client1.post("/loop/refer", json={"name": "Rekha Kumari", "today": DAY})

    # New app instance, same DB file — the restart scenario.
    client2 = _client(tmp_path)
    body = client2.get("/loop").json()
    assert body["counts"]["tracked"] == 4
    rec = next(r for r in body["records"] if r["name"] == "Rekha Kumari")
    assert rec["state"] == "referred"


def test_api_guarded_transitions_still_enforced(tmp_path):
    client = _otp_client(tmp_path)
    token = _login(client, WORKER_PHONE)
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": DAY},
                headers=_auth(token))
    r = client.post("/loop/confirm",
                    json={"name": "Rekha Kumari", "today": DAY},
                    headers=_auth(token))
    assert r.status_code == 409          # not referred yet — no skipping
    r = client.post("/loop/refer",
                    json={"name": "Ghost Person", "today": DAY},
                    headers=_auth(token))
    assert r.status_code == 404


# ---- OTP auth ---------------------------------------------------------------


def test_otp_full_flow_and_worker_isolation(tmp_path):
    client = _otp_client(tmp_path)
    # Worker endpoints reject anonymous calls in OTP mode.
    assert client.get("/loop").status_code == 401
    assert client.get("/loop", headers={
        "X-Worker-Phone": WORKER_PHONE}).status_code == 401

    token = _login(client, WORKER_PHONE)
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["worker"]["role"] == "worker"

    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": DAY},
                headers=_auth(token))
    assert client.get("/loop", headers=_auth(token)
                      ).json()["counts"]["tracked"] == 4

    other = _login(client, "919999988887")
    assert client.get("/loop", headers=_auth(other)
                      ).json()["counts"]["tracked"] == 0

    # Logout revokes the token.
    client.post("/auth/logout", headers=_auth(token))
    assert client.get("/loop", headers=_auth(token)).status_code == 401


def test_otp_wrong_code_attempts_capped(tmp_path):
    client = _otp_client(tmp_path, otp_max_attempts=3)
    _request_code(client, WORKER_PHONE)
    for _ in range(3):
        r = client.post("/auth/verify-otp",
                        json={"phone": WORKER_PHONE, "code": "000000"})
        assert r.status_code in (401, 429)
    code = client.app.state.auth.sender.log_sender.sent[-1]["code"]
    r = client.post("/auth/verify-otp",
                    json={"phone": WORKER_PHONE, "code": code})
    assert r.status_code == 429          # capped — even the right code


def test_otp_expired_code_rejected(tmp_path):
    client = _otp_client(tmp_path)
    code = _request_code(client, WORKER_PHONE)
    store = client.app.state.store
    row = store.latest_otp(WORKER_PHONE)
    with store._factory() as s:
        from sehatsathi.db import OtpCodeRow
        db_row = s.get(OtpCodeRow, row.id)
        db_row.expires_at = db_row.expires_at - timedelta(minutes=30)
        s.commit()
    r = client.post("/auth/verify-otp",
                    json={"phone": WORKER_PHONE, "code": code})
    assert r.status_code == 401


def test_otp_request_rate_limit(tmp_path):
    client = _otp_client(tmp_path, otp_requests_per_hour=2)
    _request_code(client, WORKER_PHONE)
    _request_code(client, WORKER_PHONE)
    r = client.post("/auth/request-otp", json={"phone": WORKER_PHONE})
    assert r.status_code == 429


def test_otp_production_without_channel_is_honest_503(tmp_path):
    client = _client(tmp_path, auth_mode="otp", env="production")
    r = client.post("/auth/request-otp", json={"phone": WORKER_PHONE})
    assert r.status_code == 503


# ---- supervisor + visit notes -----------------------------------------------


def test_supervisor_aggregate_without_note_contents(tmp_path):
    client = _otp_client(tmp_path)
    worker = _login(client, WORKER_PHONE)
    secret_note = ("SECRETNOTE Zebra Kumari, Rampur, pregnant 6 months, "
                   "ANC checkup due in 3 days")
    r = client.post("/plan", json={"notes": secret_note, "today": DAY},
                    headers=_auth(worker))
    assert r.status_code == 200
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": DAY},
                headers=_auth(worker))

    # A plain worker is refused the aggregate view.
    assert client.get("/supervisor/summary",
                      headers=_auth(worker)).status_code == 403

    supervisor = _login(client, SUPERVISOR_PHONE)
    r = client.get("/supervisor/summary", headers=_auth(supervisor),
                   params={"today": DAY})
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["tracked"] == 4
    assert body["visit_note_days_stored"] == 1
    # The visit-note TEXT never leaks into the supervisor view.
    assert "SECRETNOTE" not in r.text
    assert "Zebra Kumari" not in r.text
    # ...but the closure summary does name still-open loop cases.
    assert "Rekha Kumari" in r.text


def test_visit_notes_persist_per_worker(tmp_path):
    client = _otp_client(tmp_path)
    token = _login(client, WORKER_PHONE)
    client.post("/plan",
                json={"notes": "Sunita Devi, Rampur, pregnant 8 months, "
                               "ANC checkup due in 2 days", "today": DAY},
                headers=_auth(token))
    store = client.app.state.store
    assert store.visit_note_count(f"worker:{WORKER_PHONE}") == 1
    assert store.visit_note_count("worker:someone-else") == 0


# ---- demo surfaces in OTP mode -----------------------------------------------


def test_demo_surfaces_open_in_otp_mode(tmp_path):
    client = _otp_client(tmp_path)
    assert client.get("/demo").status_code == 200
    r = client.get("/loop/demo")
    assert r.status_code == 200
    assert r.json()["demo_data"] is True
    assert client.get("/health").json()["storage"] == "durable"
