"""Persistence: analyses, rule sets and settings (SQLite by default, PostgreSQL via DATABASE_URL)."""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from . import config
from .engine import default_rule_set

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20), default="test_cases")
    score: Mapped[int] = mapped_column(Integer, default=0)
    rule_set_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    report: Mapped[dict] = mapped_column(JSON)

    def summary(self) -> dict:
        s = self.report.get("summary", {})
        ex = self.report.get("execution") or {}
        return {"id": self.id, "file_name": self.file_name, "score": self.score, "rule_set": self.rule_set_name,
                "created_at": self.created_at.isoformat(), "test_cases": s.get("test_cases"),
                "findings": s.get("findings"), "high_findings": s.get("high_findings"),
                "failed_runs": ex.get("failed")}


class RuleSet(Base):
    __tablename__ = "rule_sets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    def to_dict(self) -> dict:
        return {**self.config, "id": self.id, "name": self.name, "builtin": self.id == "tricentis-default",
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class RequirementCheck(Base):
    __tablename__ = "requirement_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    issue_key: Mapped[str] = mapped_column(String(64))
    analysis_id: Mapped[str] = mapped_column(String(36))
    test_case_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    result: Mapped[dict] = mapped_column(JSON)
    posted: Mapped[str] = mapped_column(Text, default="")


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.get(RuleSet, "tricentis-default") is None:
            rs = default_rule_set()
            db.add(RuleSet(id=rs["id"], name=rs["name"], config=rs))
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def load_settings(db: Session) -> dict:
    merged = copy.deepcopy(config.DEFAULT_SETTINGS)
    row = db.get(Setting, "app")
    if row:
        for k, v in row.value.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update({kk: vv for kk, vv in v.items() if vv not in (None,)})
            else:
                merged[k] = v
    return merged


def save_settings(db: Session, incoming: dict) -> dict:
    row = db.get(Setting, "app")
    current = copy.deepcopy(row.value) if row else {}
    for k, v in incoming.items():
        if isinstance(v, dict):
            section = current.setdefault(k, {})
            for kk, vv in v.items():
                if kk in config.SECRET_KEYS and (vv is None or vv == "" or set(str(vv)) == {"•"}):
                    continue  # blank or masked secret means "keep the stored one"
                section[kk] = vv
        else:
            current[k] = v
    if row:
        row.value = current
    else:
        db.add(Setting(key="app", value=current))
    db.commit()
    return load_settings(db)


def public_settings(settings: dict) -> dict:
    """Settings with secrets masked, safe to send to the browser."""
    out = copy.deepcopy(settings)
    for section in out.values():
        if isinstance(section, dict):
            for k in list(section):
                if k in config.SECRET_KEYS:
                    section[k] = "••••••••" if section[k] else ""
    return out


def list_rule_sets(db: Session) -> list[dict]:
    return [r.to_dict() for r in db.scalars(select(RuleSet).order_by(RuleSet.name))]
