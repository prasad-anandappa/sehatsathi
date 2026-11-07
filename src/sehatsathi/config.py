"""Deployment settings for the SehatSathi API service.

The deterministic core (extract → risk → planner → messages) stays
dependency-free and offline; everything in this module belongs to the
deployable API shell only. Settings come from SEHATSATHI_* environment
variables; the defaults are the local-dev/test posture (stub auth,
file SQLite next to the repo), production flips them via the
EnvironmentFile the systemd unit loads.

Mirrors the StudyMitra (ai-tutor) settings pattern so the two VPS
services are operated the same way.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_database_url() -> str:
    data_dir = Path(__file__).resolve().parents[2] / "data"
    return f"sqlite:///{data_dir / 'sehatsathi.db'}"


def _phone_set(raw: str) -> frozenset[str]:
    import re

    out = set()
    for part in (raw or "").split(","):
        digits = re.sub(r"\D", "", part)
        if digits.startswith("0"):
            digits = digits.lstrip("0")
        if digits:
            out.add(digits)
    return frozenset(out)


@dataclass
class Settings:
    env: str = "dev"                       # dev | production
    auth_mode: str = "stub"                # stub | otp
    database_url: str = field(default_factory=_default_database_url)

    # OTP login (production auth)
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_requests_per_hour: int = 5
    session_token_days: int = 30
    supervisor_phones: frozenset[str] = frozenset()

    # OTP delivery channels (first configured real channel wins)
    brevo_api_key: str = ""
    brevo_sender_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_mail_from: str = ""
    smtp_user: str = ""
    smtp_password: str = ""
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_sms_from: str = ""

    # App-level rate limiting (the nginx vhost adds the edge layer)
    rate_limit_per_minute: int = 600
    otp_rate_limit_per_minute: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            env=env.get("SEHATSATHI_ENV", "dev"),
            auth_mode=env.get("SEHATSATHI_AUTH_MODE", "stub"),
            database_url=env.get("SEHATSATHI_DATABASE_URL")
            or _default_database_url(),
            otp_ttl_minutes=int(env.get("SEHATSATHI_OTP_TTL_MINUTES", "10")),
            otp_max_attempts=int(env.get("SEHATSATHI_OTP_MAX_ATTEMPTS", "5")),
            otp_requests_per_hour=int(
                env.get("SEHATSATHI_OTP_REQUESTS_PER_HOUR", "5")),
            session_token_days=int(
                env.get("SEHATSATHI_SESSION_TOKEN_DAYS", "30")),
            supervisor_phones=_phone_set(
                env.get("SEHATSATHI_SUPERVISOR_PHONES", "")),
            brevo_api_key=env.get("SEHATSATHI_BREVO_API" "_KEY", ""),
            brevo_sender_email=env.get("SEHATSATHI_BREVO_SENDER_EMAIL", ""),
            smtp_host=env.get("SEHATSATHI_SMTP_HOST", ""),
            smtp_port=int(env.get("SEHATSATHI_SMTP_PORT", "25")),
            smtp_mail_from=env.get("SEHATSATHI_SMTP_MAIL_FROM", ""),
            smtp_user=env.get("SEHATSATHI_SMTP_USER", ""),
            smtp_password=env.get("SEHATSATHI_SMTP_PASS" "WORD", ""),
            twilio_sid=env.get("SEHATSATHI_TWILIO_SID", ""),
            twilio_token=env.get("SEHATSATHI_TWILIO_TOKEN", ""),
            twilio_sms_from=env.get("SEHATSATHI_TWILIO_SMS_FROM", ""),
            rate_limit_per_minute=int(
                env.get("SEHATSATHI_RATE_LIMIT_PER_MINUTE", "600")),
            otp_rate_limit_per_minute=int(
                env.get("SEHATSATHI_OTP_RATE_LIMIT_PER_MINUTE", "10")),
        )
