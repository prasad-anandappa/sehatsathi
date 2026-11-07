"""SQLAlchemy persistence for the SehatSathi API service.

Production replacement for the v1.3.0 in-memory demo store. Same
pattern as the StudyMitra (ai-tutor) build: one engine per app
instance, SQLite by default (file DB in production), Postgres via
SEHATSATHI_DATABASE_URL — only portable column types are used.

What is stored:
- workers (health-worker accounts, phone identity, worker/supervisor
  role) and their OTP codes + session tokens (hashes only),
- loop records — one row per tracked person per worker, with the
  patient snapshot, the scored follow-up (incl. reminders) and the
  full state history as JSON, so a DurableScreeningLoop can rehydrate
  exactly,
- visit notes — the day's notes a worker submitted to /plan, with the
  generated plan, so a worker's history survives restarts. Supervisor
  views NEVER read this table's note text (counts only).

The deterministic core stays dependency-free; only this API-shell
module imports SQLAlchemy.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Base(DeclarativeBase):
    pass


class WorkerRow(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), index=True, default="")
    role: Mapped[str] = mapped_column(String(16), default="worker")
    display_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OtpCodeRow(Base):
    """One issued OTP. Only the SHA-256 hash of the code is stored."""

    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SessionTokenRow(Base):
    """A session token (only its SHA-256 hash is stored)."""

    __tablename__ = "session_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoopRecordRow(Base):
    """One tracked person in one worker's screening-to-care loop."""

    __tablename__ = "loop_records"
    __table_args__ = (
        UniqueConstraint("worker_id", "record_key", name="uq_loop_worker_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(160), index=True)
    record_key: Mapped[str] = mapped_column(String(320), index=True)
    patient: Mapped[dict] = mapped_column(JSON, default=dict)
    followup: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(24))
    screened_on: Mapped[str] = mapped_column(String(10))
    referred_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    care_confirmed_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow)


class VisitNoteRow(Base):
    """A day's visit notes a worker ran through /plan, + the plan."""

    __tablename__ = "visit_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(160), index=True)
    notes: Mapped[str] = mapped_column(Text)
    plan_date: Mapped[str] = mapped_column(String(10))
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


