"""Authentication for the SehatSathi API service.

Two modes (SEHATSATHI_AUTH_MODE), mirroring the StudyMitra pattern:

- "stub" (dev/tests): identity from headers — X-Worker-Phone (or
  X-Worker-Id), defaulting to a shared "local-worker". Kept for local
  development and the test-suite only.
- "otp" (production): phone-number + one-time-code login. Codes are
  generated server-side, stored SHA-256-hashed with a short expiry
  and an attempt cap, delivered via the OTP sender chain, and
  exchanged for a session token (random, stored hashed, expiring)
  sent as `Authorization: Bearer <token>`.

Roles: "worker" (own cases only) and "supervisor" (read-only
aggregate view across workers). A phone listed in
SEHATSATHI_SUPERVISOR_PHONES gets the supervisor role at login.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from .config import Settings
from .db import Store
from .otp import OtpDeliveryError, OtpSenderChain


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalise_phone(raw: str) -> str:
    """Digits-only international phone, 10-15 digits (E.164 sans '+')."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    if not (10 <= len(digits) <= 15):
        raise HTTPException(
            422, "phone must be 10-15 digits (with country code)")
    return digits


@dataclass
class WorkerContext:
    id: str
    phone: str
    role: str  # worker | supervisor


class AuthService:
    def __init__(self, settings: Settings, store: Store,
                 sender: OtpSenderChain):
        self.settings = settings
        self.store = store
        self.sender = sender

    def role_for_phone(self, phone: str) -> str:
        return ("supervisor" if phone in self.settings.supervisor_phones
                else "worker")

    # -- OTP ------------------------------------------------------------
    def request_otp(self, phone_raw: str, email: str | None = None) -> dict:
        phone = normalise_phone(phone_raw)
        if self.settings.env == "production" and not self.sender.has_real_channel:
            raise HTTPException(
                503, "OTP delivery is not configured on this deployment yet.")
        if (self.settings.env == "production" and not email
                and not self.sender.has_sms_channel):
            # As-user audit 2026-11-06: with email-only delivery, a
            # phone-only request fell through to the sender chain and
            # surfaced as a 502 claiming "no delivery channel is
            # configured" — false, and a dead end for a worker with
            # no email habit. Name the actual missing input instead.
            raise HTTPException(
                422, "Please enter your email address — on this "
                     "deployment the login code is sent by email.")
        since = _now() - timedelta(hours=1)
        if (self.store.otp_request_count(phone, since)
                >= self.settings.otp_requests_per_hour):
            raise HTTPException(
                429, "Too many code requests - try again in an hour.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        try:
            channel = self.sender.send(phone=phone, code=code, email=email)
        except OtpDeliveryError as exc:
            raise HTTPException(
                502, f"Could not deliver the code: {exc}") from exc
        self.store.create_otp(
            phone, _hash(code), channel,
            _now() + timedelta(minutes=self.settings.otp_ttl_minutes))
        result = {
            "phone": phone,
            "channel": channel,
            "expires_in_minutes": self.settings.otp_ttl_minutes,
        }
        if self.settings.env != "production":
            result["dev_hint"] = ("non-production: code also recorded "
                                  "by the log sender")
        return result

    def verify_otp(self, phone_raw: str, code: str) -> dict:
        phone = normalise_phone(phone_raw)
        row = self.store.latest_otp(phone)
        if row is None or row.consumed_at is not None:
            raise HTTPException(
                401, "No active code for this number - request a new one.")
        if row.expires_at <= _now():
            raise HTTPException(
                401, "This code has expired - request a new one.")
        if row.attempts >= self.settings.otp_max_attempts:
            raise HTTPException(
                429, "Too many wrong attempts - request a new code.")
        if not hmac.compare_digest(_hash((code or "").strip()), row.code_hash):
            self.store.record_otp_attempt(row.id)
            raise HTTPException(401, "Incorrect code.")
        self.store.consume_otp(row.id)
        worker_id = f"worker:{phone}"
        role = self.role_for_phone(phone)
        profile = self.store.upsert_worker(worker_id, phone, role)
        token = secrets.token_urlsafe(32)
        self.store.create_session_token(
            worker_id, _hash(token),
            _now() + timedelta(days=self.settings.session_token_days))
        return {
            "token": token,
            "token_type": "bearer",
            "expires_in_days": self.settings.session_token_days,
            "worker": profile,
        }

    # -- session tokens ---------------------------------------------------
    def worker_for_token(self, token: str) -> WorkerContext | None:
        if not token:
            return None
        worker_id = self.store.worker_id_for_token(_hash(token))
        if worker_id is None:
            return None
        profile = self.store.get_worker(worker_id)
        if profile is None:
            return None
        return WorkerContext(id=profile["id"], phone=profile["phone"],
                             role=profile["role"])

    def logout(self, token: str) -> None:
        if token:
            self.store.revoke_session_token(_hash(token))


# -- FastAPI identity dependency -------------------------------------------


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def make_current_worker(settings: Settings, auth: AuthService):
    """The identity dependency used by the worker API.

    stub mode -> header identity (dev/tests).
    otp mode  -> Bearer session token required, headers ignored.
    """

    def dependency(request: Request) -> WorkerContext:
        if settings.auth_mode != "otp":
            phone_raw = request.headers.get("X-Worker-Phone")
            if phone_raw:
                try:
                    phone = normalise_phone(phone_raw)
                except HTTPException:
                    phone = ""
                if phone:
                    return WorkerContext(
                        id=f"worker:{phone}", phone=phone,
                        role=auth.role_for_phone(phone))
            worker_id = request.headers.get("X-Worker-Id") or "local-worker"
            return WorkerContext(id=worker_id, phone="", role="worker")
        worker = auth.worker_for_token(_bearer_token(request))
        if worker is None:
            raise HTTPException(
                401, "Login required - request an OTP code first.")
        return worker

    return dependency
