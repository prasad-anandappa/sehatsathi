"""As-user audit 2026-11-06 — regression tests for the fixes.

Each test maps to a finding from auditing the live deployment as
its users (ASHA worker on a phone browser, supervisor, judge):

- provisional languages are marked in the picker + on the page,
- a phone-only OTP request on an email-delivery deployment gets a
  clear 422 naming the missing input (was: a false 502),
- API 404 details no longer carry KeyError repr quotes,
- a worker can remove ONE wrong record (was: reset-or-nothing),
- the public demo loop is scoped per browser (was: one list shared
  by every visitor on Earth),
- browser form errors render as HTML pages, not raw JSON,
- /demo labels its synthetic data in the payload,
- the worker web sign-in works end to end (forms + cookie session),
- the loop page leads with the chosen language's reminder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from sehatsathi import api as api_module
from sehatsathi.config import Settings

DAY = "2026-11-06"
CAMP_LIST = ("Sunita Devi, Rampur, pregnant 8 months, severe headache, "
             "ANC checkup due in 2 days\n"
             "Rekha Kumari, Rampur, pregnant 5 months, iron tablets "
             "follow-up due in 4 days")
WORKER_PHONE = "919876543210"


def _settings(tmp_path, **overrides) -> Settings:
    base = {"database_url": "sqlite:" + "///" + str(tmp_path / "t.db")}
    base.update(overrides)
    return Settings(**base)


def _otp_client(tmp_path, **overrides) -> TestClient:
    app = api_module.create_app(
        _settings(tmp_path, auth_mode="otp", env="dev", **overrides))
    return TestClient(app, base_url="https://testserver")


def _login_via_api(client: TestClient, phone: str = WORKER_PHONE) -> str:
    r = client.post("/auth/request-otp", json={"phone": phone})
    assert r.status_code == 200, r.text
    code = client.app.state.auth.sender.log_sender.sent[-1]["code"]
    r = client.post("/auth/verify-otp", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- provisional honesty label reaches the user -------------------------


def test_provisional_language_marked_in_picker(tmp_path):
    client = _otp_client(tmp_path)
    r = client.get("/?lang=or")          # Odia — provisional
    assert r.status_code == 200
    assert "provisional" in r.text       # picker suffix + page notice
    r = client.get("/?lang=hi")          # Hindi — verified
    assert "translation is <b>provisional</b>" not in r.text


def test_non_english_index_drops_english_prose(tmp_path):
    client = _otp_client(tmp_path)
    r = client.get("/?lang=hi")
    assert "Paste today" not in r.text
    r = client.get("/")
    assert "Paste today" in r.text


# ---- OTP: missing email names the real problem ---------------------------


def test_otp_phone_only_on_email_deployment_is_clear_422(tmp_path):
    client = TestClient(api_module.create_app(_settings(
        tmp_path, auth_mode="otp", env="production",
        smtp_host="127.0.0.1", smtp_mail_from="ss@example.in")))
    r = client.post("/auth/request-otp", json={"phone": WORKER_PHONE})
    assert r.status_code == 422
    assert "email" in r.json()["detail"]


# ---- KeyError quotes ------------------------------------------------------


def test_api_404_detail_has_no_repr_quotes(tmp_path):
    client = _otp_client(tmp_path)
    token = _login_via_api(client)
    r = client.post("/loop/refer", json={"name": "Ghost Person"},
                    headers=_auth(token))
    assert r.status_code == 404
    assert r.json()["detail"].startswith("no tracked person named")


# ---- single-record removal -------------------------------------------------


def test_worker_can_remove_one_record(tmp_path):
    client = _otp_client(tmp_path)
    token = _login_via_api(client)
    client.post("/screening/intake",
                json={"list_text": CAMP_LIST, "today": DAY},
                headers=_auth(token))
    r = client.post("/loop/remove", json={"name": "Rekha Kumari"},
                    headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["removed"] == "Rekha Kumari"
    body = client.get("/loop", headers=_auth(token)).json()
    assert body["counts"]["tracked"] == 1
    assert body["records"][0]["name"] == "Sunita Devi"
    r = client.post("/loop/remove", json={"name": "Rekha Kumari"},
                    headers=_auth(token))
    assert r.status_code == 404


# ---- demo loop is per-browser -----------------------------------------------


ISO_LIST = ("Isomarker Devi, Rampur, pregnant 5 months, iron tablets "
            "follow-up due in 4 days")


def test_demo_loop_not_shared_between_browsers(tmp_path):
    app = api_module.create_app(_settings(tmp_path))
    alice = TestClient(app, base_url="https://testserver")
    bob = TestClient(app, base_url="https://testserver")
    r = alice.post("/loop/ui/intake",
                   data={"list": ISO_LIST, "today": DAY})
    assert "Isomarker Devi" in r.text
    r = bob.get("/loop/ui")
    assert "Isomarker Devi" not in r.text       # Bob sees his own demo
    r = alice.get("/loop/ui")
    assert "Isomarker Devi" in r.text           # Alice keeps hers


# ---- form errors are HTML ----------------------------------------------------


def test_form_errors_render_html_not_json(tmp_path):
    client = _otp_client(tmp_path)
    r = client.post("/ui", data={"notes": "Kamla Bai, 62 years",
                                 "today": "next friday"})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "today must be a date" in r.text
    r = client.post("/loop/ui/intake",
                    data={"list": CAMP_LIST, "today": "banana"})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "today must be a date" in r.text


# ---- /demo labels itself -------------------------------------------------------


def test_demo_payload_labelled(tmp_path):
    client = _otp_client(tmp_path)
    body = client.get("/demo").json()
    assert body["demo_data"] is True
    assert "Synthetic" in body["note"]


# ---- worker web sign-in, end to end --------------------------------------------


def test_worker_web_signin_journey(tmp_path):
    client = _otp_client(tmp_path)
    # Signed-out /worker redirects to the sign-in form.
    r = client.get("/worker", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    # Request a code (dev env: log sender records it).
    r = client.post("/login/request", data={"phone": WORKER_PHONE,
                                            "email": "asha@example.in"})
    assert r.status_code == 200 and "Enter your login code" in r.text
    code = client.app.state.auth.sender.log_sender.sent[-1]["code"]
    # Wrong code re-renders the form with a message, no session.
    r = client.post("/login/verify", data={"phone": WORKER_PHONE,
                                           "code": "000000"})
    assert "Incorrect code" in r.text
    r = client.get("/worker", follow_redirects=False)
    assert r.status_code == 303
    # Right code signs in and lands on the worker's own loop page.
    r = client.post("/login/verify", data={"phone": WORKER_PHONE,
                                           "code": code},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/worker"
    r = client.get("/worker")
    assert r.status_code == 200
    assert "Signed in as" in r.text
    # Intake + advance + plan, all through the no-JS forms.
    r = client.post("/worker/intake", data={"list": CAMP_LIST,
                                            "today": DAY})
    assert "Intake done: 2 added" in r.text
    r = client.post("/worker/advance", data={"name": "Sunita Devi",
                                             "action": "refer",
                                             "today": DAY})
    assert "marked referred" in r.text
    r = client.post("/worker/plan",
                    data={"notes": "Kamla Bai, Rampur, 62 years, BP "
                                   "medicine refill due in 5 days",
                          "today": DAY})
    assert r.status_code == 200 and "Kamla Bai" in r.text
    store = client.app.state.store
    assert store.visit_note_count(f"worker:{WORKER_PHONE}") == 1
    # Remove one record from the page.
    r = client.post("/worker/remove", data={"name": "Rekha Kumari"})
    assert "record removed" in r.text
    # Sign out: the session is revoked server-side, not just cleared.
    client.post("/worker/logout")
    r = client.get("/worker", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_worker_page_language_and_isolation(tmp_path):
    app = api_module.create_app(
        _settings(tmp_path, auth_mode="otp", env="dev"))
    a = TestClient(app, base_url="https://testserver")
    b = TestClient(app, base_url="https://testserver")
    for client, phone in ((a, WORKER_PHONE), (b, "919123456780")):
        client.post("/login/request", data={"phone": phone})
        code = client.app.state.auth.sender.log_sender.sent[-1]["code"]
        client.post("/login/verify", data={"phone": phone, "code": code})
    a.post("/worker/intake", data={"list": ISO_LIST, "today": DAY})
    r = b.get("/worker")
    assert "Isomarker Devi" not in r.text       # B never sees A's cases
    r = a.get("/worker", params={"lang": "hi"})
    assert "नमस्ते Isomarker Devi जी" in r.text  # Hindi reminder leads