def make_engine(database_url: str):
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class Store:
    """All DB access for the API shell (auth + loop persistence)."""

    def __init__(self, session_factory):
        self._factory = session_factory

    # -- workers -------------------------------------------------------
    def upsert_worker(self, worker_id: str, phone: str, role: str) -> dict:
        with self._factory() as s:
            row = s.get(WorkerRow, worker_id)
            if row is None:
                row = WorkerRow(id=worker_id, phone=phone, role=role)
                s.add(row)
            else:
                row.phone = phone or row.phone
                row.role = role
            row.last_login_at = _utcnow()
            s.commit()
            return {"id": row.id, "phone": row.phone, "role": row.role}

    def get_worker(self, worker_id: str) -> dict | None:
        with self._factory() as s:
            row = s.get(WorkerRow, worker_id)
            if row is None:
                return None
            return {"id": row.id, "phone": row.phone, "role": row.role,
                    "display_name": row.display_name}

    def all_workers(self) -> list[dict]:
        with self._factory() as s:
            return [{"id": r.id, "phone": r.phone, "role": r.role}
                    for r in s.query(WorkerRow).all()]

    # -- OTP ------------------------------------------------------------
    def create_otp(self, phone: str, code_hash: str, channel: str,
                   expires_at: datetime) -> None:
        with self._factory() as s:
            s.add(OtpCodeRow(phone=phone, code_hash=code_hash,
                             channel=channel, expires_at=expires_at))
            s.commit()

    def latest_otp(self, phone: str) -> OtpCodeRow | None:
        with self._factory() as s:
            row = (s.query(OtpCodeRow)
                   .filter(OtpCodeRow.phone == phone)
                   .order_by(OtpCodeRow.id.desc())
                   .first())
            if row is not None:
                s.expunge(row)
                row.expires_at = _aware(row.expires_at)
                row.created_at = _aware(row.created_at)
            return row

    def otp_request_count(self, phone: str, since: datetime) -> int:
        with self._factory() as s:
            return (s.query(OtpCodeRow)
                    .filter(OtpCodeRow.phone == phone,
                            OtpCodeRow.created_at >= since.replace(tzinfo=None))
                    .count())

    def record_otp_attempt(self, otp_id: int) -> None:
        with self._factory() as s:
            row = s.get(OtpCodeRow, otp_id)
            if row is not None:
                row.attempts += 1
                s.commit()

    def consume_otp(self, otp_id: int) -> None:
        with self._factory() as s:
            row = s.get(OtpCodeRow, otp_id)
            if row is not None:
                row.consumed_at = _utcnow()
                s.commit()

    # -- session tokens --------------------------------------------------
    def create_session_token(self, worker_id: str, token_hash: str,
                             expires_at: datetime) -> None:
        with self._factory() as s:
            s.add(SessionTokenRow(worker_id=worker_id,
                                  token_hash=token_hash,
                                  expires_at=expires_at))
            s.commit()

    def worker_id_for_token(self, token_hash: str) -> str | None:
        with self._factory() as s:
            row = s.get(SessionTokenRow, token_hash)
            if row is None or row.revoked_at is not None:
                return None
            if _aware(row.expires_at) <= _utcnow():
                return None
            return row.worker_id

    def revoke_session_token(self, token_hash: str) -> None:
        with self._factory() as s:
            row = s.get(SessionTokenRow, token_hash)
            if row is not None:
                row.revoked_at = _utcnow()
                s.commit()

    # -- loop records ------------------------------------------------------
    def load_loop_records(self, worker_id: str) -> list[dict]:
        with self._factory() as s:
            rows = (s.query(LoopRecordRow)
                    .filter(LoopRecordRow.worker_id == worker_id)
                    .all())
            return [{"record_key": r.record_key, "patient": r.patient,
                     "followup": r.followup, "state": r.state,
                     "screened_on": r.screened_on,
                     "referred_on": r.referred_on,
                     "care_confirmed_on": r.care_confirmed_on,
                     "history": r.history} for r in rows]

    def sync_loop_records(self, worker_id: str, records: list[dict]) -> None:
        """Make the worker's stored records exactly match `records`
        (upsert present keys, delete keys no longer tracked)."""
        with self._factory() as s:
            existing = {r.record_key: r for r in
                        s.query(LoopRecordRow)
                        .filter(LoopRecordRow.worker_id == worker_id)
                        .all()}
            wanted = set()
            for rec in records:
                key = rec["record_key"]
                wanted.add(key)
                row = existing.get(key)
                if row is None:
                    s.add(LoopRecordRow(worker_id=worker_id, **rec))
                else:
                    for field_name in ("patient", "followup", "state",
                                       "screened_on", "referred_on",
                                       "care_confirmed_on", "history"):
                        setattr(row, field_name, rec[field_name])
            for key, row in existing.items():
                if key not in wanted:
                    s.delete(row)
            s.commit()

    def loop_worker_ids(self) -> list[str]:
        with self._factory() as s:
            return [r[0] for r in s.query(LoopRecordRow.worker_id)
                    .distinct().all()]

    # -- visit notes -------------------------------------------------------
    def save_visit_note(self, worker_id: str, notes: str, plan_date: str,
                        report: dict) -> None:
        with self._factory() as s:
            s.add(VisitNoteRow(worker_id=worker_id, notes=notes,
                               plan_date=plan_date, report=report))
            s.commit()

    def visit_note_count(self, worker_id: str | None = None) -> int:
        with self._factory() as s:
            q = s.query(VisitNoteRow)
            if worker_id is not None:
                q = q.filter(VisitNoteRow.worker_id == worker_id)
            return q.count()
