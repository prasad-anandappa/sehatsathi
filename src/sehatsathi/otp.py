"""OTP delivery channels (StudyMitra pattern, adapted for workers).

A chain, in preference order — the first *configured* channel wins:

1. Brevo email API   (SEHATSATHI_BREVO_API_KEY + sender email).
2. Local SMTP relay  (SEHATSATHI_SMTP_HOST) — e.g. the VPS's own Exim
   on 127.0.0.1:25, which relays out via the house smarthost.
3. Twilio SMS        (SEHATSATHI_TWILIO_* + SEHATSATHI_TWILIO_SMS_FROM).
4. Log sender        — dev/tests only; records instead of sending.

Email channels need the worker's email address; SMS needs none. When
NOTHING real is configured, send() raises so the API can answer
honestly instead of pretending a code was delivered.
"""
from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from email.message import EmailMessage

from .config import Settings

log = logging.getLogger("sehatsathi.otp")


class OtpDeliveryError(RuntimeError):
    pass


class BrevoEmailSender:
    name = "email"

    def __init__(self, api_key: str, sender_email: str):
        self.api_key = api_key
        self.sender_email = sender_email

    def send(self, *, phone: str, code: str, email: str | None) -> str:
        if not email:
            raise OtpDeliveryError("email address required for Brevo delivery")
        payload = {
            "sender": {"email": self.sender_email, "name": "SehatSathi"},
            "to": [{"email": email}],
            "subject": "Your SehatSathi login code",
            "textContent": (
                f"Your SehatSathi one-time login code is {code}. "
                "It expires in 10 minutes. Do not share it with anyone."
            ),
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode(),
            headers={
                "api-key": self.api_key,
                "content-type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            if resp.status >= 300:
                raise OtpDeliveryError(f"Brevo returned {resp.status}")
        return self.name


class SmtpEmailSender:
    name = "email"

    def __init__(self, host: str, port: int, mail_from: str,
                 user: str = "", password: str = ""):
        self.host = host
        self.port = port
        self.mail_from = mail_from
        self.user = user
        self._auth_secret = password

    def send(self, *, phone: str, code: str, email: str | None) -> str:
        if not email:
            raise OtpDeliveryError("email address required for SMTP delivery")
        msg = EmailMessage()
        msg["From"] = self.mail_from
        msg["To"] = email
        msg["Subject"] = "Your SehatSathi login code"
        msg.set_content(
            f"Your SehatSathi one-time login code is {code}.\n"
            "It expires in 10 minutes. Do not share it with anyone.\n"
        )
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.user and self._auth_secret:
                smtp.login(self.user, self._auth_secret)
            smtp.send_message(msg)
        return self.name


class TwilioSmsSender:
    name = "sms"

    def __init__(self, sid: str, token: str, from_number: str):
        import base64

        self.url = (f"https://api.twilio.com/2010-04-01/Accounts/"
                    f"{sid}/Messages.json")
        self.from_number = from_number
        creds = base64.b64encode(f"{sid}:{token}".encode()).decode()
        self.auth_header = f"Basic {creds}"

    def send(self, *, phone: str, code: str, email: str | None) -> str:
        from urllib.parse import urlencode

        body = urlencode({
            "From": self.from_number,
            "To": f"+{phone}",
            "Body": (f"Your SehatSathi login code is {code}. "
                     "It expires in 10 minutes. Do not share it."),
        }).encode()
        req = urllib.request.Request(
            self.url, data=body,
            headers={"Authorization": self.auth_header,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            if resp.status >= 300:
                raise OtpDeliveryError(f"Twilio returned {resp.status}")
        return self.name


class LogSender:
    """Dev/tests: records the code instead of delivering it."""

    name = "log"

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, *, phone: str, code: str, email: str | None) -> str:
        self.sent.append({"phone": phone, "code": code, "email": email})
        log.info("OTP for %s recorded by log sender (dev only)", phone)
        return self.name


class OtpSenderChain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.log_sender = LogSender()
        self._email_senders = []
        if settings.brevo_api_key and settings.brevo_sender_email:
            self._email_senders.append(BrevoEmailSender(
                settings.brevo_api_key, settings.brevo_sender_email))
        if settings.smtp_host:
            self._email_senders.append(SmtpEmailSender(
                settings.smtp_host, settings.smtp_port,
                settings.smtp_mail_from or "sehatsathi@localhost",
                settings.smtp_user, settings.smtp_password))
        self._sms_sender = None
        if (settings.twilio_sid and settings.twilio_token
                and settings.twilio_sms_from):
            self._sms_sender = TwilioSmsSender(
                settings.twilio_sid, settings.twilio_token,
                settings.twilio_sms_from)

    @property
    def has_real_channel(self) -> bool:
        return bool(self._email_senders or self._sms_sender)

    @property
    def has_sms_channel(self) -> bool:
        return self._sms_sender is not None

    @property
    def has_email_channel(self) -> bool:
        return bool(self._email_senders)

    def send(self, *, phone: str, code: str, email: str | None) -> str:
        if email and self._email_senders:
            return self._email_senders[0].send(phone=phone, code=code,
                                               email=email)
        if self._sms_sender is not None:
            return self._sms_sender.send(phone=phone, code=code, email=email)
        if email and not self._email_senders and self.settings.env == "production":
            raise OtpDeliveryError(
                "no email delivery channel is configured on this deployment")
        if self.settings.env == "production":
            raise OtpDeliveryError(
                "no OTP delivery channel is configured on this deployment")
        return self.log_sender.send(phone=phone, code=code, email=email)
